"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, Company, JsonReport } from "@/lib/api";
import { formatEUR } from "@/lib/format";

function Tile({ label, value, href, suffix }: { label: string; value: string; href: string; suffix?: string }) {
  return (
    <Link href={href} className="card-v2 p-4 hover:border-navy transition-colors">
      <p className="text-xs text-text-secondary">{label}</p>
      <p className="text-2xl font-semibold text-navy font-mono">
        {value}
        {suffix}
      </p>
    </Link>
  );
}

function FinancialOverviewContent() {
  const t = useTranslations("financialOverview");
  const tCommon = useTranslations("common");
  const locale = useLocale();
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [owner, setOwner] = useState<JsonReport | null>(null);
  const [portfolio, setPortfolio] = useState<JsonReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  useEffect(() => {
    if (!token) return;
    api.accountantDashboard(token).then(setPortfolio).catch((e) => setError(e.message));
  }, [token]);

  useEffect(() => {
    if (!token || !companyId) return;
    api.businessOwnerDashboard(token, Number(companyId)).then(setOwner).catch((e) => setError(e.message));
  }, [token, companyId]);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-text-primary">{t("title")}</h1>
      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      {portfolio && (
        <div className="space-y-2">
          <h2 className="text-lg font-medium text-text-primary">{t("portfolioHeading", { count: portfolio.portfolio.length })}</h2>
          <div className="card-v2 overflow-hidden">
            <div className="overflow-x-auto" tabIndex={0}>
            <table className="table-v3">
              <thead>
                <tr>
                  <th>{tCommon("company")}</th>
                  <th className="text-right">{t("revenueMonth")}</th>
                  <th className="text-right">{t("netProfitMonth")}</th>
                  <th className="text-right">{t("vatPayable")}</th>
                  <th className="text-right">{t("unreconciled")}</th>
                  <th>{t("balanced")}</th>
                </tr>
              </thead>
              <tbody>
                {portfolio.portfolio.map((row: JsonReport) => (
                  <tr key={row.company_id}>
                    <td className="text-text-primary">{row.company_name}</td>
                    <td className="col-amount">{formatEUR(row.current_month_revenue, locale)}</td>
                    <td className="col-amount">{formatEUR(row.current_month_net_profit, locale)}</td>
                    <td className="col-amount">{formatEUR(row.vat_payable, locale)}</td>
                    <td className="text-right">{row.unreconciled_bank_transactions}</td>
                    <td>
                      <span className={`status-pill ${row.balance_sheet_balanced ? "status-pill-success" : "status-pill-warning"}`}>
                        {row.balance_sheet_balanced ? tCommon("yes") : tCommon("no")}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          </div>
        </div>
      )}

      <div className="space-y-2">
        <h2 className="text-lg font-medium text-text-primary">{t("companyDetail")}</h2>
        <select
          value={companyId}
          aria-label={tCommon("company")}
          onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")}
          className="input-v2 px-3 py-2 text-sm"
        >
          <option value="">{tCommon("selectCompany")}</option>
          {companies.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>

        {owner && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-4">
            <Tile label={t("revenueThisMonth")} value={formatEUR(owner.revenue, locale)} href="/profit-and-loss" />
            <Tile label={t("netProfitThisMonth")} value={formatEUR(owner.net_profit, locale)} href="/profit-and-loss" />
            <Tile label={t("cashPosition")} value={formatEUR(owner.cash_position, locale)} href="/balance-sheet" />
            <Tile label={t("outstandingCustomerPayments")} value={formatEUR(owner.outstanding_customer_payments, locale)} href="/working-capital" />
            <Tile label={t("upcomingSupplierPayments")} value={formatEUR(owner.upcoming_supplier_payments, locale)} href="/working-capital" />
            <Tile label={t("estimatedVatPosition")} value={formatEUR(owner.estimated_vat_position, locale)} href="/vat" />
            <Tile label={t("budgetVariance")} value={owner.budget_performance ? formatEUR(owner.budget_performance.total_variance, locale) : t("noApprovedBudget")} href="/budgets" />
            <Tile label={t("threeMonthForecast")} value={t("view")} href="/forecasts" />
          </div>
        )}
      </div>
    </div>
  );
}

export default function FinancialOverviewPage() {
  return (
    <AuthGuard>
      <Shell>
        <FinancialOverviewContent />
      </Shell>
    </AuthGuard>
  );
}
