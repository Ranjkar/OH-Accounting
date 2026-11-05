"use client";

import { DragEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { useAuth } from "@/lib/auth-context";
import { api, Batch, Company, FinancialYear, LedgerSide } from "@/lib/api";

interface Props {
  category: LedgerSide;
  title: string;
  description: string;
  acceptHint: string;
}

export default function BulkUploadScreen({ category, title, description, acceptHint }: Props) {
  const { token } = useAuth();
  const router = useRouter();
  const t = useTranslations("invoices");
  const tCommon = useTranslations("common");
  const locale = useLocale();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [financialYears, setFinancialYears] = useState<FinancialYear[]>([]);
  const [financialYearId, setFinancialYearId] = useState<number | "">("");
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recentBatches, setRecentBatches] = useState<Batch[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  useEffect(() => {
    const load = token && companyId ? api.listFinancialYears(token, Number(companyId)) : Promise.resolve([]);
    load.then(setFinancialYears).catch((e) => setError(e.message));
  }, [token, companyId]);

  function refreshBatches() {
    if (!token || !companyId) return;
    api.listBatches(token, { company_id: Number(companyId), category }).then(setRecentBatches).catch(() => {});
  }

  useEffect(refreshBatches, [token, companyId, category]);

  function addFiles(newFiles: FileList | File[]) {
    setFiles((prev) => [...prev, ...Array.from(newFiles)]);
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
  }

  function removeFile(index: number) {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  }

  async function handleUpload() {
    if (!token || !companyId || !financialYearId || files.length === 0) {
      setError(t("selectRequired"));
      return;
    }
    setUploading(true);
    setError(null);
    try {
      const result = await api.uploadBatch(token, files, Number(companyId), Number(financialYearId), category);
      setFiles([]);
      router.push(`/batches/${result.batch.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("uploadFailed"));
    } finally {
      setUploading(false);
    }
  }

  const colorClass = category === "SALES" ? "border-green-300 bg-green-50" : "border-amber-300 bg-amber-50";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-text-primary">{title}</h1>
        <p className="text-sm text-text-secondary mt-1">{description}</p>
      </div>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="card-v2 p-5 space-y-4">
        <div className="grid grid-cols-2 gap-4 max-w-xl">
          <div className="space-y-1">
            <label className="text-xs font-medium text-text-secondary">{tCommon("company")}</label>
            <select
              value={companyId}
              aria-label={tCommon("company")}
              onChange={(e) => {
                setCompanyId(e.target.value ? Number(e.target.value) : "");
                setFinancialYearId("");
              }}
              className="w-full input-v2 px-2.5 py-1.5 text-sm"
            >
              <option value="">{t("selectPlaceholder")}</option>
              {companies.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-text-secondary">{t("financialYearLabel")}</label>
            <select
              value={financialYearId}
              aria-label={t("financialYearLabel")}
              onChange={(e) => setFinancialYearId(e.target.value ? Number(e.target.value) : "")}
              className="w-full input-v2 px-2.5 py-1.5 text-sm"
              disabled={!companyId}
            >
              <option value="">{t("selectPlaceholder")}</option>
              {financialYears.map((fy) => (
                <option key={fy.id} value={fy.id}>
                  {fy.year}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          className={`rounded-lg border-2 border-dashed p-8 text-center cursor-pointer transition-colors ${
            dragging ? colorClass : "border-border bg-muted"
          }`}
        >
          <p className="text-sm text-text-secondary">
            {t("dragDropFiles")} <span className="text-navy font-medium">{t("clickToSelect")}</span>
          </p>
          <p className="text-xs text-text-secondary mt-1">{acceptHint}</p>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".pdf,.jpg,.jpeg,.png,.xlsx,.csv"
            className="hidden"
            onChange={(e) => e.target.files && addFiles(e.target.files)}
          />
        </div>

        {files.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs font-medium text-text-secondary">{t("filesSelected", { count: files.length })}</p>
            <div className="divide-y divide-border border border-border rounded-md">
              {files.map((f, i) => (
                <div key={i} className="flex items-center justify-between px-3 py-2 text-sm">
                  <span className="text-text-primary">{f.name}</span>
                  <span className="text-xs text-text-secondary">{(f.size / 1024).toFixed(0)} KB</span>
                  <button onClick={() => removeFile(i)} className="text-xs text-error hover:underline ms-3">
                    {t("remove")}
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        <button
          onClick={handleUpload}
          disabled={uploading || files.length === 0}
          className="btn-primary-v2 px-4 py-2 text-sm disabled:opacity-50"
        >
          {uploading ? t("uploading") : t("uploadButton", { count: files.length || 0 })}
        </button>
      </div>

      <div className="card-v2 overflow-hidden">
        <div className="px-5 py-3 border-b border-border-subtle">
          <h2 className="text-sm font-medium text-text-primary">{t("recentBatches")}</h2>
        </div>
        {recentBatches.length === 0 ? (
          <p className="px-5 py-4 text-sm text-text-secondary">
            {companyId ? t("noBatchesYet") : t("selectCompanyToSeeBatches")}
          </p>
        ) : (
          <div className="divide-y divide-border">
            {recentBatches.map((b) => (
              <Link key={b.id} href={`/batches/${b.id}`} className="flex items-center justify-between px-5 py-3 hover:bg-muted">
                <span className="text-sm text-navy">{new Date(b.created_at).toLocaleString(locale)}</span>
                <span className="text-xs text-text-secondary">
                  {t("batchSummary", {
                    total: b.counts.total,
                    extracted: b.counts.extracted + b.counts.needs_review,
                    duplicates: b.counts.duplicates,
                    failed: b.counts.failed,
                    approved: b.counts.approved,
                  })}
                </span>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
