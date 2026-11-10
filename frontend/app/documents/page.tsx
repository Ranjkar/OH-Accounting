"use client";

import { ChangeEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import DocumentStatusBadge from "@/components/DocumentStatusBadge";
import { useAuth } from "@/lib/auth-context";
import { api, Company, DocumentStatus, DocumentSummary } from "@/lib/api";

const STATUS_FILTERS: { value: DocumentStatus | "all"; key: string }[] = [
  { value: "all", key: "all" },
  { value: "needs_review", key: "needsReview" },
  { value: "extracted", key: "readyForReview" },
  { value: "approved", key: "approved" },
  { value: "failed", key: "failed" },
];

function DocumentsContent() {
  const t = useTranslations("documents");
  const locale = useLocale();
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [statusFilter, setStatusFilter] = useState<DocumentStatus | "all">("all");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    if (!token) return;
    api
      .listDocuments(token, {
        company_id: companyId ? Number(companyId) : undefined,
        status_filter: statusFilter === "all" ? undefined : statusFilter,
      })
      .then(setDocuments)
      .catch((e) => setError(e.message));
  }

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  useEffect(refresh, [token, companyId, statusFilter]);

  async function handleUpload(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || !token) return;
    if (!companyId) {
      setError(t("selectCompanyFirst"));
      return;
    }
    setUploading(true);
    setError(null);
    try {
      await api.uploadDocument(token, file, Number(companyId));
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("uploadFailed"));
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold text-text-primary">{t("title")}</h1>
        <label className="btn-primary-v2 px-4 py-2 text-sm cursor-pointer">
          {uploading ? t("uploading") : t("uploadDocument")}
          <input
            type="file"
            accept=".pdf,.jpg,.jpeg,.png,.xlsx,.csv"
            className="hidden"
            disabled={uploading}
            onChange={handleUpload}
          />
        </label>
      </div>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="flex flex-wrap items-center gap-3 sm:gap-4">
        <select
          value={companyId}
          aria-label={t("companyLabel")}
          onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")}
          className="input-v2 px-3 py-2 text-sm"
        >
          <option value="">{t("allCompanies")}</option>
          {companies.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => setStatusFilter(f.value)}
              className={`rounded-full px-3 py-1 ${
                statusFilter === f.value
                  ? "bg-navy-solid text-white"
                  : "bg-surface-card border border-border text-text-secondary hover:bg-muted"
              }`}
            >
              {t(`statusFilters.${f.key}` as never)}
            </button>
          ))}
        </div>
      </div>

      <div className="card-v2 divide-y divide-border">
        {documents.length === 0 ? (
          <p className="px-5 py-4 text-sm text-text-secondary">
            {companyId ? t("noDocumentsForCompany") : t("selectAndUploadToStart")}
          </p>
        ) : (
          documents.map((doc) => (
            <Link
              key={doc.id}
              href={`/documents/${doc.id}`}
              className="flex items-center justify-between px-5 py-3 hover:bg-muted"
            >
              <div>
                <p className="font-medium text-navy">{doc.original_filename}</p>
                <p className="text-sm text-text-secondary">
                  {doc.document_type ?? t("unclassified")} ·{" "}
                  {new Date(doc.created_at).toLocaleString(locale)}
                  {doc.is_duplicate && <span className="text-error"> · {t("duplicate")}</span>}
                </p>
              </div>
              <DocumentStatusBadge status={doc.status} />
            </Link>
          ))
        )}
      </div>
    </div>
  );
}

export default function DocumentsPage() {
  return (
    <AuthGuard>
      <Shell>
        <DocumentsContent />
      </Shell>
    </AuthGuard>
  );
}
