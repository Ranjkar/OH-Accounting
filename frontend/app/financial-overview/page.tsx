"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, Company, JsonReport } from "@/lib/api";

function Tile({ label, value, href, suffix }: { label: string; value: string; href: string; suffix?: string }) {
  return (
    <Link href={href} className="card-v2 p-4 hover:border-navy transition-colors">
      <p className="text-xs text-text-secondary">{label}</p>
      <p className="text-2xl font-semibold text-navy font-mono">
        {value}
        {suffix}
      </p>
    </Link>
  );
}

function FinancialOverviewContent() {
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [owner, setOwner] = useState<JsonReport | null>(null);
  const [portfolio, setPortfolio] = useState<JsonReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  useEffect(() => {
    if (!token) return;
    api.accountantDashboard(token).then(setPortfolio).catch((e) => setError(e.message));
  }, [token]);

  useEffect(() => {
    if (!token || !companyId) return;
    api.businessOwnerDashboard(token, Number(companyId)).then(setOwner).catch((e) => setError(e.message));
  }, [token, companyId]);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-navy">Financial Overview</h1>
      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      {portfolio && (
        <div className="space-y-2">
          <h2 className="text-lg font-medium text-navy">Portfolio ({portfolio.portfolio.length} companies)</h2>
          <div className="card-v2 overflow-hidden">
            <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-text-secondary border-b border-border-subtle">
                  <th className="px-4 py-2 font-medium">Company</th>
                  <th className="px-4 py-2 font-medium">Revenue (month)</th>
                  <th className="px-4 py-2 font-medium">Net profit (month)</th>
                  <th className="px-4 py-2 font-medium">VAT payable</th>
                  <th className="px-4 py-2 font-medium">Unreconciled</th>
                  <th className="px-4 py-2 font-medium">Balanced</th>
                </tr>
              </thead>
              <tbody>
                {portfolio.portfolio.map((row: JsonReport) => (
                  <tr key={row.company_id} className="border-b border-slate-100 last:border-0">
                    <td className="px-4 py-2.5">{row.company_name}</td>
                    <td className="px-4 py-2.5 font-mono">{row.current_month_revenue}</td>
                    <td className="px-4 py-2.5 font-mono">{row.current_month_net_profit}</td>
                    <td className="px-4 py-2.5 font-mono">{row.vat_payable}</td>
                    <td className="px-4 py-2.5">{row.unreconciled_bank_transactions}</td>
                    <td className="px-4 py-2.5">{row.balance_sheet_balanced ? "Yes" : "No"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          </div>
        </div>
      )}

      <div className="space-y-2">
        <h2 className="text-lg font-medium text-navy">Company detail</h2>
        <select
          value={companyId}
          aria-label="Company"
          onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")}
          className="input-v2 px-3 py-2 text-sm"
        >
          <option value="">Select a company</option>
          {companies.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>

        {owner && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-4">
            <Tile label="Revenue (this month)" value={owner.revenue} href="/profit-and-loss" />
            <Tile label="Net profit (this month)" value={owner.net_profit} href="/profit-and-loss" />
            <Tile label="Cash position" value={owner.cash_position} href="/balance-sheet" />
            <Tile label="Outstanding customer payments" value={owner.outstanding_customer_payments} href="/working-capital" />
            <Tile label="Upcoming supplier payments" value={owner.upcoming_supplier_payments} href="/working-capital" />
            <Tile label="Estimated VAT position" value={owner.estimated_vat_position} href="/vat" />
            <Tile label="Budget variance" value={owner.budget_performance ? owner.budget_performance.total_variance : "No approved budget"} href="/budgets" />
            <Tile label="3-month forecast" value="View" href="/forecasts" />
          </div>
        )}
      </div>
    </div>
  );
}

export default function FinancialOverviewPage() {
  return (
    <AuthGuard>
      <Shell>
        <FinancialOverviewContent />
      </Shell>
    </AuthGuard>
  );
}
