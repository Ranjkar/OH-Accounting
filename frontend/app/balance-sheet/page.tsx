"use client";

import { FormEvent, useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, BalanceSheetItemCategory, Company, JsonReport, ManualBalanceSheetItem } from "@/lib/api";

const CATEGORIES: { value: BalanceSheetItemCategory; label: string }[] = [
  { value: "FIXED_ASSETS", label: "Fixed assets" },
  { value: "INVENTORY", label: "Inventory" },
  { value: "OTHER_ASSET", label: "Other asset" },
  { value: "EQUITY", label: "Equity / contributed capital" },
  { value: "LOANS", label: "Loans" },
  { value: "OTHER_LIABILITY", label: "Other liability" },
];

function Row({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className={`flex items-center justify-between py-1.5 ${highlight ? "font-semibold border-t border-border-subtle mt-1 pt-2" : ""}`}>
      <span className="text-slate-600">{label}</span>
      <span className="font-mono">{value}</span>
    </div>
  );
}

function BalanceSheetContent() {
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [asOfDate, setAsOfDate] = useState(new Date().toISOString().slice(0, 10));
  const [bs, setBs] = useState<JsonReport | null>(null);
  const [items, setItems] = useState<ManualBalanceSheetItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [category, setCategory] = useState<BalanceSheetItemCategory>("FIXED_ASSETS");
  const [label, setLabel] = useState("");
  const [amount, setAmount] = useState("");
  const [itemDate, setItemDate] = useState(new Date().toISOString().slice(0, 10));

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  function refresh() {
    if (!token || !companyId) return;
    api.balanceSheet(token, Number(companyId), asOfDate).then(setBs).catch((e) => setError(e.message));
    api.listBalanceSheetItems(token, Number(companyId)).then(setItems).catch((e) => setError(e.message));
  }

  useEffect(refresh, [token, companyId, asOfDate]);

  async function addItem(e: FormEvent) {
    e.preventDefault();
    if (!token || !companyId) return;
    try {
      await api.createBalanceSheetItem(token, { company_id: Number(companyId), category, label, amount, as_of_date: itemDate });
      setLabel("");
      setAmount("");
      refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-navy">Balance Sheet</h1>
      <p className="text-sm text-text-secondary">
        Fixed assets, inventory, equity, and loans are never derived automatically -- this ledger has no chart of
        accounts. Enter them manually below; until you do, the balance sheet only reflects cash, receivables,
        payables, and VAT position.
      </p>
      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="flex items-center gap-3">
        <select value={companyId} aria-label="Company" onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")} className="input-v2 px-3 py-2 text-sm">
          <option value="">Select a company</option>
          {companies.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <input type="date" value={asOfDate} aria-label="As Of Date" onChange={(e) => setAsOfDate(e.target.value)} className="input-v2 px-3 py-2 text-sm" />
        {companyId && (
          <div className="flex items-center gap-2 ml-auto text-xs">
            {(["pdf", "xlsx", "csv"] as const).map((fmt) => (
              <a key={fmt} href={api.balanceSheetReportUrl(Number(companyId), asOfDate, fmt)} className="input-v2 px-2 py-1 hover:bg-slate-50">
                Export {fmt.toUpperCase()}
              </a>
            ))}
          </div>
        )}
      </div>

      {bs && (
        <>
          {!bs.is_balanced && (
            <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">
              Balance sheet does not balance -- off by {bs.imbalance_amount}. {bs.missing_opening_balance_warning}
            </div>
          )}
          {bs.is_balanced && bs.missing_opening_balance_warning && (
            <div className="rounded-md bg-amber-50 text-amber-700 text-sm px-3 py-2">{bs.missing_opening_balance_warning}</div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="card-v2 p-4">
              <h2 className="font-medium text-navy mb-2">Assets</h2>
              <Row label="Cash and bank" value={bs.assets.cash_and_bank} />
              <Row label="Accounts receivable" value={bs.assets.accounts_receivable} />
              <Row label="Inventory" value={bs.assets.inventory} />
              <Row label="Fixed assets" value={bs.assets.fixed_assets} />
              <Row label="Other assets" value={bs.assets.other_assets} />
              <Row label="VAT receivable" value={bs.assets.vat_receivable} />
              <Row label="Total assets" value={bs.assets.total} highlight />
            </div>
            <div className="card-v2 p-4">
              <h2 className="font-medium text-navy mb-2">Liabilities</h2>
              <Row label="Accounts payable" value={bs.liabilities.accounts_payable} />
              <Row label="Loans" value={bs.liabilities.loans} />
              <Row label="Other liabilities" value={bs.liabilities.other_liabilities} />
              <Row label="VAT payable" value={bs.liabilities.vat_payable} />
              <Row label="Total liabilities" value={bs.liabilities.total} highlight />
            </div>
            <div className="card-v2 p-4">
              <h2 className="font-medium text-navy mb-2">Equity</h2>
              <Row label="Contributed / other equity" value={bs.equity.contributed_and_other_equity} />
              <Row label="Retained earnings" value={bs.equity.retained_earnings} />
              <Row label="Total equity" value={bs.equity.total} highlight />
            </div>
          </div>
        </>
      )}

      {companyId && (
        <div className="card-v2 p-4 space-y-3">
          <h2 className="font-medium text-navy">Manual balance-sheet items</h2>
          <form onSubmit={addItem} className="flex items-end gap-3 flex-wrap">
            <select value={category} aria-label="Category" onChange={(e) => setCategory(e.target.value as BalanceSheetItemCategory)} className="input-v2 px-2 py-2 text-sm">
              {CATEGORIES.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </select>
            <input required value={label} aria-label="Label" onChange={(e) => setLabel(e.target.value)} placeholder="Label (e.g. Delivery van)" className="input-v2 px-3 py-2 text-sm" />
            <input required value={amount} aria-label="Amount" onChange={(e) => setAmount(e.target.value)} placeholder="Amount" className="input-v2 px-3 py-2 text-sm w-32" />
            <input type="date" value={itemDate} aria-label="Item Date" onChange={(e) => setItemDate(e.target.value)} className="input-v2 px-3 py-2 text-sm" />
            <button type="submit" className="rounded-md bg-navy text-white px-4 py-2 text-sm font-medium">
              Add
            </button>
          </form>
          <table className="w-full text-sm">
            <tbody>
              {items.map((item) => (
                <tr key={item.id} className="border-t border-slate-100">
                  <td className="py-1.5 text-xs text-text-secondary">{item.category}</td>
                  <td className="py-1.5">{item.label}</td>
                  <td className="py-1.5 font-mono">{item.amount}</td>
                  <td className="py-1.5 text-xs text-text-secondary">{item.as_of_date}</td>
                </tr>
              ))}
              {items.length === 0 && (
                <tr>
                  <td className="py-2 text-text-secondary">No manual items recorded yet.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function BalanceSheetPage() {
  return (
    <AuthGuard>
      <Shell>
        <BalanceSheetContent />
      </Shell>
    </AuthGuard>
  );
}
