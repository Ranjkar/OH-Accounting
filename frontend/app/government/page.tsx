"use client";

import { FormEvent, useEffect, useState } from "react";
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
      setError(e instanceof ApiError ? e.message : "Verification failed");
    } finally {
      setBusy(false);
    }
  }

  if (result) {
    return (
      <span className={`text-xs ${result.name_matches ? "text-green-700" : "text-amber-700"}`}>
        {result.name_matches ? "Matches KVK record" : `Mismatch -- KVK has "${result.kvk_name}"`}
      </span>
    );
  }
  return (
    <button onClick={handleVerify} disabled={busy} className="text-xs text-brand-purple-600 hover:underline disabled:opacity-50">
      {busy ? "Checking…" : error ?? "Verify against KVK"}
    </button>
  );
}

type IntegrationStatus = "SANDBOX VERIFIED" | "BLOCKED BY EXTERNAL REQUIREMENT";

const INTEGRATIONS: { name: string; status: IntegrationStatus; detail: string; docsLink: string }[] = [
  {
    name: "KVK (Handelsregister) company lookup",
    status: "SANDBOX VERIFIED",
    detail: "Real network calls against KVK's published, no-registration test sandbox. Never scrapes the Handelsregister and never invents company data.",
    docsLink: "docs/government-integrations.md",
  },
  {
    name: "Loonheffingen (payroll tax) submission",
    status: "BLOCKED BY EXTERNAL REQUIREMENT",
    detail: "Declaration lifecycle (Draft → Submitted → Acknowledged → Accepted/Rejected) is fully built -- see Payroll Tax. Actual SBR/Digipoort transmission needs a PKIoverheid/Logius test certificate this environment cannot obtain.",
    docsLink: "docs/government-integrations.md",
  },
  {
    name: "VAT (BTW) return submission",
    status: "BLOCKED BY EXTERNAL REQUIREMENT",
    detail: "Return calculation and filing status are tracked in VAT Returns. Direct Belastingdienst submission has the same SBR/Digipoort certificate requirement as above.",
    docsLink: "docs/government-integrations.md",
  },
];

const STATUS_STYLE: Record<IntegrationStatus, string> = {
  "SANDBOX VERIFIED": "bg-green-500/10 text-green-700 border border-green-300/50",
  "BLOCKED BY EXTERNAL REQUIREMENT": "bg-amber-500/10 text-amber-700 border border-amber-300/50",
};

function GovernmentContent() {
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
      <GlassPageHeader
        title="Government Integration Centre"
        subtitle="Real status of this app's Dutch government integrations -- no fabricated connections. Declaration filing itself happens in Payroll Tax and VAT Returns; this page is the KVK lookup tool plus an honest integration status overview."
      />

      {error && <GlassErrorState message={error} />}

      <GlassPanel title="Integration status">
        <div className="space-y-3">
          {INTEGRATIONS.map((i) => (
            <div key={i.name} className="flex flex-col gap-1.5 rounded-lg border border-border p-3">
              <div className="flex items-center justify-between gap-3">
                <span className="font-medium text-text-primary text-sm">{i.name}</span>
                <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_STYLE[i.status]}`}>{i.status}</span>
              </div>
              <p className="text-xs text-text-secondary">{i.detail}</p>
            </div>
          ))}
        </div>
      </GlassPanel>

      <GlassCard className="space-y-4">
        <h2 className="font-medium text-text-primary">KVK company lookup</h2>
        <form onSubmit={handleLookup} className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1">
            <label htmlFor="kvk-number" className="text-label-v2">KVK number</label>
            <GlassInput id="kvk-number" required value={kvkNumber} onChange={(e) => setKvkNumber(e.target.value)} placeholder="68750110" />
          </div>
          <GlassButton type="submit" loading={loading}>
            Look up
          </GlassButton>
        </form>

        {result && (
          <div className="rounded-lg border border-border p-4 space-y-1 text-sm">
            {result.is_test_data && (
              <span className="inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium bg-amber-500/10 text-amber-700 border border-amber-300/50 mb-1">
                Sandbox test data -- not a real Handelsregister lookup
              </span>
            )}
            <p className="font-medium text-text-primary">{result.name}</p>
            <p className="text-text-secondary">KVK number: {result.kvk_number}</p>
            {result.legal_form && <p className="text-text-secondary">Legal form: {result.legal_form}</p>}
            {result.trade_names.length > 0 && <p className="text-text-secondary">Trade names: {result.trade_names.join(", ")}</p>}
            {result.address && <p className="text-text-secondary">Address: {result.address}</p>}
            {result.sbi_activity && <p className="text-text-secondary">SBI activity: {result.sbi_activity}</p>}
          </div>
        )}
      </GlassCard>

      <GlassPanel title="Companies on file">
        <GlassTable
          emptyMessage="No companies yet."
          columns={[
            { key: "name", header: "Company", render: (c) => c.name },
            {
              key: "kvk",
              header: "KVK number",
              render: (c) =>
                c.kvk_number ? (
                  <span className="font-mono text-xs">{c.kvk_number}</span>
                ) : (
                  <span className="text-xs text-amber-700">No KVK number on file</span>
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
