"use client";

import { ChangeEvent, useEffect, useState } from "react";
import Link from "next/link";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import DocumentStatusBadge from "@/components/DocumentStatusBadge";
import { useAuth } from "@/lib/auth-context";
import { api, Company, DocumentStatus, DocumentSummary } from "@/lib/api";

const STATUS_FILTERS: { value: DocumentStatus | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "needs_review", label: "Needs review" },
  { value: "extracted", label: "Ready for review" },
  { value: "approved", label: "Approved" },
  { value: "failed", label: "Failed" },
];

function DocumentsContent() {
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
      setError("Select a company before uploading.");
      return;
    }
    setUploading(true);
    setError(null);
    try {
      await api.uploadDocument(token, file, Number(companyId));
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-navy">Documents</h1>
        <label className="rounded-md bg-navy text-white px-4 py-2 text-sm font-medium hover:bg-navy-light transition-colors cursor-pointer">
          {uploading ? "Uploading…" : "Upload document"}
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

      <div className="flex items-center gap-4">
        <select
          value={companyId}
          onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm"
        >
          <option value="">All companies</option>
          {companies.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <div className="flex items-center gap-2 text-sm">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => setStatusFilter(f.value)}
              className={`rounded-full px-3 py-1 ${
                statusFilter === f.value
                  ? "bg-navy text-white"
                  : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <div className="bg-white rounded-lg border border-slate-200 divide-y divide-slate-100">
        {documents.length === 0 ? (
          <p className="px-5 py-4 text-sm text-slate-500">
            {companyId ? "No documents yet for this company." : "Select a company and upload a document to get started."}
          </p>
        ) : (
          documents.map((doc) => (
            <Link
              key={doc.id}
              href={`/documents/${doc.id}`}
              className="flex items-center justify-between px-5 py-3 hover:bg-slate-50"
            >
              <div>
                <p className="font-medium text-navy">{doc.original_filename}</p>
                <p className="text-sm text-slate-500">
                  {doc.document_type ?? "Unclassified"} ·{" "}
                  {new Date(doc.created_at).toLocaleString()}
                  {doc.is_duplicate && <span className="text-error"> · duplicate</span>}
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
