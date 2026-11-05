"use client";

import { FormEvent, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import GlassPageHeader from "@/components/glass/GlassPageHeader";
import GlassPanel from "@/components/glass/GlassPanel";
import GlassCard from "@/components/glass/GlassCard";
import GlassButton from "@/components/glass/GlassButton";
import { GlassInput } from "@/components/glass/GlassInput";
import GlassTable from "@/components/glass/GlassTable";
import { GlassErrorState } from "@/components/glass/GlassLoadingState";
import { useAuth } from "@/lib/auth-context";
import { api, ApiError, Company, KvkLookupResult } from "@/lib/api";

function VerifyCompanyButton({ companyId }: { companyId: number }) {
  const t = useTranslations("government");
  const { token } = useAuth();
  const [result, setResult] = useState<{ name_matches: boolean; kvk_name: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleVerify() {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api.verifyCompanyKvk(token, companyId);
      setResult({ name_matches: r.name_matches, kvk_name: r.kvk_name });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("verificationFailed"));
    } finally {
      setBusy(false);
    }
  }

  if (result) {
    return (
      <span className={`text-xs ${result.name_matches ? "text-green-700" : "text-amber-700"}`}>
        {result.name_matches ? t("matchesKvkRecord") : t("mismatch", { kvkName: result.kvk_name })}
      </span>
    );
  }
  return (
    <button onClick={handleVerify} disabled={busy} className="text-xs text-brand-purple-600 hover:underline disabled:opacity-50">
      {busy ? t("checking") : error ?? t("verifyAgainstKvk")}
    </button>
  );
}

type IntegrationStatus = "SANDBOX_VERIFIED" | "BLOCKED_BY_EXTERNAL_REQUIREMENT";

const INTEGRATIONS: { key: string; status: IntegrationStatus }[] = [
  { key: "kvkLookup", status: "SANDBOX_VERIFIED" },
  { key: "loonheffingenSubmission", status: "BLOCKED_BY_EXTERNAL_REQUIREMENT" },
  { key: "vatSubmission", status: "BLOCKED_BY_EXTERNAL_REQUIREMENT" },
];

const STATUS_STYLE: Record<IntegrationStatus, string> = {
  SANDBOX_VERIFIED: "bg-green-500/10 text-green-700 border border-green-300/50",
  BLOCKED_BY_EXTERNAL_REQUIREMENT: "bg-amber-500/10 text-amber-700 border border-amber-300/50",
};

function GovernmentContent() {
  const t = useTranslations("government");
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [kvkNumber, setKvkNumber] = useState("");
  const [result, setResult] = useState<KvkLookupResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  async function handleLookup(e: FormEvent) {
    e.preventDefault();
    if (!token || !kvkNumber) return;
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      setResult(await api.lookupKvk(token, kvkNumber));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-5">
      <GlassPageHeader title={t("title")} subtitle={t("subtitle")} />

      {error && <GlassErrorState message={error} />}

      <GlassPanel title={t("integrationStatus")}>
        <div className="space-y-3">
          {INTEGRATIONS.map((i) => (
            <div key={i.key} className="flex flex-col gap-1.5 rounded-lg border border-border p-3">
              <div className="flex items-center justify-between gap-3">
                <span className="font-medium text-text-primary text-sm">{t(`integrations.${i.key}.name` as never)}</span>
                <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_STYLE[i.status]}`}>{t(`statusLabel.${i.status}` as never)}</span>
              </div>
              <p className="text-xs text-text-secondary">{t(`integrations.${i.key}.detail` as never)}</p>
            </div>
          ))}
        </div>
      </GlassPanel>

      <GlassCard className="space-y-4">
        <h2 className="font-medium text-text-primary">{t("kvkCompanyLookup")}</h2>
        <form onSubmit={handleLookup} className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1">
            <label htmlFor="kvk-number" className="text-label-v2">{t("kvkNumber")}</label>
            <GlassInput id="kvk-number" required dir="ltr" value={kvkNumber} onChange={(e) => setKvkNumber(e.target.value)} placeholder="68750110" />
          </div>
          <GlassButton type="submit" loading={loading}>
            {t("lookUp")}
          </GlassButton>
        </form>

        {result && (
          <div className="rounded-lg border border-border p-4 space-y-1 text-sm">
            {result.is_test_data && (
              <span className="inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium bg-amber-500/10 text-amber-700 border border-amber-300/50 mb-1">
                {t("sandboxTestData")}
              </span>
            )}
            <p className="font-medium text-text-primary">{result.name}</p>
            <p className="text-text-secondary">{t("kvkNumber")}: <span dir="ltr">{result.kvk_number}</span></p>
            {result.legal_form && <p className="text-text-secondary">{t("legalForm")}: {result.legal_form}</p>}
            {result.trade_names.length > 0 && <p className="text-text-secondary">{t("tradeNames")}: {result.trade_names.join(", ")}</p>}
            {result.address && <p className="text-text-secondary">{t("address")}: {result.address}</p>}
            {result.sbi_activity && <p className="text-text-secondary">{t("sbiActivity")}: {result.sbi_activity}</p>}
          </div>
        )}
      </GlassCard>

      <GlassPanel title={t("companiesOnFile")}>
        <GlassTable
          emptyMessage={t("noCompaniesYet")}
          columns={[
            { key: "name", header: t("companyHeader"), render: (c) => c.name },
            {
              key: "kvk",
              header: t("kvkNumber"),
              render: (c) =>
                c.kvk_number ? (
                  <span className="font-mono text-xs" dir="ltr">{c.kvk_number}</span>
                ) : (
                  <span className="text-xs text-amber-700">{t("noKvkNumberOnFile")}</span>
                ),
            },
            {
              key: "verify",
              header: "",
              render: (c) => (c.kvk_number ? <VerifyCompanyButton companyId={c.id} /> : null),
            },
          ]}
          rows={companies}
          rowKey={(c) => c.id}
        />
      </GlassPanel>
    </div>
  );
}

export default function GovernmentPage() {
  return (
    <AuthGuard>
      <Shell>
        <GovernmentContent />
      </Shell>
    </AuthGuard>
  );
}
