"use client";

import { FormEvent, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, Company, JsonReport } from "@/lib/api";

const CATEGORY_KEYS = ["business_activity", "training", "administration", "business_development", "travel", "other"];

function EntrepreneurHoursContent() {
  const t = useTranslations("entrepreneurHours");
  const tCommon = useTranslations("common");
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [year, setYear] = useState(2025);
  const [entries, setEntries] = useState<JsonReport[]>([]);
  const [dashboard, setDashboard] = useState<JsonReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [entryDate, setEntryDate] = useState("2025-03-01");
  const [category, setCategory] = useState("business_activity");
  const [durationHours, setDurationHours] = useState("4");
  const [description, setDescription] = useState("");

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  function refresh() {
    if (!token || !companyId) return;
    api.listEntrepreneurHoursEntries(token, Number(companyId)).then(setEntries).catch((e) => setError(e.message));
    api.urencriteriumDashboard(token, Number(companyId), year).then(setDashboard).catch((e) => setError(e.message));
  }

  useEffect(refresh, [token, companyId, year]);

  async function createEntry(e: FormEvent) {
    e.preventDefault();
    if (!token || !companyId) return;
    try {
      await api.createEntrepreneurHoursEntry(token, {
        company_id: Number(companyId), entry_date: entryDate, activity_category: category, duration_hours: durationHours, description,
      });
      setDescription("");
      refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const pct = dashboard ? Math.min(100, (Number(dashboard.total_recorded_hours) / dashboard.threshold_hours) * 100) : 0;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-text-primary">{t("title")}</h1>
      <p className="text-sm text-text-secondary">{t("urencriteriumNotice")}</p>
      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="flex items-center gap-3">
        <select value={companyId} aria-label={tCommon("company")} onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")} className="input-v2 px-3 py-2 text-sm">
          <option value="">{tCommon("selectCompany")}</option>
          {companies.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <input type="number" value={year} aria-label={t("year")} onChange={(e) => setYear(Number(e.target.value))} className="input-v2 px-3 py-2 text-sm w-24" />
      </div>

      {dashboard && (
        <div className="card-v2 p-4 space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span>
              {t("hoursRecorded", { recorded: String(dashboard.total_recorded_hours), threshold: String(dashboard.threshold_hours) })}
            </span>
            <span className={dashboard.threshold_met_by_recorded_hours_alone ? "text-green-700" : "text-text-secondary"}>
              {dashboard.threshold_met_by_recorded_hours_alone ? t("thresholdMet") : t("belowThreshold")}
            </span>
          </div>
          <div className="h-2 bg-surface-page rounded-full overflow-hidden">
            <div className="h-2 hero-gradient-v2 rounded-full" style={{ width: `${pct}%` }} />
          </div>
          <p className="text-xs text-pending">{dashboard.disclaimer}</p>
          <div className="text-xs text-text-secondary">
            {Object.entries(dashboard.hours_by_category as Record<string, string>).map(([cat, hrs]) => (
              <span key={cat} className="me-3">
                {CATEGORY_KEYS.includes(cat) ? t(`category.${cat}` as never) : cat}: {hrs}h
              </span>
            ))}
          </div>
        </div>
      )}

      {companyId && (
        <form onSubmit={createEntry} className="card-v2 p-4 flex items-end gap-3 flex-wrap">
          <input type="date" value={entryDate} aria-label={t("entryDate")} onChange={(e) => setEntryDate(e.target.value)} className="input-v2 px-3 py-2 text-sm" />
          <select value={category} aria-label={t("categoryLabel")} onChange={(e) => setCategory(e.target.value)} className="input-v2 px-3 py-2 text-sm">
            {CATEGORY_KEYS.map((key) => (
              <option key={key} value={key}>
                {t(`category.${key}` as never)}
              </option>
            ))}
          </select>
          <input value={durationHours} aria-label={t("durationHours")} onChange={(e) => setDurationHours(e.target.value)} placeholder={t("hours")} className="input-v2 px-3 py-2 text-sm w-24" />
          <input value={description} aria-label={tCommon("description")} onChange={(e) => setDescription(e.target.value)} placeholder={tCommon("description")} className="input-v2 px-3 py-2 text-sm flex-1" />
          <button type="submit" className="btn-primary-v2 px-4 py-2 text-sm">
            {t("logHours")}
          </button>
        </form>
      )}

      <div className="card-v2 overflow-hidden">
        <div className="overflow-x-auto">
        <table className="table-v3">
          <thead>
            <tr>
              <th>{tCommon("date")}</th>
              <th>{t("categoryLabel")}</th>
              <th className="text-right">{t("hours")}</th>
              <th>{tCommon("description")}</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <tr key={entry.id}>
                <td className="text-text-secondary">{entry.entry_date}</td>
                <td className="text-text-primary">{CATEGORY_KEYS.includes(entry.activity_category as string) ? t(`category.${entry.activity_category}` as never) : String(entry.activity_category)}</td>
                <td className="text-right font-mono tabular-nums">{entry.duration_hours}</td>
                <td className="text-text-secondary">{entry.description ?? "—"}</td>
              </tr>
            ))}
            {entries.length === 0 && (
              <tr>
                <td colSpan={4} className="text-text-secondary">
                  {t("noHoursLoggedYet")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
        </div>
      </div>
    </div>
  );
}

export default function EntrepreneurHoursPage() {
  return (
    <AuthGuard>
      <Shell>
        <EntrepreneurHoursContent />
      </Shell>
    </AuthGuard>
  );
}
