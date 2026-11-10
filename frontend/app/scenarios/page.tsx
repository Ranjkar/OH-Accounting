"use client";

import { FormEvent, useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, Company, JsonReport, Scenario, ScenarioType } from "@/lib/api";
import { formatEUR } from "@/lib/format";

/** labelKey/placeholderKey resolved against the "scenarios" namespace at
 * render time -- plain module-level array, not a component. */
const ASSUMPTION_FIELDS: { key: string; labelKey: string; placeholderKey: string }[] = [
  { key: "revenue_change_pct", labelKey: "revenueChangePct", placeholderKey: "revenueChangePctPlaceholder" },
  { key: "expense_change_pct", labelKey: "expenseChangePct", placeholderKey: "expenseChangePctPlaceholder" },
  { key: "new_hire_monthly_cost", labelKey: "newHireMonthlyCost", placeholderKey: "newHireMonthlyCostPlaceholder" },
  { key: "payment_delay_days", labelKey: "paymentDelayDays", placeholderKey: "paymentDelayDaysPlaceholder" },
  { key: "new_equipment_investment", labelKey: "newEquipmentInvestment", placeholderKey: "newEquipmentInvestmentPlaceholder" },
  { key: "additional_financing", labelKey: "additionalFinancing", placeholderKey: "additionalFinancingPlaceholder" },
];

function ScenariosContent() {
  const t = useTranslations("scenarios");
  const locale = useLocale();
  const tCommon = useTranslations("common");
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
      <h1 className="text-2xl font-semibold text-text-primary">{t("title")}</h1>
      <p className="text-sm text-text-secondary">{t("subtitle")}</p>
      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <select value={companyId} aria-label={tCommon("company")} onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")} className="input-v2 px-3 py-2 text-sm">
        <option value="">{tCommon("selectCompany")}</option>
        {companies.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </select>

      {companyId && (
        <div className="card-v2 p-4 space-y-3">
          <h2 className="font-medium text-text-primary">{t("newScenario")}</h2>
          <form onSubmit={createScenario} className="space-y-3">
            <div className="flex flex-wrap items-center gap-3">
              <input required value={name} aria-label={tCommon("name")} onChange={(e) => setName(e.target.value)} placeholder={t("scenarioNamePlaceholder")} className="input-v2 px-3 py-2 text-sm w-56" />
              <select value={scenarioType} aria-label={t("scenarioType")} onChange={(e) => setScenarioType(e.target.value as ScenarioType)} className="input-v2 px-2 py-2 text-sm">
                <option value="BASE">{t("baseCase")}</option>
                <option value="OPTIMISTIC">{t("optimistic")}</option>
                <option value="CONSERVATIVE">{t("conservative")}</option>
                <option value="CUSTOM">{t("custom")}</option>
              </select>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {ASSUMPTION_FIELDS.map((f) => (
                <input
                  key={f.key}
                  value={assumptions[f.key] ?? ""}
                  onChange={(e) => setAssumptions((prev) => ({ ...prev, [f.key]: e.target.value }))}
                  placeholder={`${t(f.labelKey as never)} (${t(f.placeholderKey as never)})`}
                  className="input-v2 px-3 py-2 text-xs"
                />
              ))}
            </div>
            <button type="submit" className="rounded-md bg-navy-solid text-white px-4 py-2 text-sm font-medium">
              {t("createScenario")}
            </button>
          </form>
        </div>
      )}

      <div className="card-v2 overflow-hidden">
        <div className="overflow-x-auto" tabIndex={0}>
        <table className="table-v3">
          <thead>
            <tr>
              <th />
              <th>{tCommon("name")}</th>
              <th>{t("type")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {scenarios.map((s) => (
              <tr key={s.id}>
                <td>
                  <input type="checkbox" aria-label={t("selectScenario", { name: s.name })} checked={selectedIds.includes(s.id)} onChange={() => toggleSelect(s.id)} />
                </td>
                <td className="text-text-primary">{s.name}</td>
                <td className="text-xs text-text-secondary">{s.scenario_type}</td>
                <td className="text-xs">
                  <button onClick={() => duplicate(s)} className="text-navy hover:underline">
                    {t("duplicate")}
                  </button>
                </td>
              </tr>
            ))}
            {scenarios.length === 0 && (
              <tr>
                <td colSpan={4} className="text-text-secondary">
                  {t("noScenariosYet")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button onClick={compare} disabled={selectedIds.length < 2} className="rounded-md bg-navy-solid text-white px-4 py-2 text-sm font-medium disabled:opacity-50">
          {t("compareSelected")}
        </button>
        {companyId && selectedIds.length >= 2 && (
          <a href={api.scenarioComparisonReportUrl(Number(companyId), selectedIds)} className="text-xs text-navy underline">
            {t("exportComparisonCsv")}
          </a>
        )}
      </div>

      {comparison && (
        <div className="card-v2 p-4">
          <h2 className="font-medium text-text-primary mb-2">{t("comparison")}</h2>
          <div className="overflow-x-auto" tabIndex={0}>
          <table className="table-v3">
            <thead>
              <tr>
                <th>{t("scenario")}</th>
                <th className="text-right">{t("forecastProfit")}</th>
                <th className="text-right">{t("netCashChange")}</th>
              </tr>
            </thead>
            <tbody>
              {comparison.comparison.map((row: JsonReport) => (
                <tr key={row.name}>
                  <td className="text-text-primary">{row.name}</td>
                  <td className="col-amount">{formatEUR(row.total_forecast_profit, locale)}</td>
                  <td className="col-amount">{formatEUR(row.scenario_net_cash_change, locale)}</td>
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
