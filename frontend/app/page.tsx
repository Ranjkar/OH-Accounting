"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import GlassCard from "@/components/glass/GlassCard";
import GlassPanel from "@/components/glass/GlassPanel";
import GlassStatCard from "@/components/glass/GlassStatCard";
import GlassChartCard from "@/components/glass/GlassChartCard";
import GlassButton from "@/components/glass/GlassButton";
import { GlassInput, GlassSelect } from "@/components/glass/GlassInput";
import GlassEmptyState from "@/components/glass/GlassEmptyState";
import GlassLoadingState, { GlassErrorState } from "@/components/glass/GlassLoadingState";
import { IconSparkle, IconBank, IconCalculator, IconChart } from "@/components/glass/icons";
import { useAuth } from "@/lib/auth-context";
import { api, AssistantResponse, BankAccount, CashFlowForecast, Company, DashboardSummary, JsonReport } from "@/lib/api";

function AssistantCard({ companyId }: { companyId: number | "" }) {
  const { token } = useAuth();
  const [question, setQuestion] = useState("");
  const [response, setResponse] = useState<AssistantResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function ask(e: FormEvent) {
    e.preventDefault();
    if (!token || !companyId || !question.trim()) return;
    setLoading(true);
    setError(null);
    try {
      setResponse(await api.askAssistant(token, { company_id: Number(companyId), question }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "The assistant could not answer that");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="glass-hero p-6 sm:p-7 h-full flex flex-col">
      <div className="relative z-10 flex flex-col flex-1">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 rounded-xl bg-white/15 flex items-center justify-center flex-shrink-0">
            <IconSparkle size={20} />
          </div>
          <div>
            <p className="font-semibold">OnHolland AI</p>
            <p className="text-xs text-white/70">Your accounting &amp; tax assistant · live, not scripted</p>
          </div>
        </div>
        <p className="text-sm text-white/90 max-w-md mb-4">
          Ask about profitability, cash position, tax obligations, or what-if scenarios. Answers are built only from
          this company&apos;s real financial data, never fabricated.
        </p>

        {!companyId ? (
          <p className="text-sm text-white/70 mt-auto">Select a company above to ask the assistant a question.</p>
        ) : (
          <>
            <form onSubmit={ask} className="flex items-center gap-2 mb-3">
              <input
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="e.g. How is my cash position this quarter?"
                className="flex-1 rounded-lg bg-white/10 border border-white/20 px-3 py-2 text-sm text-white placeholder:text-white/50 focus:outline-none focus:border-white/50"
              />
              <GlassButton type="submit" disabled={loading || !question.trim()} variant="secondary" size="sm" className="!bg-white/15 !text-white !border-white/25 flex-shrink-0">
                {loading ? "Asking…" : "Ask"}
              </GlassButton>
            </form>

            {error && <div className="rounded-lg bg-red-500/20 border border-red-300/30 text-white text-xs px-3 py-2 mb-2">{error}</div>}

            {response && (
              <div className="rounded-lg bg-white/10 border border-white/15 p-3 text-sm text-white/95 mb-2 max-h-40 overflow-y-auto glass-scroll">
                {response.answer}
              </div>
            )}

            <div className="flex items-center gap-2 flex-wrap mt-auto pt-2">
              <Link href="/assistant" className="pill-v2 bg-white/15 hover:bg-white/25 px-3 py-1.5 text-xs transition-colors">
                Open full assistant
              </Link>
              <Link href="/tax-centre" className="pill-v2 bg-white/15 hover:bg-white/25 px-3 py-1.5 text-xs transition-colors">
                Review my taxes
              </Link>
              <Link href="/tax-optimization" className="pill-v2 bg-white/15 hover:bg-white/25 px-3 py-1.5 text-xs transition-colors">
                Find tax-saving opportunities
              </Link>
            </div>
          </>
        )}
      </div>
      <div className="absolute -right-10 -bottom-16 w-56 h-56 rounded-full bg-accent-cyan-400/20 blur-2xl pointer-events-none" aria-hidden />
    </div>
  );
}

function BankAccountsCard({ companyId }: { companyId: number | "" }) {
  const { token } = useAuth();
  const [accounts, setAccounts] = useState<BankAccount[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token || !companyId) {
      // Clearing stale data for a different/no-longer-selected company --
      // syncing to the companyId prop change, not derivable during render.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setAccounts(null);
      return;
    }
    api.listBankAccounts(token, Number(companyId)).then(setAccounts).catch((e) => setError(e.message));
  }, [token, companyId]);

  return (
    <GlassPanel title="Bank Accounts" subtitle="Connected accounts for this company" actions={<Link href="/banking" className="text-xs text-brand-purple-600 hover:underline">Manage</Link>}>
      <div className="p-4 sm:p-5">
        {!companyId ? (
          <p className="text-sm text-text-secondary">Select a company to see its bank accounts.</p>
        ) : error ? (
          <GlassErrorState message={error} />
        ) : accounts === null ? (
          <GlassLoadingState rows={2} />
        ) : accounts.length === 0 ? (
          <GlassEmptyState title="No bank accounts yet" description="Add one from the Banking page to start importing statements." icon={<IconBank size={28} />} />
        ) : (
          <ul className="space-y-2">
            {accounts.map((a) => (
              <li key={a.id} className="flex items-center justify-between gap-2 rounded-lg bg-white/40 px-3 py-2.5">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-text-primary truncate">{a.account_name}</p>
                  <p className="text-xs text-text-secondary font-mono truncate">{a.iban}</p>
                </div>
                <span className="text-[10px] uppercase tracking-wide bg-white/60 rounded-full px-2 py-1 text-text-secondary flex-shrink-0">
                  {a.consent_status.replace(/_/g, " ")}
                </span>
              </li>
            ))}
          </ul>
        )}
        <p className="text-[11px] text-text-secondary mt-3">
          Balance tracking requires a connected bank feed and is not available for file-import-only accounts.
        </p>
      </div>
    </GlassPanel>
  );
}

