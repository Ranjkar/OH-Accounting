"use client";

import { FormEvent, useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, Company, JsonReport, Scenario, ScenarioType } from "@/lib/api";

const ASSUMPTION_FIELDS: { key: string; label: string; placeholder: string }[] = [
  { key: "revenue_change_pct", label: "Revenue change %", placeholder: "e.g. 10 or -15" },
  { key: "expense_change_pct", label: "Expense change %", placeholder: "e.g. 5" },
  { key: "new_hire_monthly_cost", label: "New hire monthly cost", placeholder: "e.g. 3500" },
  { key: "payment_delay_days", label: "Payment delay (days)", placeholder: "e.g. 30" },
  { key: "new_equipment_investment", label: "New equipment investment", placeholder: "one-off, e.g. 8000" },
  { key: "additional_financing", label: "Additional financing", placeholder: "one-off, e.g. 20000" },
];

function ScenariosContent() {
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [comparison, setComparison] = useState<JsonReport | null>(null);
  const [name, setName] = useState("");
  const [scenarioType, setScenarioType] = useState<ScenarioType>("CUSTOM");
  const [assumptions, setAssumptions] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  function refresh() {
    if (!token || !companyId) return;
    api.listScenarios(token, Number(companyId)).then(setScenarios).catch((e) => setError(e.message));
  }

  useEffect(refresh, [token, companyId]);

  async function createScenario(e: FormEvent) {
    e.preventDefault();
    if (!token || !companyId) return;
    const cleaned = Object.fromEntries(Object.entries(assumptions).filter(([, v]) => v !== ""));
    try {
      await api.createScenario(token, { company_id: Number(companyId), name, scenario_type: scenarioType, assumptions: cleaned, horizon_months: 3 });
      setName("");
      setAssumptions({});
      refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  function toggleSelect(id: number) {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  async function compare() {
    if (!token || selectedIds.length < 2) return;
    try {
      setComparison(await api.compareScenarios(token, selectedIds));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function duplicate(scenario: Scenario) {
    if (!token) return;
    await api.duplicateScenario(token, scenario.id, `${scenario.name} (copy)`);
    refresh();
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-text-primary">Scenario Planning</h1>
      <p className="text-sm text-text-secondary">
        Scenarios never touch the ledger -- every result here is recomputed on the fly from your current forecast
        plus the assumptions below.
      </p>
      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <select value={companyId} aria-label="Company" onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")} className="input-v2 px-3 py-2 text-sm">
        <option value="">Select a company</option>
        {companies.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </select>

      {companyId && (
        <div className="card-v2 p-4 space-y-3">
          <h2 className="font-medium text-navy">New scenario</h2>
          <form onSubmit={createScenario} className="space-y-3">
            <div className="flex items-center gap-3">
              <input required value={name} aria-label="Name" onChange={(e) => setName(e.target.value)} placeholder="Scenario name" className="input-v2 px-3 py-2 text-sm w-56" />
              <select value={scenarioType} aria-label="Scenario Type" onChange={(e) => setScenarioType(e.target.value as ScenarioType)} className="input-v2 px-2 py-2 text-sm">
                <option value="BASE">Base case</option>
                <option value="OPTIMISTIC">Optimistic</option>
                <option value="CONSERVATIVE">Conservative</option>
                <option value="CUSTOM">Custom</option>
              </select>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {ASSUMPTION_FIELDS.map((f) => (
                <input
                  key={f.key}
                  value={assumptions[f.key] ?? ""}
                  onChange={(e) => setAssumptions((prev) => ({ ...prev, [f.key]: e.target.value }))}
                  placeholder={`${f.label} (${f.placeholder})`}
                  className="input-v2 px-3 py-2 text-xs"
                />
              ))}
            </div>
            <button type="submit" className="rounded-md bg-navy-solid text-white px-4 py-2 text-sm font-medium">
              Create scenario
            </button>
          </form>
        </div>
      )}

      <div className="card-v2 overflow-hidden">
        <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-text-secondary border-b border-border-subtle">
              <th className="px-4 py-2 font-medium" />
              <th className="px-4 py-2 font-medium">Name</th>
              <th className="px-4 py-2 font-medium">Type</th>
              <th className="px-4 py-2 font-medium" />
            </tr>
          </thead>
          <tbody>
            {scenarios.map((s) => (
              <tr key={s.id} className="border-b border-slate-100 last:border-0">
                <td className="px-4 py-2.5">
                  <input type="checkbox" checked={selectedIds.includes(s.id)} onChange={() => toggleSelect(s.id)} />
                </td>
                <td className="px-4 py-2.5">{s.name}</td>
                <td className="px-4 py-2.5 text-xs">{s.scenario_type}</td>
                <td className="px-4 py-2.5 text-xs">
                  <button onClick={() => duplicate(s)} className="text-navy underline">
                    Duplicate
                  </button>
                </td>
              </tr>
            ))}
            {scenarios.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-4 text-text-secondary">
                  No scenarios yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button onClick={compare} disabled={selectedIds.length < 2} className="rounded-md bg-navy-solid text-white px-4 py-2 text-sm font-medium disabled:opacity-50">
          Compare selected
        </button>
        {companyId && selectedIds.length >= 2 && (
          <a href={api.scenarioComparisonReportUrl(Number(companyId), selectedIds)} className="text-xs text-navy underline">
            Export comparison CSV
          </a>
        )}
      </div>

      {comparison && (
        <div className="card-v2 p-4">
          <h2 className="font-medium text-navy mb-2">Comparison</h2>
          <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-text-secondary border-b border-border-subtle">
                <th className="py-1">Scenario</th>
                <th className="py-1">Forecast profit</th>
                <th className="py-1">Net cash change</th>
              </tr>
            </thead>
            <tbody>
              {comparison.comparison.map((row: JsonReport) => (
                <tr key={row.name} className="border-b border-slate-100 last:border-0">
                  <td className="py-1.5">{row.name}</td>
                  <td className="py-1.5 font-mono">{row.total_forecast_profit}</td>
                  <td className="py-1.5 font-mono">{row.scenario_net_cash_change}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
      )}
    </div>
  );
}

export default function ScenariosPage() {
  return (
    <AuthGuard>
      <Shell>
        <ScenariosContent />
      </Shell>
    </AuthGuard>
  );
}
