"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, Company, JsonReport } from "@/lib/api";
import { formatEUR } from "@/lib/format";

/** labelKey resolved against the "profitAndLoss" namespace at render
 * time -- this is a plain module-level array, not a component, so it
 * can't call useTranslations() itself (same pattern as navConfig.ts). */
const PNL_LINES: { key: string; labelKey: string; highlight?: boolean }[] = [
  { key: "revenue", labelKey: "revenue" },
  { key: "cost_of_sales", labelKey: "costOfSales" },
  { key: "gross_profit", labelKey: "grossProfit", highlight: true },
  { key: "operating_expenses", labelKey: "operatingExpenses" },
  { key: "uncategorized_expenses", labelKey: "uncategorizedExpenses" },
  { key: "personnel_expenses", labelKey: "personnelExpenses" },
  { key: "ebitda", labelKey: "ebitda", highlight: true },
  { key: "depreciation", labelKey: "depreciation" },
  { key: "ebit", labelKey: "ebit", highlight: true },
  { key: "interest_expense", labelKey: "interestExpense" },
  { key: "profit_before_tax", labelKey: "profitBeforeTax" },
  { key: "tax_expense", labelKey: "taxExpense" },
  { key: "net_profit", labelKey: "netProfit", highlight: true },
];

function PnlContent() {
  const t = useTranslations("profitAndLoss");
  const tCommon = useTranslations("common");
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
      <h1 className="text-2xl font-semibold text-text-primary">{t("title")}</h1>
      <p className="text-sm text-text-secondary">{t("subtitle")}</p>
      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="flex items-center gap-3 flex-wrap">
        <select value={companyId} aria-label={tCommon("company")} onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")} className="input-v2 px-3 py-2 text-sm">
          <option value="">{tCommon("selectCompany")}</option>
          {companies.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <select value={periodType} aria-label={t("periodType")} onChange={(e) => setPeriodType(e.target.value as typeof periodType)} className="input-v2 px-3 py-2 text-sm">
          <option value="MONTHLY">{t("monthly")}</option>
          <option value="QUARTERLY">{t("quarterly")}</option>
          <option value="ANNUAL">{t("annual")}</option>
        </select>
        <input type="date" value={referenceDate} aria-label={t("referenceDate")} onChange={(e) => setReferenceDate(e.target.value)} className="input-v2 px-3 py-2 text-sm" />
        <select value={compare} aria-label={t("compare")} onChange={(e) => setCompare(e.target.value as typeof compare)} className="input-v2 px-3 py-2 text-sm">
          <option value="">{t("noComparison")}</option>
          <option value="previous">{t("vsPreviousPeriod")}</option>
          <option value="year_on_year">{t("vsSamePeriodLastYear")}</option>
        </select>
        {companyId && (
          <div className="flex items-center gap-2 ms-auto text-xs">
            {(["pdf", "xlsx", "csv"] as const).map((fmt) => (
              <a
                key={fmt}
                href={api.pnlReportUrl(Number(companyId), periodType, referenceDate, fmt)}
                className="input-v2 px-2 py-1 hover:bg-muted"
              >
                {t("exportFormat", { format: fmt.toUpperCase() })}
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
                <th>{t("line")}</th>
                <th className="text-right">{t("current")}</th>
                {comparisonKey && <th className="text-right">{compare === "previous" ? t("previousPeriod") : t("samePeriodLastYear")}</th>}
                {comparisonKey && <th className="text-right">{t("change")}</th>}
                {comparisonKey && <th className="text-right">{t("percentChange")}</th>}
              </tr>
            </thead>
            <tbody>
              {PNL_LINES.map((line) => {
                const comparison = comparisonKey ? report.comparison?.[line.key] : null;
                return (
                  <tr key={line.key} className={line.highlight ? "bg-muted font-medium" : ""}>
                    <td className="text-text-primary">{t(line.labelKey as never)}</td>
                    <td className="col-amount">{formatEUR(report.current[line.key])}</td>
                    {comparisonKey && <td className="col-amount text-text-secondary">{formatEUR(comparison?.previous ?? 0)}</td>}
                    {comparisonKey && <td className="col-amount">{formatEUR(comparison?.change ?? 0)}</td>}
                    {comparisonKey && (
                      <td className={`col-amount ${comparison?.change_pct && Number(comparison.change_pct) < 0 ? "value-negative" : "value-positive"}`}>
                        {comparison?.change_pct !== null && comparison?.change_pct !== undefined ? `${comparison.change_pct}%` : t("notApplicable")}
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
