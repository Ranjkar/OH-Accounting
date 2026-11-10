"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, AnomalyFlag, AnomalyStatus, Company } from "@/lib/api";

const SEVERITY_COLOR: Record<string, string> = {
  info: "bg-muted text-text-secondary",
  warning: "bg-amber-100 text-amber-700",
  critical: "bg-red-100 text-error",
};

const STATUS_KEY: Record<string, string> = { OPEN: "open", ACKNOWLEDGED: "acknowledged", DISMISSED: "dismissed", all: "all" };

function AnomaliesContent() {
  const t = useTranslations("anomalies");
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
        <h1 className="text-2xl font-semibold text-text-primary">{t("title")}</h1>
        <button onClick={detect} disabled={!companyId} className="rounded-md bg-navy-solid text-white px-4 py-2 text-sm font-medium disabled:opacity-50">
          {t("runDetection")}
        </button>
      </div>
      <p className="text-sm text-text-secondary">{t("intro")}</p>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="flex items-center gap-4">
        <select
          value={companyId}
          aria-label={t("companyLabel")}
          onChange={(e) => {
            setCompanyId(e.target.value ? Number(e.target.value) : "");
            if (!e.target.value) setFlags([]);
          }}
          className="input-v2 px-3 py-2 text-sm"
        >
          <option value="">{t("selectCompanyOption")}</option>
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
              className={`rounded-full px-3 py-1 ${statusFilter === s ? "bg-navy-solid text-white" : "bg-surface-card border border-border text-text-secondary"}`}
            >
              {t(`statusLabels.${STATUS_KEY[s]}` as never)}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-3">
        {flags.map((f) => (
          <div key={f.id} className="card-v2 p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className={`text-xs rounded-full px-2 py-0.5 ${SEVERITY_COLOR[f.severity]}`}>
                {t.has(`severityLabels.${f.severity}`) ? t(`severityLabels.${f.severity}` as never) : f.severity}
              </span>
              <span className="text-xs text-text-secondary" dir="ltr">{f.rule_code}</span>
            </div>
            <p className="text-sm">{f.message}</p>
            <pre className="text-xs bg-muted rounded-md p-2 overflow-x-auto" dir="ltr">{JSON.stringify(f.evidence, null, 2)}</pre>
            {f.status === "OPEN" && (
              <div className="flex items-center gap-2">
                <button onClick={() => acknowledge(f.id)} className="btn-primary-v2 px-3 py-1.5 text-xs">
                  {t("acknowledge")}
                </button>
                <button onClick={() => dismiss(f.id)} className="input-v2 px-3 py-1.5 text-xs">
                  {t("dismiss")}
                </button>
              </div>
            )}
          </div>
        ))}
        {flags.length === 0 && <p className="text-sm text-text-secondary">{t("noMatches")}</p>}
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
