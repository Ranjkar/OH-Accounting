"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, Company, FinancialYear, VatReturn } from "@/lib/api";

function VatContent() {
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [financialYears, setFinancialYears] = useState<FinancialYear[]>([]);
  const [returns, setReturns] = useState<Record<number, VatReturn>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  useEffect(() => {
    const load = token && companyId ? api.listFinancialYears(token, Number(companyId)) : Promise.resolve([]);
    load.then(setFinancialYears).catch((e) => setError(e.message));
  }, [token, companyId]);

  useEffect(() => {
    if (!token || !companyId) return;
    financialYears.forEach((fy) => {
      fy.vat_periods.forEach((p) => {
        api
          .getOrComputeVatReturn(token, Number(companyId), p.id)
          .then((vr) => setReturns((prev) => ({ ...prev, [p.id]: vr })))
          .catch(() => {});
      });
    });
  }, [token, companyId, financialYears]);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-navy">VAT Overview</h1>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <select
        value={companyId}
        onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")}
        className="input-v2 px-3 py-2 text-sm"
      >
        <option value="">Select a company</option>
        {companies.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </select>

      {financialYears.map((fy) => (
        <div key={fy.id} className="card-v2">
          <div className="px-5 py-3 border-b border-border-subtle">
            <h2 className="text-sm font-medium text-navy">Financial year {fy.year}</h2>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-text-secondary border-b border-border-subtle">
                <th className="px-5 py-2 font-medium">Period</th>
                <th className="px-5 py-2 font-medium">Filing deadline</th>
                <th className="px-5 py-2 font-medium">VAT due (5a)</th>
                <th className="px-5 py-2 font-medium">Deductible (5b)</th>
                <th className="px-5 py-2 font-medium">Net payable</th>
                <th className="px-5 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {fy.vat_periods.map((p) => {
                const vr = returns[p.id];
                return (
                  <tr key={p.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                    <td className="px-5 py-2.5">
                      {vr ? (
                        <Link href={`/vat/${vr.id}`} className="text-navy hover:underline">
                          {p.label}
                        </Link>
                      ) : (
                        p.label
                      )}
                    </td>
                    <td className="px-5 py-2.5">{p.filing_deadline}</td>
                    <td className="px-5 py-2.5">{vr?.box_5a_vat ?? "—"}</td>
                    <td className="px-5 py-2.5">{vr?.box_5b_vat ?? "—"}</td>
                    <td className="px-5 py-2.5 font-medium">{vr?.net_payable ?? "—"}</td>
                    <td className="px-5 py-2.5 text-xs uppercase text-text-secondary">{vr?.status.replaceAll("_", " ") ?? "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}

export default function VatPage() {
  return (
    <AuthGuard>
      <Shell>
        <VatContent />
      </Shell>
    </AuthGuard>
  );
}
