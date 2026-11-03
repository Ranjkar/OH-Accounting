"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, AutomationCentreSummary, Company } from "@/lib/api";

function Tile({ label, value, href, tone }: { label: string; value: number; href: string; tone?: "warn" | "crit" }) {
  const toneClass = tone === "crit" ? "text-error" : tone === "warn" ? "text-amber-600" : "text-navy";
  return (
    <Link href={href} className="card-v2 p-4 hover:border-navy transition-colors">
      <p className="text-xs text-text-secondary">{label}</p>
      <p className={`text-3xl font-semibold ${toneClass}`}>{value}</p>
    </Link>
  );
}

function AutomationContent() {
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [summary, setSummary] = useState<AutomationCentreSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  function refresh() {
    if (!token || !companyId) return;
    api.automationCentreSummary(token, Number(companyId)).then(setSummary).catch((e) => setError(e.message));
  }

  useEffect(refresh, [token, companyId]);

  async function run(action: () => Promise<string>) {
    setError(null);
    setMessage(null);
    try {
      setMessage(await action());
      refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-navy">Automation Centre</h1>
      <p className="text-sm text-text-secondary">
        Everything here is advisory. Suggestions, detections, and anomalies always wait for an accountant to review,
        approve, or correct them -- nothing is posted, paid, or filed automatically.
      </p>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}
      {message && <div className="rounded-md bg-green-50 text-green-700 text-sm px-3 py-2">{message}</div>}

      <select
        value={companyId}
        aria-label="Company"
        onChange={(e) => {
          setCompanyId(e.target.value ? Number(e.target.value) : "");
          if (!e.target.value) setSummary(null);
        }}
        className="input-v2 px-3 py-2 text-sm"
      >
        <option value="">Select a company</option>
        {companies.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </select>

      {summary && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <Tile label="Unmatched transactions" value={summary.unmatched_transactions} href="/bank-transactions" tone="warn" />
            <Tile label="Suggested matches" value={summary.suggested_matches} href="/reconciliation" />
            <Tile label="High-confidence suggested" value={summary.high_confidence_suggested_matches} href="/reconciliation" />
            <Tile label="Awaiting categorization" value={summary.expenses_awaiting_categorization} href="/categories" />
            <Tile label="Open anomalies" value={summary.open_anomalies} href="/anomalies" tone="crit" />
            <Tile label="Recurring missing" value={summary.recurring_missing} href="/cash-flow" tone="warn" />
            <Tile label="Failed import batches" value={summary.failed_import_batches} href="/banking" tone="crit" />
            <Tile label="Pending notes" value={summary.pending_notes} href="/companies" />
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() =>
                run(async () => {
                  const patterns = await api.detectRecurring(token!, Number(companyId));
                  return `Recurring-pattern detection re-run -- ${patterns.length} pattern(s) found.`;
                })
              }
              className="input-v2 px-4 py-2 text-sm"
            >
              Run recurring-pattern detection
            </button>
            <button
              onClick={() =>
                run(async () => {
                  const flags = await api.detectAnomalies(token!, Number(companyId));
                  return `Anomaly detection re-run -- ${flags.length} flag(s) found.`;
                })
              }
              className="input-v2 px-4 py-2 text-sm"
            >
              Run anomaly detection
            </button>
            <button
              onClick={() =>
                run(async () => {
                  const result = await api.applyCategorizationRules(token!, Number(companyId));
                  return `Applied rules to ${result.rules_applied} of ${result.transactions_checked} transaction(s).`;
                })
              }
              className="input-v2 px-4 py-2 text-sm"
            >
              Apply categorization rules
            </button>
          </div>
        </>
      )}
    </div>
  );
}

export default function AutomationPage() {
  return (
    <AuthGuard>
      <Shell>
        <AutomationContent />
      </Shell>
    </AuthGuard>
  );
}
