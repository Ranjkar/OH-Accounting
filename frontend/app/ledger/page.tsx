"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { ApprovalBadge, PaymentBadge } from "@/components/TransactionBadges";
import { useAuth } from "@/lib/auth-context";
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

const TYPE_FILTERS: { value: TransactionType | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "SALES_INVOICE", label: "Sales invoices" },
  { value: "PURCHASE_INVOICE", label: "Purchase invoices" },
  { value: "CREDIT_NOTE", label: "Credit notes" },
  { value: "RECEIPT", label: "Receipts" },
  { value: "MANUAL_ENTRY", label: "Manual entries" },
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
      setError("Select a company and financial year first.");
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
      setError(err instanceof Error ? err.message : "Failed to create entry");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-navy">Accounting Ledger</h1>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="btn-primary-v2 px-4 py-2 text-sm"
        >
          {showForm ? "Cancel" : "New manual entry"}
        </button>
      </div>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      {showForm && (
        <form onSubmit={handleCreate} className="card-v2 p-5 space-y-4">
          <div className="grid grid-cols-4 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-medium text-text-secondary">Company</label>
              <select
                value={companyId}
                onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")}
                className="w-full input-v2 px-2.5 py-1.5 text-sm"
              >
                <option value="">Select…</option>
                {companies.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-text-secondary">Financial year</label>
              <select
                value={financialYearId}
                onChange={(e) => setFinancialYearId(e.target.value ? Number(e.target.value) : "")}
                className="w-full input-v2 px-2.5 py-1.5 text-sm"
              >
                <option value="">Select…</option>
                {financialYears.map((fy) => (
                  <option key={fy.id} value={fy.id}>
                    {fy.year}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-text-secondary">Ledger side</label>
              <select
                value={ledgerSide}
                onChange={(e) => setLedgerSide(e.target.value as LedgerSide)}
                className="w-full input-v2 px-2.5 py-1.5 text-sm"
              >
                <option value="SALES">Sales</option>
                <option value="PURCHASES">Purchases</option>
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-text-secondary">Counterparty</label>
              <input
                value={counterpartyName}
                onChange={(e) => setCounterpartyName(e.target.value)}
                className="w-full input-v2 px-2.5 py-1.5 text-sm"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-medium text-text-secondary">Invoice date</label>
              <input
                type="date"
                required
                value={invoiceDate}
                onChange={(e) => setInvoiceDate(e.target.value)}
                className="w-full input-v2 px-2.5 py-1.5 text-sm"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-text-secondary">Due date</label>
              <input
                type="date"
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
                className="w-full input-v2 px-2.5 py-1.5 text-sm"
              />
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-xs font-medium text-text-secondary">Line items</label>
            {lines.map((line, i) => (
              <div key={i} className="grid grid-cols-6 gap-2 items-end">
                <input
                  placeholder="Description"
                  value={line.description}
                  onChange={(e) => updateLine(i, { description: e.target.value })}
                  className="col-span-2 input-v2 px-2 py-1.5 text-sm"
                />
                <input
                  placeholder="Net"
                  required
                  value={line.net_amount}
                  onChange={(e) => updateLine(i, { net_amount: e.target.value })}
                  className="input-v2 px-2 py-1.5 text-sm"
                />
                <input
                  placeholder="VAT rate %"
                  required
                  value={line.vat_rate}
                  onChange={(e) => updateLine(i, { vat_rate: e.target.value })}
                  className="input-v2 px-2 py-1.5 text-sm"
                />
                <input
                  placeholder="VAT amount"
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
                  {treatmentOptions.map((t) => (
                    <option key={t} value={t}>
                      {t.replaceAll("_", " ")}
                    </option>
                  ))}
                </select>
              </div>
            ))}
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setLines((prev) => [...prev, emptyLine()])}
                className="text-sm text-navy hover:underline"
              >
                + Add line
              </button>
              {lines.length > 1 && (
                <button
                  type="button"
                  onClick={() => setLines((prev) => prev.slice(0, -1))}
                  className="text-sm text-text-secondary hover:underline"
                >
                  Remove last
                </button>
              )}
            </div>
          </div>

          <button
            type="submit"
            className="btn-primary-v2 px-4 py-2 text-sm"
          >
            Create entry
          </button>
        </form>
      )}

      <div className="flex items-center gap-4">
        <select
          value={companyId}
          onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")}
          className="input-v2 px-3 py-2 text-sm"
        >
          <option value="">All companies</option>
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
                typeFilter === f.value ? "bg-navy text-white" : "bg-white border border-border-subtle text-slate-600 hover:bg-slate-50"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <div className="card-v2 overflow-hidden">
        {transactions.length === 0 ? (
          <p className="px-5 py-4 text-sm text-text-secondary">No transactions yet.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-text-secondary border-b border-border-subtle">
                <th className="px-5 py-2 font-medium">Date</th>
                <th className="px-5 py-2 font-medium">Type</th>
                <th className="px-5 py-2 font-medium">Counterparty</th>
                <th className="px-5 py-2 font-medium">Net</th>
                <th className="px-5 py-2 font-medium">VAT</th>
                <th className="px-5 py-2 font-medium">Gross</th>
                <th className="px-5 py-2 font-medium">Payment</th>
                <th className="px-5 py-2 font-medium">Approval</th>
              </tr>
            </thead>
            <tbody>
              {transactions.map((t) => (
                <tr key={t.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                  <td className="px-5 py-2.5">
                    <Link href={`/ledger/${t.id}`} className="text-navy hover:underline">
                      {t.invoice_date}
                    </Link>
                  </td>
                  <td className="px-5 py-2.5">{t.transaction_type.replaceAll("_", " ")}</td>
                  <td className="px-5 py-2.5">{t.counterparty_name ?? "—"}</td>
                  <td className="px-5 py-2.5">{t.net_amount}</td>
                  <td className="px-5 py-2.5">{t.vat_amount}</td>
                  <td className="px-5 py-2.5">{t.gross_amount}</td>
                  <td className="px-5 py-2.5">
                    <PaymentBadge status={t.payment_status} />
                  </td>
                  <td className="px-5 py-2.5">
                    <ApprovalBadge status={t.approval_status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
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
