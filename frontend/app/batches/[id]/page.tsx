"use client";

import { Suspense, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
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
      if (failures.length) setError(`${failures.length} document(s) could not be approved: ${failures[0].detail}`);
      setSelected(new Set());
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bulk approval failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleBulkReject() {
    if (!token || selected.size === 0) return;
    const reason = window.prompt("Reason for rejecting the selected documents:");
    if (!reason) return;
    setBusy(true);
    setError(null);
    try {
      await api.bulkRejectDocuments(token, batchId, [...selected], reason);
      setSelected(new Set());
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bulk rejection failed");
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
      setError(err instanceof Error ? err.message : "Failed to remove file");
    }
  }

  async function handleRetry(documentId: number) {
    if (!token) return;
    try {
      await api.reprocessDocument(token, documentId);
      setTimeout(refresh, 1500);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to retry");
    }
  }

  if (!batch) return <p className="text-text-secondary">Loading…</p>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <button onClick={() => router.back()} className="text-sm text-navy hover:underline">
            ← Back
          </button>
          <h1 className="text-xl font-semibold text-navy mt-1">
            Batch #{batch.id} · {batch.category} · {new Date(batch.created_at).toLocaleString()}
          </h1>
        </div>
        <a href={api.batchExportUrl(batch.id)} target="_blank" rel="noreferrer" className="text-sm text-navy hover:underline">
          Export CSV
        </a>
      </div>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
        <StatCard label="Total" value={batch.counts.total} />
        <StatCard label="Extracted" value={batch.counts.extracted} tone="green" />
        <StatCard label="Needs review" value={batch.counts.needs_review} tone="amber" />
        <StatCard label="Duplicates" value={batch.counts.duplicates} tone="red" />
        <StatCard label="Failed" value={batch.counts.failed} tone="red" />
        <StatCard label="Approved" value={batch.counts.approved} tone="green" />
        <StatCard label="Pending" value={batch.counts.pending_or_processing} />
      </div>

      {canEdit && (
        <div className="flex items-center gap-2">
          <button onClick={toggleAllEligible} className="text-sm text-navy hover:underline">
            Select all ready-to-approve
          </button>
          <button
            onClick={handleBulkApprove}
            disabled={busy || selected.size === 0}
            className="rounded-md bg-green-600 text-white px-3 py-1.5 text-sm font-medium hover:bg-green-700 transition-colors disabled:opacity-50"
          >
            Approve selected ({selected.size})
          </button>
          <button
            onClick={handleBulkReject}
            disabled={busy || selected.size === 0}
            className="rounded-md bg-red-600 text-white px-3 py-1.5 text-sm font-medium hover:bg-red-700 transition-colors disabled:opacity-50"
          >
            Reject selected
          </button>
        </div>
      )}

      <div className="card-v2 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-text-secondary border-b border-border-subtle">
              {canEdit && <th className="px-4 py-2"></th>}
              <th className="px-4 py-2 font-medium">Document</th>
              <th className="px-4 py-2 font-medium">Type</th>
              <th className="px-4 py-2 font-medium">Confidence</th>
              <th className="px-4 py-2 font-medium">Status</th>
              <th className="px-4 py-2 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {batch.documents.map((doc) => (
              <tr key={doc.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                {canEdit && (
                  <td className="px-4 py-2.5">
                    <input
                      type="checkbox"
                      aria-label={`Select document ${doc.id}`}
                      checked={selected.has(doc.id)}
                      onChange={() => toggle(doc.id)}
                      disabled={doc.status !== "extracted"}
                    />
                  </td>
                )}
                <td className="px-4 py-2.5">
                  <a href={`/documents/${doc.id}`} className="text-navy hover:underline">
                    {doc.original_filename}
                  </a>
                </td>
                <td className="px-4 py-2.5 text-xs">{doc.document_type ?? "—"}</td>
                <td className="px-4 py-2.5 text-xs">
                  {doc.classification_confidence !== null ? `${(doc.classification_confidence * 100).toFixed(0)}%` : "—"}
                </td>
                <td className="px-4 py-2.5">
                  <DocumentStatusBadge status={doc.status} isDuplicate={doc.is_duplicate} />
                </td>
                <td className="px-4 py-2.5 text-xs space-x-2">
                  {canEdit && doc.status === "failed" && (
                    <button onClick={() => handleRetry(doc.id)} className="text-navy hover:underline">
                      Retry
                    </button>
                  )}
                  {canEdit && doc.status !== "approved" && (
                    <button onClick={() => handleRemove(doc.id)} className="text-error hover:underline">
                      Remove
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
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
