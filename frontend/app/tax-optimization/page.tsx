"use client";

import { useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, Company, JsonReport } from "@/lib/api";

const RISK_COLOR: Record<string, string> = { LOW: "bg-green-100 text-green-700", MEDIUM: "bg-amber-100 text-amber-700", HIGH: "bg-red-100 text-error" };

function TaxOptimizationContent() {
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
      <h1 className="text-2xl font-semibold text-text-primary">Tax Optimisation</h1>
      <p className="text-sm text-text-secondary">
        Every item names its legal basis, eligibility conditions, and required evidence. Only items this system has
        real data for show a computed saving -- everything else is flagged as requiring data this system doesn&apos;t
        track, never a fabricated number.
      </p>
      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="flex items-end gap-3">
        <select value={companyId} aria-label="Company" onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")} className="input-v2 px-3 py-2 text-sm">
          <option value="">Select a company</option>
          {companies.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <input value={annualProfit} aria-label="Annual Profit" onChange={(e) => setAnnualProfit(e.target.value)} placeholder="Annual profit" className="input-v2 px-3 py-2 text-sm w-36" />
        <input value={annualRevenue} aria-label="Annual Revenue" onChange={(e) => setAnnualRevenue(e.target.value)} placeholder="Annual revenue" className="input-v2 px-3 py-2 text-sm w-36" />
        <button onClick={load} disabled={!companyId} className="btn-primary-v2 px-4 py-2 text-sm disabled:opacity-50">
          Find opportunities
        </button>
      </div>

      <div className="space-y-3">
        {opportunities.map((o, i) => (
          <div key={i} className="card-v2 p-4 space-y-1">
            <div className="flex items-center justify-between">
              <h2 className="font-medium text-text-primary">{o.recommendation}</h2>
              <span className={`pill-v2 px-2 py-0.5 text-xs ${RISK_COLOR[o.risk as string] ?? ""}`}>{o.risk}</span>
            </div>
            <p className="text-xs text-text-secondary">{o.legal_basis} -- {o.official_source}</p>
            {o.potential_savings !== null ? (
              <p className="text-sm">
                Estimated savings: <span className="font-mono text-green-700">{o.potential_savings}</span>
              </p>
            ) : (
              <p className="text-sm text-pending">Confidence: {o.confidence}</p>
            )}
            <ul className="text-xs text-text-secondary list-disc pl-4">
              {(o.eligibility_conditions as string[]).map((c, j) => (
                <li key={j}>{c}</li>
              ))}
            </ul>
            {(o.notes as string[])?.length > 0 && <p className="text-xs text-text-secondary">{(o.notes as string[]).join(" ")}</p>}
          </div>
        ))}
        {opportunities.length === 0 && <p className="text-sm text-text-secondary">Select a company and run the search.</p>}
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
