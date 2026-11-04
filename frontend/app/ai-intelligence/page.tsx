"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import GlassPageHeader from "@/components/glass/GlassPageHeader";
import GlassPanel from "@/components/glass/GlassPanel";
import GlassCard from "@/components/glass/GlassCard";
import GlassButton from "@/components/glass/GlassButton";
import { GlassSelect } from "@/components/glass/GlassInput";
import GlassStatCard from "@/components/glass/GlassStatCard";
import GlassTable from "@/components/glass/GlassTable";
import GlassLoadingState, { GlassErrorState } from "@/components/glass/GlassLoadingState";
import { useAuth } from "@/lib/auth-context";
import { useCompany } from "@/lib/company-context";
import {
  api,
  AnomalyFlag,
  AssistantResponse,
  AutomationCentreSummary,
  CashFlowForecast,
  JsonReport,
  TaxCalendarEntry,
} from "@/lib/api";
import { formatEUR } from "@/lib/format";

function AiIntelligenceContent() {
  const { token } = useAuth();
  const { companies, selectedCompanyId, setSelectedCompanyId } = useCompany();
  const companyId = selectedCompanyId ?? "";
  const setCompanyId = (id: number | "") => setSelectedCompanyId(id === "" ? null : id);
  const [insights, setInsights] = useState<AssistantResponse | null>(null);
  const [anomalies, setAnomalies] = useState<AnomalyFlag[]>([]);
  const [automation, setAutomation] = useState<AutomationCentreSummary | null>(null);
  const [cashFlow, setCashFlow] = useState<CashFlowForecast | null>(null);
  const [forecast, setForecast] = useState<JsonReport | null>(null);
  const [taxCalendar, setTaxCalendar] = useState<TaxCalendarEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token || !companyId) return;
    // Clearing stale data and showing a loading state for a newly selected
    // company -- syncing to the companyId change, not derivable during render.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setError(null);
    setLoading(true);
    setInsights(null);
    const id = Number(companyId);
    Promise.all([
      api.assistantCompanySummary(token, id).then(setInsights),
      api.listAnomalies(token, id, "OPEN").then(setAnomalies),
      api.automationCentreSummary(token, id).then(setAutomation),
      api.cashFlowForecast(token, id).then(setCashFlow),
      api.fullForecast(token, id).then(setForecast),
      api.getTaxCalendar(token, { company_id: id }).then(setTaxCalendar),
    ])
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [token, companyId]);

  const upcomingDeadlines = taxCalendar
    .filter((t) => new Date(t.filing_deadline) >= new Date())
    .sort((a, b) => a.filing_deadline.localeCompare(b.filing_deadline))
    .slice(0, 4);

  return (
    <div className="space-y-5">
      <GlassPageHeader
        title="AI Accounting Intelligence"
        subtitle="Every figure below comes from the real accounting engine (ledger, VAT, forecast, anomaly-detection, automation services) -- AI only narrates and explains, it never invents a number or silently posts anything."
      />

      {error && <GlassErrorState message={error} />}

      <GlassSelect aria-label="Company" value={companyId} onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")}>
        <option value="">Select a company</option>
        {companies.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </GlassSelect>

      {!companyId && <p className="text-sm text-text-secondary">Select a company to see its financial health, AI insights, and pending reviews.</p>}

      {loading && <GlassLoadingState />}

      {companyId && !loading && (
        <>
          <GlassPanel title="AI insights">
            {insights ? (
              <div className="space-y-3">
                <p className="text-sm text-text-primary whitespace-pre-wrap">{insights.answer}</p>
                <p className="text-xs text-text-secondary rounded-md bg-amber-500/10 border border-amber-300/50 px-3 py-2">{insights.disclaimer}</p>
              </div>
            ) : (
              <p className="text-sm text-text-secondary">No insights available yet.</p>
            )}
          </GlassPanel>

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
            <GlassStatCard
              label="Open anomalies"
              value={anomalies.length}
              tone={anomalies.some((a) => a.severity === "critical") ? "error" : anomalies.length > 0 ? "warning" : "success"}
              href="/anomalies"
            />
            <GlassStatCard
              label="Awaiting categorization"
              value={automation?.expenses_awaiting_categorization ?? 0}
              tone={(automation?.expenses_awaiting_categorization ?? 0) > 0 ? "warning" : "success"}
              href="/automation"
            />
            <GlassStatCard
              label="Unmatched bank transactions"
              value={automation?.unmatched_transactions ?? 0}
              tone={(automation?.unmatched_transactions ?? 0) > 0 ? "warning" : "success"}
              href="/reconciliation"
            />
            <GlassStatCard
              label="Suggested matches"
              value={automation?.suggested_matches ?? 0}
              href="/reconciliation"
            />
            <GlassStatCard
              label="Failed import batches"
              value={automation?.failed_import_batches ?? 0}
              tone={(automation?.failed_import_batches ?? 0) > 0 ? "error" : "success"}
              href="/banking"
            />
            <GlassStatCard
              label="Pending accountant notes"
              value={automation?.pending_notes ?? 0}
              href="/companies"
            />
          </div>

          <GlassPanel title="Unusual transactions">
            <GlassTable
              emptyMessage="No open anomaly flags for this company."
              columns={[
                { key: "rule", header: "Rule", render: (a) => <span className="font-mono text-xs">{a.rule_code}</span> },
                {
                  key: "severity",
                  header: "Severity",
                  render: (a) => <span className={a.severity === "critical" ? "value-negative" : a.severity === "warning" ? "value-warning" : "text-text-secondary"}>{a.severity}</span>,
                },
                { key: "message", header: "Reason", render: (a) => <span className="text-xs">{a.message}</span> },
                { key: "when", header: "Flagged", render: (a) => <span className="text-xs text-text-secondary">{new Date(a.created_at).toLocaleDateString()}</span> },
              ]}
              rows={anomalies.slice(0, 8)}
              rowKey={(a) => a.id}
            />
            {anomalies.length > 0 && (
              <div className="mt-3">
                <Link href="/anomalies" className="text-xs text-brand-purple-600 hover:underline">
                  Review all anomalies →
                </Link>
              </div>
            )}
          </GlassPanel>

          <div className="grid gap-4 md:grid-cols-2">
            <GlassCard className="space-y-3">
              <h2 className="font-medium text-text-primary">Cash-flow prediction</h2>
              {cashFlow ? (
                <dl className="text-sm space-y-1.5">
                  <div className="flex justify-between"><dt className="text-text-secondary">Expected incoming</dt><dd className="font-mono">{formatEUR(cashFlow.expected_incoming_total)}</dd></div>
                  <div className="flex justify-between"><dt className="text-text-secondary">Expected outgoing</dt><dd className="font-mono">{formatEUR(cashFlow.expected_outgoing_total)}</dd></div>
                  <div className="flex justify-between"><dt className="text-text-secondary">Forecast VAT payable</dt><dd className="font-mono">{formatEUR(cashFlow.forecast_vat_payable)}</dd></div>
                  <p className="text-xs text-text-secondary pt-1">{cashFlow.forecast_vat_disclaimer}</p>
                </dl>
              ) : (
                <p className="text-sm text-text-secondary">No forecast available.</p>
              )}
              <Link href="/cash-flow" className="text-xs text-brand-purple-600 hover:underline">
                Full cash-flow forecast →
              </Link>
            </GlassCard>

            <GlassCard className="space-y-3">
              <h2 className="font-medium text-text-primary">Outstanding invoices</h2>
              {forecast?.outstanding_invoices ? (
                <dl className="text-sm space-y-1.5">
                  <div className="flex justify-between"><dt className="text-text-secondary">Receivables outstanding</dt><dd className="font-mono">{formatEUR(forecast.outstanding_invoices.confirmed_receivables_outstanding)}</dd></div>
                  <div className="flex justify-between"><dt className="text-text-secondary">Payables outstanding</dt><dd className="font-mono">{formatEUR(forecast.outstanding_invoices.confirmed_payables_outstanding)}</dd></div>
                  <p className="text-xs text-text-secondary pt-1">{forecast.outstanding_invoices.note}</p>
                </dl>
              ) : (
                <p className="text-sm text-text-secondary">No data available.</p>
              )}
              <Link href="/working-capital" className="text-xs text-brand-purple-600 hover:underline">
                Full working-capital view →
              </Link>
            </GlassCard>
          </div>

          <GlassPanel title="Tax preparation">
            {upcomingDeadlines.length === 0 ? (
              <p className="text-sm text-text-secondary">No upcoming VAT filing deadlines on file for this company.</p>
            ) : (
              <ul className="space-y-2 text-sm">
                {upcomingDeadlines.map((d) => (
                  <li key={d.vat_period_id} className="flex items-center justify-between gap-3 rounded-lg border border-border p-3">
                    <span>{d.period_label}</span>
                    <span className="text-xs text-text-secondary">Filing deadline {new Date(d.filing_deadline).toLocaleDateString()}</span>
                  </li>
                ))}
              </ul>
            )}
            {forecast?.vat_payments?.upcoming_vat_payments?.length > 0 && (
              <p className="text-xs text-text-secondary mt-3">{forecast?.vat_payments.disclaimer}</p>
            )}
            <Link href="/calendar" className="text-xs text-brand-purple-600 hover:underline mt-2 inline-block">
              Full compliance calendar →
            </Link>
          </GlassPanel>

          <div className="flex justify-end">
            <GlassButton
              variant="outline"
              onClick={() => companyId && token && api.assistantCompanySummary(token, Number(companyId)).then(setInsights)}
            >
              Refresh insights
            </GlassButton>
          </div>
        </>
      )}
    </div>
  );
}

export default function AiIntelligencePage() {
  return (
    <AuthGuard>
      <Shell>
        <AiIntelligenceContent />
      </Shell>
    </AuthGuard>
  );
}
