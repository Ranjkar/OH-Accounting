"use client";

import { useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, CashFlowForecast, Company, JsonReport } from "@/lib/api";
import { formatEUR } from "@/lib/format";

function CashFlowContent() {
  const t = useTranslations("cashFlow");
  const locale = useLocale();
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
        <h1 className="text-2xl font-semibold text-text-primary">{t("title")}</h1>
        <div className="flex items-center gap-2 text-sm">
          <button onClick={() => setTab("forecast")} className={`rounded-full px-3 py-1 ${tab === "forecast" ? "bg-navy-solid text-white" : "bg-surface-card border border-border text-text-secondary hover:bg-muted"}`}>
            {t("forecast")}
          </button>
          <button onClick={() => setTab("statement")} className={`rounded-full px-3 py-1 ${tab === "statement" ? "bg-navy-solid text-white" : "bg-surface-card border border-border text-text-secondary hover:bg-muted"}`}>
            {t("statementActual")}
          </button>
        </div>
      </div>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="flex items-center gap-3">
        <select
          value={companyId}
          aria-label={t("companyLabel")}
          onChange={(e) => {
            setCompanyId(e.target.value ? Number(e.target.value) : "");
            if (!e.target.value) {
              setForecast(null);
              setStatement(null);
            }
          }}
          className="input-v2 px-3 py-2 text-sm"
        >
          <option value="">{t("selectCompanyOption")}</option>
          {companies.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        {tab === "statement" && (
          <>
            <select value={periodType} aria-label={t("periodTypeLabel")} onChange={(e) => setPeriodType(e.target.value as typeof periodType)} className="input-v2 px-3 py-2 text-sm">
              <option value="MONTHLY">{t("periodMonthly")}</option>
              <option value="QUARTERLY">{t("periodQuarterly")}</option>
              <option value="ANNUAL">{t("periodAnnual")}</option>
            </select>
            <input type="date" value={referenceDate} aria-label={t("referenceDateLabel")} onChange={(e) => setReferenceDate(e.target.value)} className="input-v2 px-3 py-2 text-sm" />
          </>
        )}
      </div>

      {tab === "statement" && statement && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="card-v2 p-4">
              <p className="text-xs text-text-secondary">{t("operatingActivitiesNet")}</p>
              <p className="text-xl font-semibold text-navy font-mono">{formatEUR(statement.operating_activities.net, locale)}</p>
              <p className="text-xs text-text-secondary">{t("receiptsPayments", { receipts: formatEUR(statement.operating_activities.receipts, locale), payments: formatEUR(statement.operating_activities.payments, locale) })}</p>
            </div>
            <div className="card-v2 p-4">
              <p className="text-xs text-text-secondary">{t("investingActivitiesNet")}</p>
              <p className="text-xl font-semibold text-navy font-mono">{formatEUR(statement.investing_activities.net, locale)}</p>
              <p className="text-xs text-text-secondary">{statement.investing_activities.note}</p>
            </div>
            <div className="card-v2 p-4">
              <p className="text-xs text-text-secondary">{t("financingActivitiesNet")}</p>
              <p className="text-xl font-semibold text-navy font-mono">{formatEUR(statement.financing_activities.net, locale)}</p>
              <p className="text-xs text-text-secondary">{statement.financing_activities.note}</p>
            </div>
          </div>
          <div className="card-v2 p-4">
            <p className="text-sm font-medium text-navy">{t("netChangeInCash")} <span className="font-mono">{formatEUR(statement.net_change_in_cash, locale)}</span></p>
          </div>
          <div className="card-v2 p-4">
            <h2 className="font-medium text-text-primary mb-2">{t("accrualVsCashHeading")}</h2>
            <p className="text-sm">{t("netProfitAccrual")} <span className="font-mono">{formatEUR(statement.accrual_vs_cash_reconciliation.net_profit_accrual, locale)}</span></p>
            <p className="text-sm">{t("depreciationAddback")} <span className="font-mono">{formatEUR(statement.accrual_vs_cash_reconciliation.depreciation_addback, locale)}</span></p>
            <p className="text-sm">{t("increaseInAR")} <span className="font-mono">{formatEUR(statement.accrual_vs_cash_reconciliation.increase_in_accounts_receivable, locale)}</span></p>
            <p className="text-sm">{t("increaseInAP")} <span className="font-mono">{formatEUR(statement.accrual_vs_cash_reconciliation.increase_in_accounts_payable, locale)}</span></p>
            <p className="text-sm font-medium">{t("approxOperatingCash")} <span className="font-mono">{formatEUR(statement.accrual_vs_cash_reconciliation.approx_operating_cash_from_accrual, locale)}</span></p>
            <p className="text-sm font-medium">{t("actualOperatingCash")} <span className="font-mono">{formatEUR(statement.accrual_vs_cash_reconciliation.actual_operating_cash, locale)}</span></p>
            <p className="text-xs text-pending mt-2">{statement.accrual_vs_cash_reconciliation.note}</p>
          </div>
        </div>
      )}

      {tab === "forecast" && forecast && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="card-v2 p-4">
              <p className="text-xs text-text-secondary">{t("actualNetBankMovement")}</p>
              <p className="text-2xl font-semibold text-navy font-mono">{formatEUR(forecast.net_bank_transaction_movement, locale)}</p>
              <p className="text-xs text-pending mt-1">{forecast.net_bank_transaction_movement_disclaimer}</p>
            </div>
            <div className="card-v2 p-4">
              <p className="text-xs text-text-secondary">{t("confirmedOutstandingInvoices")}</p>
              <p className="text-sm">
                {t("salesPurchaseCount", { sales: forecast.outstanding_sales_invoice_count, purchases: forecast.outstanding_purchase_invoice_count })}
              </p>
              <p className="text-sm font-mono mt-1">
                +{formatEUR(forecast.expected_incoming_total, locale)} / -{formatEUR(forecast.expected_outgoing_total, locale)}
              </p>
            </div>
            <div className="card-v2 p-4">
              <p className="text-xs text-text-secondary">{t("aiEstimatedRecurringExpenses")}</p>
              <p className="text-sm font-mono">{t("perMonth", { amount: formatEUR(forecast.recurring_expenses_monthly_equivalent, locale) })}</p>
              <p className="text-xs text-text-secondary">{t("patternsDetected", { count: forecast.recurring_pattern_count })}</p>
            </div>
          </div>

          <div className="card-v2 p-4">
            <p className="text-sm font-medium text-navy">{t("forecastVatPosition")}</p>
            <p className="text-sm font-mono mt-1">
              {t("payableRefundable", { payable: formatEUR(forecast.forecast_vat_payable, locale), refundable: formatEUR(forecast.forecast_vat_refundable, locale) })}
            </p>
            <p className="text-xs text-pending mt-1">{forecast.forecast_vat_disclaimer}</p>
          </div>

          <div className="card-v2 overflow-hidden">
            <div className="p-4 pb-0 flex items-center justify-between">
              <h2 className="font-medium text-text-primary">{t("monthlyProjection")}</h2>
              <span className="text-xs bg-amber-100 text-amber-700 rounded-full px-2 py-0.5">{t("estimateNotConfirmed")}</span>
            </div>
            <div className="overflow-x-auto">
            <table className="table-v3">
              <thead>
                <tr>
                  <th>{t("colMonth")}</th>
                  <th className="text-right">{t("expectedIncoming")}</th>
                  <th className="text-right">{t("expectedOutgoing")}</th>
                  <th className="text-right">{t("colNet")}</th>
                </tr>
              </thead>
              <tbody>
                {forecast.monthly_projection.map((m) => (
                  <tr key={m.month}>
                    <td className="text-text-secondary">{m.month}</td>
                    <td className="col-amount value-positive">+{formatEUR(m.expected_incoming, locale)}</td>
                    <td className="col-amount value-negative">-{formatEUR(m.expected_outgoing, locale)}</td>
                    <td className="col-amount font-medium">{formatEUR(m.net, locale)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
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
