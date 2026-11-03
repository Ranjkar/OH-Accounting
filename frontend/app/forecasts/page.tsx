"use client";

import { useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, Company, JsonReport } from "@/lib/api";

function Bar({ value, max, color }: { value: number; max: number; color: string }) {
  const pct = max > 0 ? Math.min(100, (Math.abs(value) / max) * 100) : 0;
  return (
    <div className="h-2 bg-slate-100 rounded-full overflow-hidden w-full">
      <div className={`h-2 rounded-full ${color}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

function ForecastsContent() {
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [horizon, setHorizon] = useState(3);
  const [forecast, setForecast] = useState<JsonReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  useEffect(() => {
    if (!token || !companyId) return;
    api.fullForecast(token, Number(companyId), horizon).then(setForecast).catch((e) => setError(e.message));
  }, [token, companyId, horizon]);

  const months: JsonReport[] = forecast?.revenue_expense_profit.monthly_forecast ?? [];
  const maxValue = Math.max(1, ...months.map((m) => Math.abs(Number(m.forecast_revenue))));

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-navy">Financial Forecasts</h1>
      <p className="text-sm text-text-secondary">
        Revenue, expense, and profit forecasts are a simple trend projection from recent actuals -- never a guaranteed
        outcome. Outstanding-invoice and VAT figures are confirmed amounts already on the books, not projections.
      </p>
      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="flex items-center gap-3">
        <select value={companyId} aria-label="Company" onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")} className="input-v2 px-3 py-2 text-sm">
          <option value="">Select a company</option>
          {companies.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <select value={horizon} aria-label="Horizon" onChange={(e) => setHorizon(Number(e.target.value))} className="input-v2 px-3 py-2 text-sm">
          <option value={3}>3 months</option>
          <option value={6}>6 months</option>
          <option value={12}>12 months</option>
        </select>
      </div>

      {forecast && (
        <>
          <div className="card-v2 p-4 space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="font-medium text-navy">Revenue / expense / profit trend</h2>
              <span className="text-xs bg-amber-100 text-amber-700 rounded-full px-2 py-0.5">Estimate</span>
            </div>
            {months.map((m) => (
              <div key={m.month} className="space-y-1">
                <div className="flex items-center justify-between text-xs text-text-secondary">
                  <span>{m.month}</span>
                  <span>
                    Revenue {m.forecast_revenue} · Profit {m.forecast_profit} (range {m.low_estimate_profit} to {m.high_estimate_profit})
                  </span>
                </div>
                <Bar value={Number(m.forecast_revenue)} max={maxValue} color="bg-navy" />
              </div>
            ))}
            <ul className="text-xs text-text-secondary list-disc pl-4">
              {forecast.revenue_expense_profit.assumptions.map((a: string, i: number) => (
                <li key={i}>{a}</li>
              ))}
            </ul>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="card-v2 p-4">
              <h2 className="font-medium text-navy mb-2">Outstanding invoices (confirmed, not estimated)</h2>
              <p className="text-sm">Receivables outstanding: <span className="font-mono">{forecast.outstanding_invoices.confirmed_receivables_outstanding}</span></p>
              <p className="text-sm">Payables outstanding: <span className="font-mono">{forecast.outstanding_invoices.confirmed_payables_outstanding}</span></p>
              <p className="text-sm">Net working capital: <span className="font-mono">{forecast.outstanding_invoices.net_working_capital_from_trade}</span></p>
            </div>
            <div className="card-v2 p-4">
              <h2 className="font-medium text-navy mb-2">Upcoming VAT payments</h2>
              {forecast.vat_payments.upcoming_vat_payments.map((p: JsonReport) => (
                <p key={p.vat_period_id} className="text-sm">
                  {p.period_label} (due {p.payment_deadline}): <span className="font-mono">{p.estimated_net_payable}</span>{" "}
                  {!p.is_final && <span className="text-amber-600 text-xs">(estimate)</span>}
                </p>
              ))}
              <p className="text-xs text-text-secondary mt-2">{forecast.tax_liability.note}</p>
            </div>
          </div>

          <div className="card-v2 p-4">
            <h2 className="font-medium text-navy mb-2">Cash flow forecast (Phase 6 engine, reused)</h2>
            <p className="text-xs text-amber-600">{forecast.cash_flow.net_bank_transaction_movement_disclaimer}</p>
            <table className="w-full text-sm mt-2">
              <thead>
                <tr className="text-left text-text-secondary border-b border-border-subtle">
                  <th className="py-1">Month</th>
                  <th className="py-1">Incoming</th>
                  <th className="py-1">Outgoing</th>
                  <th className="py-1">Net</th>
                </tr>
              </thead>
              <tbody>
                {forecast.cash_flow.monthly_projection.map((m: JsonReport) => (
                  <tr key={m.month} className="border-b border-slate-100 last:border-0">
                    <td className="py-1">{m.month}</td>
                    <td className="py-1 font-mono text-green-700">+{m.expected_incoming}</td>
                    <td className="py-1 font-mono text-error">-{m.expected_outgoing}</td>
                    <td className="py-1 font-mono">{m.net}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

export default function ForecastsPage() {
  return (
    <AuthGuard>
      <Shell>
        <ForecastsContent />
      </Shell>
    </AuthGuard>
  );
}
