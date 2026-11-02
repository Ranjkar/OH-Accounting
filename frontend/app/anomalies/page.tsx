"use client";

import { useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, AnomalyFlag, AnomalyStatus, Company } from "@/lib/api";

const SEVERITY_COLOR: Record<string, string> = {
  info: "bg-slate-100 text-slate-600",
  warning: "bg-amber-100 text-amber-700",
  critical: "bg-red-100 text-error",
};

function AnomaliesContent() {
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [statusFilter, setStatusFilter] = useState<AnomalyStatus | "all">("OPEN");
  const [flags, setFlags] = useState<AnomalyFlag[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  function refresh() {
    if (!token || !companyId) return;
    api
      .listAnomalies(token, Number(companyId), statusFilter === "all" ? undefined : statusFilter)
      .then(setFlags)
      .catch((e) => setError(e.message));
  }

  useEffect(refresh, [token, companyId, statusFilter]);

  async function detect() {
    if (!token || !companyId) return;
    try {
      await api.detectAnomalies(token, Number(companyId));
      refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function acknowledge(id: number) {
    if (!token) return;
    await api.acknowledgeAnomaly(token, id);
    refresh();
  }

  async function dismiss(id: number) {
    if (!token) return;
    await api.dismissAnomaly(token, id);
    refresh();
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-navy">Anomalies</h1>
        <button onClick={detect} disabled={!companyId} className="rounded-md bg-navy text-white px-4 py-2 text-sm font-medium disabled:opacity-50">
          Run anomaly detection
        </button>
      </div>
      <p className="text-sm text-slate-500">
        Transparent, evidence-based flags for review -- never a verdict. Nothing here labels a transaction
        fraudulent; every flag names the rule and the evidence behind it so an accountant can judge it.
      </p>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="flex items-center gap-4">
        <select
          value={companyId}
          onChange={(e) => {
            setCompanyId(e.target.value ? Number(e.target.value) : "");
            if (!e.target.value) setFlags([]);
          }}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm"
        >
          <option value="">Select a company</option>
          {companies.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <div className="flex items-center gap-2 text-sm">
          {(["OPEN", "ACKNOWLEDGED", "DISMISSED", "all"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`rounded-full px-3 py-1 ${statusFilter === s ? "bg-navy text-white" : "bg-white border border-slate-200 text-slate-600"}`}
            >
              {s === "all" ? "All" : s}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-3">
        {flags.map((f) => (
          <div key={f.id} className="bg-white rounded-lg border border-slate-200 p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className={`text-xs rounded-full px-2 py-0.5 ${SEVERITY_COLOR[f.severity]}`}>{f.severity}</span>
              <span className="text-xs text-slate-400">{f.rule_code}</span>
            </div>
            <p className="text-sm">{f.message}</p>
            <pre className="text-xs bg-slate-50 rounded-md p-2 overflow-x-auto">{JSON.stringify(f.evidence, null, 2)}</pre>
            {f.status === "OPEN" && (
              <div className="flex items-center gap-2">
                <button onClick={() => acknowledge(f.id)} className="rounded-md bg-navy text-white px-3 py-1.5 text-xs">
                  Acknowledge
                </button>
                <button onClick={() => dismiss(f.id)} className="rounded-md border border-slate-300 px-3 py-1.5 text-xs">
                  Dismiss
                </button>
              </div>
            )}
          </div>
        ))}
        {flags.length === 0 && <p className="text-sm text-slate-500">No anomalies match these filters.</p>}
      </div>
    </div>
  );
}

export default function AnomaliesPage() {
  return (
    <AuthGuard>
      <Shell>
        <AnomaliesContent />
      </Shell>
    </AuthGuard>
  );
}
