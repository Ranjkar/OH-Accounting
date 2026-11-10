"use client";

import { Fragment, useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, ApiError, AuditLogEntry } from "@/lib/api";

const PAGE_SIZE = 25;

function JsonSnapshot({ label, value }: { label: string; value: Record<string, unknown> | null }) {
  if (!value || Object.keys(value).length === 0) return null;
  return (
    <div>
      <p className="text-[10px] font-semibold uppercase tracking-wide text-text-secondary">{label}</p>
      <pre className="text-xs bg-muted rounded-md p-2 overflow-x-auto" dir="ltr" tabIndex={0}>{JSON.stringify(value, null, 2)}</pre>
    </div>
  );
}

function AuditLogContent() {
  const t = useTranslations("auditLog");
  const tCommon = useTranslations("common");
  const tErrors = useTranslations("errors");
  const locale = useLocale();
  const { token } = useAuth();
  const [entries, setEntries] = useState<AuditLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [skip, setSkip] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const [actions, setActions] = useState<string[]>([]);
  const [entityTypes, setEntityTypes] = useState<string[]>([]);

  const [q, setQ] = useState("");
  const [action, setAction] = useState("");
  const [entityType, setEntityType] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  function formatTimestamp(value: string): string {
    return new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "medium" }).format(new Date(value));
  }

  useEffect(() => {
    if (!token) return;
    api.listAuditActions(token).then(setActions).catch(() => {});
    api.listAuditEntityTypes(token).then(setEntityTypes).catch(() => {});
  }, [token]);

  function refresh() {
    if (!token) return;
    api
      .listAuditLog(token, {
        skip,
        limit: PAGE_SIZE,
        q: q || undefined,
        action: action || undefined,
        entity_type: entityType || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
      })
      .then((page) => {
        setEntries(page.items);
        setTotal(page.total);
        setError(null);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : tErrors("loadFailed")))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, [token, skip]);

  function applyFilters() {
    setSkip(0);
    refresh();
  }

  function clearFilters() {
    setQ("");
    setAction("");
    setEntityType("");
    setDateFrom("");
    setDateTo("");
    setSkip(0);
  }

  const pageStart = total === 0 ? 0 : skip + 1;
  const pageEnd = Math.min(skip + PAGE_SIZE, total);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-text-primary">{t("title")}</h1>
        <p className="text-sm text-text-secondary mt-1">{t("subtitle")}</p>
      </div>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="card-v2 p-4 flex flex-wrap items-end gap-3">
        <div className="space-y-1">
          <label htmlFor="audit-search" className="text-xs font-medium text-text-secondary">{tCommon("search")}</label>
          <input
            id="audit-search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t("searchPlaceholder")}
            className="input-v2 px-3 py-2 text-sm w-48"
          />
        </div>
        <div className="space-y-1">
          <label htmlFor="audit-action" className="text-xs font-medium text-text-secondary">{t("action")}</label>
          <select id="audit-action" value={action} onChange={(e) => setAction(e.target.value)} className="input-v2 px-3 py-2 text-sm">
            <option value="">{t("allActions")}</option>
            {actions.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <label htmlFor="audit-entity" className="text-xs font-medium text-text-secondary">{t("entity")}</label>
          <select id="audit-entity" value={entityType} onChange={(e) => setEntityType(e.target.value)} className="input-v2 px-3 py-2 text-sm">
            <option value="">{t("allEntities")}</option>
            {entityTypes.map((et) => (
              <option key={et} value={et}>
                {et}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <label htmlFor="audit-from" className="text-xs font-medium text-text-secondary">{t("from")}</label>
          <input id="audit-from" type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="input-v2 px-3 py-2 text-sm" />
        </div>
        <div className="space-y-1">
          <label htmlFor="audit-to" className="text-xs font-medium text-text-secondary">{t("to")}</label>
          <input id="audit-to" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="input-v2 px-3 py-2 text-sm" />
        </div>
        <button onClick={applyFilters} className="btn-primary-v2 px-4 py-2 text-sm">
          {tCommon("apply")}
        </button>
        <button onClick={clearFilters} className="input-v2 px-3 py-2 text-sm">
          {tCommon("clear")}
        </button>
      </div>

      <div className="card-v2 overflow-hidden">
        <div className="overflow-x-auto" tabIndex={0}>
          <table className="table-v3">
            <thead>
              <tr>
                <th>{t("timestamp")}</th>
                <th>{t("actor")}</th>
                <th>{t("action")}</th>
                <th>{t("entity")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => (
                <Fragment key={entry.id}>
                  <tr
                    className="cursor-pointer hover:bg-muted"
                    onClick={() => setExpandedId(expandedId === entry.id ? null : entry.id)}
                  >
                    <td className="text-text-secondary text-xs">{formatTimestamp(entry.created_at)}</td>
                    <td className="text-text-primary text-xs">{entry.actor ? entry.actor.full_name : t("system")}</td>
                    <td className="text-text-primary text-xs font-mono" dir="ltr">{entry.action}</td>
                    <td className="text-text-secondary text-xs" dir="ltr">
                      {entry.entity_type} #{entry.entity_id}
                    </td>
                    <td className="text-xs text-navy">{expandedId === entry.id ? tCommon("hide") : tCommon("details")}</td>
                  </tr>
                  {expandedId === entry.id && (
                    <tr>
                      <td colSpan={5} className="bg-muted">
                        <div className="p-3 space-y-2">
                          {entry.request_id && (
                            <p className="text-xs text-text-secondary">
                              {t("requestId")}: <span className="font-mono" dir="ltr">{entry.request_id}</span>
                            </p>
                          )}
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            <JsonSnapshot label={t("before")} value={entry.before} />
                            <JsonSnapshot label={t("after")} value={entry.after} />
                          </div>
                          {!entry.before && !entry.after && (
                            <p className="text-xs text-text-secondary">{t("noAdditionalDetail")}</p>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
              {!loading && entries.length === 0 && (
                <tr>
                  <td colSpan={5} className="text-text-secondary">
                    {t("noEventsMatch")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="flex items-center justify-between text-sm text-text-secondary">
        <span>
          {total === 0 ? t("noEvents") : t("showingRange", { start: pageStart, end: pageEnd, total })}
        </span>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setSkip((s) => Math.max(0, s - PAGE_SIZE))}
            disabled={skip === 0}
            className="input-v2 px-3 py-1.5 text-xs disabled:opacity-50"
          >
            {tCommon("previous")}
          </button>
          <button
            onClick={() => setSkip((s) => s + PAGE_SIZE)}
            disabled={skip + PAGE_SIZE >= total}
            className="input-v2 px-3 py-1.5 text-xs disabled:opacity-50"
          >
            {tCommon("next")}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function AuditLogPage() {
  return (
    <AuthGuard>
      <Shell>
        <AuditLogContent />
      </Shell>
    </AuthGuard>
  );
}
