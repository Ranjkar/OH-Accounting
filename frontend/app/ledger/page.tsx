"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { ApprovalBadge, PaymentBadge } from "@/components/TransactionBadges";
import { useAuth } from "@/lib/auth-context";
import { formatEUR } from "@/lib/format";
import {
  api,
  Company,
  LedgerSide,
  PURCHASE_TREATMENTS,
  SALES_TREATMENTS,
  Transaction,
  TransactionType,
  VatTreatment,
} from "@/lib/api";

/** labelKey resolved against the "ledger" namespace at render time --
 * this is a plain module-level array, not a component. */
const TYPE_FILTERS: { value: TransactionType | "all"; labelKey: string }[] = [
  { value: "all", labelKey: "allTypes" },
  { value: "SALES_INVOICE", labelKey: "salesInvoices" },
  { value: "PURCHASE_INVOICE", labelKey: "purchaseInvoices" },
  { value: "CREDIT_NOTE", labelKey: "creditNotes" },
  { value: "RECEIPT", labelKey: "receipts" },
  { value: "MANUAL_ENTRY", labelKey: "manualEntries" },
];

interface LineForm {
  description: string;
  net_amount: string;
  vat_rate: string;
  vat_amount: string;
  vat_treatment: VatTreatment;
}

function emptyLine(): LineForm {
  return { description: "", net_amount: "", vat_rate: "21", vat_amount: "", vat_treatment: "DOMESTIC_STANDARD" };
}

