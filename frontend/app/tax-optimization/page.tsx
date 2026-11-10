"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, Company, JsonReport } from "@/lib/api";

const RISK_COLOR: Record<string, string> = { LOW: "bg-green-100 text-green-700", MEDIUM: "bg-amber-100 text-amber-700", HIGH: "bg-red-100 text-error" };
const RISK_KEY: Record<string, string> = { LOW: "low", MEDIUM: "medium", HIGH: "high" };

function TaxOptimizationContent() {
  const t = useTranslations("taxOptimization");
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [annualProfit, setAnnualProfit] = useState("50000");
  const [annualRevenue, setAnnualRevenue] = useState("60000");
  const [opportunities, setOpportunities] = useState<JsonReport[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  async function load() {
    if (!token || !companyId) return;
    try {
      setOpportunities(await api.taxOptimizationOpportunities(token, Number(companyId), annualProfit, annualRevenue));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-text-primary">{t("title")}</h1>
      <p className="text-sm text-text-secondary">{t("intro")}</p>
      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="flex flex-wrap items-end gap-3">
        <select value={companyId} aria-label={t("companyLabel")} onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")} className="input-v2 px-3 py-2 text-sm">
          <option value="">{t("selectCompanyOption")}</option>
          {companies.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <input inputMode="decimal" value={annualProfit} aria-label={t("annualProfitLabel")} onChange={(e) => setAnnualProfit(e.target.value)} placeholder={t("annualProfitLabel")} className="input-v2 px-3 py-2 text-sm w-36" />
        <input inputMode="decimal" value={annualRevenue} aria-label={t("annualRevenueLabel")} onChange={(e) => setAnnualRevenue(e.target.value)} placeholder={t("annualRevenueLabel")} className="input-v2 px-3 py-2 text-sm w-36" />
        <button onClick={load} disabled={!companyId} className="btn-primary-v2 px-4 py-2 text-sm disabled:opacity-50">
          {t("findOpportunities")}
        </button>
      </div>

      <div className="space-y-3">
        {opportunities.map((o, i) => (
          <div key={i} className="card-v2 p-4 space-y-1">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="font-medium text-text-primary">{o.recommendation}</h2>
              <span className={`pill-v2 px-2 py-0.5 text-xs ${RISK_COLOR[o.risk as string] ?? ""}`}>
                {RISK_KEY[o.risk as string] ? t(`riskLabels.${RISK_KEY[o.risk as string]}` as never) : o.risk}
              </span>
            </div>
            <p className="text-xs text-text-secondary">{o.legal_basis} -- {o.official_source}</p>
            {o.potential_savings !== null ? (
              <p className="text-sm">
                {t("estimatedSavings")} <span className="font-mono text-green-700">{o.potential_savings}</span>
              </p>
            ) : (
              <p className="text-sm text-pending">{t("confidenceLabel")} {o.confidence}</p>
            )}
            <ul className="text-xs text-text-secondary list-disc ps-4">
              {(o.eligibility_conditions as string[]).map((c, j) => (
                <li key={j}>{c}</li>
              ))}
            </ul>
            {(o.notes as string[])?.length > 0 && <p className="text-xs text-text-secondary">{(o.notes as string[]).join(" ")}</p>}
          </div>
        ))}
        {opportunities.length === 0 && <p className="text-sm text-text-secondary">{t("selectAndRun")}</p>}
      </div>
    </div>
  );
}

export default function TaxOptimizationPage() {
  return (
    <AuthGuard>
      <Shell>
        <TaxOptimizationContent />
      </Shell>
    </AuthGuard>
  );
}
