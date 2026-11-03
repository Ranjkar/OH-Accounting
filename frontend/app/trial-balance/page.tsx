"use client";

import { useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import GlassPageHeader from "@/components/glass/GlassPageHeader";
import GlassPanel from "@/components/glass/GlassPanel";
import { GlassSelect, GlassInput } from "@/components/glass/GlassInput";
import GlassLoadingState, { GlassErrorState } from "@/components/glass/GlassLoadingState";
import { useAuth } from "@/lib/auth-context";
import { api, Company, JsonReport } from "@/lib/api";

function TrialBalanceContent() {
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
      <GlassPageHeader
        title="Trial Balance"
        subtitle="A best-effort trial balance derived from this single-entry invoice ledger -- not a formal double-entry trial balance. Any imbalance is reported, never forced to zero."
      />
      {error && <GlassErrorState message={error} />}

      <div className="flex flex-wrap items-end gap-3">
        <GlassSelect aria-label="Company" value={companyId} onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")}>
          <option value="">Select a company</option>
          {companies.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </GlassSelect>
        <GlassSelect aria-label="Period type" value={periodType} onChange={(e) => setPeriodType(e.target.value as typeof periodType)}>
          <option value="MONTHLY">Monthly</option>
          <option value="QUARTERLY">Quarterly</option>
          <option value="ANNUAL">Annual</option>
        </GlassSelect>
        <GlassInput aria-label="Reference date" type="date" value={referenceDate} onChange={(e) => setReferenceDate(e.target.value)} />
      </div>

      {!companyId ? (
        <p className="text-sm text-text-secondary">Select a company to view its trial balance.</p>
      ) : !report ? (
        <GlassLoadingState rows={4} />
      ) : (
        <>
          {!report.is_balanced && (
            <div className="rounded-lg bg-amber-500/10 border border-amber-300/50 text-amber-700 text-sm px-4 py-3">
              Debits and credits differ by €{String(report.difference)} -- this is reported honestly, not forced to balance.
            </div>
          )}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <GlassPanel title="Debits" actions={<span className="text-sm font-mono text-text-primary">€{String(report.total_debits)}</span>}>
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
            <GlassPanel title="Credits" actions={<span className="text-sm font-mono text-text-primary">€{String(report.total_credits)}</span>}>
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
