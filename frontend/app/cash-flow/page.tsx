"use client";

import { useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, CashFlowForecast, Company, JsonReport } from "@/lib/api";

function CashFlowContent() {
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [forecast, setForecast] = useState<CashFlowForecast | null>(null);
  const [tab, setTab] = useState<"forecast" | "statement">("forecast");
  const [periodType, setPeriodType] = useState<"MONTHLY" | "QUARTERLY" | "ANNUAL">("MONTHLY");
  const [referenceDate, setReferenceDate] = useState(new Date().toISOString().slice(0, 10));
  const [statement, setStatement] = useState<JsonReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  useEffect(() => {
    if (!token || !companyId) return;
    api.cashFlowForecast(token, Number(companyId)).then(setForecast).catch((e) => setError(e.message));
  }, [token, companyId]);

  useEffect(() => {
    if (!token || !companyId || tab !== "statement") return;
    api
      .cashFlowStatement(token, { company_id: Number(companyId), period_type: periodType, reference_date: referenceDate })
      .then(setStatement)
      .catch((e) => setError(e.message));
  }, [token, companyId, tab, periodType, referenceDate]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-navy">Cash Flow</h1>
        <div className="flex items-center gap-2 text-sm">
          <button onClick={() => setTab("forecast")} className={`rounded-full px-3 py-1 ${tab === "forecast" ? "bg-navy text-white" : "bg-white border border-border-subtle"}`}>
            Forecast
          </button>
          <button onClick={() => setTab("statement")} className={`rounded-full px-3 py-1 ${tab === "statement" ? "bg-navy text-white" : "bg-white border border-border-subtle"}`}>
            Statement (actual)
          </button>
        </div>
      </div>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="flex items-center gap-3">
        <select
          value={companyId}
          onChange={(e) => {
            setCompanyId(e.target.value ? Number(e.target.value) : "");
            if (!e.target.value) {
              setForecast(null);
              setStatement(null);
            }
          }}
          className="input-v2 px-3 py-2 text-sm"
        >
          <option value="">Select a company</option>
          {companies.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        {tab === "statement" && (
          <>
            <select value={periodType} onChange={(e) => setPeriodType(e.target.value as typeof periodType)} className="input-v2 px-3 py-2 text-sm">
              <option value="MONTHLY">Monthly</option>
              <option value="QUARTERLY">Quarterly</option>
              <option value="ANNUAL">Annual</option>
            </select>
            <input type="date" value={referenceDate} onChange={(e) => setReferenceDate(e.target.value)} className="input-v2 px-3 py-2 text-sm" />
          </>
        )}
      </div>

      {tab === "statement" && statement && (
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-4">
            <div className="card-v2 p-4">
              <p className="text-xs text-text-secondary">Operating activities (net)</p>
              <p className="text-xl font-semibold text-navy font-mono">{statement.operating_activities.net}</p>
              <p className="text-xs text-text-secondary">Receipts {statement.operating_activities.receipts} / Payments {statement.operating_activities.payments}</p>
            </div>
            <div className="card-v2 p-4">
              <p className="text-xs text-text-secondary">Investing activities (net)</p>
              <p className="text-xl font-semibold text-navy font-mono">{statement.investing_activities.net}</p>
              <p className="text-xs text-text-secondary">{statement.investing_activities.note}</p>
            </div>
            <div className="card-v2 p-4">
              <p className="text-xs text-text-secondary">Financing activities (net)</p>
              <p className="text-xl font-semibold text-navy font-mono">{statement.financing_activities.net}</p>
              <p className="text-xs text-text-secondary">{statement.financing_activities.note}</p>
            </div>
          </div>
          <div className="card-v2 p-4">
            <p className="text-sm font-medium text-navy">Net change in cash: <span className="font-mono">{statement.net_change_in_cash}</span></p>
          </div>
          <div className="card-v2 p-4">
            <h2 className="font-medium text-navy mb-2">Accrual vs cash reconciliation</h2>
            <p className="text-sm">Net profit (accrual): <span className="font-mono">{statement.accrual_vs_cash_reconciliation.net_profit_accrual}</span></p>
            <p className="text-sm">+ Depreciation addback: <span className="font-mono">{statement.accrual_vs_cash_reconciliation.depreciation_addback}</span></p>
            <p className="text-sm">- Increase in AR: <span className="font-mono">{statement.accrual_vs_cash_reconciliation.increase_in_accounts_receivable}</span></p>
            <p className="text-sm">+ Increase in AP: <span className="font-mono">{statement.accrual_vs_cash_reconciliation.increase_in_accounts_payable}</span></p>
            <p className="text-sm font-medium">≈ Approx operating cash: <span className="font-mono">{statement.accrual_vs_cash_reconciliation.approx_operating_cash_from_accrual}</span></p>
            <p className="text-sm font-medium">Actual operating cash: <span className="font-mono">{statement.accrual_vs_cash_reconciliation.actual_operating_cash}</span></p>
            <p className="text-xs text-amber-600 mt-2">{statement.accrual_vs_cash_reconciliation.note}</p>
          </div>
        </div>
      )}

      {tab === "forecast" && forecast && (
        <>
          <div className="grid grid-cols-3 gap-4">
            <div className="card-v2 p-4">
              <p className="text-xs text-text-secondary">Actual -- net bank movement to date</p>
              <p className="text-2xl font-semibold text-navy font-mono">{forecast.net_bank_transaction_movement}</p>
              <p className="text-xs text-amber-600 mt-1">{forecast.net_bank_transaction_movement_disclaimer}</p>
            </div>
            <div className="card-v2 p-4">
              <p className="text-xs text-text-secondary">Confirmed -- outstanding invoices</p>
              <p className="text-sm">
                {forecast.outstanding_sales_invoice_count} sales / {forecast.outstanding_purchase_invoice_count} purchase
              </p>
              <p className="text-sm font-mono mt-1">
                +{forecast.expected_incoming_total} / -{forecast.expected_outgoing_total}
              </p>
            </div>
            <div className="card-v2 p-4">
              <p className="text-xs text-text-secondary">AI-estimated -- recurring expenses</p>
              <p className="text-sm font-mono">{forecast.recurring_expenses_monthly_equivalent} / month</p>
              <p className="text-xs text-text-secondary">{forecast.recurring_pattern_count} pattern(s) detected</p>
            </div>
          </div>

          <div className="card-v2 p-4">
            <p className="text-sm font-medium text-navy">Forecast VAT position</p>
            <p className="text-sm font-mono mt-1">
              Payable: {forecast.forecast_vat_payable} · Refundable: {forecast.forecast_vat_refundable}
            </p>
            <p className="text-xs text-amber-600 mt-1">{forecast.forecast_vat_disclaimer}</p>
          </div>

          <div className="card-v2 overflow-hidden">
            <div className="p-4 pb-0 flex items-center justify-between">
              <h2 className="font-medium text-navy">Monthly projection</h2>
              <span className="text-xs bg-amber-100 text-amber-700 rounded-full px-2 py-0.5">Estimate, not a confirmed balance</span>
            </div>
            <table className="w-full text-sm mt-2">
              <thead>
                <tr className="text-left text-text-secondary border-b border-border-subtle">
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
            <p className="text-xs text-text-secondary p-4 pt-2">{forecast.monthly_projection_disclaimer}</p>
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
