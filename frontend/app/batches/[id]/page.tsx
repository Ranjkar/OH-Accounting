"use client";

import { Suspense, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import DocumentStatusBadge from "@/components/DocumentStatusBadge";
import { useAuth } from "@/lib/auth-context";
import { api, BatchDetail } from "@/lib/api";

function StatCard({ label, value, tone = "navy" }: { label: string; value: number; tone?: "navy" | "amber" | "red" | "green" }) {
  const toneClass = { navy: "text-navy", amber: "text-pending", red: "text-error", green: "text-approved" }[tone];
  return (
    <div className="card-v2 p-3">
      <p className="text-xs text-text-secondary">{label}</p>
      <p className={`text-xl font-semibold mt-0.5 ${toneClass}`}>{value}</p>
    </div>
  );
}

function BatchDetailContent({ batchId }: { batchId: number }) {
  const t = useTranslations("batches");
  const tCommon = useTranslations("common");
  const locale = useLocale();
  const { token, user } = useAuth();
  const router = useRouter();
  const canEdit = user?.role === "admin" || user?.role === "accountant";

  const [batch, setBatch] = useState<BatchDetail | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function refresh() {
    if (!token) return;
    api.getBatch(token, batchId).then(setBatch).catch((e) => setError(e.message));
  }

  useEffect(refresh, [token, batchId]);

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAllEligible() {
    if (!batch) return;
    const eligible = batch.documents.filter((d) => d.status === "extracted").map((d) => d.id);
    setSelected(new Set(selected.size === eligible.length ? [] : eligible));
  }

  async function handleBulkApprove() {
    if (!token || selected.size === 0) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.bulkApproveDocuments(token, batchId, [...selected]);
      const failures = result.results.filter((r) => !r.success);
      if (failures.length) setError(t("bulkApprovalPartialFailure", { count: failures.length, detail: failures[0].detail }));
      setSelected(new Set());
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("bulkApprovalFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function handleBulkReject() {
    if (!token || selected.size === 0) return;
    const reason = window.prompt(t("rejectReasonPrompt"));
    if (!reason) return;
    setBusy(true);
    setError(null);
    try {
      await api.bulkRejectDocuments(token, batchId, [...selected], reason);
      setSelected(new Set());
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("bulkRejectionFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function handleRemove(documentId: number) {
    if (!token) return;
    try {
      await api.deleteDocument(token, documentId);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("removeFailed"));
    }
  }

  async function handleRetry(documentId: number) {
    if (!token) return;
    try {
      await api.reprocessDocument(token, documentId);
      setTimeout(refresh, 1500);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("retryFailed"));
    }
  }

  if (!batch) return <p className="text-text-secondary">{tCommon("loading")}</p>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <button onClick={() => router.back()} className="text-sm text-navy hover:underline">
            ← {tCommon("back")}
          </button>
          <h1 className="text-xl font-semibold text-navy mt-1">
            {t("batchHeading", { id: batch.id, category: batch.category, date: new Date(batch.created_at).toLocaleString(locale) })}
          </h1>
        </div>
        <a href={api.batchExportUrl(batch.id)} target="_blank" rel="noreferrer" className="text-sm text-navy hover:underline">
          {t("exportCsv")}
        </a>
      </div>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
        <StatCard label={t("total")} value={batch.counts.total} />
        <StatCard label={t("extracted")} value={batch.counts.extracted} tone="green" />
        <StatCard label={t("needsReview")} value={batch.counts.needs_review} tone="amber" />
        <StatCard label={t("duplicates")} value={batch.counts.duplicates} tone="red" />
        <StatCard label={t("failed")} value={batch.counts.failed} tone="red" />
        <StatCard label={t("approved")} value={batch.counts.approved} tone="green" />
        <StatCard label={t("pending")} value={batch.counts.pending_or_processing} />
      </div>

      {canEdit && (
        <div className="flex items-center gap-2">
          <button onClick={toggleAllEligible} className="text-sm text-navy hover:underline">
            {t("selectAllReadyToApprove")}
          </button>
          <button
            onClick={handleBulkApprove}
            disabled={busy || selected.size === 0}
            className="rounded-md bg-green-600 text-white px-3 py-1.5 text-sm font-medium hover:bg-green-700 transition-colors disabled:opacity-50"
          >
            {t("approveSelected", { count: selected.size })}
          </button>
          <button
            onClick={handleBulkReject}
            disabled={busy || selected.size === 0}
            className="rounded-md bg-red-600 text-white px-3 py-1.5 text-sm font-medium hover:bg-red-700 transition-colors disabled:opacity-50"
          >
            {t("rejectSelected")}
          </button>
        </div>
      )}

      <div className="card-v2 overflow-hidden">
        <div className="overflow-x-auto">
        <table className="table-v3">
          <thead>
            <tr>
              {canEdit && <th></th>}
              <th>{t("document")}</th>
              <th>{t("type")}</th>
              <th className="text-right">{t("confidence")}</th>
              <th>{tCommon("status")}</th>
              <th>{tCommon("actions")}</th>
            </tr>
          </thead>
          <tbody>
            {batch.documents.map((doc) => (
              <tr key={doc.id} className="hover:bg-muted">
                {canEdit && (
                  <td>
                    <input
                      type="checkbox"
                      aria-label={t("selectDocument", { id: doc.id })}
                      checked={selected.has(doc.id)}
                      onChange={() => toggle(doc.id)}
                      disabled={doc.status !== "extracted"}
                    />
                  </td>
                )}
                <td>
                  <a href={`/documents/${doc.id}`} className="text-navy hover:underline">
                    {doc.original_filename}
                  </a>
                </td>
                <td className="text-xs text-text-secondary">{doc.document_type ?? "—"}</td>
                <td className="text-right text-xs text-text-secondary">
                  {doc.classification_confidence !== null ? `${(doc.classification_confidence * 100).toFixed(0)}%` : "—"}
                </td>
                <td>
                  <DocumentStatusBadge status={doc.status} isDuplicate={doc.is_duplicate} />
                </td>
                <td className="text-xs space-x-2">
                  {canEdit && doc.status === "failed" && (
                    <button onClick={() => handleRetry(doc.id)} className="text-navy hover:underline">
                      {t("retry")}
                    </button>
                  )}
                  {canEdit && doc.status !== "approved" && (
                    <button onClick={() => handleRemove(doc.id)} className="text-error hover:underline">
                      {t("remove")}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      </div>
    </div>
  );
}

function BatchDetailRoute() {
  const params = useParams<{ id: string }>();
  return (
    <AuthGuard>
      <Shell>
        <BatchDetailContent batchId={Number(params.id)} />
      </Shell>
    </AuthGuard>
  );
}

export default function BatchDetailPage() {
  return (
    <Suspense>
      <BatchDetailRoute />
    </Suspense>
  );
}