function TaxCalculatorCard({ companyId }: { companyId: number | "" }) {
  const { token } = useAuth();
  const [annualProfit, setAnnualProfit] = useState("50000");
  const [hoursCriterionMet, setHoursCriterionMet] = useState(true);
  const [isStarter, setIsStarter] = useState(false);
  const [result, setResult] = useState<JsonReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function calculate(e: FormEvent) {
    e.preventDefault();
    if (!token || !companyId) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await api.incomeTaxEstimate(token, Number(companyId), annualProfit, hoursCriterionMet, isStarter));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not calculate");
    } finally {
      setLoading(false);
    }
  }

  return (
    <GlassCard padding="lg" className="h-full flex flex-col">
      <div className="flex items-center gap-2 mb-3">
        <IconCalculator size={18} className="text-brand-purple-500" />
        <h3 className="font-semibold text-text-primary">Tax Calculator</h3>
      </div>
      {!companyId ? (
        <p className="text-sm text-text-secondary">Select a company to run a real income-tax estimate.</p>
      ) : (
        <form onSubmit={calculate} className="space-y-3 flex-1 flex flex-col">
          <div>
            <label htmlFor="dash-annual-profit" className="text-label-v2">Annual profit (EUR)</label>
            <GlassInput id="dash-annual-profit" type="number" min="0" step="1" value={annualProfit} onChange={(e) => setAnnualProfit(e.target.value)} className="mt-1" />
          </div>
          <label className="flex items-center gap-2 text-sm text-text-primary">
            <input type="checkbox" checked={hoursCriterionMet} onChange={(e) => setHoursCriterionMet(e.target.checked)} />
            Urencriterium (1,225 hrs) met
          </label>
          <label className="flex items-center gap-2 text-sm text-text-primary">
            <input type="checkbox" checked={isStarter} onChange={(e) => setIsStarter(e.target.checked)} />
            Starter (startersaftrek)
          </label>
          <GlassButton type="submit" disabled={loading} size="sm">
            {loading ? "Calculating…" : "Calculate"}
          </GlassButton>

          {error && <GlassErrorState message={error} />}
          {result && (
            <div className="mt-2 rounded-lg bg-white/50 p-3 text-sm space-y-1">
              <p className="flex justify-between"><span className="text-text-secondary">Entrepreneur deduction</span><span className="font-mono">€{String(result.entrepreneur_deduction_applied)}</span></p>
              <p className="flex justify-between"><span className="text-text-secondary">MKB-winstvrijstelling</span><span className="font-mono">€{String(result.mkb_winstvrijstelling_applied)}</span></p>
              <p className="flex justify-between"><span className="text-text-secondary">Taxable profit</span><span className="font-mono">€{String(result.taxable_profit)}</span></p>
              <p className="flex justify-between font-medium"><span>Net income tax</span><span className="font-mono value-negative">€{String(result.net_income_tax)}</span></p>
              <p className="text-[11px] text-text-secondary pt-1">{String(result.note)}</p>
            </div>
          )}
        </form>
      )}
    </GlassCard>
  );
}