function LedgerContent() {
  const t = useTranslations("ledger");
  const locale = useLocale();
  const tCommon = useTranslations("common");
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [typeFilter, setTypeFilter] = useState<TransactionType | "all">("all");
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [financialYearId, setFinancialYearId] = useState<number | "">("");
  const [financialYears, setFinancialYears] = useState<{ id: number; year: number }[]>([]);
  const [ledgerSide, setLedgerSide] = useState<LedgerSide>("SALES");
  const [invoiceDate, setInvoiceDate] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [counterpartyName, setCounterpartyName] = useState("");
  const [lines, setLines] = useState<LineForm[]>([emptyLine()]);

  function refresh() {
    if (!token) return;
    api
      .listTransactions(token, {
        company_id: companyId ? Number(companyId) : undefined,
        transaction_type: typeFilter === "all" ? undefined : typeFilter,
      })
      .then(setTransactions)
      .catch((e) => setError(e.message));
  }

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  useEffect(refresh, [token, companyId, typeFilter]);

  useEffect(() => {
    const load = token && companyId ? api.listFinancialYears(token, Number(companyId)) : Promise.resolve([]);
    load.then(setFinancialYears).catch(() => setFinancialYears([]));
  }, [token, companyId]);

  const treatmentOptions = ledgerSide === "SALES" ? SALES_TREATMENTS : PURCHASE_TREATMENTS;

  function updateLine(index: number, patch: Partial<LineForm>) {
    setLines((prev) => prev.map((l, i) => (i === index ? { ...l, ...patch } : l)));
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    if (!token || !companyId || !financialYearId) {
      setError(t("selectCompanyAndYearFirst"));
      return;
    }
    setError(null);
    try {
      await api.createManualEntry(token, {
        company_id: Number(companyId),
        financial_year_id: Number(financialYearId),
        ledger_side: ledgerSide,
        invoice_date: invoiceDate,
        due_date: dueDate || null,
        counterparty_name: counterpartyName || null,
        line_items: lines.map((l) => ({
          description: l.description || null,
          net_amount: l.net_amount,
          vat_rate: l.vat_rate,
          vat_amount: l.vat_amount,
          vat_treatment: l.vat_treatment,
        })),
      });
      setShowForm(false);
      setLines([emptyLine()]);
      setCounterpartyName("");
      setInvoiceDate("");
      setDueDate("");
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("createEntryFailed"));
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold text-text-primary">{t("title")}</h1>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="btn-primary-v2 px-4 py-2 text-sm"
        >
          {showForm ? tCommon("cancel") : t("newManualEntry")}
        </button>
      </div>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      {showForm && (
        <form onSubmit={handleCreate} className="card-v2 p-5 space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="space-y-1">
              <label htmlFor="ledger-form-company" className="text-xs font-medium text-text-secondary">{tCommon("company")}</label>
              <select
                id="ledger-form-company"
                value={companyId}
                onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")}
                className="w-full input-v2 px-2.5 py-1.5 text-sm"
              >
                <option value="">{t("selectEllipsis")}</option>
                {companies.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <label htmlFor="ledger-form-fy" className="text-xs font-medium text-text-secondary">{t("financialYearLabel")}</label>
              <select
                id="ledger-form-fy"
                value={financialYearId}
                onChange={(e) => setFinancialYearId(e.target.value ? Number(e.target.value) : "")}
                className="w-full input-v2 px-2.5 py-1.5 text-sm"
              >
                <option value="">{t("selectEllipsis")}</option>
                {financialYears.map((fy) => (
                  <option key={fy.id} value={fy.id}>
                    {fy.year}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <label htmlFor="ledger-form-side" className="text-xs font-medium text-text-secondary">{t("ledgerSide")}</label>
              <select
                id="ledger-form-side"
                value={ledgerSide}
                onChange={(e) => setLedgerSide(e.target.value as LedgerSide)}
                className="w-full input-v2 px-2.5 py-1.5 text-sm"
              >
                <option value="SALES">{t("salesOption")}</option>
                <option value="PURCHASES">{t("purchasesOption")}</option>
              </select>
            </div>
            <div className="space-y-1">
              <label htmlFor="ledger-form-counterparty" className="text-xs font-medium text-text-secondary">{t("counterparty")}</label>
              <input
                id="ledger-form-counterparty"
                value={counterpartyName}
                onChange={(e) => setCounterpartyName(e.target.value)}
                className="w-full input-v2 px-2.5 py-1.5 text-sm"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="space-y-1">
              <label htmlFor="ledger-form-invoice-date" className="text-xs font-medium text-text-secondary">{t("invoiceDate")}</label>
              <input
                id="ledger-form-invoice-date"
                type="date"
                required
                value={invoiceDate}
                onChange={(e) => setInvoiceDate(e.target.value)}
                className="w-full input-v2 px-2.5 py-1.5 text-sm"
              />
            </div>
            <div className="space-y-1">
              <label htmlFor="ledger-form-due-date" className="text-xs font-medium text-text-secondary">{t("dueDate")}</label>
              <input
                id="ledger-form-due-date"
                type="date"
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
                className="w-full input-v2 px-2.5 py-1.5 text-sm"
              />
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-xs font-medium text-text-secondary">{t("lineItems")}</label>
            {lines.map((line, i) => (
              <div key={i} className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 items-end">
                <input
                  placeholder={tCommon("description")}
                  value={line.description}
                  onChange={(e) => updateLine(i, { description: e.target.value })}
                  className="col-span-2 input-v2 px-2 py-1.5 text-sm"
                />
                <input inputMode="decimal"
                  placeholder={t("net")}
                  required
                  value={line.net_amount}
                  onChange={(e) => updateLine(i, { net_amount: e.target.value })}
                  className="input-v2 px-2 py-1.5 text-sm"
                />
                <input inputMode="decimal"
                  placeholder={t("vatRatePercent")}
                  required
                  value={line.vat_rate}
                  onChange={(e) => updateLine(i, { vat_rate: e.target.value })}
                  className="input-v2 px-2 py-1.5 text-sm"
                />
                <input inputMode="decimal"
                  placeholder={t("vatAmount")}
                  required
                  value={line.vat_amount}
                  onChange={(e) => updateLine(i, { vat_amount: e.target.value })}
                  className="input-v2 px-2 py-1.5 text-sm"
                />
                <select
                  value={line.vat_treatment}
                  onChange={(e) => updateLine(i, { vat_treatment: e.target.value as VatTreatment })}
                  className="input-v2 px-2 py-1.5 text-sm"
                >
                  {treatmentOptions.map((opt) => (
                    <option key={opt} value={opt}>
                      {opt.replaceAll("_", " ")}
                    </option>
                  ))}
                </select>
              </div>
            ))}
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setLines((prev) => [...prev, emptyLine()])}
                className="text-sm text-navy hover:underline"
              >
                {t("addLine")}
              </button>
              {lines.length > 1 && (
                <button
                  type="button"
                  onClick={() => setLines((prev) => prev.slice(0, -1))}
                  className="text-sm text-text-secondary hover:underline"
                >
                  {t("removeLast")}
                </button>
              )}
            </div>
          </div>

          <button
            type="submit"
            className="btn-primary-v2 px-4 py-2 text-sm"
          >
            {t("createEntry")}
          </button>
        </form>
      )}

      <div className="flex flex-wrap items-center gap-3 sm:gap-4">
        <select
          aria-label={t("filterByCompany")}
          value={companyId}
          onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")}
          className="input-v2 px-3 py-2 text-sm"
        >
          <option value="">{tCommon("allCompanies")}</option>
          {companies.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <div className="flex items-center gap-2 text-sm flex-wrap">
          {TYPE_FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => setTypeFilter(f.value)}
              className={`rounded-full px-3 py-1 ${
                typeFilter === f.value ? "bg-navy-solid text-white" : "bg-surface-card border border-border text-text-secondary hover:bg-muted"
              }`}
            >
              {t(f.labelKey as never)}
            </button>
          ))}
        </div>
      </div>

      <div className="card-v2 overflow-hidden">
        {transactions.length === 0 ? (
          <p className="px-5 py-4 text-sm text-text-secondary">{t("noTransactionsYet")}</p>
        ) : (
          <div className="overflow-x-auto" tabIndex={0}>
          <table className="table-v3">
            <thead>
              <tr>
                <th>{tCommon("date")}</th>
                <th>{t("type")}</th>
                <th>{t("counterparty")}</th>
                <th className="text-right">{t("net")}</th>
                <th className="text-right">{t("vat")}</th>
                <th className="text-right">{t("gross")}</th>
                <th>{t("payment")}</th>
                <th>{t("approval")}</th>
              </tr>
            </thead>
            <tbody>
              {transactions.map((tx) => (
                <tr key={tx.id} className="hover:bg-muted">
                  <td>
                    <Link href={`/ledger/${tx.id}`} className="text-navy hover:underline">
                      {tx.invoice_date}
                    </Link>
                  </td>
                  <td className="text-text-secondary">{tx.transaction_type.replaceAll("_", " ")}</td>
                  <td className="text-text-primary">{tx.counterparty_name ?? "—"}</td>
                  <td className="col-amount">{formatEUR(tx.net_amount, locale)}</td>
                  <td className="col-amount text-text-secondary">{formatEUR(tx.vat_amount, locale)}</td>
                  <td className="col-amount font-medium">{formatEUR(tx.gross_amount, locale)}</td>
                  <td>
                    <PaymentBadge status={tx.payment_status} />
                  </td>
                  <td>
                    <ApprovalBadge status={tx.approval_status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </div>
    </div>
  );
}

export default function LedgerPage() {
  return (
    <AuthGuard>
      <Shell>
        <LedgerContent />
      </Shell>
    </AuthGuard>
  );
}
