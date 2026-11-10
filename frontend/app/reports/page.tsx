"use client";

import { useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, Company, FinancialYear } from "@/lib/api";
import { formatEUR } from "@/lib/format";

type Format = "pdf" | "xlsx" | "csv";

function DownloadButtons({ onDownload }: { onDownload: (format: Format) => void }) {
  return (
    <div className="flex flex-wrap gap-2">
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
  const t = useTranslations("reports");
  const tCommon = useTranslations("common");
  const locale = useLocale();
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
      setError(err instanceof Error ? err.message : t("downloadFailed"));
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-text-primary">{t("title")}</h1>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="flex flex-wrap items-center gap-3 sm:gap-4">
        <select
          value={companyId}
          aria-label={tCommon("company")}
          onChange={(e) => {
            setCompanyId(e.target.value ? Number(e.target.value) : "");
            setFinancialYearId("");
          }}
          className="input-v2 px-3 py-2 text-sm"
        >
          <option value="">{t("selectCompanyEllipsis")}</option>
          {companies.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <select
          value={financialYearId}
          aria-label={t("financialYear")}
          onChange={(e) => setFinancialYearId(e.target.value ? Number(e.target.value) : "")}
          className="input-v2 px-3 py-2 text-sm"
          disabled={!companyId}
        >
          <option value="">{t("selectFinancialYearEllipsis")}</option>
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
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-sm font-medium text-text-primary">{t("financialOverviewReport")}</h2>
              <DownloadButtons onDownload={downloadFinancialOverview} />
            </div>
            <p className="text-xs text-text-secondary">{t("financialOverviewReportDescription")}</p>
          </div>

          {comparison && (
            <div className="card-v2">
              <div className="px-5 py-3 border-b border-border-subtle">
                <h2 className="text-sm font-medium text-text-primary">{t("periodComparisonHeading", { year: comparison.financial_year })}</h2>
              </div>
              <div className="overflow-x-auto" tabIndex={0}>
              <table className="table-v3">
                <thead>
                  <tr>
                    <th>{t("period")}</th>
                    <th className="text-right">{t("salesNet")}</th>
                    <th className="text-right">{t("purchasesNet")}</th>
                    <th className="text-right">{t("net")}</th>
                    <th className="text-right">{t("transactionsAbbr")}</th>
                  </tr>
                </thead>
                <tbody>
                  {comparison.periods.map((p) => (
                    <tr key={p.label}>
                      <td className="text-text-primary">{p.label}</td>
                      <td className="col-amount">{formatEUR(p.sales_net, locale)}</td>
                      <td className="col-amount">{formatEUR(p.purchases_net, locale)}</td>
                      <td className="col-amount font-medium">{formatEUR(p.income_minus_expense, locale)}</td>
                      <td className="text-right text-text-secondary">{p.transaction_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            </div>
          )}

          <div className="card-v2 p-5 space-y-3">
            <h2 className="text-sm font-medium text-text-primary">{t("vatReturnReports")}</h2>
            <p className="text-xs text-text-secondary">{t("vatReturnReportsDescription")}</p>
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