function DashboardContent() {
  const { token, user } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [forecast, setForecast] = useState<CashFlowForecast | null>(null);
  const [pnl, setPnl] = useState<JsonReport | null>(null);
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

  useEffect(() => {
    if (!token || !companyId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setForecast(null);
      setPnl(null);
      return;
    }
    api.cashFlowForecast(token, Number(companyId)).then(setForecast).catch(() => setForecast(null));
    api
      .profitAndLoss(token, { company_id: Number(companyId), period_type: "ANNUAL" })
      .then((r) => setPnl(r.current as JsonReport))
      .catch(() => setPnl(null));
  }, [token, companyId]);

  if (error) return <GlassErrorState message={error} />;
  if (!summary) return <GlassLoadingState rows={4} />;

  const chartPoints = (forecast?.monthly_projection ?? []).map((m) => ({ label: m.month, value: Number(m.net) }));

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary">Dashboard</h1>
          <p className="text-sm text-text-secondary mt-1">
            {user ? `Welcome back, ${user.full_name.split(" ")[0]}.` : "Welcome back."}
          </p>
        </div>
        <GlassSelect value={companyId} onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")}>
          <option value="">All companies</option>
          {companies.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </GlassSelect>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          <AssistantCard companyId={companyId} />
        </div>
        <BankAccountsCard companyId={companyId} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          <GlassChartCard
            title="Cash Flow"
            subtitle={forecast ? `Monthly net projection, as of ${forecast.as_of}` : "Select a company to see its cash flow projection"}
            points={chartPoints}
            formatValue={(v) => `€${v.toLocaleString("nl-NL", { maximumFractionDigits: 0 })}`}
            actions={<Link href="/cash-flow" className="text-xs text-brand-purple-600 hover:underline flex-shrink-0">Full forecast &amp; statement →</Link>}
          />
        </div>
        <TaxCalculatorCard companyId={companyId} />
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <GlassStatCard label="Total Income (YTD)" value={pnl ? `€${pnl.revenue}` : "—"} tone="success" icon={<IconChart size={16} />} />
        <GlassStatCard
          label="Total Expenses (YTD)"
          value={pnl ? `€${(Number(pnl.revenue) - Number(pnl.net_profit)).toFixed(2)}` : "—"}
          tone="error"
          icon={<IconChart size={16} />}
        />
        <GlassStatCard label="Net Profit (YTD)" value={pnl ? `€${pnl.net_profit}` : "—"} tone={pnl && Number(pnl.net_profit) >= 0 ? "success" : "error"} />
        <GlassStatCard
          label="Est. VAT payable (open)"
          value={`€${summary.estimated_vat_payable}`}
          tone="warning"
          href="/vat"
        />
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <GlassStatCard label="Managed companies" value={summary.company_count} href="/companies" />
        <GlassStatCard
          label="Needs attention"
          value={summary.companies_requiring_attention.length}
          tone={summary.companies_requiring_attention.length ? "warning" : "success"}
          href="/financial-overview"
        />
        <GlassStatCard label="VAT awaiting review" value={summary.vat_returns_awaiting_review} tone="warning" href="/vat" />
        <GlassStatCard label="Overdue VAT returns" value={summary.overdue_vat_returns} tone={summary.overdue_vat_returns ? "error" : "success"} href="/calendar" />
      </div>

      {summary.companies_requiring_attention.length > 0 && (
        <GlassPanel title="Companies requiring attention">
          <div className="divide-y divide-white/40">
            {summary.companies_requiring_attention.map((c) => (
              <Link key={c.company_id} href={`/companies/${c.company_id}/workspace`} className="block px-5 py-3 hover:bg-white/40">
                <p className="font-medium text-text-primary">{c.company_name}</p>
                <p className="text-sm value-warning">{c.reasons.join(" · ")}</p>
              </Link>
            ))}
          </div>
        </GlassPanel>
      )}

      <GlassPanel title="Upcoming filing deadlines">
        {summary.upcoming_deadlines.length === 0 ? (
          <p className="px-5 py-4 text-sm text-text-secondary">No open VAT periods.</p>
        ) : (
          <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-text-secondary border-b border-white/40">
                <th className="px-5 py-2 font-medium">Company</th>
                <th className="px-5 py-2 font-medium">Period</th>
                <th className="px-5 py-2 font-medium">Filing deadline</th>
                <th className="px-5 py-2 font-medium">Payment deadline</th>
                <th className="px-5 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {summary.upcoming_deadlines.map((d, i) => (
                <tr key={i} className="border-b border-white/30 last:border-0">
                  <td className="px-5 py-2.5">
                    <Link href={`/companies/${d.company_id}/workspace`} className="text-brand-purple-600 hover:underline">
                      {d.company_name}
                    </Link>
                  </td>
                  <td className="px-5 py-2.5">{d.period_label}</td>
                  <td className="px-5 py-2.5">{d.filing_deadline}</td>
                  <td className="px-5 py-2.5">{d.payment_deadline}</td>
                  <td className="px-5 py-2.5">
                    {d.is_overdue ? <span className="value-negative font-medium">Overdue</span> : <span className="value-warning">Upcoming</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </GlassPanel>
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
