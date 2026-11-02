"use client";

import { FormEvent, Suspense, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import StatusBadge from "@/components/StatusBadge";
import { useAuth } from "@/lib/auth-context";
import { api, Company, FinancialYear, VatAccountingBasis } from "@/lib/api";

function CompanyDetailContent({ companyId }: { companyId: number }) {
  const { token, user } = useAuth();
  const canEdit = user?.role === "admin";
  const [company, setCompany] = useState<Company | null>(null);
  const [years, setYears] = useState<FinancialYear[]>([]);
  const [newYear, setNewYear] = useState(new Date().getFullYear());
  const [error, setError] = useState<string | null>(null);
  const [proRata, setProRata] = useState("");

  function refresh() {
    if (!token) return;
    api.getCompany(token, companyId).then((c) => {
      setCompany(c);
      setProRata(c.input_vat_pro_rata_percentage ?? "");
    }).catch((e) => setError(e.message));
    api.listFinancialYears(token, companyId).then(setYears).catch((e) => setError(e.message));
  }

  useEffect(refresh, [token, companyId]);

  async function handleAddYear(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setError(null);
    try {
      await api.createFinancialYear(token, companyId, newYear);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create financial year");
    }
  }

  async function handleBasisChange(basis: VatAccountingBasis) {
    if (!token) return;
    try {
      await api.updateCompany(token, companyId, { vat_accounting_basis: basis });
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update VAT accounting basis");
    }
  }

  async function handleProRataSave() {
    if (!token) return;
    try {
      await api.updateCompany(token, companyId, {
        input_vat_pro_rata_percentage: proRata === "" ? null : Number(proRata),
      });
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update pro-rata percentage");
    }
  }

  if (!company) return <p className="text-slate-500">Loading…</p>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-navy">{company.name}</h1>
          <p className="text-sm text-slate-500">
            {company.kvk_number ? `KVK ${company.kvk_number}` : "No KVK number"} ·{" "}
            {company.vat_number ?? "No VAT number"} · {company.vat_frequency} filing
          </p>
        </div>
        <a
          href={`/companies/${companyId}/workspace`}
          className="rounded-md bg-navy text-white px-4 py-2 text-sm font-medium hover:bg-navy-light transition-colors"
        >
          Open workspace
        </a>
      </div>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="bg-white rounded-lg border border-slate-200 p-4 flex items-end gap-6">
        <div className="space-y-1">
          <label className="text-xs font-medium text-slate-500">VAT accounting basis</label>
          <select
            disabled={!canEdit}
            value={company.vat_accounting_basis}
            onChange={(e) => handleBasisChange(e.target.value as VatAccountingBasis)}
            className="rounded-md border border-slate-300 px-2.5 py-1.5 text-sm disabled:bg-slate-50"
          >
            <option value="invoice_based">Invoice-based</option>
            <option value="cash_based">Cash-based</option>
          </select>
        </div>
        <div className="space-y-1">
          <label className="text-xs font-medium text-slate-500">Input VAT pro-rata % (mixed activities)</label>
          <div className="flex gap-2">
            <input
              disabled={!canEdit}
              value={proRata}
              onChange={(e) => setProRata(e.target.value)}
              placeholder="e.g. 80"
              className="w-24 rounded-md border border-slate-300 px-2.5 py-1.5 text-sm disabled:bg-slate-50"
            />
            {canEdit && (
              <button
                onClick={handleProRataSave}
                className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50 transition-colors"
              >
                Save
              </button>
            )}
          </div>
        </div>
      </div>

      <form onSubmit={handleAddYear} className="flex items-end gap-3">
        <div className="space-y-1">
          <label className="text-sm font-medium text-slate-700">Add financial year</label>
          <input
            type="number"
            value={newYear}
            onChange={(e) => setNewYear(Number(e.target.value))}
            className="w-32 rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
        </div>
        <button
          type="submit"
          className="rounded-md bg-navy text-white px-4 py-2 text-sm font-medium hover:bg-navy-light transition-colors"
        >
          Generate VAT periods
        </button>
      </form>

      <div className="space-y-6">
        {years.map((fy) => (
          <div key={fy.id} className="bg-white rounded-lg border border-slate-200">
            <div className="px-5 py-4 border-b border-slate-200">
              <h2 className="font-medium text-navy">Financial year {fy.year}</h2>
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-slate-500 border-b border-slate-200">
                  <th className="px-5 py-2 font-medium">Period</th>
                  <th className="px-5 py-2 font-medium">Start</th>
                  <th className="px-5 py-2 font-medium">End</th>
                  <th className="px-5 py-2 font-medium">Filing deadline</th>
                  <th className="px-5 py-2 font-medium">Payment deadline</th>
                  <th className="px-5 py-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {fy.vat_periods.map((p) => (
                  <tr key={p.id} className="border-b border-slate-100 last:border-0">
                    <td className="px-5 py-2.5">{p.label}</td>
                    <td className="px-5 py-2.5">{p.start_date}</td>
                    <td className="px-5 py-2.5">{p.end_date}</td>
                    <td className="px-5 py-2.5">{p.filing_deadline}</td>
                    <td className="px-5 py-2.5">{p.payment_deadline}</td>
                    <td className="px-5 py-2.5">
                      <StatusBadge status={p.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </div>
    </div>
  );
}

function CompanyDetailRoute() {
  const params = useParams<{ id: string }>();
  const companyId = Number(params.id);

  return (
    <AuthGuard>
      <Shell>
        <CompanyDetailContent companyId={companyId} />
      </Shell>
    </AuthGuard>
  );
}

export default function CompanyDetailPage() {
  return (
    <Suspense>
      <CompanyDetailRoute />
    </Suspense>
  );
}
