"use client";

import { FormEvent, Suspense, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import DocumentStatusBadge from "@/components/DocumentStatusBadge";
import { useAuth } from "@/lib/auth-context";
import { api, Company, DocumentDetail, ExtractedFields, ValidationResult } from "@/lib/api";

const SEVERITY_STYLES: Record<ValidationResult["severity"], string> = {
  error: "bg-red-50 text-error border-red-200",
  warning: "bg-amber-50 text-pending border-amber-200",
  info: "bg-slate-50 text-slate-600 border-border-subtle",
};

function FieldInput({
  label,
  value,
  onChange,
  type = "text",
}: {
  label: string;
  value: string | number | null;
  onChange: (v: string) => void;
  type?: string;
}) {
  return (
    <div className="space-y-1">
      <label className="text-xs font-medium text-text-secondary">{label}</label>
      <input
        type={type}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        className="w-full input-v2 px-2.5 py-1.5 text-sm"
      />
    </div>
  );
}

function DocumentReviewContent({ documentId }: { documentId: number }) {
  const { token, user } = useAuth();
  const router = useRouter();
  const canEdit = user?.role === "admin" || user?.role === "accountant";

  const [doc, setDocument] = useState<DocumentDetail | null>(null);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [form, setForm] = useState<Partial<ExtractedFields>>({});
  const [fileUrl, setFileUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  function refresh() {
    if (!token) return;
    api
      .getDocument(token, documentId)
      .then((result) => {
        setDocument(result);
        setForm(result.fields ?? {});
      })
      .catch((e) => setError(e.message));
  }

  useEffect(refresh, [token, documentId]);
  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch(() => {});
  }, [token]);

  useEffect(() => {
    if (!token) return;
    let url: string | null = null;
    api
      .documentFileBlobUrl(token, documentId)
      .then((u) => {
        url = u;
        setFileUrl(u);
      })
      .catch(() => {});
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [token, documentId]);

  function setField<K extends keyof ExtractedFields>(key: K, value: ExtractedFields[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function handleSaveCorrections(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setSaving(true);
    setError(null);
    try {
      await api.updateDocumentFields(token, documentId, form);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save corrections");
    } finally {
      setSaving(false);
    }
  }

  async function handleApprove() {
    if (!token) return;
    try {
      await api.approveDocument(token, documentId);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to approve");
    }
  }

  async function handleReject() {
    if (!token) return;
    const reason = window.prompt("Reason for rejection:");
    if (!reason) return;
    try {
      await api.rejectDocument(token, documentId, reason);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reject");
    }
  }

  async function handleReprocess() {
    if (!token) return;
    try {
      await api.reprocessDocument(token, documentId);
      setTimeout(refresh, 1500);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reprocess");
    }
  }

  async function handleReassignCompany(newCompanyId: number) {
    if (!token) return;
    try {
      await api.reassignDocument(token, documentId, { company_id: newCompanyId });
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reassign");
    }
  }

  if (!doc) return <p className="text-text-secondary">Loading…</p>;

  const isImage = doc.content_type.startsWith("image/");
  const isPdf = doc.content_type === "application/pdf";
  const isFinal = doc.status === "approved" || doc.status === "rejected";

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <button onClick={() => router.push("/documents")} className="text-sm text-navy hover:underline">
            ← Back to documents
          </button>
          <h1 className="text-xl font-semibold text-navy mt-1">{doc.original_filename}</h1>
        </div>
        <DocumentStatusBadge status={doc.status} />
      </div>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      {doc.error_message && (
        <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">
          Processing error: {doc.error_message}
        </div>
      )}

      <div className="grid grid-cols-2 gap-6">
        {/* Left: preview */}
        <div className="card-v2 overflow-hidden">
          <div className="px-4 py-3 border-b border-border-subtle flex items-center justify-between">
            <span className="text-sm font-medium text-navy">Original document</span>
            <span className="text-xs text-text-secondary">
              {doc.content_type} · {(doc.file_size / 1024).toFixed(0)} KB
            </span>
          </div>
          <div className="h-[600px] bg-slate-100 flex items-center justify-center">
            {!fileUrl && <p className="text-sm text-text-secondary">Loading preview…</p>}
            {fileUrl && isPdf && <iframe src={fileUrl} className="w-full h-full" title="document preview" />}
            {fileUrl && isImage && (
              <img src={fileUrl} alt="document preview" className="max-w-full max-h-full object-contain" />
            )}
            {fileUrl && !isPdf && !isImage && (
              <a href={fileUrl} download className="text-navy hover:underline text-sm">
                Download file to view
              </a>
            )}
          </div>
        </div>

        {/* Right: extracted fields + review */}
        <div className="space-y-4">
          <div className="card-v2 p-4 flex items-center justify-between">
            <div className="text-sm">
              <span className="text-text-secondary">Classification: </span>
              <span className="font-medium text-navy">{doc.document_type ?? "Unclassified"}</span>
            </div>
            {doc.classification_confidence !== null && (
              <span className="text-xs text-text-secondary">
                Confidence: {(doc.classification_confidence * 100).toFixed(0)}%
              </span>
            )}
          </div>

          {doc.validation_results.length > 0 && (
            <div className="space-y-1.5">
              {doc.validation_results.map((v, i) => (
                <div key={i} className={`rounded-md border px-3 py-2 text-sm ${SEVERITY_STYLES[v.severity]}`}>
                  <span className="font-medium uppercase text-xs mr-2">{v.severity}</span>
                  {v.message}
                </div>
              ))}
            </div>
          )}

          <form onSubmit={handleSaveCorrections} className="card-v2 p-4 space-y-4">
            <h2 className="text-sm font-medium text-navy">Extracted fields</h2>
            <div className="grid grid-cols-2 gap-3">
              <FieldInput label="Invoice number" value={form.invoice_number ?? null} onChange={(v) => setField("invoice_number", v)} />
              <FieldInput label="Invoice date" type="date" value={form.invoice_date ?? null} onChange={(v) => setField("invoice_date", v)} />
              <FieldInput label="Due date" type="date" value={form.due_date ?? null} onChange={(v) => setField("due_date", v)} />
              <FieldInput label="Currency" value={form.currency ?? null} onChange={(v) => setField("currency", v)} />
              <FieldInput label="Supplier name" value={form.supplier_name ?? null} onChange={(v) => setField("supplier_name", v)} />
              <FieldInput label="Supplier VAT number" value={form.supplier_vat_number ?? null} onChange={(v) => setField("supplier_vat_number", v)} />
              <FieldInput label="Customer name" value={form.customer_name ?? null} onChange={(v) => setField("customer_name", v)} />
              <FieldInput label="Customer VAT number" value={form.customer_vat_number ?? null} onChange={(v) => setField("customer_vat_number", v)} />
              <FieldInput label="IBAN" value={form.iban ?? null} onChange={(v) => setField("iban", v)} />
              <FieldInput label="Credit note reference" value={form.credit_note_reference ?? null} onChange={(v) => setField("credit_note_reference", v)} />
            </div>

            <h3 className="text-xs font-semibold text-text-secondary uppercase pt-2">VAT breakdown</h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <FieldInput label="Net amount" type="number" value={form.net_amount ?? null} onChange={(v) => setField("net_amount", v ? Number(v) : null)} />
              <FieldInput label="VAT rate %" type="number" value={form.vat_rate ?? null} onChange={(v) => setField("vat_rate", v ? Number(v) : null)} />
              <FieldInput label="VAT amount" type="number" value={form.vat_amount ?? null} onChange={(v) => setField("vat_amount", v ? Number(v) : null)} />
              <FieldInput label="Gross amount" type="number" value={form.gross_amount ?? null} onChange={(v) => setField("gross_amount", v ? Number(v) : null)} />
            </div>

            <div className="space-y-1">
              <label className="text-xs font-medium text-text-secondary">Description</label>
              <textarea
                value={form.description ?? ""}
                onChange={(e) => setField("description", e.target.value)}
                className="w-full input-v2 px-2.5 py-1.5 text-sm"
                rows={2}
              />
            </div>

            {canEdit && !isFinal && (
              <button
                type="submit"
                disabled={saving}
                className="btn-primary-v2 px-4 py-2 text-sm disabled:opacity-50"
              >
                {saving ? "Saving…" : "Save corrections"}
              </button>
            )}
          </form>

          {doc.line_items.length > 0 && (
            <div className="card-v2 p-4">
              <h2 className="text-sm font-medium text-navy mb-2">Line items</h2>
              <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-text-secondary border-b border-border-subtle">
                    <th className="py-1.5 font-medium">#</th>
                    <th className="py-1.5 font-medium">Description</th>
                    <th className="py-1.5 font-medium">Net</th>
                    <th className="py-1.5 font-medium">VAT</th>
                    <th className="py-1.5 font-medium">Gross</th>
                  </tr>
                </thead>
                <tbody>
                  {doc.line_items.map((li) => (
                    <tr key={li.line_number} className="border-b border-slate-100 last:border-0">
                      <td className="py-1.5">{li.line_number}</td>
                      <td className="py-1.5">{li.description ?? "—"}</td>
                      <td className="py-1.5">{li.net_amount ?? "—"}</td>
                      <td className="py-1.5">{li.vat_amount ?? "—"}</td>
                      <td className="py-1.5">{li.gross_amount ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            </div>
          )}

          {canEdit && (
            <div className="card-v2 p-4 space-y-3">
              <h2 className="text-sm font-medium text-navy">Actions</h2>
              <div className="flex flex-wrap gap-2">
                {!isFinal && (
                  <>
                    <button onClick={handleApprove} className="rounded-md bg-green-600 text-white px-4 py-2 text-sm font-medium hover:bg-green-700 transition-colors">
                      Approve
                    </button>
                    <button onClick={handleReject} className="rounded-md bg-red-600 text-white px-4 py-2 text-sm font-medium hover:bg-red-700 transition-colors">
                      Reject
                    </button>
                  </>
                )}
                {doc.status !== "approved" && (
                  <button onClick={handleReprocess} className="input-v2 px-4 py-2 text-sm font-medium hover:bg-slate-50 transition-colors">
                    Reprocess
                  </button>
                )}
              </div>
              <div className="flex items-center gap-2 pt-1">
                <label className="text-xs text-text-secondary">Reassign to company:</label>
                <select
                  value={doc.company_id}
                  onChange={(e) => handleReassignCompany(Number(e.target.value))}
                  className="input-v2 px-2 py-1 text-sm"
                >
                  {companies.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function DocumentReviewRoute() {
  const params = useParams<{ id: string }>();
  return (
    <AuthGuard>
      <Shell>
        <DocumentReviewContent documentId={Number(params.id)} />
      </Shell>
    </AuthGuard>
  );
}

export default function DocumentReviewPage() {
  return (
    <Suspense>
      <DocumentReviewRoute />
    </Suspense>
  );
}
