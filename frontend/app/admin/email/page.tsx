"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import GlassPageHeader from "@/components/glass/GlassPageHeader";
import GlassPanel from "@/components/glass/GlassPanel";
import GlassTable from "@/components/glass/GlassTable";
import GlassLoadingState, { GlassErrorState } from "@/components/glass/GlassLoadingState";
import { useAuth } from "@/lib/auth-context";
import { api, ApiError, EmailOutboxEntry, EmailStatus } from "@/lib/api";
import { formatRelativeDate } from "@/lib/format";

const STATUS_FILTERS = ["", "queued", "sent", "failed"] as const;

const STATUS_PILL: Record<string, string> = {
  sent: "status-pill-success",
  failed: "status-pill-danger",
  queued: "status-pill-warning",
};

function EmailAdminContent() {
  const t = useTranslations("emailAdmin");
  const tAdmin = useTranslations("admin");
  const locale = useLocale();
  const { token, user } = useAuth();
  const [status, setStatus] = useState<EmailStatus | null>(null);
  const [outbox, setOutbox] = useState<EmailOutboxEntry[] | null>(null);
  const [filter, setFilter] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [testTo, setTestTo] = useState("");
  const [testBusy, setTestBusy] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [testError, setTestError] = useState<string | null>(null);
  const [busyRow, setBusyRow] = useState<number | null>(null);

  const loadOutbox = useCallback(
    (nextFilter: string) => {
      if (!token) return;
      api.emailOutbox(token, nextFilter || undefined).then(setOutbox).catch((e) => setError(e instanceof ApiError ? e.message : t("loadFailed")));
    },
    [token, t]
  );

  useEffect(() => {
    if (!token || !user?.is_platform_admin) return;
    api.emailStatus(token).then(setStatus).catch((e) => setError(e instanceof ApiError ? e.message : t("loadFailed")));
    loadOutbox("");
  }, [token, user, loadOutbox, t]);

  if (!user?.is_platform_admin) {
    return <GlassErrorState message={tAdmin("platformAdminOnly")} />;
  }

  async function sendTest(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setTestBusy(true);
    setTestError(null);
    setTestResult(null);
    try {
      const row = await api.sendTestEmail(token, testTo.trim() || undefined);
      setTestResult(t("testSent", { status: row.status }));
      setTestTo("");
      loadOutbox(filter);
    } catch (err) {
      setTestError(err instanceof ApiError ? err.message : t("testFailed"));
    } finally {
      setTestBusy(false);
    }
  }

  async function retry(row: EmailOutboxEntry) {
    if (!token) return;
    setBusyRow(row.id);
    setError(null);
    try {
      await api.retryEmail(token, row.id);
      loadOutbox(filter);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("retryFailed"));
    } finally {
      setBusyRow(null);
    }
  }

  const row = (label: string, value: string | null) => (
    <div className="flex flex-wrap justify-between gap-x-4 gap-y-1 py-1.5 text-sm">
      <dt className="text-text-secondary">{label}</dt>
      <dd className="font-medium text-text-primary text-end" dir="ltr">{value ?? "—"}</dd>
    </div>
  );

  return (
    <div className="space-y-5">
      <GlassPageHeader title={t("title")} subtitle={t("subtitle")} />

      {error && <GlassErrorState message={error} />}

      {!status ? (
        <GlassLoadingState />
      ) : (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            <GlassPanel title={t("statusTitle")}>
              <div className="px-5 py-3">
                <dl className="divide-y divide-border-subtle">
                  {row(t("provider"), status.provider)}
                  {row(
                    t("configured"),
                    status.configured ? t("configuredYes") : t("configuredNo")
                  )}
                  {row(t("fromAddress"), status.from_address)}
                  {row(t("fromName"), status.from_name)}
                  {row(t("appBaseUrl"), status.app_base_url)}
                  {status.provider === "smtp" && row(t("smtpHost"), `${status.smtp_host ?? "—"}:${status.smtp_port ?? ""} (${status.smtp_security})`)}
                  {row(t("rateLimits"), `${status.rate_limits.per_recipient_per_hour} / ${status.rate_limits.per_tenant_per_hour}`)}
                  {row(t("last24h"), `${t("sent")}: ${status.last_24h.sent} · ${t("failed")}: ${status.last_24h.failed} · ${t("queued")}: ${status.last_24h.queued}`)}
                </dl>
                {!status.configured && (
                  <div className="mt-3 rounded-md bg-amber-50 border border-amber-200 text-sm px-3 py-2 text-pending">
                    <p className="font-medium">{t("missingSettings")}</p>
                    <p className="text-xs mt-1">{t("missingSettingsHelp")}</p>
                    <ul className="list-disc ps-5 mt-1 text-xs font-mono" dir="ltr">
                      {(status.missing_settings.length ? status.missing_settings : ["EMAIL_PROVIDER"]).map((s) => (
                        <li key={s}>{s}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </GlassPanel>

            <GlassPanel title={t("dnsTitle")}>
              <div className="px-5 py-3 space-y-2">
                <p className="text-xs text-text-secondary">{t("dnsHelp")}</p>
                <dl className="divide-y divide-border-subtle">
                  {row(t("dnsDomain"), status.dns.domain)}
                  {row("SPF", status.dns.spf)}
                  {row("DMARC", status.dns.dmarc)}
                </dl>
                <p className="text-xs text-text-secondary break-words" dir="ltr">{status.dns.dkim}</p>
              </div>
            </GlassPanel>
          </div>

          <GlassPanel title={t("testTitle")}>
            <form onSubmit={sendTest} className="px-5 py-4 flex flex-wrap items-end gap-3">
              <div className="space-y-1">
                <label htmlFor="test-to" className="text-label-v2">{t("testToLabel")}</label>
                <input
                  id="test-to"
                  type="email"
                  dir="ltr"
                  value={testTo}
                  onChange={(e) => setTestTo(e.target.value)}
                  placeholder={t("testToPlaceholder")}
                  className="input-v2 px-3 py-2 text-sm w-72 max-w-full"
                />
              </div>
              <button type="submit" disabled={testBusy} className="btn-primary-v2 px-4 py-2 text-sm disabled:opacity-50">
                {testBusy ? t("testWorking") : t("testButton")}
              </button>
              {testResult && <p className="text-sm text-green-700" role="status">{testResult}</p>}
              {testError && <p className="text-sm text-error" role="alert">{testError}</p>}
              <p className="w-full text-xs text-text-secondary">{t("testHelp")}</p>
            </form>
          </GlassPanel>

          <GlassPanel
            title={t("outboxTitle")}
            actions={
              <select
                aria-label={t("filterLabel")}
                value={filter}
                onChange={(e) => {
                  setFilter(e.target.value);
                  loadOutbox(e.target.value);
                }}
                className="input-v2 px-2 py-1 text-xs"
              >
                {STATUS_FILTERS.map((f) => (
                  <option key={f || "all"} value={f}>
                    {f ? t(`filter${f[0].toUpperCase()}${f.slice(1)}` as never) : t("filterAll")}
                  </option>
                ))}
              </select>
            }
          >
            <GlassTable
              emptyMessage={t("outboxEmpty")}
              columns={[
                { key: "to", header: t("colTo"), render: (r: EmailOutboxEntry) => <span dir="ltr">{r.to_email}</span> },
                { key: "template", header: t("colTemplate"), render: (r: EmailOutboxEntry) => r.template },
                { key: "status", header: t("colStatus"), render: (r: EmailOutboxEntry) => <span className={`status-pill ${STATUS_PILL[r.status] ?? "status-pill-neutral"}`}>{r.status}</span> },
                { key: "attempts", header: t("colAttempts"), render: (r: EmailOutboxEntry) => r.attempts },
                { key: "created", header: t("colCreated"), render: (r: EmailOutboxEntry) => formatRelativeDate(r.created_at, locale) },
                {
                  key: "actions",
                  header: "",
                  render: (r: EmailOutboxEntry) =>
                    r.status === "failed" && r.template === "test" ? (
                      <button onClick={() => retry(r)} disabled={busyRow === r.id} className="text-navy hover:underline disabled:opacity-50 text-xs">
                        {t("retry")}
                      </button>
                    ) : (
                      <span className="text-text-secondary text-xs">{r.last_error ?? ""}</span>
                    ),
                },
              ]}
              rows={outbox ?? []}
              rowKey={(r) => r.id}
            />
          </GlassPanel>
        </>
      )}
    </div>
  );
}

export default function EmailAdminPage() {
  return (
    <AuthGuard>
      <Shell>
        <EmailAdminContent />
      </Shell>
    </AuthGuard>
  );
}
