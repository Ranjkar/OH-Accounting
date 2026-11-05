"use client";

import { FormEvent, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, CategorizationRule, CategorizationRuleType, CategorySuggestion, Company, Transaction } from "@/lib/api";
import { formatEUR } from "@/lib/format";

// Stored verbatim as the transaction's `category` value (no separate
// code), so these are never translated -- same rule as any other
// stored/API value, see the file-level translation conventions.
const EXPENSE_CATEGORIES = [
  "Office expenses", "Travel", "Fuel", "Software subscriptions", "Telecommunications",
  "Rent", "Insurance", "Professional services", "Equipment", "Marketing", "Other",
];

function CategoriesContent() {
  const t = useTranslations("categories");
  const tCommon = useTranslations("common");
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [rules, setRules] = useState<CategorizationRule[]>([]);
  const [uncategorized, setUncategorized] = useState<Transaction[]>([]);
  const [suggestions, setSuggestions] = useState<Record<number, CategorySuggestion>>({});
  const [chosenCategory, setChosenCategory] = useState<Record<number, string>>({});
  const [ruleType, setRuleType] = useState<CategorizationRuleType>("SUPPLIER_NAME");
  const [matchValue, setMatchValue] = useState("");
  const [ruleCategory, setRuleCategory] = useState(EXPENSE_CATEGORIES[0]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  function refresh() {
    if (!token || !companyId) return;
    api.listCategorizationRules(token, Number(companyId)).then(setRules).catch((e) => setError(e.message));
    api.listUncategorizedTransactions(token, Number(companyId)).then(setUncategorized).catch((e) => setError(e.message));
  }

  useEffect(refresh, [token, companyId]);

  async function createRule(e: FormEvent) {
    e.preventDefault();
    if (!token || !companyId) return;
    try {
      await api.createCategorizationRule(token, {
        company_id: Number(companyId), rule_type: ruleType, match_value: matchValue, category: ruleCategory,
      });
      setMatchValue("");
      refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function suggest(txId: number) {
    if (!token) return;
    try {
      const suggestion = await api.suggestCategory(token, txId);
      setSuggestions((prev) => ({ ...prev, [txId]: suggestion }));
      setChosenCategory((prev) => ({ ...prev, [txId]: suggestion.suggested_category }));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function categorize(txId: number, rememberAsRule: boolean) {
    if (!token) return;
    const category = chosenCategory[txId];
    if (!category) return;
    try {
      await api.categorizeTransaction(token, txId, category, rememberAsRule);
      setUncategorized((prev) => prev.filter((t) => t.id !== txId));
      refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-text-primary">{t("title")}</h1>
      <p className="text-sm text-text-secondary">
        {t("pageExplainer")}
      </p>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <select
        value={companyId}
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

      {companyId && (
        <>
          <div className="card-v2 p-4 space-y-3">
            <h2 className="font-medium text-text-primary">{t("rules")}</h2>
            <form onSubmit={createRule} className="flex items-end gap-3">
              <select value={ruleType} aria-label={t("ruleType")} onChange={(e) => setRuleType(e.target.value as CategorizationRuleType)} className="input-v2 px-2 py-2 text-sm">
                <option value="SUPPLIER_NAME">{t("ruleTypeSupplierName")}</option>
                <option value="IBAN">{t("ruleTypeIban")}</option>
                <option value="DESCRIPTION_PATTERN">{t("ruleTypeDescriptionPattern")}</option>
              </select>
              <input
                required
                value={matchValue}
                onChange={(e) => setMatchValue(e.target.value)}
                placeholder={t("matchValuePlaceholder")}
                className="input-v2 px-3 py-2 text-sm"
              />
              <select value={ruleCategory} aria-label={t("ruleCategory")} onChange={(e) => setRuleCategory(e.target.value)} className="input-v2 px-2 py-2 text-sm">
                {EXPENSE_CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
              <button type="submit" className="rounded-md bg-navy-solid text-white px-4 py-2 text-sm font-medium">
                {t("addRule")}
              </button>
            </form>
            <div className="overflow-x-auto">
            <table className="table-v3">
              <tbody>
                {rules.map((r) => (
                  <tr key={r.id}>
                    <td className="text-xs text-text-secondary">{r.rule_type}</td>
                    <td className="text-text-primary">{r.match_value}</td>
                    <td className="font-medium text-text-primary">{r.category}</td>
                  </tr>
                ))}
                {rules.length === 0 && (
                  <tr>
                    <td className="text-text-secondary">{t("noRulesYet")}</td>
                  </tr>
                )}
              </tbody>
            </table>
            </div>
          </div>

          <div className="card-v2 overflow-hidden">
            <h2 className="font-medium text-text-primary p-4 pb-0">{t("purchaseTransactions")}</h2>
            <div className="overflow-x-auto">
            <table className="table-v3">
              <thead>
                <tr>
                  <th>{t("invoice")}</th>
                  <th>{t("counterparty")}</th>
                  <th className="text-right">{tCommon("amount")}</th>
                  <th>{t("suggestion")}</th>
                  <th>{t("category")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {uncategorized.map((t2) => (
                  <tr key={t2.id}>
                    <td className="text-text-primary" dir="ltr">{t2.invoice_number ?? `#${t2.id}`}</td>
                    <td className="text-text-secondary">{t2.counterparty_name ?? "—"}</td>
                    <td className="col-amount">{formatEUR(t2.net_amount)}</td>
                    <td>
                      {suggestions[t2.id] ? (
                        <span className="text-xs text-text-secondary">
                          {suggestions[t2.id].suggested_category} ({Math.round(suggestions[t2.id].confidence * 100)}%)
                          {suggestions[t2.id].requires_accountant_review && ` · ${t("review")}`}
                        </span>
                      ) : (
                        <button onClick={() => suggest(t2.id)} className="text-xs text-navy hover:underline">
                          {t("suggest")}
                        </button>
                      )}
                    </td>
                    <td>
                      <select
                        value={chosenCategory[t2.id] ?? ""}
                        onChange={(e) => setChosenCategory((prev) => ({ ...prev, [t2.id]: e.target.value }))}
                        className="input-v2 px-2 py-1 text-xs"
                      >
                        <option value="">—</option>
                        {EXPENSE_CATEGORIES.map((c) => (
                          <option key={c} value={c}>
                            {c}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <button
                        onClick={() => categorize(t2.id, true)}
                        disabled={!chosenCategory[t2.id]}
                        className="rounded-md bg-navy-solid text-white px-3 py-1 text-xs disabled:opacity-50"
                      >
                        {t("applyAndRemember")}
                      </button>
                    </td>
                  </tr>
                ))}
                {uncategorized.length === 0 && (
                  <tr>
                    <td colSpan={6} className="text-text-secondary">
                      {t("noPurchaseTransactions")}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default function CategoriesPage() {
  return (
    <AuthGuard>
      <Shell>
        <CategoriesContent />
      </Shell>
    </AuthGuard>
  );
}
