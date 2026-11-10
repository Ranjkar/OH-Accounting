"use client";

import { FormEvent, useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, BalanceSheetItemCategory, Company, JsonReport, ManualBalanceSheetItem } from "@/lib/api";
import { formatEUR } from "@/lib/format";

const CATEGORY_KEYS: { value: BalanceSheetItemCategory; key: string }[] = [
  { value: "FIXED_ASSETS", key: "fixedAssets" },
  { value: "INVENTORY", key: "inventory" },
  { value: "OTHER_ASSET", key: "otherAsset" },
  { value: "EQUITY", key: "equity" },
  { value: "LOANS", key: "loans" },
  { value: "OTHER_LIABILITY", key: "otherLiability" },
];

function Row({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  const locale = useLocale();
  return (
    <div className={`flex items-center justify-between py-1.5 ${highlight ? "font-semibold border-t border-border mt-1 pt-2" : ""}`}>
      <span className="text-text-secondary">{label}</span>
      <span className="font-mono tabular-nums">{formatEUR(value, locale)}</span>
    </div>
  );
}

function BalanceSheetContent() {
  const t = useTranslations("balanceSheet");
  const tCommon = useTranslations("common");
  const locale = useLocale();
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [asOfDate, setAsOfDate] = useState(new Date().toISOString().slice(0, 10));
  const [bs, setBs] = useState<JsonReport | null>(null);
  const [items, setItems] = useState<ManualBalanceSheetItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [category, setCategory] = useState<BalanceSheetItemCategory>("FIXED_ASSETS");
  const [label, setLabel] = useState("");
  const [amount, setAmount] = useState("");
  const [itemDate, setItemDate] = useState(new Date().toISOString().slice(0, 10));

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  function refresh() {
    if (!token || !companyId) return;
    api.balanceSheet(token, Number(companyId), asOfDate).then(setBs).catch((e) => setError(e.message));
    api.listBalanceSheetItems(token, Number(companyId)).then(setItems).catch((e) => setError(e.message));
  }

  useEffect(refresh, [token, companyId, asOfDate]);

  async function addItem(e: FormEvent) {
    e.preventDefault();
    if (!token || !companyId) return;
    try {
      await api.createBalanceSheetItem(token, { company_id: Number(companyId), category, label, amount, as_of_date: itemDate });
      setLabel("");
      setAmount("");
      refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-text-primary">{t("title")}</h1>
      <p className="text-sm text-text-secondary">{t("manualItemsNotice")}</p>
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
        {companyId && (
          <div className="flex items-center gap-2 ms-auto text-xs">
            {(["pdf", "xlsx", "csv"] as const).map((fmt) => (
              <a key={fmt} href={api.balanceSheetReportUrl(Number(companyId), asOfDate, fmt)} className="input-v2 px-2 py-1 hover:bg-muted">
                {tCommon("export")} {fmt.toUpperCase()}
              </a>
            ))}
          </div>
        )}
      </div>

      {bs && (
        <>
          {!bs.is_balanced && (
            <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">
              {t("doesNotBalance", { amount: formatEUR(bs.imbalance_amount, locale) })} {bs.missing_opening_balance_warning}
            </div>
          )}
          {bs.is_balanced && bs.missing_opening_balance_warning && (
            <div className="rounded-md bg-amber-50 text-amber-700 text-sm px-3 py-2">{bs.missing_opening_balance_warning}</div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="card-v2 p-4">
              <h2 className="font-medium text-text-primary mb-2">{t("assets")}</h2>
              <Row label={t("cashAndBank")} value={bs.assets.cash_and_bank} />
              <Row label={t("accountsReceivable")} value={bs.assets.accounts_receivable} />
              <Row label={t("inventory")} value={bs.assets.inventory} />
              <Row label={t("fixedAssets")} value={bs.assets.fixed_assets} />
              <Row label={t("otherAssets")} value={bs.assets.other_assets} />
              <Row label={t("vatReceivable")} value={bs.assets.vat_receivable} />
              <Row label={t("totalAssets")} value={bs.assets.total} highlight />
            </div>
            <div className="card-v2 p-4">
              <h2 className="font-medium text-text-primary mb-2">{t("liabilities")}</h2>
              <Row label={t("accountsPayable")} value={bs.liabilities.accounts_payable} />
              <Row label={t("loans")} value={bs.liabilities.loans} />
              <Row label={t("otherLiabilities")} value={bs.liabilities.other_liabilities} />
              <Row label={t("vatPayable")} value={bs.liabilities.vat_payable} />
              <Row label={t("totalLiabilities")} value={bs.liabilities.total} highlight />
            </div>
            <div className="card-v2 p-4">
              <h2 className="font-medium text-text-primary mb-2">{t("equity")}</h2>
              <Row label={t("contributedEquity")} value={bs.equity.contributed_and_other_equity} />
              <Row label={t("retainedEarnings")} value={bs.equity.retained_earnings} />
              <Row label={t("totalEquity")} value={bs.equity.total} highlight />
            </div>
          </div>
        </>
      )}

      {companyId && (
        <div className="card-v2 p-4 space-y-3">
          <h2 className="font-medium text-text-primary">{t("manualItemsHeading")}</h2>
          <form onSubmit={addItem} className="flex items-end gap-3 flex-wrap">
            <select value={category} aria-label={tCommon("category")} onChange={(e) => setCategory(e.target.value as BalanceSheetItemCategory)} className="input-v2 px-2 py-2 text-sm">
              {CATEGORY_KEYS.map((c) => (
                <option key={c.value} value={c.value}>
                  {t(`category.${c.key}` as never)}
                </option>
              ))}
            </select>
            <input required value={label} aria-label={tCommon("name")} onChange={(e) => setLabel(e.target.value)} placeholder={t("labelPlaceholder")} className="input-v2 px-3 py-2 text-sm" />
            <input inputMode="decimal" required value={amount} aria-label={tCommon("amount")} onChange={(e) => setAmount(e.target.value)} placeholder={tCommon("amount")} className="input-v2 px-3 py-2 text-sm w-32" />
            <input type="date" value={itemDate} aria-label={t("itemDate")} onChange={(e) => setItemDate(e.target.value)} className="input-v2 px-3 py-2 text-sm" />
            <button type="submit" className="rounded-md bg-navy-solid text-white px-4 py-2 text-sm font-medium">
              {tCommon("create")}
            </button>
          </form>
          <div className="overflow-x-auto" tabIndex={0}>
          <table className="table-v3">
            <thead>
              <tr>
                <th>{tCommon("category")}</th>
                <th>{tCommon("name")}</th>
                <th className="text-right">{tCommon("amount")}</th>
                <th>{tCommon("date")}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td className="text-xs text-text-secondary">{item.category}</td>
                  <td className="text-text-primary">{item.label}</td>
                  <td className="col-amount">{formatEUR(item.amount, locale)}</td>
                  <td className="text-xs text-text-secondary">{item.as_of_date}</td>
                </tr>
              ))}
              {items.length === 0 && (
                <tr>
                  <td colSpan={4} className="text-text-secondary">{t("noManualItems")}</td>
                </tr>
              )}
            </tbody>
          </table>
          </div>
        </div>
      )}
    </div>
  );
}

export default function BalanceSheetPage() {
  return (
    <AuthGuard>
      <Shell>
        <BalanceSheetContent />
      </Shell>
    </AuthGuard>
  );
}
