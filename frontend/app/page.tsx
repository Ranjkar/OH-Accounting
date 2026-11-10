"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
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
import { IconSparkle, IconBank, IconCalculator, IconChart, IconChevronRight } from "@/components/glass/icons";
import { useAuth } from "@/lib/auth-context";
import { api, AssistantResponse, BankAccount, CashFlowForecast, Company, DashboardSummary, JsonReport } from "@/lib/api";
import { formatEUR } from "@/lib/format";

function AssistantCard({ companyId }: { companyId: number | "" }) {
  const { token } = useAuth();
  const t = useTranslations("dashboard");
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
      setError(err instanceof Error ? err.message : t("assistantCouldNotAnswer"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="glass-hero p-6 sm:p-7 h-full flex flex-col">
      <div className="flex flex-col flex-1">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 rounded-xl bg-surface-card flex items-center justify-center flex-shrink-0 text-navy">
            <IconSparkle size={20} />
          </div>
          <div>
            <p className="font-semibold text-text-primary">{t("aiCardTitle")}</p>
            <p className="text-xs text-text-secondary">{t("aiCardSubtitle")}</p>
          </div>
        </div>
        <p className="text-sm text-text-secondary max-w-md mb-4">{t("aiCardBody")}</p>

        {!companyId ? (
          <p className="text-sm text-text-secondary mt-auto">{t("aiCardSelectPrompt")}</p>
        ) : (
          <>
            <form onSubmit={ask} className="flex items-center gap-2 mb-3">
              <input
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder={t("aiAskPlaceholder")}
                className="flex-1 rounded-lg bg-surface-card border border-border px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-navy"
              />
              <GlassButton type="submit" disabled={loading || !question.trim()} variant="secondary" size="sm" className="flex-shrink-0">
                {loading ? t("askingLabel") : t("ask")}
              </GlassButton>
            </form>

            {error && <div className="rounded-lg bg-red-500/10 border border-red-300/50 text-red-700 text-xs px-3 py-2 mb-2">{error}</div>}

            {response && (
              <div className="rounded-lg bg-surface-card border border-border p-3 text-sm text-text-primary mb-2 max-h-40 overflow-y-auto glass-scroll">
                {response.answer}
              </div>
            )}

            <div className="flex items-center gap-2 flex-wrap mt-auto pt-2">
              <Link href="/assistant" className="pill-v2 bg-surface-card border border-border hover:bg-muted px-3 py-1.5 text-xs text-text-primary transition-colors">
                {t("openFullAssistant")}
              </Link>
              <Link href="/tax-centre" className="pill-v2 bg-surface-card border border-border hover:bg-muted px-3 py-1.5 text-xs text-text-primary transition-colors">
                {t("reviewMyTaxes")}
              </Link>
              <Link href="/tax-optimization" className="pill-v2 bg-surface-card border border-border hover:bg-muted px-3 py-1.5 text-xs text-text-primary transition-colors">
                {t("findTaxSavingOpportunities")}
              </Link>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function BankAccountsCard({ companyId }: { companyId: number | "" }) {
  const { token } = useAuth();
  const t = useTranslations("dashboard");
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
    <GlassPanel title={t("bankAccountsTitle")} subtitle={t("bankAccountsSubtitle")} actions={<Link href="/banking" className="text-xs text-brand-purple-600 hover:underline">{t("manage")}</Link>}>
      <div className="p-4 sm:p-5">
        {!companyId ? (
          <p className="text-sm text-text-secondary">{t("selectCompanyBankAccounts")}</p>
        ) : error ? (
          <GlassErrorState message={error} />
        ) : accounts === null ? (
          <GlassLoadingState rows={2} />
        ) : accounts.length === 0 ? (
          <GlassEmptyState title={t("noBankAccountsYet")} description={t("addOneFromBanking")} icon={<IconBank size={28} />} />
        ) : (
          <ul className="space-y-2">
            {accounts.map((a) => (
              <li key={a.id} className="flex items-center justify-between gap-2 rounded-lg bg-muted px-3 py-2.5">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-text-primary truncate">{a.account_name}</p>
                  <p className="text-xs text-text-secondary font-mono truncate" dir="ltr">{a.iban}</p>
                </div>
                <span className="text-[10px] uppercase tracking-wide bg-muted rounded-full px-2 py-1 text-text-secondary flex-shrink-0">
                  {a.consent_status.replace(/_/g, " ")}
                </span>
              </li>
            ))}
          </ul>
        )}
        <p className="text-[11px] text-text-secondary mt-3">{t("balanceTrackingNote")}</p>
      </div>
    </GlassPanel>
  );
}

function TaxCalculatorCard({ companyId }: { companyId: number | "" }) {
  const { token } = useAuth();
  const t = useTranslations("dashboard");
  const locale = useLocale();
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
      setError(err instanceof Error ? err.message : t("couldNotCalculate"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <GlassCard padding="lg" className="h-full flex flex-col">
      <div className="flex items-center gap-2 mb-3">
        <IconCalculator size={18} className="text-brand-purple-500" />
        <h3 className="font-semibold text-text-primary">{t("taxCalculatorTitle")}</h3>
      </div>
      {!companyId ? (
        <p className="text-sm text-text-secondary">{t("selectCompanyTaxEstimate")}</p>
      ) : (
        <form onSubmit={calculate} className="space-y-3 flex-1 flex flex-col">
          <div>
            <label htmlFor="dash-annual-profit" className="text-label-v2">{t("annualProfitLabel")}</label>
            <GlassInput id="dash-annual-profit" type="number" min="0" step="1" value={annualProfit} onChange={(e) => setAnnualProfit(e.target.value)} className="mt-1" />
          </div>
          <label className="flex items-center gap-2 text-sm text-text-primary">
            <input type="checkbox" checked={hoursCriterionMet} onChange={(e) => setHoursCriterionMet(e.target.checked)} />
            {t("urencriterium")}
          </label>
          <label className="flex items-center gap-2 text-sm text-text-primary">
            <input type="checkbox" checked={isStarter} onChange={(e) => setIsStarter(e.target.checked)} />
            {t("starter")}
          </label>
          <GlassButton type="submit" disabled={loading} size="sm">
            {loading ? t("calculating") : t("calculate")}
          </GlassButton>

          {error && <GlassErrorState message={error} />}
          {result && (
            <div className="mt-2 rounded-lg bg-muted p-3 text-sm space-y-1">
              <p className="flex justify-between"><span className="text-text-secondary">{t("entrepreneurDeduction")}</span><span className="font-mono">{formatEUR(String(result.entrepreneur_deduction_applied), locale)}</span></p>
              <p className="flex justify-between"><span className="text-text-secondary">{t("mkbWinstvrijstelling")}</span><span className="font-mono">{formatEUR(String(result.mkb_winstvrijstelling_applied), locale)}</span></p>
              <p className="flex justify-between"><span className="text-text-secondary">{t("taxableProfit")}</span><span className="font-mono">{formatEUR(String(result.taxable_profit), locale)}</span></p>
              <p className="flex justify-between font-medium"><span>{t("netIncomeTax")}</span><span className="font-mono value-negative">{formatEUR(String(result.net_income_tax), locale)}</span></p>
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
  const t = useTranslations("dashboard");
  const tCommon = useTranslations("common");
  const tVat = useTranslations("vat");
  const locale = useLocale();
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
          <h1 className="text-2xl font-semibold text-text-primary">{t("title")}</h1>
          <p className="text-sm text-text-secondary mt-1">
            {t("welcome", { name: user ? user.full_name.split(" ")[0] : "" })}
          </p>
        </div>
        <GlassSelect aria-label={tCommon("company")} value={companyId} onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")}>
          <option value="">{tCommon("allCompanies")}</option>
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
            title={t("cashFlowTitle")}
            subtitle={forecast ? t("cashFlowSubtitle", { date: forecast.as_of }) : t("aiCardSelectPrompt")}
            points={chartPoints}
            formatValue={(v) => formatEUR(v, locale)}
            actions={
              <Link href="/cash-flow" className="text-xs text-brand-purple-600 hover:underline flex-shrink-0 inline-flex items-center gap-0.5">
                {t("fullForecastStatement")} <IconChevronRight size={12} className="icon-directional" />
              </Link>
            }
          />
        </div>
        <TaxCalculatorCard companyId={companyId} />
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <GlassStatCard label={t("totalIncomeYtd")} value={pnl ? formatEUR(pnl.revenue, locale) : "—"} tone="success" icon={<IconChart size={16} />} />
        <GlassStatCard
          label={t("totalExpensesYtd")}
          value={pnl ? formatEUR((Number(pnl.revenue) - Number(pnl.net_profit)).toFixed(2), locale) : "—"}
          tone="error"
          icon={<IconChart size={16} />}
        />
        <GlassStatCard label={t("netProfitYtd")} value={pnl ? formatEUR(pnl.net_profit, locale) : "—"} tone={pnl && Number(pnl.net_profit) >= 0 ? "success" : "error"} />
        <GlassStatCard
          label={t("estVatPayableOpen")}
          value={formatEUR(summary.estimated_vat_payable, locale)}
          tone="warning"
          href="/vat"
        />
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <GlassStatCard label={t("managedCompanies")} value={summary.company_count} href="/companies" />
        <GlassStatCard
          label={t("needsAttention")}
          value={summary.companies_requiring_attention.length}
          tone={summary.companies_requiring_attention.length ? "warning" : "success"}
          href="/financial-overview"
        />
        <GlassStatCard label={t("vatAwaitingReview")} value={summary.vat_returns_awaiting_review} tone="warning" href="/vat" />
        <GlassStatCard label={t("overdueVatReturns")} value={summary.overdue_vat_returns} tone={summary.overdue_vat_returns ? "error" : "success"} href="/calendar" />
      </div>

      {summary.companies_requiring_attention.length > 0 && (
        <GlassPanel title={t("companiesRequiringAttention")}>
          <div className="divide-y divide-white/40">
            {summary.companies_requiring_attention.map((c) => (
              <Link key={c.company_id} href={`/companies/${c.company_id}/workspace`} className="block px-5 py-3 hover:bg-muted">
                <p className="font-medium text-text-primary">{c.company_name}</p>
                <p className="text-sm value-warning">{c.reasons.join(" · ")}</p>
              </Link>
            ))}
          </div>
        </GlassPanel>
      )}

      <GlassPanel title={t("upcomingFilingDeadlines")}>
        {summary.upcoming_deadlines.length === 0 ? (
          <p className="px-5 py-4 text-sm text-text-secondary">{t("noOpenVatPeriods")}</p>
        ) : (
          <div className="overflow-x-auto">
          <table className="table-v3">
            <thead>
              <tr>
                <th>{tCommon("company")}</th>
                <th>{tVat("period")}</th>
                <th>{tVat("filingDeadline")}</th>
                <th>{t("paymentDeadlineHeader")}</th>
                <th>{tCommon("status")}</th>
              </tr>
            </thead>
            <tbody>
              {summary.upcoming_deadlines.map((d, i) => (
                <tr key={i}>
                  <td>
                    <Link href={`/companies/${d.company_id}/workspace`} className="text-navy hover:underline">
                      {d.company_name}
                    </Link>
                  </td>
                  <td className="text-text-secondary">{d.period_label}</td>
                  <td className="text-text-secondary">{d.filing_deadline}</td>
                  <td className="text-text-secondary">{d.payment_deadline}</td>
                  <td>
                    <span className={`status-pill ${d.is_overdue ? "status-pill-danger" : "status-pill-warning"}`}>
                      {d.is_overdue ? t("overdueLabel") : t("upcomingLabel")}
                    </span>
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
