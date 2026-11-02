"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, DashboardSummary } from "@/lib/api";

function DashboardContent() {
  const { token } = useAuth();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    api.dashboard(token).then(setSummary).catch((e) => setError(e.message));
  }, [token]);

  if (error) return <p className="text-error">{error}</p>;
  if (!summary) return <p className="text-slate-500">Loading…</p>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-navy">Dashboard</h1>
        <Link
          href="/companies"
          className="rounded-md bg-navy text-white px-4 py-2 text-sm font-medium hover:bg-navy-light transition-colors"
        >
          Manage companies
        </Link>
      </div>

      <div className="grid grid-cols-2 gap-4 max-w-md">
        <div className="bg-white rounded-lg border border-slate-200 p-5">
          <p className="text-sm text-slate-500">Companies</p>
          <p className="text-3xl font-semibold text-navy mt-1">{summary.company_count}</p>
        </div>
        <div className="bg-white rounded-lg border border-slate-200 p-5">
          <p className="text-sm text-slate-500">Open VAT periods</p>
          <p className="text-3xl font-semibold text-pending mt-1">{summary.open_vat_periods}</p>
        </div>
      </div>

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
              </tr>
            </thead>
            <tbody>
              {summary.upcoming_deadlines.map((d, i) => (
                <tr key={i} className="border-b border-slate-100 last:border-0">
                  <td className="px-5 py-2.5">
                    <Link href={`/companies/${d.company_id}`} className="text-navy hover:underline">
                      {d.company_name}
                    </Link>
                  </td>
                  <td className="px-5 py-2.5">{d.period_label}</td>
                  <td className="px-5 py-2.5">{d.filing_deadline}</td>
                  <td className="px-5 py-2.5">{d.payment_deadline}</td>
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
