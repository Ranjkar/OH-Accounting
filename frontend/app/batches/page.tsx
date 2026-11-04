"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, Batch, Company, LedgerSide } from "@/lib/api";

function BatchesContent() {
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [category, setCategory] = useState<LedgerSide | "all">("all");
  const [batches, setBatches] = useState<Batch[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  useEffect(() => {
    if (!token) return;
    api
      .listBatches(token, { company_id: companyId ? Number(companyId) : undefined, category: category === "all" ? undefined : category })
      .then(setBatches)
      .catch((e) => setError(e.message));
  }, [token, companyId, category]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-text-primary">Batch Processing</h1>
        <div className="flex gap-2">
          <Link href="/sales/upload" className="rounded-md bg-green-600 text-white px-4 py-2 text-sm font-medium hover:bg-green-700 transition-colors">
            Upload sales invoices
          </Link>
          <Link href="/purchases/upload" className="rounded-md bg-amber-600 text-white px-4 py-2 text-sm font-medium hover:bg-amber-700 transition-colors">
            Upload purchase invoices
          </Link>
        </div>
      </div>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="flex items-center gap-4">
        <select value={companyId} aria-label="Company" onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")} className="input-v2 px-3 py-2 text-sm">
          <option value="">All companies</option>
          {companies.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <div className="flex gap-2 text-sm">
          {(["all", "SALES", "PURCHASES"] as const).map((c) => (
            <button
              key={c}
              onClick={() => setCategory(c)}
              className={`rounded-full px-3 py-1 ${category === c ? "bg-navy-solid text-white" : "bg-surface-card border border-border text-text-secondary"}`}
            >
              {c === "all" ? "All" : c}
            </button>
          ))}
        </div>
      </div>

      <div className="card-v2 overflow-hidden">
        {batches.length === 0 ? (
          <p className="px-5 py-4 text-sm text-text-secondary">No batches yet.</p>
        ) : (
          <div className="overflow-x-auto">
          <table className="table-v3">
            <thead>
              <tr>
                <th>Uploaded</th>
                <th>Category</th>
                <th className="text-right">Total</th>
                <th className="text-right">Extracted</th>
                <th className="text-right">Needs review</th>
                <th className="text-right">Duplicates</th>
                <th className="text-right">Failed</th>
                <th className="text-right">Approved</th>
              </tr>
            </thead>
            <tbody>
              {batches.map((b) => (
                <tr key={b.id} className="hover:bg-muted">
                  <td>
                    <Link href={`/batches/${b.id}`} className="text-navy hover:underline">
                      {new Date(b.created_at).toLocaleString()}
                    </Link>
                  </td>
                  <td className="text-text-secondary">{b.category}</td>
                  <td className="text-right">{b.counts.total}</td>
                  <td className="text-right">{b.counts.extracted}</td>
                  <td className="text-right text-pending">{b.counts.needs_review}</td>
                  <td className="text-right text-error">{b.counts.duplicates}</td>
                  <td className="text-right text-error">{b.counts.failed}</td>
                  <td className="text-right text-approved">{b.counts.approved}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </div>
    </div>
  );
}

export default function BatchesPage() {
  return (
    <AuthGuard>
      <Shell>
        <BatchesContent />
      </Shell>
    </AuthGuard>
  );
}
