"use client";

import { useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, Company, JsonReport } from "@/lib/api";
import { formatEUR } from "@/lib/format";

const PNL_LINES: { key: string; label: string; highlight?: boolean }[] = [
  { key: "revenue", label: "Revenue" },
  { key: "cost_of_sales", label: "Cost of sales" },
  { key: "gross_profit", label: "Gross profit", highlight: true },
  { key: "operating_expenses", label: "Operating expenses" },
  { key: "uncategorized_expenses", label: "Uncategorized expenses" },
  { key: "personnel_expenses", label: "Personnel expenses" },
  { key: "ebitda", label: "EBITDA", highlight: true },
  { key: "depreciation", label: "Depreciation" },
  { key: "ebit", label: "EBIT", highlight: true },
  { key: "interest_expense", label: "Interest expense" },
  { key: "profit_before_tax", label: "Profit before tax" },
  { key: "tax_expense", label: "Tax expense" },
  { key: "net_profit", label: "Net profit", highlight: true },
];

function PnlContent() {
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [periodType, setPeriodType] = useState<"MONTHLY" | "QUARTERLY" | "ANNUAL">("MONTHLY");
  const [referenceDate, setReferenceDate] = useState(new Date().toISOString().slice(0, 10));
  const [compare, setCompare] = useState<"" | "previous" | "year_on_year">("previous");
  const [report, setReport] = useState<JsonReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  useEffect(() => {
    if (!token || !companyId) return;
    api
      .profitAndLoss(token, { company_id: Number(companyId), period_type: periodType, reference_date: referenceDate, compare: compare || undefined })
      .then(setReport)
      .catch((e) => setError(e.message));
  }, [token, companyId, periodType, referenceDate, compare]);

  const comparisonKey = compare === "previous" ? "previous" : compare === "year_on_year" ? "year_on_year" : null;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-text-primary">Profit &amp; Loss</h1>
      <p className="text-sm text-text-secondary">
        All figures are accrual-basis actuals from the ledger, never an estimate. Revenue and cost-of-sales categories
        are only split out when transactions have been tagged with that category.
      </p>
      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="flex items-center gap-3 flex-wrap">
        <select value={companyId} aria-label="Company" onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")} className="input-v2 px-3 py-2 text-sm">
          <option value="">Select a company</option>
          {companies.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <select value={periodType} aria-label="Period Type" onChange={(e) => setPeriodType(e.target.value as typeof periodType)} className="input-v2 px-3 py-2 text-sm">
          <option value="MONTHLY">Monthly</option>
          <option value="QUARTERLY">Quarterly</option>
          <option value="ANNUAL">Annual</option>
        </select>
        <input type="date" value={referenceDate} aria-label="Reference Date" onChange={(e) => setReferenceDate(e.target.value)} className="input-v2 px-3 py-2 text-sm" />
        <select value={compare} aria-label="Compare" onChange={(e) => setCompare(e.target.value as typeof compare)} className="input-v2 px-3 py-2 text-sm">
          <option value="">No comparison</option>
          <option value="previous">vs previous period</option>
          <option value="year_on_year">vs same period last year</option>
        </select>
        {companyId && (
          <div className="flex items-center gap-2 ms-auto text-xs">
            {(["pdf", "xlsx", "csv"] as const).map((fmt) => (
              <a
                key={fmt}
                href={api.pnlReportUrl(Number(companyId), periodType, referenceDate, fmt)}
                className="input-v2 px-2 py-1 hover:bg-muted"
              >
                Export {fmt.toUpperCase()}
              </a>
            ))}
          </div>
        )}
      </div>

      {report && (
        <div className="card-v2 overflow-hidden">
          <div className="overflow-x-auto">
          <table className="table-v3">
            <thead>
              <tr>
                <th>Line</th>
                <th className="text-right">Current</th>
                {comparisonKey && <th className="text-right">{compare === "previous" ? "Previous period" : "Same period last year"}</th>}
                {comparisonKey && <th className="text-right">Change</th>}
                {comparisonKey && <th className="text-right">% change</th>}
              </tr>
            </thead>
            <tbody>
              {PNL_LINES.map((line) => {
                const comparison = comparisonKey ? report.comparison?.[line.key] : null;
                return (
                  <tr key={line.key} className={line.highlight ? "bg-muted font-medium" : ""}>
                    <td className="text-text-primary">{line.label}</td>
                    <td className="col-amount">{formatEUR(report.current[line.key])}</td>
                    {comparisonKey && <td className="col-amount text-text-secondary">{formatEUR(comparison?.previous ?? 0)}</td>}
                    {comparisonKey && <td className="col-amount">{formatEUR(comparison?.change ?? 0)}</td>}
                    {comparisonKey && (
                      <td className={`col-amount ${comparison?.change_pct && Number(comparison.change_pct) < 0 ? "value-negative" : "value-positive"}`}>
                        {comparison?.change_pct !== null && comparison?.change_pct !== undefined ? `${comparison.change_pct}%` : "n/a"}
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
          </div>
          <p className="text-xs text-text-secondary p-4 pt-2">{report.current.tax_expense_note}</p>
        </div>
      )}
    </div>
  );
}

export default function ProfitAndLossPage() {
  return (
    <AuthGuard>
      <Shell>
        <PnlContent />
      </Shell>
    </AuthGuard>
  );
}
