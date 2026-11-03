"use client";

import { useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, Company, JsonReport } from "@/lib/api";

function OptionCard({ title, total_tax, net_result, highlight }: { title: string; total_tax: string; net_result: string; highlight: boolean }) {
  return (
    <div className={`card-v2 p-4 ${highlight ? "border-2 border-brand-purple-500" : ""}`}>
      <p className="text-xs text-text-secondary">{title}</p>
      <p className="text-2xl font-semibold text-text-primary font-mono">{total_tax}</p>
      <p className="text-xs text-text-secondary">estimated tax</p>
      <p className="text-sm font-mono mt-2">{net_result}</p>
      <p className="text-xs text-text-secondary">net result</p>
      {highlight && <p className="text-xs text-brand-purple-600 mt-2 font-medium">Lowest estimated tax</p>}
    </div>
  );
}

function LegalStructureContent() {
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [annualRevenue, setAnnualRevenue] = useState("200000");
  const [annualExpenses, setAnnualExpenses] = useState("50000");
  const [result, setResult] = useState<JsonReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  async function compare() {
    if (!token || !companyId) return;
    try {
      setResult(await api.structureComparison(token, Number(companyId), annualRevenue, annualExpenses));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-text-primary">Legal Structure Calculator</h1>
      <p className="text-sm text-text-secondary">
        Compares estimated tax under simplified assumptions for one tax year. This never claims one structure is
        always best, and never writes to any real company or ledger record -- it&apos;s a planning aid only.
      </p>
      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="flex items-end gap-3">
        <select value={companyId} aria-label="Company" onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")} className="input-v2 px-3 py-2 text-sm">
          <option value="">Select a company</option>
          {companies.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <input value={annualRevenue} aria-label="Annual Revenue" onChange={(e) => setAnnualRevenue(e.target.value)} placeholder="Annual revenue" className="input-v2 px-3 py-2 text-sm w-40" />
        <input value={annualExpenses} aria-label="Annual Expenses" onChange={(e) => setAnnualExpenses(e.target.value)} placeholder="Annual operating expenses" className="input-v2 px-3 py-2 text-sm w-48" />
        <button onClick={compare} disabled={!companyId} className="btn-primary-v2 px-4 py-2 text-sm disabled:opacity-50">
          Compare
        </button>
      </div>

      {result && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <OptionCard title="Eenmanszaak" total_tax={result.eenmanszaak.total_tax} net_result={result.eenmanszaak.net_result} highlight={result.lowest_total_tax_option === "eenmanszaak"} />
            <OptionCard title="VOF (equal split)" total_tax={result.vof.total_tax} net_result={result.vof.net_result} highlight={result.lowest_total_tax_option === "vof"} />
            <OptionCard title="BV" total_tax={result.bv.total_tax} net_result={result.bv.net_result} highlight={result.lowest_total_tax_option === "bv"} />
          </div>
          <div className="card-v2 p-4">
            <h2 className="font-medium text-text-primary mb-2">BV detail</h2>
            <p className="text-sm">DGA salary used: <span className="font-mono">{result.bv.dga_salary_used}</span></p>
            <p className="text-sm">
              Salary compliant with gebruikelijk loon: {result.bv.dga_salary_check.compliant ? "Yes" : `No -- required minimum ${result.bv.dga_salary_check.required_minimum}`}
            </p>
            <p className="text-sm">Corporate tax: <span className="font-mono">{result.bv.corporate_tax}</span></p>
            <p className="text-sm">Retained profit after corporate tax: <span className="font-mono">{result.bv.retained_profit_after_corporate_tax}</span></p>
          </div>
          <p className="text-xs text-amber-600">{result.disclaimer}</p>
        </>
      )}
    </div>
  );
}

export default function LegalStructurePage() {
  return (
    <AuthGuard>
      <Shell>
        <LegalStructureContent />
      </Shell>
    </AuthGuard>
  );
}
