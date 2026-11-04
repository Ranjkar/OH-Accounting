"use client";

import { DragEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
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
      setError("Select a company, financial year, and at least one file.");
      return;
    }
    setUploading(true);
    setError(null);
    try {
      const result = await api.uploadBatch(token, files, Number(companyId), Number(financialYearId), category);
      setFiles([]);
      router.push(`/batches/${result.batch.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  const colorClass = category === "SALES" ? "border-green-300 bg-green-50" : "border-amber-300 bg-amber-50";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-navy">{title}</h1>
        <p className="text-sm text-slate-500 mt-1">{description}</p>
      </div>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="bg-white rounded-lg border border-slate-200 p-5 space-y-4">
        <div className="grid grid-cols-2 gap-4 max-w-xl">
          <div className="space-y-1">
            <label className="text-xs font-medium text-slate-500">Company</label>
            <select
              value={companyId}
              onChange={(e) => {
                setCompanyId(e.target.value ? Number(e.target.value) : "");
                setFinancialYearId("");
              }}
              className="w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-sm"
            >
              <option value="">Select…</option>
              {companies.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-slate-500">Financial year</label>
            <select
              value={financialYearId}
              onChange={(e) => setFinancialYearId(e.target.value ? Number(e.target.value) : "")}
              className="w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-sm"
              disabled={!companyId}
            >
              <option value="">Select…</option>
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
            dragging ? colorClass : "border-slate-300 bg-slate-50"
          }`}
        >
          <p className="text-sm text-slate-600">
            Drag and drop files here, or <span className="text-navy font-medium">click to select</span>
          </p>
          <p className="text-xs text-slate-400 mt-1">{acceptHint}</p>
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
            <p className="text-xs font-medium text-slate-500">{files.length} file(s) selected</p>
            <div className="divide-y divide-slate-100 border border-slate-200 rounded-md">
              {files.map((f, i) => (
                <div key={i} className="flex items-center justify-between px-3 py-2 text-sm">
                  <span className="text-slate-700">{f.name}</span>
                  <span className="text-xs text-slate-400">{(f.size / 1024).toFixed(0)} KB</span>
                  <button onClick={() => removeFile(i)} className="text-xs text-error hover:underline ml-3">
                    Remove
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        <button
          onClick={handleUpload}
          disabled={uploading || files.length === 0}
          className="rounded-md bg-navy-solid text-white px-4 py-2 text-sm font-medium hover:bg-navy-solid-hover transition-colors disabled:opacity-50"
        >
          {uploading ? "Uploading…" : `Upload ${files.length || ""} file${files.length === 1 ? "" : "s"}`}
        </button>
      </div>

      <div className="bg-white rounded-lg border border-slate-200">
        <div className="px-5 py-3 border-b border-slate-200">
          <h2 className="text-sm font-medium text-navy">Recent batches</h2>
        </div>
        {recentBatches.length === 0 ? (
          <p className="px-5 py-4 text-sm text-slate-500">
            {companyId ? "No batches yet for this company." : "Select a company to see recent batches."}
          </p>
        ) : (
          <div className="divide-y divide-slate-100">
            {recentBatches.map((b) => (
              <Link key={b.id} href={`/batches/${b.id}`} className="flex items-center justify-between px-5 py-3 hover:bg-slate-50">
                <span className="text-sm text-navy">{new Date(b.created_at).toLocaleString()}</span>
                <span className="text-xs text-slate-500">
                  {b.counts.total} files · {b.counts.extracted + b.counts.needs_review} extracted ·{" "}
                  {b.counts.duplicates} duplicates · {b.counts.failed} failed · {b.counts.approved} approved
                </span>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
