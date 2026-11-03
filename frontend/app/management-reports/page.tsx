"use client";

import { useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, Budget, Company, Scenario } from "@/lib/api";

function ManagementReportsContent() {
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
      <h1 className="text-2xl font-semibold text-navy">Management Reports</h1>
      <p className="text-sm text-text-secondary">
        Every export includes the company, period, generation timestamp, accounting basis, and whether figures are
        actual or forecast.
      </p>
      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <select aria-label="Company" value={companyId} onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")} className="input-v2 px-3 py-2 text-sm">
        <option value="">Select a company</option>
        {companies.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </select>

      {companyId && (
        <>
          <div className="card-v2 p-4 space-y-3">
            <h2 className="font-medium text-navy">Profit &amp; Loss / monthly management pack, quarterly review, annual summary</h2>
            <p className="text-xs text-text-secondary">Choose a period width -- monthly for a management pack, quarterly for a review, annual for a summary.</p>
            <div className="flex items-center gap-3">
              <select aria-label="Period type" value={periodType} onChange={(e) => setPeriodType(e.target.value as typeof periodType)} className="input-v2 px-3 py-2 text-sm">
                <option value="MONTHLY">Monthly</option>
                <option value="QUARTERLY">Quarterly</option>
                <option value="ANNUAL">Annual</option>
              </select>
              <input aria-label="Reference date" type="date" value={referenceDate} onChange={(e) => setReferenceDate(e.target.value)} className="input-v2 px-3 py-2 text-sm" />
              {(["pdf", "xlsx", "csv"] as const).map((fmt) => (
                <a key={fmt} href={api.pnlReportUrl(Number(companyId), periodType, referenceDate, fmt)} className="input-v2 px-3 py-1.5 text-sm">
                  P&amp;L {fmt.toUpperCase()}
                </a>
              ))}
            </div>
            <div className="flex items-center gap-3">
              {(["pdf", "xlsx", "csv"] as const).map((fmt) => (
                <a key={fmt} href={api.balanceSheetReportUrl(Number(companyId), referenceDate, fmt)} className="input-v2 px-3 py-1.5 text-sm">
                  Balance Sheet {fmt.toUpperCase()}
                </a>
              ))}
            </div>
          </div>

          <div className="card-v2 p-4 space-y-3">
            <h2 className="font-medium text-navy">Budget vs Actual</h2>
            {budgets.length === 0 && <p className="text-sm text-text-secondary">No budgets for this company yet.</p>}
            {budgets.map((b) => (
              <div key={b.id} className="flex items-center gap-3 text-sm">
                <span className="flex-1">{b.name} (v{b.version}, {b.status})</span>
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
            <h2 className="font-medium text-navy">Scenario comparison</h2>
            {scenarios.length === 0 && <p className="text-sm text-text-secondary">No scenarios for this company yet.</p>}
            {scenarios.map((s) => (
              <label key={s.id} className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={scenarioIds.includes(s.id)} onChange={() => toggleScenario(s.id)} />
                {s.name} ({s.scenario_type})
              </label>
            ))}
            {scenarioIds.length >= 2 && (
              <a href={api.scenarioComparisonReportUrl(Number(companyId), scenarioIds)} className="input-v2 px-3 py-1.5 text-sm inline-block">
                Export comparison CSV
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
