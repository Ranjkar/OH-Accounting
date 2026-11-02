"use client";

import { useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, CashFlowForecast, Company } from "@/lib/api";

function CashFlowContent() {
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [forecast, setForecast] = useState<CashFlowForecast | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  useEffect(() => {
    if (!token || !companyId) return;
    api.cashFlowForecast(token, Number(companyId)).then(setForecast).catch((e) => setError(e.message));
  }, [token, companyId]);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-navy">Cash Flow</h1>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <select
        value={companyId}
        onChange={(e) => {
          setCompanyId(e.target.value ? Number(e.target.value) : "");
          if (!e.target.value) setForecast(null);
        }}
        className="rounded-md border border-slate-300 px-3 py-2 text-sm"
      >
        <option value="">Select a company</option>
        {companies.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </select>

      {forecast && (
        <>
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-white rounded-lg border border-slate-200 p-4">
              <p className="text-xs text-slate-500">Actual -- net bank movement to date</p>
              <p className="text-2xl font-semibold text-navy font-mono">{forecast.net_bank_transaction_movement}</p>
              <p className="text-xs text-amber-600 mt-1">{forecast.net_bank_transaction_movement_disclaimer}</p>
            </div>
            <div className="bg-white rounded-lg border border-slate-200 p-4">
              <p className="text-xs text-slate-500">Confirmed -- outstanding invoices</p>
              <p className="text-sm">
                {forecast.outstanding_sales_invoice_count} sales / {forecast.outstanding_purchase_invoice_count} purchase
              </p>
              <p className="text-sm font-mono mt-1">
                +{forecast.expected_incoming_total} / -{forecast.expected_outgoing_total}
              </p>
            </div>
            <div className="bg-white rounded-lg border border-slate-200 p-4">
              <p className="text-xs text-slate-500">AI-estimated -- recurring expenses</p>
              <p className="text-sm font-mono">{forecast.recurring_expenses_monthly_equivalent} / month</p>
              <p className="text-xs text-slate-400">{forecast.recurring_pattern_count} pattern(s) detected</p>
            </div>
          </div>

          <div className="bg-white rounded-lg border border-slate-200 p-4">
            <p className="text-sm font-medium text-navy">Forecast VAT position</p>
            <p className="text-sm font-mono mt-1">
              Payable: {forecast.forecast_vat_payable} · Refundable: {forecast.forecast_vat_refundable}
            </p>
            <p className="text-xs text-amber-600 mt-1">{forecast.forecast_vat_disclaimer}</p>
          </div>

          <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
            <div className="p-4 pb-0 flex items-center justify-between">
              <h2 className="font-medium text-navy">Monthly projection</h2>
              <span className="text-xs bg-amber-100 text-amber-700 rounded-full px-2 py-0.5">Estimate, not a confirmed balance</span>
            </div>
            <table className="w-full text-sm mt-2">
              <thead>
                <tr className="text-left text-slate-500 border-b border-slate-200">
                  <th className="px-4 py-2 font-medium">Month</th>
                  <th className="px-4 py-2 font-medium">Expected incoming</th>
                  <th className="px-4 py-2 font-medium">Expected outgoing</th>
                  <th className="px-4 py-2 font-medium">Net</th>
                </tr>
              </thead>
              <tbody>
                {forecast.monthly_projection.map((m) => (
                  <tr key={m.month} className="border-b border-slate-100 last:border-0">
                    <td className="px-4 py-2.5">{m.month}</td>
                    <td className="px-4 py-2.5 font-mono text-green-700">+{m.expected_incoming}</td>
                    <td className="px-4 py-2.5 font-mono text-error">-{m.expected_outgoing}</td>
                    <td className="px-4 py-2.5 font-mono">{m.net}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="text-xs text-slate-400 p-4 pt-2">{forecast.monthly_projection_disclaimer}</p>
          </div>
        </>
      )}
    </div>
  );
}

export default function CashFlowPage() {
  return (
    <AuthGuard>
      <Shell>
        <CashFlowContent />
      </Shell>
    </AuthGuard>
  );
}
