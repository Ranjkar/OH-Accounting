"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, AutomationCentreSummary, Company } from "@/lib/api";

function Tile({ label, value, href, tone }: { label: string; value: number; href: string; tone?: "warn" | "crit" }) {
  const toneClass = tone === "crit" ? "text-error" : tone === "warn" ? "text-pending" : "text-navy";
  return (
    <Link href={href} className="card-v2 p-4 hover:border-navy transition-colors">
      <p className="text-xs text-text-secondary">{label}</p>
      <p className={`text-3xl font-semibold ${toneClass}`}>{value}</p>
    </Link>
  );
}

function AutomationContent() {
  const t = useTranslations("automation");
  const tCommon = useTranslations("common");
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
      <h1 className="text-2xl font-semibold text-text-primary">{t("title")}</h1>
      <p className="text-sm text-text-secondary">{t("advisoryNotice")}</p>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}
      {message && <div className="rounded-md bg-green-50 text-green-700 text-sm px-3 py-2">{message}</div>}

      <select
        value={companyId}
        aria-label={tCommon("company")}
        onChange={(e) => {
          setCompanyId(e.target.value ? Number(e.target.value) : "");
          if (!e.target.value) setSummary(null);
        }}
        className="input-v2 px-3 py-2 text-sm"
      >
        <option value="">{tCommon("selectCompany")}</option>
        {companies.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </select>

      {summary && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <Tile label={t("unmatchedTransactions")} value={summary.unmatched_transactions} href="/bank-transactions" tone="warn" />
            <Tile label={t("suggestedMatches")} value={summary.suggested_matches} href="/reconciliation" />
            <Tile label={t("highConfidenceSuggested")} value={summary.high_confidence_suggested_matches} href="/reconciliation" />
            <Tile label={t("awaitingCategorization")} value={summary.expenses_awaiting_categorization} href="/categories" />
            <Tile label={t("openAnomalies")} value={summary.open_anomalies} href="/anomalies" tone="crit" />
            <Tile label={t("recurringMissing")} value={summary.recurring_missing} href="/cash-flow" tone="warn" />
            <Tile label={t("failedImportBatches")} value={summary.failed_import_batches} href="/banking" tone="crit" />
            <Tile label={t("pendingNotes")} value={summary.pending_notes} href="/companies" />
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() =>
                run(async () => {
                  const patterns = await api.detectRecurring(token!, Number(companyId));
                  return t("recurringDetectionResult", { count: patterns.length });
                })
              }
              className="input-v2 px-4 py-2 text-sm"
            >
              {t("runRecurringDetection")}
            </button>
            <button
              onClick={() =>
                run(async () => {
                  const flags = await api.detectAnomalies(token!, Number(companyId));
                  return t("anomalyDetectionResult", { count: flags.length });
                })
              }
              className="input-v2 px-4 py-2 text-sm"
            >
              {t("runAnomalyDetection")}
            </button>
            <button
              onClick={() =>
                run(async () => {
                  const result = await api.applyCategorizationRules(token!, Number(companyId));
                  return t("categorizationRulesResult", { applied: result.rules_applied, total: result.transactions_checked });
                })
              }
              className="input-v2 px-4 py-2 text-sm"
            >
              {t("applyCategorizationRules")}
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
