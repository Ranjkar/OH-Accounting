"use client";

import { useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, Company, JsonReport } from "@/lib/api";

function KpiCard({ name, kpi }: { name: string; kpi: JsonReport }) {
  return (
    <div className="card-v2 p-4">
      <p className="text-xs text-text-secondary">{name}</p>
      {kpi.value !== null ? (
        <p className="text-2xl font-semibold text-navy font-mono">{kpi.value}</p>
      ) : (
        <p className="text-sm text-amber-600">Not available</p>
      )}
      <p className="text-xs text-text-secondary mt-1">{kpi.explanation}</p>
      <p className="text-xs text-slate-300 mt-1 font-mono">{kpi.formula}</p>
      {kpi.missing_data && <p className="text-xs text-error mt-1">{kpi.missing_data}</p>}
    </div>
  );
}

function KpiSection({ title, kpis }: { title: string; kpis: Record<string, JsonReport> }) {
  return (
    <div className="space-y-2">
      <h2 className="text-lg font-medium text-text-primary">{title}</h2>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {Object.entries(kpis).map(([key, kpi]) => (
          <KpiCard key={key} name={key.replace(/_/g, " ")} kpi={kpi} />
        ))}
      </div>
    </div>
  );
}

function KpisContent() {
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
      <h1 className="text-2xl font-semibold text-text-primary">Financial KPIs</h1>
      <p className="text-sm text-text-secondary">
        Every KPI shows its formula and source; where the underlying data doesn&apos;t exist, the KPI says so instead
        of showing a misleading number.
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
        <select value={periodType} aria-label="Period Type" onChange={(e) => setPeriodType(e.target.value as typeof periodType)} className="input-v2 px-3 py-2 text-sm">
          <option value="MONTHLY">Monthly</option>
          <option value="QUARTERLY">Quarterly</option>
          <option value="ANNUAL">Annual</option>
        </select>
        <input type="date" value={referenceDate} aria-label="Reference Date" onChange={(e) => setReferenceDate(e.target.value)} className="input-v2 px-3 py-2 text-sm" />
      </div>

      {kpis && (
        <>
          <KpiSection title="Profitability" kpis={kpis.profitability} />
          <KpiSection title="Liquidity" kpis={kpis.liquidity} />
          <KpiSection title="Efficiency" kpis={kpis.efficiency} />
          <KpiSection title="Business performance" kpis={kpis.business_performance} />
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
