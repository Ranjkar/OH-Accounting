"use client";

import { useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, Company, JsonReport } from "@/lib/api";
import { formatEUR } from "@/lib/format";

function WorkingCapitalContent() {
  const t = useTranslations("workingCapital");
  const tCommon = useTranslations("common");
  const locale = useLocale();
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [asOfDate, setAsOfDate] = useState(new Date().toISOString().slice(0, 10));
  const [customerBehavior, setCustomerBehavior] = useState<JsonReport[]>([]);
  const [supplierTrends, setSupplierTrends] = useState<JsonReport[]>([]);
  const [alerts, setAlerts] = useState<JsonReport[]>([]);
  const [trend, setTrend] = useState<JsonReport[]>([]);
  const [ccc, setCcc] = useState<JsonReport | null>(null);
  const [customerConcentration, setCustomerConcentration] = useState<JsonReport | null>(null);
  const [supplierDependency, setSupplierDependency] = useState<JsonReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  useEffect(() => {
    if (!token || !companyId) return;
    const params = { company_id: Number(companyId), period_type: "ANNUAL" as const, reference_date: asOfDate };
    api.workingCapitalCustomerPaymentBehavior(token, params).then(setCustomerBehavior).catch((e) => setError(e.message));
    api.workingCapitalSupplierPaymentTrends(token, params).then(setSupplierTrends).catch((e) => setError(e.message));
    api.workingCapitalPaymentDelayAlerts(token, Number(companyId), asOfDate).then(setAlerts).catch((e) => setError(e.message));
    api.workingCapitalTrend(token, Number(companyId), 6).then(setTrend).catch((e) => setError(e.message));
    api.cashConversionCycle(token, params).then(setCcc).catch((e) => setError(e.message));
    api.customerConcentration(token, params).then(setCustomerConcentration).catch((e) => setError(e.message));
    api.supplierDependency(token, params).then(setSupplierDependency).catch((e) => setError(e.message));
  }, [token, companyId, asOfDate]);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-text-primary">{t("title")}</h1>
      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="flex flex-wrap items-center gap-3">
        <select value={companyId} aria-label={tCommon("company")} onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")} className="input-v2 px-3 py-2 text-sm">
          <option value="">{tCommon("selectCompany")}</option>
          {companies.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <input type="date" value={asOfDate} aria-label={t("asOfDate")} onChange={(e) => setAsOfDate(e.target.value)} className="input-v2 px-3 py-2 text-sm" />
      </div>

      {companyId && (
        <>
          {alerts.length > 0 && (
            <div className="card-v2 rounded-lg border border-red-200 p-4">
              <h2 className="font-medium text-error mb-2">{t("paymentDelayAlerts")}</h2>
              {alerts.map((a) => (
                <div key={a.transaction_id} className="flex items-center justify-between text-sm py-1 border-b border-border last:border-0">
                  <span>
                    {t("alertLine", { counterparty: a.counterparty_name, invoiceId: a.transaction_id, days: a.days_overdue })}
                  </span>
                  <span className="font-mono">{formatEUR(a.remaining_balance, locale)}</span>
                  <span className="text-xs text-text-secondary">{a.alert_reason}</span>
                </div>
              ))}
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="card-v2 p-4">
              <h2 className="font-medium text-text-primary mb-2">{t("customerPaymentBehavior")}</h2>
              {customerBehavior.length === 0 && <p className="text-sm text-text-secondary">{t("noSettledInvoicesYet")}</p>}
              {customerBehavior.map((c) => (
                <p key={c.counterparty_name} className="text-sm">
                  {t("avgDaysToPay", { name: c.counterparty_name, days: c.average_days_to_pay, count: c.invoices_settled })}
                </p>
              ))}
            </div>
            <div className="card-v2 p-4">
              <h2 className="font-medium text-text-primary mb-2">{t("supplierPaymentTrends")}</h2>
              {supplierTrends.length === 0 && <p className="text-sm text-text-secondary">{t("noSettledPurchaseInvoicesYet")}</p>}
              {supplierTrends.map((s) => (
                <p key={s.counterparty_name} className="text-sm">
                  {t("avgDaysToPay", { name: s.counterparty_name, days: s.average_days_to_pay, count: s.invoices_settled })}
                </p>
              ))}
            </div>
          </div>

          <div className="card-v2 p-4">
            <h2 className="font-medium text-text-primary mb-2">{t("workingCapitalTrend")}</h2>
            <div className="overflow-x-auto" tabIndex={0}>
            <table className="table-v3">
              <thead>
                <tr>
                  <th>{t("monthEnd")}</th>
                  <th className="text-right">{t("ar")}</th>
                  <th className="text-right">{t("ap")}</th>
                  <th className="text-right">{t("netWorkingCapital")}</th>
                </tr>
              </thead>
              <tbody>
                {trend.map((row) => (
                  <tr key={row.period_end}>
                    <td className="text-text-secondary">{row.period_end}</td>
                    <td className="col-amount">{formatEUR(row.accounts_receivable, locale)}</td>
                    <td className="col-amount">{formatEUR(row.accounts_payable, locale)}</td>
                    <td className="col-amount font-medium">{formatEUR(row.net_working_capital, locale)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="card-v2 p-4">
              <h2 className="font-medium text-text-primary mb-2">{t("cashConversionCycle")}</h2>
              {ccc && (
                <>
                  <p className="text-sm">DSO: <span className="font-mono">{ccc.days_sales_outstanding ?? t("notApplicable")}</span></p>
                  <p className="text-sm">DPO: <span className="font-mono">{ccc.days_payable_outstanding ?? t("notApplicable")}</span></p>
                  <p className="text-sm">DIO: <span className="font-mono">{t("notApplicable")}</span></p>
                  <p className="text-xs text-pending mt-1">{ccc.missing_data}</p>
                </>
              )}
            </div>
            <div className="card-v2 p-4">
              <h2 className="font-medium text-text-primary mb-2">{t("customerConcentration")}</h2>
              {customerConcentration?.top_customers?.map((c: JsonReport) => (
                <p key={c.counterparty_name} className="text-sm">
                  {c.counterparty_name}: {c.pct_of_total}%
                </p>
              ))}
              {customerConcentration?.missing_data && <p className="text-xs text-pending">{customerConcentration.missing_data}</p>}
            </div>
            <div className="card-v2 p-4">
              <h2 className="font-medium text-text-primary mb-2">{t("supplierDependency")}</h2>
              {supplierDependency?.top_expense_categories?.map((c: JsonReport) => (
                <p key={c.category} className="text-sm">
                  {c.category}: {c.pct_of_total}%
                </p>
              ))}
              {supplierDependency?.missing_data && <p className="text-xs text-pending">{supplierDependency.missing_data}</p>}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default function WorkingCapitalPage() {
  return (
    <AuthGuard>
      <Shell>
        <WorkingCapitalContent />
      </Shell>
    </AuthGuard>
  );
}
