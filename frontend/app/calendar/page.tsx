"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import CalendarStatusBadge from "@/components/CalendarStatusBadge";
import { useAuth } from "@/lib/auth-context";
import { api, CalendarStatus, Company, TaxCalendarEntry } from "@/lib/api";

const STATUS_FILTERS: { value: CalendarStatus | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "overdue", label: "Overdue" },
  { value: "pending", label: "Pending" },
  { value: "upcoming", label: "Upcoming" },
  { value: "completed", label: "Completed" },
];

function TaxCalendarContent() {
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
        <h1 className="text-2xl font-semibold text-navy">Tax Calendar</h1>
        <div className="flex items-center gap-2 text-sm">
          <button
            onClick={() => setView("list")}
            className={`rounded-full px-3 py-1 ${view === "list" ? "bg-navy text-white" : "bg-white border border-border-subtle"}`}
          >
            List
          </button>
          <button
            onClick={() => setView("calendar")}
            className={`rounded-full px-3 py-1 ${view === "calendar" ? "bg-navy text-white" : "bg-white border border-border-subtle"}`}
          >
            Calendar
          </button>
        </div>
      </div>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="flex items-center gap-4">
        <select
          value={companyId}
          onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")}
          className="input-v2 px-3 py-2 text-sm"
        >
          <option value="">All companies</option>
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
                statusFilter === f.value ? "bg-navy text-white" : "bg-white border border-border-subtle text-slate-600 hover:bg-slate-50"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {filtered.length === 0 ? (
        <p className="text-sm text-text-secondary">No VAT periods match these filters.</p>
      ) : view === "list" ? (
        <div className="card-v2 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-text-secondary border-b border-border-subtle">
                <th className="px-5 py-2 font-medium">Company</th>
                <th className="px-5 py-2 font-medium">Period</th>
                <th className="px-5 py-2 font-medium">Frequency</th>
                <th className="px-5 py-2 font-medium">Filing deadline</th>
                <th className="px-5 py-2 font-medium">Payment deadline</th>
                <th className="px-5 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((e) => (
                <tr key={e.vat_period_id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                  <td className="px-5 py-2.5">
                    <Link href={`/companies/${e.company_id}/workspace`} className="text-navy hover:underline">
                      {e.company_name}
                    </Link>
                  </td>
                  <td className="px-5 py-2.5">
                    {e.financial_year} {e.period_label}
                  </td>
                  <td className="px-5 py-2.5 capitalize">{e.vat_frequency}</td>
                  <td className="px-5 py-2.5">{e.filing_deadline}</td>
                  <td className="px-5 py-2.5">{e.payment_deadline}</td>
                  <td className="px-5 py-2.5">
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
      ) : (
        <div className="space-y-4">
          {[...byMonth.entries()].sort().map(([month, monthEntries]) => (
            <div key={month} className="card-v2">
              <div className="px-5 py-3 border-b border-border-subtle font-medium text-navy">{month}</div>
              <div className="divide-y divide-slate-100">
                {monthEntries.map((e) => (
                  <div key={e.vat_period_id} className="px-5 py-3 flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium text-navy">{e.company_name}</p>
                      <p className="text-xs text-text-secondary">
                        {e.financial_year} {e.period_label} · due {e.filing_deadline}
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
