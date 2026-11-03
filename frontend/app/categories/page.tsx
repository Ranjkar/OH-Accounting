"use client";

import { FormEvent, useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, CategorizationRule, CategorizationRuleType, CategorySuggestion, Company, Transaction } from "@/lib/api";

const EXPENSE_CATEGORIES = [
  "Office expenses", "Travel", "Fuel", "Software subscriptions", "Telecommunications",
  "Rent", "Insurance", "Professional services", "Equipment", "Marketing", "Other",
];

function CategoriesContent() {
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
      <h1 className="text-2xl font-semibold text-navy">Expense Categories</h1>
      <p className="text-sm text-text-secondary">
        Rules are company-specific -- a rule created for one company is never applied to another. AI suggestions are
        advisory only and always require accountant confirmation before being applied.
      </p>

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

      {companyId && (
        <>
          <div className="card-v2 p-4 space-y-3">
            <h2 className="font-medium text-navy">Rules</h2>
            <form onSubmit={createRule} className="flex items-end gap-3">
              <select value={ruleType} aria-label="Rule Type" onChange={(e) => setRuleType(e.target.value as CategorizationRuleType)} className="input-v2 px-2 py-2 text-sm">
                <option value="SUPPLIER_NAME">Supplier name contains</option>
                <option value="IBAN">IBAN equals</option>
                <option value="DESCRIPTION_PATTERN">Description matches pattern</option>
              </select>
              <input
                required
                value={matchValue}
                onChange={(e) => setMatchValue(e.target.value)}
                placeholder="match value"
                className="input-v2 px-3 py-2 text-sm"
              />
              <select value={ruleCategory} aria-label="Rule Category" onChange={(e) => setRuleCategory(e.target.value)} className="input-v2 px-2 py-2 text-sm">
                {EXPENSE_CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
              <button type="submit" className="rounded-md bg-navy text-white px-4 py-2 text-sm font-medium">
                Add rule
              </button>
            </form>
            <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <tbody>
                {rules.map((r) => (
                  <tr key={r.id} className="border-t border-slate-100">
                    <td className="py-1.5 text-xs text-text-secondary">{r.rule_type}</td>
                    <td className="py-1.5">{r.match_value}</td>
                    <td className="py-1.5 font-medium">{r.category}</td>
                  </tr>
                ))}
                {rules.length === 0 && (
                  <tr>
                    <td className="py-2 text-text-secondary">No rules yet for this company.</td>
                  </tr>
                )}
              </tbody>
            </table>
            </div>
          </div>

          <div className="card-v2 overflow-hidden">
            <h2 className="font-medium text-navy p-4 pb-0">Purchase transactions</h2>
            <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-text-secondary border-b border-border-subtle">
                  <th className="px-4 py-2 font-medium">Invoice</th>
                  <th className="px-4 py-2 font-medium">Counterparty</th>
                  <th className="px-4 py-2 font-medium">Amount</th>
                  <th className="px-4 py-2 font-medium">Suggestion</th>
                  <th className="px-4 py-2 font-medium">Category</th>
                  <th className="px-4 py-2 font-medium" />
                </tr>
              </thead>
              <tbody>
                {uncategorized.map((t) => (
                  <tr key={t.id} className="border-b border-slate-100 last:border-0">
                    <td className="px-4 py-2.5">{t.invoice_number ?? `#${t.id}`}</td>
                    <td className="px-4 py-2.5">{t.counterparty_name ?? "—"}</td>
                    <td className="px-4 py-2.5 font-mono">{t.net_amount}</td>
                    <td className="px-4 py-2.5">
                      {suggestions[t.id] ? (
                        <span className="text-xs text-text-secondary">
                          {suggestions[t.id].suggested_category} ({Math.round(suggestions[t.id].confidence * 100)}%)
                          {suggestions[t.id].requires_accountant_review && " · review"}
                        </span>
                      ) : (
                        <button onClick={() => suggest(t.id)} className="text-xs text-navy underline">
                          Suggest
                        </button>
                      )}
                    </td>
                    <td className="px-4 py-2.5">
                      <select
                        value={chosenCategory[t.id] ?? ""}
                        onChange={(e) => setChosenCategory((prev) => ({ ...prev, [t.id]: e.target.value }))}
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
                    <td className="px-4 py-2.5">
                      <button
                        onClick={() => categorize(t.id, true)}
                        disabled={!chosenCategory[t.id]}
                        className="rounded-md bg-navy text-white px-3 py-1 text-xs disabled:opacity-50"
                      >
                        Apply &amp; remember
                      </button>
                    </td>
                  </tr>
                ))}
                {uncategorized.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-4 text-text-secondary">
                      No purchase transactions to categorize.
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
