"use client";

import { FormEvent, Suspense, useEffect, useState, useId } from "react";
import { useParams, useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import DocumentStatusBadge from "@/components/DocumentStatusBadge";
import { useAuth } from "@/lib/auth-context";
import { api, Company, DocumentDetail, ExtractedFields, ValidationResult } from "@/lib/api";
import { formatEUR } from "@/lib/format";

const SEVERITY_STYLES: Record<ValidationResult["severity"], string> = {
  error: "bg-red-50 text-error border-red-200",
  warning: "bg-amber-50 text-pending border-amber-200",
  info: "bg-muted text-text-secondary border-border-subtle",
};

function FieldInput({
  label,
  value,
  onChange,
  type = "text",
  dir,
}: {
  label: string;
  value: string | number | null;
  onChange: (v: string) => void;
  type?: string;
  dir?: "ltr";
}) {
  const id = useId();
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="text-xs font-medium text-text-secondary">{label}</label>
      <input
        id={id}
        type={type}
        dir={dir}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        className="w-full input-v2 px-2.5 py-1.5 text-sm"
      />
    </div>
  );
}

function DocumentReviewContent({ documentId }: { documentId: number }) {
  const t = useTranslations("documents");
  const tCommon = useTranslations("common");
  const locale = useLocale();
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
      setError(err instanceof Error ? err.message : t("saveCorrectionsFailed"));
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
      setError(err instanceof Error ? err.message : t("approveFailed"));
    }
  }

  async function handleReject() {
    if (!token) return;
    const reason = window.prompt(t("reasonForRejection"));
    if (!reason) return;
    try {
      await api.rejectDocument(token, documentId, reason);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("rejectFailed"));
    }
  }

  async function handleReprocess() {
    if (!token) return;
    try {
      await api.reprocessDocument(token, documentId);
      setTimeout(refresh, 1500);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("reprocessFailed"));
    }
  }

  async function handleReassignCompany(newCompanyId: number) {
    if (!token) return;
    try {
      await api.reassignDocument(token, documentId, { company_id: newCompanyId });
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("reassignFailed"));
    }
  }

  if (!doc) return <p className="text-text-secondary">{tCommon("loading")}</p>;

  const isImage = doc.content_type.startsWith("image/");
  const isPdf = doc.content_type === "application/pdf";
  const isFinal = doc.status === "approved" || doc.status === "rejected";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <button onClick={() => router.push("/documents")} className="text-sm text-navy hover:underline">
            {t("backToDocuments")}
          </button>
          <h1 className="text-xl font-semibold text-navy mt-1">{doc.original_filename}</h1>
        </div>
        <DocumentStatusBadge status={doc.status} />
      </div>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      {doc.error_message && (
        <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">
          {t("processingError", { message: doc.error_message })}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: preview */}
        <div className="card-v2 overflow-hidden">
          <div className="px-4 py-3 border-b border-border-subtle flex items-center justify-between">
            <span className="text-sm font-medium text-navy">{t("originalDocument")}</span>
            <span className="text-xs text-text-secondary" dir="ltr">
              {doc.content_type} · {(doc.file_size / 1024).toFixed(0)} KB
            </span>
          </div>
          <div className="h-[60dvh] lg:h-[600px] bg-muted flex items-center justify-center">
            {!fileUrl && <p className="text-sm text-text-secondary">{t("loadingPreview")}</p>}
            {fileUrl && isPdf && <iframe src={fileUrl} className="w-full h-full" title={t("documentPreview")} />}
            {fileUrl && isImage && (
              <img src={fileUrl} alt={t("documentPreview")} className="max-w-full max-h-full object-contain" />
            )}
            {fileUrl && !isPdf && !isImage && (
              <a href={fileUrl} download className="text-navy hover:underline text-sm">
                {t("downloadFileToView")}
              </a>
            )}
          </div>
        </div>

        {/* Right: extracted fields + review */}
        <div className="space-y-4">
          <div className="card-v2 p-4 flex items-center justify-between">
            <div className="text-sm">
              <span className="text-text-secondary">{t("classification")}: </span>
              <span className="font-medium text-navy">{doc.document_type ?? t("unclassified")}</span>
            </div>
            {doc.classification_confidence !== null && (
              <span className="text-xs text-text-secondary">
                {t("confidence", { pct: (doc.classification_confidence * 100).toFixed(0) })}
              </span>
            )}
          </div>

          {doc.validation_results.length > 0 && (
            <div className="space-y-1.5">
              {doc.validation_results.map((v, i) => (
                <div key={i} className={`rounded-md border px-3 py-2 text-sm ${SEVERITY_STYLES[v.severity]}`}>
                  <span className="font-medium uppercase text-xs me-2">{t(`severity.${v.severity}` as never)}</span>
                  {v.message}
                </div>
              ))}
            </div>
          )}

          <form onSubmit={handleSaveCorrections} className="card-v2 p-4 space-y-4">
            <h2 className="text-sm font-medium text-text-primary">{t("extractedFields")}</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <FieldInput label={t("invoiceNumber")} value={form.invoice_number ?? null} onChange={(v) => setField("invoice_number", v)} />
              <FieldInput label={t("invoiceDate")} type="date" value={form.invoice_date ?? null} onChange={(v) => setField("invoice_date", v)} />
              <FieldInput label={t("dueDate")} type="date" value={form.due_date ?? null} onChange={(v) => setField("due_date", v)} />
              <FieldInput label={t("currency")} value={form.currency ?? null} onChange={(v) => setField("currency", v)} dir="ltr" />
              <FieldInput label={t("supplierName")} value={form.supplier_name ?? null} onChange={(v) => setField("supplier_name", v)} />
              <FieldInput label={t("supplierVatNumber")} value={form.supplier_vat_number ?? null} onChange={(v) => setField("supplier_vat_number", v)} dir="ltr" />
              <FieldInput label={t("customerName")} value={form.customer_name ?? null} onChange={(v) => setField("customer_name", v)} />
              <FieldInput label={t("customerVatNumber")} value={form.customer_vat_number ?? null} onChange={(v) => setField("customer_vat_number", v)} dir="ltr" />
              <FieldInput label={t("iban")} value={form.iban ?? null} onChange={(v) => setField("iban", v)} dir="ltr" />
              <FieldInput label={t("creditNoteReference")} value={form.credit_note_reference ?? null} onChange={(v) => setField("credit_note_reference", v)} dir="ltr" />
            </div>

            <h3 className="text-xs font-semibold text-text-secondary uppercase pt-2">{t("vatBreakdown")}</h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <FieldInput label={t("netAmount")} type="number" value={form.net_amount ?? null} onChange={(v) => setField("net_amount", v ? Number(v) : null)} />
              <FieldInput label={t("vatRatePct")} type="number" value={form.vat_rate ?? null} onChange={(v) => setField("vat_rate", v ? Number(v) : null)} />
              <FieldInput label={t("vatAmount")} type="number" value={form.vat_amount ?? null} onChange={(v) => setField("vat_amount", v ? Number(v) : null)} />
              <FieldInput label={t("grossAmount")} type="number" value={form.gross_amount ?? null} onChange={(v) => setField("gross_amount", v ? Number(v) : null)} />
            </div>

            <div className="space-y-1">
              <label htmlFor="doc-description" className="text-xs font-medium text-text-secondary">{tCommon("description")}</label>
              <textarea
                id="doc-description"
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
                {saving ? tCommon("saving") : t("saveCorrections")}
              </button>
            )}
          </form>

          {doc.line_items.length > 0 && (
            <div className="card-v2 p-4">
              <h2 className="text-sm font-medium text-text-primary mb-2">{t("lineItems")}</h2>
              <div className="overflow-x-auto" tabIndex={0}>
              <table className="table-v3">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>{tCommon("description")}</th>
                    <th className="text-right">{t("net")}</th>
                    <th className="text-right">{t("vat")}</th>
                    <th className="text-right">{t("gross")}</th>
                  </tr>
                </thead>
                <tbody>
                  {doc.line_items.map((li) => (
                    <tr key={li.line_number}>
                      <td className="text-text-secondary">{li.line_number}</td>
                      <td className="text-text-primary">{li.description ?? "—"}</td>
                      <td className="col-amount">{li.net_amount != null ? formatEUR(li.net_amount, locale) : "—"}</td>
                      <td className="col-amount">{li.vat_amount != null ? formatEUR(li.vat_amount, locale) : "—"}</td>
                      <td className="col-amount font-medium">{li.gross_amount != null ? formatEUR(li.gross_amount, locale) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            </div>
          )}

          {canEdit && (
            <div className="card-v2 p-4 space-y-3">
              <h2 className="text-sm font-medium text-text-primary">{tCommon("actions")}</h2>
              <div className="flex flex-wrap gap-2">
                {!isFinal && (
                  <>
                    <button onClick={handleApprove} className="rounded-md bg-green-600 text-white px-4 py-2 text-sm font-medium hover:bg-green-700 transition-colors">
                      {t("approve")}
                    </button>
                    <button onClick={handleReject} className="rounded-md bg-red-600 text-white px-4 py-2 text-sm font-medium hover:bg-red-700 transition-colors">
                      {t("reject")}
                    </button>
                  </>
                )}
                {doc.status !== "approved" && (
                  <button onClick={handleReprocess} className="input-v2 px-4 py-2 text-sm font-medium hover:bg-muted transition-colors">
                    {t("reprocess")}
                  </button>
                )}
              </div>
              <div className="flex items-center gap-2 pt-1">
                <label className="text-xs text-text-secondary">{t("reassignToCompany")}:</label>
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
