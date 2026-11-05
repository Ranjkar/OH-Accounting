"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, Batch, Company, LedgerSide } from "@/lib/api";

function BatchesContent() {
  const t = useTranslations("batches");
  const tCommon = useTranslations("common");
  const locale = useLocale();
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
        <h1 className="text-2xl font-semibold text-text-primary">{t("title")}</h1>
        <div className="flex gap-2">
          <Link href="/sales/upload" className="rounded-md bg-green-600 text-white px-4 py-2 text-sm font-medium hover:bg-green-700 transition-colors">
            {t("uploadSalesInvoices")}
          </Link>
          <Link href="/purchases/upload" className="rounded-md bg-amber-600 text-white px-4 py-2 text-sm font-medium hover:bg-amber-700 transition-colors">
            {t("uploadPurchaseInvoices")}
          </Link>
        </div>
      </div>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="flex items-center gap-4">
        <select value={companyId} aria-label={tCommon("company")} onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")} className="input-v2 px-3 py-2 text-sm">
          <option value="">{tCommon("allCompanies")}</option>
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
              {c === "all" ? t("categoryAll") : c}
            </button>
          ))}
        </div>
      </div>

      <div className="card-v2 overflow-hidden">
        {batches.length === 0 ? (
          <p className="px-5 py-4 text-sm text-text-secondary">{t("noBatchesYet")}</p>
        ) : (
          <div className="overflow-x-auto">
          <table className="table-v3">
            <thead>
              <tr>
                <th>{t("uploaded")}</th>
                <th>{t("category")}</th>
                <th className="text-right">{tCommon("total")}</th>
                <th className="text-right">{t("extracted")}</th>
                <th className="text-right">{t("needsReview")}</th>
                <th className="text-right">{t("duplicates")}</th>
                <th className="text-right">{t("failed")}</th>
                <th className="text-right">{t("approved")}</th>
              </tr>
            </thead>
            <tbody>
              {batches.map((b) => (
                <tr key={b.id} className="hover:bg-muted">
                  <td>
                    <Link href={`/batches/${b.id}`} className="text-navy hover:underline">
                      {new Date(b.created_at).toLocaleString(locale)}
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
