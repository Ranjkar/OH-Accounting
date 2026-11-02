"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, Company, DashboardSummary } from "@/lib/api";

function StatCard({ label, value, tone = "navy" }: { label: string; value: string | number; tone?: "navy" | "amber" | "red" | "green" }) {
  const toneClass = {
    navy: "text-navy",
    amber: "text-pending",
    red: "text-error",
    green: "text-approved",
  }[tone];
  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <p className="text-xs text-slate-500">{label}</p>
      <p className={`text-2xl font-semibold mt-1 ${toneClass}`}>{value}</p>
    </div>
  );
}

function DashboardContent() {
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  useEffect(() => {
    if (!token) return;
    api
      .dashboard(token, { company_id: companyId ? Number(companyId) : undefined })
      .then(setSummary)
      .catch((e) => setError(e.message));
  }, [token, companyId]);

  if (error) return <p className="text-error">{error}</p>;
  if (!summary) return <p className="text-slate-500">Loading…</p>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-navy">Accountant Dashboard</h1>
        <div className="flex items-center gap-3">
          <select
            value={companyId}
            onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="">All companies</option>
            {companies.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          <Link
            href="/companies"
            className="rounded-md bg-navy text-white px-4 py-2 text-sm font-medium hover:bg-navy-light transition-colors"
          >
            Manage companies
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-4">
        <StatCard label="Managed companies" value={summary.company_count} />
        <StatCard
          label="Companies requiring attention"
          value={summary.companies_requiring_attention.length}
          tone={summary.companies_requiring_attention.length ? "amber" : "green"}
        />
        <StatCard label="VAT returns awaiting review" value={summary.vat_returns_awaiting_review} tone="amber" />
        <StatCard label="VAT returns approved" value={summary.vat_returns_approved} tone="green" />
        <StatCard label="Overdue VAT returns" value={summary.overdue_vat_returns} tone={summary.overdue_vat_returns ? "red" : "green"} />
        <StatCard label="Documents awaiting approval" value={summary.documents_awaiting_approval} tone="amber" />
        <StatCard label="Unmatched / overdue payments" value={summary.unmatched_payments} tone={summary.unmatched_payments ? "red" : "green"} />
        <StatCard label="Outstanding customer info" value={summary.outstanding_customer_info} tone="amber" />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="bg-white rounded-lg border border-slate-200 p-4">
          <p className="text-xs text-slate-500">Estimated VAT payable (open periods)</p>
          <p className="text-2xl font-semibold text-error mt-1">€ {summary.estimated_vat_payable}</p>
        </div>
        <div className="bg-white rounded-lg border border-slate-200 p-4">
          <p className="text-xs text-slate-500">Estimated VAT refundable (open periods)</p>
          <p className="text-2xl font-semibold text-approved mt-1">€ {summary.estimated_vat_refundable}</p>
        </div>
      </div>

      {summary.companies_requiring_attention.length > 0 && (
        <div className="bg-white rounded-lg border border-slate-200">
          <div className="px-5 py-3 border-b border-slate-200">
            <h2 className="font-medium text-navy">Companies requiring attention</h2>
          </div>
          <div className="divide-y divide-slate-100">
            {summary.companies_requiring_attention.map((c) => (
              <Link key={c.company_id} href={`/companies/${c.company_id}/workspace`} className="block px-5 py-3 hover:bg-slate-50">
                <p className="font-medium text-navy">{c.company_name}</p>
                <p className="text-sm text-pending">{c.reasons.join(" · ")}</p>
              </Link>
            ))}
          </div>
        </div>
      )}

      <div className="bg-white rounded-lg border border-slate-200">
        <div className="px-5 py-4 border-b border-slate-200">
          <h2 className="font-medium text-navy">Upcoming filing deadlines</h2>
        </div>
        {summary.upcoming_deadlines.length === 0 ? (
          <p className="px-5 py-4 text-sm text-slate-500">No open VAT periods.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b border-slate-200">
                <th className="px-5 py-2 font-medium">Company</th>
                <th className="px-5 py-2 font-medium">Period</th>
                <th className="px-5 py-2 font-medium">Filing deadline</th>
                <th className="px-5 py-2 font-medium">Payment deadline</th>
                <th className="px-5 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {summary.upcoming_deadlines.map((d, i) => (
                <tr key={i} className="border-b border-slate-100 last:border-0">
                  <td className="px-5 py-2.5">
                    <Link href={`/companies/${d.company_id}/workspace`} className="text-navy hover:underline">
                      {d.company_name}
                    </Link>
                  </td>
                  <td className="px-5 py-2.5">{d.period_label}</td>
                  <td className="px-5 py-2.5">{d.filing_deadline}</td>
                  <td className="px-5 py-2.5">{d.payment_deadline}</td>
                  <td className="px-5 py-2.5">
                    {d.is_overdue ? (
                      <span className="text-error font-medium">Overdue</span>
                    ) : (
                      <span className="text-pending">Upcoming</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export default function Home() {
  return (
    <AuthGuard>
      <Shell>
        <DashboardContent />
      </Shell>
    </AuthGuard>
  );
}
