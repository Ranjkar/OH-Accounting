"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, Company, DashboardSummary } from "@/lib/api";

function StatCard({ label, value, tone = "default", href }: { label: string; value: string | number; tone?: "default" | "warning" | "error" | "success"; href?: string }) {
  const toneClass = { default: "text-text-primary", warning: "text-semantic-warning", error: "text-semantic-error", success: "text-semantic-success" }[tone];
  const content = (
    <div className="card-v2 card-v2-hover p-4">
      <p className="text-xs text-text-secondary">{label}</p>
      <p className={`text-2xl font-semibold mt-1 ${toneClass}`}>{value}</p>
    </div>
  );
  return href ? <Link href={href}>{content}</Link> : content;
}

function AssistantHero() {
  return (
    <div className="hero-gradient-v2 p-6 relative overflow-hidden">
      <div className="relative z-10 space-y-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-white/15 flex items-center justify-center text-lg font-bold">AI</div>
          <div>
            <p className="font-semibold">OnHolland AI</p>
            <p className="text-xs text-white/70">Your accounting &amp; tax assistant</p>
          </div>
        </div>
        <p className="text-sm text-white/90 max-w-md">
          Ask about your profitability, cash position, tax obligations, or what-if scenarios -- answers are built
          only from your own company&apos;s real financial data, never fabricated.
        </p>
        <div className="flex items-center gap-2 flex-wrap">
          <Link href="/assistant" className="pill-v2 bg-white/15 hover:bg-white/25 px-3 py-1.5 text-xs transition-colors">
            Ask a question
          </Link>
          <Link href="/profit-and-loss" className="pill-v2 bg-white/15 hover:bg-white/25 px-3 py-1.5 text-xs transition-colors">
            Explain my finances
          </Link>
          <Link href="/tax-centre" className="pill-v2 bg-white/15 hover:bg-white/25 px-3 py-1.5 text-xs transition-colors">
            Review my taxes
          </Link>
          <Link href="/tax-optimization" className="pill-v2 bg-white/15 hover:bg-white/25 px-3 py-1.5 text-xs transition-colors">
            Find tax-saving opportunities
          </Link>
        </div>
      </div>
      <div className="absolute -right-10 -bottom-16 w-56 h-56 rounded-full bg-accent-cyan-400/20 blur-2xl" aria-hidden />
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
  if (!summary) return <p className="text-text-secondary">Loading…</p>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-text-primary">Dashboard</h1>
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
      </div>

      <AssistantHero />

      <div className="grid grid-cols-4 gap-4">
        <StatCard label="Managed companies" value={summary.company_count} href="/companies" />
        <StatCard
          label="Companies requiring attention"
          value={summary.companies_requiring_attention.length}
          tone={summary.companies_requiring_attention.length ? "warning" : "success"}
          href="/financial-overview"
        />
        <StatCard label="VAT returns awaiting review" value={summary.vat_returns_awaiting_review} tone="warning" href="/vat" />
        <StatCard label="VAT returns approved" value={summary.vat_returns_approved} tone="success" href="/vat" />
        <StatCard label="Overdue VAT returns" value={summary.overdue_vat_returns} tone={summary.overdue_vat_returns ? "error" : "success"} href="/calendar" />
        <StatCard label="Documents awaiting approval" value={summary.documents_awaiting_approval} tone="warning" href="/documents" />
        <StatCard label="Unmatched / overdue payments" value={summary.unmatched_payments} tone={summary.unmatched_payments ? "error" : "success"} href="/working-capital" />
        <StatCard label="Outstanding customer info" value={summary.outstanding_customer_info} tone="warning" href="/documents" />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="card-v2 p-4">
          <p className="text-xs text-text-secondary">Estimated VAT payable (open periods)</p>
          <p className="text-2xl font-semibold text-semantic-error mt-1">€ {summary.estimated_vat_payable}</p>
        </div>
        <div className="card-v2 p-4">
          <p className="text-xs text-text-secondary">Estimated VAT refundable (open periods)</p>
          <p className="text-2xl font-semibold text-semantic-success mt-1">€ {summary.estimated_vat_refundable}</p>
        </div>
      </div>

      {summary.companies_requiring_attention.length > 0 && (
        <div className="card-v2">
          <div className="px-5 py-3 border-b border-border-subtle">
            <h2 className="font-medium text-text-primary">Companies requiring attention</h2>
          </div>
          <div className="divide-y divide-border-subtle">
            {summary.companies_requiring_attention.map((c) => (
              <Link key={c.company_id} href={`/companies/${c.company_id}/workspace`} className="block px-5 py-3 hover:bg-surface-page">
                <p className="font-medium text-text-primary">{c.company_name}</p>
                <p className="text-sm text-semantic-warning">{c.reasons.join(" · ")}</p>
              </Link>
            ))}
          </div>
        </div>
      )}

      <div className="card-v2">
        <div className="px-5 py-4 border-b border-border-subtle">
          <h2 className="font-medium text-text-primary">Upcoming filing deadlines</h2>
        </div>
        {summary.upcoming_deadlines.length === 0 ? (
          <p className="px-5 py-4 text-sm text-text-secondary">No open VAT periods.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-text-secondary border-b border-border-subtle">
                <th className="px-5 py-2 font-medium">Company</th>
                <th className="px-5 py-2 font-medium">Period</th>
                <th className="px-5 py-2 font-medium">Filing deadline</th>
                <th className="px-5 py-2 font-medium">Payment deadline</th>
                <th className="px-5 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {summary.upcoming_deadlines.map((d, i) => (
                <tr key={i} className="border-b border-border-subtle last:border-0">
                  <td className="px-5 py-2.5">
                    <Link href={`/companies/${d.company_id}/workspace`} className="text-brand-purple-600 hover:underline">
                      {d.company_name}
                    </Link>
                  </td>
                  <td className="px-5 py-2.5">{d.period_label}</td>
                  <td className="px-5 py-2.5">{d.filing_deadline}</td>
                  <td className="px-5 py-2.5">{d.payment_deadline}</td>
                  <td className="px-5 py-2.5">
                    {d.is_overdue ? (
                      <span className="text-semantic-error font-medium">Overdue</span>
                    ) : (
                      <span className="text-semantic-warning">Upcoming</span>
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
