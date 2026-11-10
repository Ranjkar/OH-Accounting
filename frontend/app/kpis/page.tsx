"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, Company, JsonReport } from "@/lib/api";

function KpiCard({ name, kpi, notAvailable }: { name: string; kpi: JsonReport; notAvailable: string }) {
  return (
    <div className="card-v2 p-4">
      <p className="text-xs text-text-secondary">{name}</p>
      {kpi.value !== null ? (
        <p className="text-2xl font-semibold text-navy font-mono">{kpi.value}</p>
      ) : (
        <p className="text-sm text-pending">{notAvailable}</p>
      )}
      <p className="text-xs text-text-secondary mt-1">{kpi.explanation}</p>
      <p className="text-xs text-text-secondary mt-1 font-mono">{kpi.formula}</p>
      {kpi.missing_data && <p className="text-xs text-error mt-1">{kpi.missing_data}</p>}
    </div>
  );
}

function KpiSection({ title, kpis, notAvailable }: { title: string; kpis: Record<string, JsonReport>; notAvailable: string }) {
  return (
    <div className="space-y-2">
      <h2 className="text-lg font-medium text-text-primary">{title}</h2>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {Object.entries(kpis).map(([key, kpi]) => (
          <KpiCard key={key} name={key.replace(/_/g, " ")} kpi={kpi} notAvailable={notAvailable} />
        ))}
      </div>
    </div>
  );
}

function KpisContent() {
  const t = useTranslations("kpis");
  const tCommon = useTranslations("common");
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [periodType, setPeriodType] = useState<"MONTHLY" | "QUARTERLY" | "ANNUAL">("ANNUAL");
  const [referenceDate, setReferenceDate] = useState(new Date().toISOString().slice(0, 10));
  const [kpis, setKpis] = useState<JsonReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  useEffect(() => {
    if (!token || !companyId) return;
    api.kpis(token, { company_id: Number(companyId), period_type: periodType, reference_date: referenceDate }).then(setKpis).catch((e) => setError(e.message));
  }, [token, companyId, periodType, referenceDate]);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-text-primary">{t("title")}</h1>
      <p className="text-sm text-text-secondary">{t("subtitle")}</p>
      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="flex flex-wrap items-center gap-3">
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
      </div>

      {kpis && (
        <>
          <KpiSection title={t("profitability")} kpis={kpis.profitability} notAvailable={t("notAvailable")} />
          <KpiSection title={t("liquidity")} kpis={kpis.liquidity} notAvailable={t("notAvailable")} />
          <KpiSection title={t("efficiency")} kpis={kpis.efficiency} notAvailable={t("notAvailable")} />
          <KpiSection title={t("businessPerformance")} kpis={kpis.business_performance} notAvailable={t("notAvailable")} />
        </>
      )}
    </div>
  );
}

export default function KpisPage() {
  return (
    <AuthGuard>
      <Shell>
        <KpisContent />
      </Shell>
    </AuthGuard>
  );
}
