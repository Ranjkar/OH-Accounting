"""Deterministic financial reporting engine. Every figure here is a plain
Decimal sum over already-posted ledger data (AccountingTransaction, Payment,
BankTransaction, VatReturn, ManualBalanceSheetItem) -- no AI, no invented
entries. Reuses app.accounting.payment_engine for remaining-balance math
and app.accounting.categorization's category buckets for P&L classification
instead of introducing a second chart of accounts.

Fixed assets, inventory, equity, and loans cannot be derived from this
ledger (there is no chart of accounts) -- they come only from
ManualBalanceSheetItem rows an accountant explicitly entered. When none
exist, the balance sheet says so and does not force a balance.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum

from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session

from app.accounting import payment_engine
from app.accounting.categorization import (
    COST_OF_SALES_CATEGORIES,
    DEPRECIATION_CATEGORIES,
    INTEREST_CATEGORIES,
    PERSONNEL_CATEGORIES,
)
from app.models.accounting import AccountingTransaction, VatReturn
from app.models.balance_sheet import ManualBalanceSheetItem
from app.models.banking import BankTransaction
from app.models.enums import BalanceSheetItemCategory, LedgerSide, VatPeriodStatus
from app.models.financial_year import VatPeriod

ZERO = Decimal("0")
BALANCE_TOLERANCE = Decimal("0.01")


class ReportPeriod(str, Enum):
    monthly = "MONTHLY"
    quarterly = "QUARTERLY"
    annual = "ANNUAL"
    custom = "CUSTOM"


@dataclass(frozen=True)
class DateRange:
    start: date
    end: date


def resolve_period(period_type: ReportPeriod, reference_date: date, custom_start: date | None = None, custom_end: date | None = None) -> DateRange:
    """Monthly/quarterly/annual periods are the calendar period containing
    reference_date; CUSTOM requires explicit start/end."""
    if period_type == ReportPeriod.custom:
        if custom_start is None or custom_end is None:
            raise ValueError("CUSTOM period requires both custom_start and custom_end")
        return DateRange(custom_start, custom_end)
    if period_type == ReportPeriod.monthly:
        start = reference_date.replace(day=1)
        end = start + relativedelta(months=1) - relativedelta(days=1)
    elif period_type == ReportPeriod.quarterly:
        quarter_start_month = ((reference_date.month - 1) // 3) * 3 + 1
        start = reference_date.replace(month=quarter_start_month, day=1)
        end = start + relativedelta(months=3) - relativedelta(days=1)
    else:  # annual
        start = reference_date.replace(month=1, day=1)
        end = reference_date.replace(month=12, day=31)
    return DateRange(start, end)


def previous_period(period: DateRange) -> DateRange:
    """Same-length period immediately before this one, for period-over-period comparison."""
    length = (period.end - period.start).days
    return DateRange(period.start - relativedelta(days=length + 1), period.start - relativedelta(days=1))


def year_on_year_period(period: DateRange) -> DateRange:
    return DateRange(period.start - relativedelta(years=1), period.end - relativedelta(years=1))


def transactions_in_period(db: Session, company_id: int, period: DateRange, ledger_side: LedgerSide | None = None) -> list[AccountingTransaction]:
    query = db.query(AccountingTransaction).filter(
        AccountingTransaction.company_id == company_id,
        AccountingTransaction.invoice_date >= period.start,
        AccountingTransaction.invoice_date <= period.end,
    )
    if ledger_side is not None:
        query = query.filter(AccountingTransaction.ledger_side == ledger_side)
    return query.all()


def _category_total(transactions: list[AccountingTransaction], categories: set[str]) -> Decimal:
    return sum((t.net_amount for t in transactions if t.expense_category in categories), ZERO)


def profit_and_loss(db: Session, company_id: int, period: DateRange) -> dict:
    sales = transactions_in_period(db, company_id, period, LedgerSide.sales)
    purchases = transactions_in_period(db, company_id, period, LedgerSide.purchases)

    revenue = sum((t.net_amount for t in sales), ZERO)
    cost_of_sales = _category_total(purchases, COST_OF_SALES_CATEGORIES)
    personnel_expenses = _category_total(purchases, PERSONNEL_CATEGORIES)
    depreciation = _category_total(purchases, DEPRECIATION_CATEGORIES)
    interest_expense = _category_total(purchases, INTEREST_CATEGORIES)
    classified_other = COST_OF_SALES_CATEGORIES | PERSONNEL_CATEGORIES | DEPRECIATION_CATEGORIES | INTEREST_CATEGORIES
    operating_expenses = sum(
        (t.net_amount for t in purchases if t.expense_category not in classified_other and t.expense_category is not None), ZERO
    )
    uncategorized_expenses = sum((t.net_amount for t in purchases if t.expense_category is None), ZERO)

    gross_profit = revenue - cost_of_sales
    ebitda = gross_profit - operating_expenses - personnel_expenses - uncategorized_expenses
    ebit = ebitda - depreciation
    profit_before_tax = ebit - interest_expense
    tax_expense = ZERO  # this system computes Dutch VAT, not corporate income tax -- never fabricated
    net_profit = profit_before_tax - tax_expense

    return {
        "period_start": period.start,
        "period_end": period.end,
        "revenue": revenue,
        "cost_of_sales": cost_of_sales,
        "gross_profit": gross_profit,
        "operating_expenses": operating_expenses,
        "uncategorized_expenses": uncategorized_expenses,
        "personnel_expenses": personnel_expenses,
        "depreciation": depreciation,
        "ebitda": ebitda,
        "ebit": ebit,
        "interest_expense": interest_expense,
        "profit_before_tax": profit_before_tax,
        "tax_expense": tax_expense,
        "tax_expense_note": "Corporate income tax is not tracked by this system (Dutch VAT only) -- always 0, never estimated.",
        "net_profit": net_profit,
        "sales_transaction_count": len(sales),
        "purchase_transaction_count": len(purchases),
    }


def compare_periods(current: dict, previous: dict) -> dict:
    """Absolute and percentage change for every numeric P&L line. A None
    percentage means the previous period was zero (division is undefined,
    never silently shown as 0% or infinite)."""
    changes = {}
    for key in ("revenue", "cost_of_sales", "gross_profit", "operating_expenses", "personnel_expenses",
                "depreciation", "ebitda", "ebit", "interest_expense", "profit_before_tax", "net_profit"):
        cur, prev = current[key], previous[key]
        delta = cur - prev
        pct = None if prev == 0 else (delta / abs(prev) * 100).quantize(Decimal("0.1"))
        changes[key] = {"current": cur, "previous": prev, "change": delta, "change_pct": pct}
    return changes


def revenue_breakdown(db: Session, company_id: int, period: DateRange) -> list[dict]:
    sales = transactions_in_period(db, company_id, period, LedgerSide.sales)
    totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for t in sales:
        totals[t.counterparty_name or "Unknown counterparty"] += t.net_amount
    total = sum(totals.values(), ZERO)
    return sorted(
        [
            {"counterparty_name": name, "net_amount": amount, "pct_of_total": (amount / total * 100).quantize(Decimal("0.1")) if total else None}
            for name, amount in totals.items()
        ],
        key=lambda r: r["net_amount"],
        reverse=True,
    )


def expense_breakdown(db: Session, company_id: int, period: DateRange) -> list[dict]:
    purchases = transactions_in_period(db, company_id, period, LedgerSide.purchases)
    totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for t in purchases:
        totals[t.expense_category or "Uncategorized"] += t.net_amount
    total = sum(totals.values(), ZERO)
    return sorted(
        [
            {"category": cat, "net_amount": amount, "pct_of_total": (amount / total * 100).quantize(Decimal("0.1")) if total else None}
            for cat, amount in totals.items()
        ],
        key=lambda r: r["net_amount"],
        reverse=True,
    )


def _remaining_balance_as_of(transaction: AccountingTransaction, as_of_date: date) -> Decimal:
    payments_counted = [p for p in transaction.payments if not p.voided and p.payment_date <= as_of_date]
    return transaction.gross_amount - payment_engine.total_paid(payments_counted)


def debtors(db: Session, company_id: int, as_of_date: date) -> dict:
    return _ar_ap(db, company_id, as_of_date, LedgerSide.sales)


def creditors(db: Session, company_id: int, as_of_date: date) -> dict:
    return _ar_ap(db, company_id, as_of_date, LedgerSide.purchases)


_AGING_BUCKETS = [(0, "current"), (1, "1-30"), (31, "31-60"), (61, "61-90"), (91, "90+")]


def _aging_bucket(days_overdue: int) -> str:
    bucket = "current"
    for threshold, label in _AGING_BUCKETS:
        if days_overdue >= threshold:
            bucket = label
    return bucket


def _ar_ap(db: Session, company_id: int, as_of_date: date, ledger_side: LedgerSide) -> dict:
    transactions = (
        db.query(AccountingTransaction)
        .filter(
            AccountingTransaction.company_id == company_id,
            AccountingTransaction.ledger_side == ledger_side,
            AccountingTransaction.invoice_date <= as_of_date,
        )
        .all()
    )
    rows = []
    aging_totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    total_outstanding = ZERO
    for t in transactions:
        remaining = _remaining_balance_as_of(t, as_of_date)
        if remaining <= 0:
            continue
        days_overdue = (as_of_date - t.due_date).days if t.due_date and t.due_date < as_of_date else 0
        bucket = _aging_bucket(days_overdue)
        aging_totals[bucket] += remaining
        total_outstanding += remaining
        rows.append(
            {
                "transaction_id": t.id,
                "counterparty_name": t.counterparty_name,
                "invoice_number": t.invoice_number,
                "invoice_date": t.invoice_date,
                "due_date": t.due_date,
                "remaining_balance": remaining,
                "days_overdue": days_overdue,
                "aging_bucket": bucket,
            }
        )
    return {
        "as_of_date": as_of_date,
        "total_outstanding": total_outstanding,
        "aging_summary": {label: aging_totals.get(label, ZERO) for _, label in _AGING_BUCKETS},
        "items": sorted(rows, key=lambda r: r["days_overdue"], reverse=True),
    }


def _manual_items_total(db: Session, company_id: int, category: BalanceSheetItemCategory, as_of_date: date) -> Decimal:
    items = (
        db.query(ManualBalanceSheetItem)
        .filter(
            ManualBalanceSheetItem.company_id == company_id,
            ManualBalanceSheetItem.category == category,
            ManualBalanceSheetItem.as_of_date <= as_of_date,
        )
        .all()
    )
    return sum((i.amount for i in items), ZERO)


def _cash_balance(db: Session, company_id: int, as_of_date: date) -> Decimal:
    transactions = (
        db.query(BankTransaction)
        .filter(BankTransaction.company_id == company_id, BankTransaction.booking_date <= as_of_date)
        .all()
    )
    return sum((t.amount for t in transactions), ZERO)


def _outstanding_vat_position(db: Session, company_id: int, as_of_date: date) -> Decimal:
    """Positive = net VAT payable (liability); negative = net VAT receivable (asset).
    Only returns not yet marked paid on their VAT period, so once paid it drops out."""
    returns = (
        db.query(VatReturn)
        .join(VatPeriod, VatReturn.vat_period_id == VatPeriod.id)
        .filter(
            VatReturn.company_id == company_id,
            VatPeriod.end_date <= as_of_date,
            VatPeriod.status != VatPeriodStatus.paid,
        )
        .all()
    )
    return sum((r.net_payable for r in returns), ZERO)


def retained_earnings(db: Session, company_id: int, as_of_date: date, earliest_date: date) -> Decimal:
    """Cumulative net profit from the start of this company's records through
    as_of_date -- the genuine link between the P&L and the balance sheet's
    equity section, never a plug figure."""
    pnl = profit_and_loss(db, company_id, DateRange(earliest_date, as_of_date))
    return pnl["net_profit"]


def _earliest_transaction_date(db: Session, company_id: int, as_of_date: date) -> date:
    earliest = (
        db.query(AccountingTransaction.invoice_date)
        .filter(AccountingTransaction.company_id == company_id, AccountingTransaction.invoice_date <= as_of_date)
        .order_by(AccountingTransaction.invoice_date.asc())
        .first()
    )
    return earliest[0] if earliest else as_of_date


def balance_sheet(db: Session, company_id: int, as_of_date: date) -> dict:
    cash = _cash_balance(db, company_id, as_of_date)
    ar = debtors(db, company_id, as_of_date)["total_outstanding"]
    ap = creditors(db, company_id, as_of_date)["total_outstanding"]
    fixed_assets = _manual_items_total(db, company_id, BalanceSheetItemCategory.fixed_assets, as_of_date)
    inventory = _manual_items_total(db, company_id, BalanceSheetItemCategory.inventory, as_of_date)
    other_assets = _manual_items_total(db, company_id, BalanceSheetItemCategory.other_asset, as_of_date)
    equity_manual = _manual_items_total(db, company_id, BalanceSheetItemCategory.equity, as_of_date)
    loans = _manual_items_total(db, company_id, BalanceSheetItemCategory.loans, as_of_date)
    other_liabilities = _manual_items_total(db, company_id, BalanceSheetItemCategory.other_liability, as_of_date)

    vat_position = _outstanding_vat_position(db, company_id, as_of_date)
    vat_receivable = -vat_position if vat_position < 0 else ZERO
    vat_payable = vat_position if vat_position > 0 else ZERO

    earliest = _earliest_transaction_date(db, company_id, as_of_date)
    earnings = retained_earnings(db, company_id, as_of_date, earliest)

    total_assets = cash + ar + inventory + fixed_assets + other_assets + vat_receivable
    total_liabilities = ap + loans + other_liabilities + vat_payable
    total_equity = equity_manual + earnings

    imbalance = total_assets - (total_liabilities + total_equity)
    no_manual_items_entered = fixed_assets == inventory == other_assets == equity_manual == loans == other_liabilities == ZERO

    return {
        "as_of_date": as_of_date,
        "assets": {
            "cash_and_bank": cash,
            "accounts_receivable": ar,
            "inventory": inventory,
            "fixed_assets": fixed_assets,
            "other_assets": other_assets,
            "vat_receivable": vat_receivable,
            "total": total_assets,
        },
        "liabilities": {
            "accounts_payable": ap,
            "loans": loans,
            "other_liabilities": other_liabilities,
            "vat_payable": vat_payable,
            "total": total_liabilities,
        },
        "equity": {
            "contributed_and_other_equity": equity_manual,
            "retained_earnings": earnings,
            "total": total_equity,
        },
        "is_balanced": abs(imbalance) <= BALANCE_TOLERANCE,
        "imbalance_amount": imbalance,
        "missing_opening_balance_warning": (
            "No fixed assets, inventory, equity, or loan balances have been manually entered for this company. "
            "This ledger has no chart of accounts, so these can never be derived automatically -- the balance "
            "sheet below reflects only cash, receivables, payables, and VAT position until they are recorded."
            if no_manual_items_entered
            else None
        ),
    }


def cash_flow_statement(db: Session, company_id: int, period: DateRange) -> dict:
    bank_transactions = (
        db.query(BankTransaction)
        .filter(
            BankTransaction.company_id == company_id,
            BankTransaction.booking_date >= period.start,
            BankTransaction.booking_date <= period.end,
        )
        .all()
    )
    receipts = sum((t.amount for t in bank_transactions if t.amount > 0), ZERO)
    payments_out = sum((t.amount for t in bank_transactions if t.amount < 0), ZERO)
    net_operating_cash = receipts + payments_out

    investing = _manual_items_total(db, company_id, BalanceSheetItemCategory.fixed_assets, period.end) - \
        _manual_items_total(db, company_id, BalanceSheetItemCategory.fixed_assets, period.start - relativedelta(days=1))
    other_assets_delta = _manual_items_total(db, company_id, BalanceSheetItemCategory.other_asset, period.end) - \
        _manual_items_total(db, company_id, BalanceSheetItemCategory.other_asset, period.start - relativedelta(days=1))
    investing_total = -(investing + other_assets_delta)  # buying an asset is a cash outflow

    loans_delta = _manual_items_total(db, company_id, BalanceSheetItemCategory.loans, period.end) - \
        _manual_items_total(db, company_id, BalanceSheetItemCategory.loans, period.start - relativedelta(days=1))
    equity_delta = _manual_items_total(db, company_id, BalanceSheetItemCategory.equity, period.end) - \
        _manual_items_total(db, company_id, BalanceSheetItemCategory.equity, period.start - relativedelta(days=1))
    financing_total = loans_delta + equity_delta

    net_change_in_cash = net_operating_cash + investing_total + financing_total

    pnl = profit_and_loss(db, company_id, period)
    ar_start = debtors(db, company_id, period.start - relativedelta(days=1))["total_outstanding"]
    ar_end = debtors(db, company_id, period.end)["total_outstanding"]
    ap_start = creditors(db, company_id, period.start - relativedelta(days=1))["total_outstanding"]
    ap_end = creditors(db, company_id, period.end)["total_outstanding"]

    return {
        "period_start": period.start,
        "period_end": period.end,
        "operating_activities": {
            "receipts": receipts,
            "payments": payments_out,
            "net": net_operating_cash,
        },
        "investing_activities": {
            "net": investing_total,
            "note": "Derived only from manually-recorded fixed-asset/other-asset entries dated within this period -- "
            "may double-count against operating cash if those purchases also moved through the bank account shown above.",
        },
        "financing_activities": {
            "net": financing_total,
            "note": "Derived only from manually-recorded loan/equity entries dated within this period, same caveat as investing activities.",
        },
        "net_change_in_cash": net_change_in_cash,
        "accrual_vs_cash_reconciliation": {
            "net_profit_accrual": pnl["net_profit"],
            "depreciation_addback": pnl["depreciation"],
            "increase_in_accounts_receivable": ar_end - ar_start,
            "increase_in_accounts_payable": ap_end - ap_start,
            "approx_operating_cash_from_accrual": (
                pnl["net_profit"] + pnl["depreciation"] - (ar_end - ar_start) + (ap_end - ap_start)
            ),
            "actual_operating_cash": net_operating_cash,
            "note": "The approximation and the actual bank-derived figure will not match exactly -- this ledger is "
            "not a full double-entry system, so timing differences beyond AR/AP and depreciation are not individually "
            "tracked. The gap itself is informative: a large, unexplained gap is worth investigating.",
        },
    }


def trial_balance(db: Session, company_id: int, period: DateRange) -> dict:
    """Best-effort trial balance derived from this single-entry invoice
    ledger, not a formal double-entry trial balance. Labeled as such;
    imbalance is reported, never forced to zero."""
    pnl = profit_and_loss(db, company_id, period)
    bs = balance_sheet(db, company_id, period.end)
    # Revenue/expense lines above cover only this period's activity, so the
    # equity side must use the RETAINED EARNINGS BALANCE BEFORE this period
    # (prior periods' closed earnings) -- using bs["equity"]["total"] here
    # would double-count this period's own net profit (once directly via the
    # revenue/expense lines, once again inside retained earnings).
    opening_date = period.start - relativedelta(days=1)
    earliest = _earliest_transaction_date(db, company_id, opening_date)
    opening_retained_earnings = retained_earnings(db, company_id, opening_date, earliest)
    opening_equity_manual = _manual_items_total(db, company_id, BalanceSheetItemCategory.equity, opening_date)

    debits = {
        "Cost of sales": pnl["cost_of_sales"],
        "Operating expenses": pnl["operating_expenses"],
        "Uncategorized expenses": pnl["uncategorized_expenses"],
        "Personnel expenses": pnl["personnel_expenses"],
        "Depreciation": pnl["depreciation"],
        "Interest expense": pnl["interest_expense"],
        "Cash and bank": bs["assets"]["cash_and_bank"] if bs["assets"]["cash_and_bank"] > 0 else ZERO,
        "Accounts receivable": bs["assets"]["accounts_receivable"],
        "Inventory": bs["assets"]["inventory"],
        "Fixed assets": bs["assets"]["fixed_assets"],
        "Other assets": bs["assets"]["other_assets"],
        "VAT receivable": bs["assets"]["vat_receivable"],
    }
    credits = {
        "Revenue": pnl["revenue"],
        "Cash and bank (overdrawn)": -bs["assets"]["cash_and_bank"] if bs["assets"]["cash_and_bank"] < 0 else ZERO,
        "Accounts payable": bs["liabilities"]["accounts_payable"],
        "Loans": bs["liabilities"]["loans"],
        "Other liabilities": bs["liabilities"]["other_liabilities"],
        "VAT payable": bs["liabilities"]["vat_payable"],
        "Opening retained earnings": opening_retained_earnings,
        "Contributed and other equity": opening_equity_manual,
    }
    total_debits = sum(debits.values(), ZERO)
    total_credits = sum(credits.values(), ZERO)
    return {
        "period_start": period.start,
        "period_end": period.end,
        "debits": debits,
        "credits": credits,
        "total_debits": total_debits,
        "total_credits": total_credits,
        "is_balanced": abs(total_debits - total_credits) <= BALANCE_TOLERANCE,
        "difference": total_debits - total_credits,
    }


def general_ledger(db: Session, company_id: int, period: DateRange, ledger_side: LedgerSide | None = None) -> list[dict]:
    transactions = transactions_in_period(db, company_id, period, ledger_side)
    entries = []
    for t in sorted(transactions, key=lambda x: x.invoice_date):
        entries.append(
            {
                "date": t.invoice_date,
                "type": "invoice",
                "ledger_side": t.ledger_side.value,
                "transaction_id": t.id,
                "invoice_number": t.invoice_number,
                "counterparty_name": t.counterparty_name,
                "description": t.accounting_classification or t.expense_category,
                "net_amount": t.net_amount,
                "vat_amount": t.vat_amount,
                "gross_amount": t.gross_amount,
            }
        )
        for p in t.payments:
            if p.voided or not (period.start <= p.payment_date <= period.end):
                continue
            entries.append(
                {
                    "date": p.payment_date,
                    "type": "payment",
                    "ledger_side": t.ledger_side.value,
                    "transaction_id": t.id,
                    "invoice_number": t.invoice_number,
                    "counterparty_name": t.counterparty_name,
                    "description": p.reference or f"Payment against invoice {t.invoice_number or t.id}",
                    "net_amount": None,
                    "vat_amount": None,
                    "gross_amount": p.amount,
                }
            )
    return sorted(entries, key=lambda e: e["date"])


def vat_overview(db: Session, company_id: int, period: DateRange) -> list[dict]:
    returns = (
        db.query(VatReturn)
        .join(VatPeriod, VatReturn.vat_period_id == VatPeriod.id)
        .filter(
            VatReturn.company_id == company_id,
            VatPeriod.start_date <= period.end,
            VatPeriod.end_date >= period.start,
        )
        .all()
    )
    return [
        {
            "vat_period_id": r.vat_period_id,
            "period_label": r.vat_period.label,
            "status": r.status.value,
            "vat_collected": r.box_5a_vat,
            "vat_deductible": r.box_5b_vat,
            "net_payable": r.net_payable,
        }
        for r in sorted(returns, key=lambda r: r.vat_period.start_date)
    ]
