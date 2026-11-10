"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, Budget, Company, Scenario } from "@/lib/api";

function ManagementReportsContent() {
  const t = useTranslations("reports");
  const tCommon = useTranslations("common");
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [periodType, setPeriodType] = useState<"MONTHLY" | "QUARTERLY" | "ANNUAL">("ANNUAL");
  const [referenceDate, setReferenceDate] = useState(new Date().toISOString().slice(0, 10));
  const [budgets, setBudgets] = useState<Budget[]>([]);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioIds, setScenarioIds] = useState<number[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  useEffect(() => {
    if (!token || !companyId) return;
    api.listBudgets(token, Number(companyId)).then(setBudgets).catch((e) => setError(e.message));
    api.listScenarios(token, Number(companyId)).then(setScenarios).catch((e) => setError(e.message));
  }, [token, companyId]);

  function toggleScenario(id: number) {
    setScenarioIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-text-primary">{t("managementReports")}</h1>
      <p className="text-sm text-text-secondary">{t("exportIncludesNotice")}</p>
      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <select aria-label={tCommon("company")} value={companyId} onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")} className="input-v2 px-3 py-2 text-sm">
        <option value="">{tCommon("selectCompany")}</option>
        {companies.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </select>

      {companyId && (
        <>
          <div className="card-v2 p-4 space-y-3">
            <h2 className="font-medium text-text-primary">{t("pnlPackTitle")}</h2>
            <p className="text-xs text-text-secondary">{t("pnlPackHint")}</p>
            <div className="flex items-center gap-3">
              <select aria-label={t("periodType")} value={periodType} onChange={(e) => setPeriodType(e.target.value as typeof periodType)} className="input-v2 px-3 py-2 text-sm">
                <option value="MONTHLY">{t("monthly")}</option>
                <option value="QUARTERLY">{t("quarterly")}</option>
                <option value="ANNUAL">{t("annual")}</option>
              </select>
              <input aria-label={t("referenceDate")} type="date" value={referenceDate} onChange={(e) => setReferenceDate(e.target.value)} className="input-v2 px-3 py-2 text-sm" />
              {(["pdf", "xlsx", "csv"] as const).map((fmt) => (
                <a key={fmt} href={api.pnlReportUrl(Number(companyId), periodType, referenceDate, fmt)} className="input-v2 px-3 py-1.5 text-sm">
                  {t("pnl")} {fmt.toUpperCase()}
                </a>
              ))}
            </div>
            <div className="flex items-center gap-3">
              {(["pdf", "xlsx", "csv"] as const).map((fmt) => (
                <a key={fmt} href={api.balanceSheetReportUrl(Number(companyId), referenceDate, fmt)} className="input-v2 px-3 py-1.5 text-sm">
                  {t("balanceSheet")} {fmt.toUpperCase()}
                </a>
              ))}
            </div>
          </div>

          <div className="card-v2 p-4 space-y-3">
            <h2 className="font-medium text-text-primary">{t("budgetVsActual")}</h2>
            {budgets.length === 0 && <p className="text-sm text-text-secondary">{t("noBudgetsYet")}</p>}
            {budgets.map((b) => (
              <div key={b.id} className="flex items-center gap-3 text-sm">
                <span className="flex-1">{b.name} ({t("version", { version: b.version })}, {b.status})</span>
                <a href={api.budgetVsActualReportUrl(b.id, "pdf")} className="input-v2 px-2 py-1 text-xs">
                  PDF
                </a>
                <a href={api.budgetVsActualReportUrl(b.id, "csv")} className="input-v2 px-2 py-1 text-xs">
                  CSV
                </a>
              </div>
            ))}
          </div>

          <div className="card-v2 p-4 space-y-3">
            <h2 className="font-medium text-text-primary">{t("scenarioComparison")}</h2>
            {scenarios.length === 0 && <p className="text-sm text-text-secondary">{t("noScenariosYet")}</p>}
            {scenarios.map((s) => (
              <label key={s.id} className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={scenarioIds.includes(s.id)} onChange={() => toggleScenario(s.id)} />
                {s.name} ({s.scenario_type})
              </label>
            ))}
            {scenarioIds.length >= 2 && (
              <a href={api.scenarioComparisonReportUrl(Number(companyId), scenarioIds)} className="input-v2 px-3 py-1.5 text-sm inline-block">
                {t("exportComparisonCsv")}
              </a>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default function ManagementReportsPage() {
  return (
    <AuthGuard>
      <Shell>
        <ManagementReportsContent />
      </Shell>
    </AuthGuard>
  );
}
