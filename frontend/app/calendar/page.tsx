"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import CalendarStatusBadge from "@/components/CalendarStatusBadge";
import { useAuth } from "@/lib/auth-context";
import { api, CalendarStatus, Company, TaxCalendarEntry } from "@/lib/api";

const STATUS_FILTERS: { value: CalendarStatus | "all" }[] = [
  { value: "all" },
  { value: "overdue" },
  { value: "pending" },
  { value: "upcoming" },
  { value: "completed" },
];

function TaxCalendarContent() {
  const t = useTranslations("calendar");
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [statusFilter, setStatusFilter] = useState<CalendarStatus | "all">("all");
  const [view, setView] = useState<"list" | "calendar">("list");
  const [entries, setEntries] = useState<TaxCalendarEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  useEffect(() => {
    if (!token) return;
    api
      .getTaxCalendar(token, { company_id: companyId ? Number(companyId) : undefined })
      .then(setEntries)
      .catch((e) => setError(e.message));
  }, [token, companyId]);

  const filtered = statusFilter === "all" ? entries : entries.filter((e) => e.calendar_status === statusFilter);

  const byMonth = new Map<string, TaxCalendarEntry[]>();
  for (const e of filtered) {
    const month = e.filing_deadline.slice(0, 7);
    byMonth.set(month, [...(byMonth.get(month) ?? []), e]);
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-text-primary">{t("title")}</h1>
        <div className="flex items-center gap-2 text-sm">
          <button
            onClick={() => setView("list")}
            className={`rounded-full px-3 py-1 ${view === "list" ? "bg-navy-solid text-white" : "bg-surface-card border border-border text-text-secondary hover:bg-muted"}`}
          >
            {t("listView")}
          </button>
          <button
            onClick={() => setView("calendar")}
            className={`rounded-full px-3 py-1 ${view === "calendar" ? "bg-navy-solid text-white" : "bg-surface-card border border-border text-text-secondary hover:bg-muted"}`}
          >
            {t("calendarView")}
          </button>
        </div>
      </div>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="flex items-center gap-4">
        <select
          value={companyId}
          aria-label={t("companyLabel")}
          onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")}
          className="input-v2 px-3 py-2 text-sm"
        >
          <option value="">{t("allCompanies")}</option>
          {companies.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <div className="flex items-center gap-2 text-sm">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => setStatusFilter(f.value)}
              className={`rounded-full px-3 py-1 ${
                statusFilter === f.value ? "bg-navy-solid text-white" : "bg-surface-card border border-border text-text-secondary hover:bg-muted"
              }`}
            >
              {t(`statusFilters.${f.value}`)}
            </button>
          ))}
        </div>
      </div>

      {filtered.length === 0 ? (
        <p className="text-sm text-text-secondary">{t("noMatches")}</p>
      ) : view === "list" ? (
        <div className="card-v2 overflow-hidden">
          <div className="overflow-x-auto">
          <table className="table-v3">
            <thead>
              <tr>
                <th>{t("colCompany")}</th>
                <th>{t("colPeriod")}</th>
                <th>{t("colFrequency")}</th>
                <th>{t("colFilingDeadline")}</th>
                <th>{t("colPaymentDeadline")}</th>
                <th>{t("colStatus")}</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((e) => (
                <tr key={e.vat_period_id} className="hover:bg-muted">
                  <td>
                    <Link href={`/companies/${e.company_id}/workspace`} className="text-navy hover:underline">
                      {e.company_name}
                    </Link>
                  </td>
                  <td className="text-text-secondary">
                    {e.financial_year} {e.period_label}
                  </td>
                  <td className="text-text-secondary capitalize">{e.vat_frequency}</td>
                  <td className="text-text-secondary">{e.filing_deadline}</td>
                  <td className="text-text-secondary">{e.payment_deadline}</td>
                  <td>
                    {e.vat_return_id ? (
                      <Link href={`/vat/${e.vat_return_id}`}>
                        <CalendarStatusBadge status={e.calendar_status} />
                      </Link>
                    ) : (
                      <CalendarStatusBadge status={e.calendar_status} />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          {[...byMonth.entries()].sort().map(([month, monthEntries]) => (
            <div key={month} className="card-v2">
              <div className="px-5 py-3 border-b border-border-subtle font-medium text-text-primary">{month}</div>
              <div className="divide-y divide-border">
                {monthEntries.map((e) => (
                  <div key={e.vat_period_id} className="px-5 py-3 flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium text-text-primary">{e.company_name}</p>
                      <p className="text-xs text-text-secondary">
                        {e.financial_year} {e.period_label} · {t("dueOn", { date: e.filing_deadline })}
                      </p>
                    </div>
                    <CalendarStatusBadge status={e.calendar_status} />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function TaxCalendarPage() {
  return (
    <AuthGuard>
      <Shell>
        <TaxCalendarContent />
      </Shell>
    </AuthGuard>
  );
}
