"use client";

import { useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, Company, FinancialYear } from "@/lib/api";
import { formatEUR } from "@/lib/format";

type Format = "pdf" | "xlsx" | "csv";

function DownloadButtons({ onDownload }: { onDownload: (format: Format) => void }) {
  return (
    <div className="flex gap-2">
      {(["pdf", "xlsx", "csv"] as Format[]).map((fmt) => (
        <button
          key={fmt}
          onClick={() => onDownload(fmt)}
          className="input-v2 px-3 py-1.5 text-xs font-medium uppercase hover:bg-muted transition-colors"
        >
          {fmt}
        </button>
      ))}
    </div>
  );
}

function ReportsContent() {
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [financialYears, setFinancialYears] = useState<FinancialYear[]>([]);
  const [financialYearId, setFinancialYearId] = useState<number | "">("");
  const [error, setError] = useState<string | null>(null);
  const [comparison, setComparison] = useState<Awaited<ReturnType<typeof api.getPeriodComparison>> | null>(null);

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  useEffect(() => {
    const load = token && companyId ? api.listFinancialYears(token, Number(companyId)) : Promise.resolve([]);
    load.then(setFinancialYears).catch((e) => setError(e.message));
  }, [token, companyId]);

  useEffect(() => {
    const load =
      token && companyId && financialYearId
        ? api.getPeriodComparison(token, Number(companyId), Number(financialYearId))
        : Promise.resolve(null);
    load.then(setComparison).catch((e) => setError(e.message));
  }, [token, companyId, financialYearId]);

  async function downloadFinancialOverview(format: Format) {
    if (!token || !companyId || !financialYearId) return;
    try {
      await api.downloadReport(
        token,
        api.financialOverviewReportUrl(Number(companyId), Number(financialYearId), format),
        `financial-overview.${format}`
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to download report");
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-text-primary">Reports</h1>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="flex items-center gap-4">
        <select
          value={companyId}
          aria-label="Company"
          onChange={(e) => {
            setCompanyId(e.target.value ? Number(e.target.value) : "");
            setFinancialYearId("");
          }}
          className="input-v2 px-3 py-2 text-sm"
        >
          <option value="">Select a company…</option>
          {companies.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <select
          value={financialYearId}
          aria-label="Financial Year"
          onChange={(e) => setFinancialYearId(e.target.value ? Number(e.target.value) : "")}
          className="input-v2 px-3 py-2 text-sm"
          disabled={!companyId}
        >
          <option value="">Select a financial year…</option>
          {financialYears.map((fy) => (
            <option key={fy.id} value={fy.id}>
              {fy.year}
            </option>
          ))}
        </select>
      </div>

      {companyId && financialYearId && (
        <>
          <div className="card-v2 p-5 space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-medium text-text-primary">Financial Overview Report</h2>
              <DownloadButtons onDownload={downloadFinancialOverview} />
            </div>
            <p className="text-xs text-text-secondary">
              Income/expense overview, period-by-period comparison, payment status, and outstanding invoices.
            </p>
          </div>

          {comparison && (
            <div className="card-v2">
              <div className="px-5 py-3 border-b border-border-subtle">
                <h2 className="text-sm font-medium text-text-primary">Period comparison — financial year {comparison.financial_year}</h2>
              </div>
              <div className="overflow-x-auto">
              <table className="table-v3">
                <thead>
                  <tr>
                    <th>Period</th>
                    <th className="text-right">Sales (net)</th>
                    <th className="text-right">Purchases (net)</th>
                    <th className="text-right">Net</th>
                    <th className="text-right">Txns</th>
                  </tr>
                </thead>
                <tbody>
                  {comparison.periods.map((p) => (
                    <tr key={p.label}>
                      <td className="text-text-primary">{p.label}</td>
                      <td className="col-amount">{formatEUR(p.sales_net)}</td>
                      <td className="col-amount">{formatEUR(p.purchases_net)}</td>
                      <td className="col-amount font-medium">{formatEUR(p.income_minus_expense)}</td>
                      <td className="text-right text-text-secondary">{p.transaction_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            </div>
          )}

          <div className="card-v2 p-5 space-y-3">
            <h2 className="text-sm font-medium text-text-primary">VAT Return Reports</h2>
            <p className="text-xs text-text-secondary">Open a period&apos;s VAT return from the VAT Returns or Tax Calendar page to download its report.</p>
          </div>
        </>
      )}
    </div>
  );
}

export default function ReportsPage() {
  return (
    <AuthGuard>
      <Shell>
        <ReportsContent />
      </Shell>
    </AuthGuard>
  );
}
