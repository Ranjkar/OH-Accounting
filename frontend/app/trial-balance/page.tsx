"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import GlassPageHeader from "@/components/glass/GlassPageHeader";
import GlassPanel from "@/components/glass/GlassPanel";
import { GlassSelect, GlassInput } from "@/components/glass/GlassInput";
import GlassLoadingState, { GlassErrorState } from "@/components/glass/GlassLoadingState";
import { useAuth } from "@/lib/auth-context";
import { api, Company, JsonReport } from "@/lib/api";

function TrialBalanceContent() {
  const t = useTranslations("trialBalance");
  const tCommon = useTranslations("common");
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [periodType, setPeriodType] = useState<"MONTHLY" | "QUARTERLY" | "ANNUAL">("ANNUAL");
  const [referenceDate, setReferenceDate] = useState(new Date().toISOString().slice(0, 10));
  const [report, setReport] = useState<JsonReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  useEffect(() => {
    if (!token || !companyId) return;
    api
      .trialBalance(token, { company_id: Number(companyId), period_type: periodType, reference_date: referenceDate })
      .then(setReport)
      .catch((e) => setError(e.message));
  }, [token, companyId, periodType, referenceDate]);

  return (
    <div className="space-y-5">
      <GlassPageHeader title={t("title")} subtitle={t("subtitle")} />
      {error && <GlassErrorState message={error} />}

      <div className="flex flex-wrap items-end gap-3">
        <GlassSelect aria-label={tCommon("company")} value={companyId} onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")}>
          <option value="">{tCommon("selectCompany")}</option>
          {companies.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </GlassSelect>
        <GlassSelect aria-label={t("periodType")} value={periodType} onChange={(e) => setPeriodType(e.target.value as typeof periodType)}>
          <option value="MONTHLY">{t("monthly")}</option>
          <option value="QUARTERLY">{t("quarterly")}</option>
          <option value="ANNUAL">{t("annual")}</option>
        </GlassSelect>
        <GlassInput aria-label={t("referenceDate")} type="date" value={referenceDate} onChange={(e) => setReferenceDate(e.target.value)} />
      </div>

      {!companyId ? (
        <p className="text-sm text-text-secondary">{t("selectCompanyPrompt")}</p>
      ) : !report ? (
        <GlassLoadingState rows={4} />
      ) : (
        <>
          {!report.is_balanced && (
            <div className="rounded-lg bg-amber-500/10 border border-amber-300/50 text-amber-700 text-sm px-4 py-3">
              {t("imbalanceWarning", { amount: String(report.difference) })}
            </div>
          )}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <GlassPanel title={t("debits")} actions={<span className="text-sm font-mono text-text-primary">€{String(report.total_debits)}</span>}>
              <ul className="divide-y divide-white/30">
                {Object.entries(report.debits as Record<string, string>)
                  .filter(([, v]) => Number(v) !== 0)
                  .map(([label, amount]) => (
                    <li key={label} className="flex justify-between px-5 py-2.5 text-sm">
                      <span className="text-text-secondary">{label}</span>
                      <span className="font-mono text-text-primary">€{amount}</span>
                    </li>
                  ))}
              </ul>
            </GlassPanel>
            <GlassPanel title={t("credits")} actions={<span className="text-sm font-mono text-text-primary">€{String(report.total_credits)}</span>}>
              <ul className="divide-y divide-white/30">
                {Object.entries(report.credits as Record<string, string>)
                  .filter(([, v]) => Number(v) !== 0)
                  .map(([label, amount]) => (
                    <li key={label} className="flex justify-between px-5 py-2.5 text-sm">
                      <span className="text-text-secondary">{label}</span>
                      <span className="font-mono text-text-primary">€{amount}</span>
                    </li>
                  ))}
              </ul>
            </GlassPanel>
          </div>
        </>
      )}
    </div>
  );
}

export default function TrialBalancePage() {
  return (
    <AuthGuard>
      <Shell>
        <TrialBalanceContent />
      </Shell>
    </AuthGuard>
  );
}
