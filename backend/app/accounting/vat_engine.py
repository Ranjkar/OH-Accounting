"""Deterministic Dutch VAT return calculation. Pure Decimal arithmetic over
already-posted ledger transactions -- no AI involved anywhere in this module."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.accounting import vat_rules
from app.models.accounting import AccountingTransaction, TransactionLineItem, VatReturn
from app.models.enums import LedgerSide, VatReturnStatus
from app.models.financial_year import VatPeriod

ZERO = Decimal("0")


@dataclass
class VatBoxTotals:
    box_1a_net: Decimal = ZERO
    box_1a_vat: Decimal = ZERO
    box_1b_net: Decimal = ZERO
    box_1b_vat: Decimal = ZERO
    box_1c_net: Decimal = ZERO
    box_1c_vat: Decimal = ZERO
    box_1d_vat: Decimal = ZERO
    box_1e_net: Decimal = ZERO
    box_2a_net: Decimal = ZERO
    box_2a_vat: Decimal = ZERO
    box_3a_net: Decimal = ZERO
    box_3b_net: Decimal = ZERO
    box_3c_net: Decimal = ZERO
    box_4a_net: Decimal = ZERO
    box_4a_vat: Decimal = ZERO
    box_4b_net: Decimal = ZERO
    box_4b_vat: Decimal = ZERO
    box_5a_vat: Decimal = ZERO
    box_5b_vat: Decimal = ZERO
    net_payable: Decimal = ZERO
    excluded_transaction_ids: list[int] = field(default_factory=list)


_BOX_FIELD_NAMES = {
    "1a": ("box_1a_net", "box_1a_vat"),
    "1b": ("box_1b_net", "box_1b_vat"),
    "1c": ("box_1c_net", "box_1c_vat"),
    "1d": (None, "box_1d_vat"),
    "1e": ("box_1e_net", None),
    "2a": ("box_2a_net", "box_2a_vat"),
    "3a": ("box_3a_net", None),
    "3b": ("box_3b_net", None),
    "3c": ("box_3c_net", None),
    "4a": ("box_4a_net", "box_4a_vat"),
    "4b": ("box_4b_net", "box_4b_vat"),
}


def calculate_vat_return(db: Session, company_id: int, vat_period_id: int, rules_version: str | None = None) -> VatBoxTotals:
    rules = vat_rules.get_rule_set(rules_version)
    totals = VatBoxTotals()

    lines = (
        db.query(TransactionLineItem)
        .join(AccountingTransaction, TransactionLineItem.transaction_id == AccountingTransaction.id)
        .filter(
            AccountingTransaction.vat_period_id == vat_period_id,
            AccountingTransaction.company_id == company_id,
        )
        .all()
    )

    for line in lines:
        transaction = line.transaction
        if transaction.currency != "EUR" and transaction.net_amount_eur is None:
            if transaction.id not in totals.excluded_transaction_ids:
                totals.excluded_transaction_ids.append(transaction.id)
            continue

        if transaction.currency == "EUR":
            net, vat = line.net_amount, line.vat_amount
        else:
            # EUR equivalents are only ever derived from a confirmed FX rate
            # (checked above); never fall back to a guessed rate here.
            fx = transaction.fx_rate_to_eur
            net, vat = (line.net_amount * fx).quantize(Decimal("0.01")), (line.vat_amount * fx).quantize(Decimal("0.01"))

        box = vat_rules.box_for_line(transaction.ledger_side, line.vat_treatment)
        if box:
            net_field, vat_field = _BOX_FIELD_NAMES[box]
            if net_field:
                setattr(totals, net_field, getattr(totals, net_field) + net)
            if vat_field:
                setattr(totals, vat_field, getattr(totals, vat_field) + vat)

        if transaction.ledger_side == LedgerSide.purchases:
            totals.box_5b_vat += line.deductible_vat_amount or ZERO

    totals.box_5a_vat = (
        totals.box_1a_vat
        + totals.box_1b_vat
        + totals.box_1c_vat
        + totals.box_1d_vat
        + totals.box_2a_vat
        + totals.box_4a_vat
        + totals.box_4b_vat
    )
    totals.net_payable = totals.box_5a_vat - totals.box_5b_vat
    return totals


def recalculate_and_store(
    db: Session, company_id: int, tenant_id: int, vat_period: VatPeriod, rules_version: str | None = None
) -> VatReturn:
    vat_return = db.query(VatReturn).filter(VatReturn.vat_period_id == vat_period.id).first()
    if vat_return is not None and vat_return.status in (VatReturnStatus.approved, VatReturnStatus.locked):
        raise ValueError(f"Cannot recalculate a VAT return that is already {vat_return.status.value}")

    totals = calculate_vat_return(db, company_id, vat_period.id, rules_version)

    if vat_return is None:
        vat_return = VatReturn(
            tenant_id=tenant_id,
            company_id=company_id,
            vat_period_id=vat_period.id,
            rules_version=rules_version or vat_rules.CURRENT_RULE_VERSION,
        )
        db.add(vat_return)

    for box_field in _dataclass_box_fields():
        setattr(vat_return, box_field, getattr(totals, box_field))
    vat_return.rules_version = rules_version or vat_rules.CURRENT_RULE_VERSION
    vat_return.computed_at = datetime.now(timezone.utc)
    db.flush()
    return vat_return


def _dataclass_box_fields() -> list[str]:
    return [
        "box_1a_net", "box_1a_vat", "box_1b_net", "box_1b_vat", "box_1c_net", "box_1c_vat",
        "box_1d_vat", "box_1e_net", "box_2a_net", "box_2a_vat", "box_3a_net", "box_3b_net",
        "box_3c_net", "box_4a_net", "box_4a_vat", "box_4b_net", "box_4b_vat",
        "box_5a_vat", "box_5b_vat", "net_payable",
    ]
