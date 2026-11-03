"use client";

import { FormEvent, useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, Budget, Company, FinancialYear, JsonReport } from "@/lib/api";

const MONTHS = Array.from({ length: 12 }, (_, i) => i + 1);

function BudgetsContent() {
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [financialYears, setFinancialYears] = useState<FinancialYear[]>([]);
  const [financialYearId, setFinancialYearId] = useState<number | "">("");
  const [budgets, setBudgets] = useState<Budget[]>([]);
  const [selected, setSelected] = useState<Budget | null>(null);
  const [variance, setVariance] = useState<JsonReport | null>(null);
  const [name, setName] = useState("");
  const [category, setCategory] = useState("Revenue");
  const [month, setMonth] = useState(1);
  const [amount, setAmount] = useState("");
  const [draftLines, setDraftLines] = useState<{ category: string; month: number; amount: string }[]>([]);
  const [suggestion, setSuggestion] = useState<JsonReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  useEffect(() => {
    if (!token || !companyId) return;
    api.listFinancialYears(token, Number(companyId)).then(setFinancialYears).catch((e) => setError(e.message));
  }, [token, companyId]);

  function refreshBudgets() {
    if (!token || !companyId) return;
    api.listBudgets(token, Number(companyId), financialYearId ? Number(financialYearId) : undefined).then(setBudgets).catch((e) => setError(e.message));
  }

  useEffect(refreshBudgets, [token, companyId, financialYearId]);

  async function viewBudget(budget: Budget) {
    if (!token) return;
    setSelected(budget);
    try {
      setVariance(await api.budgetVariance(token, budget.id));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  function addDraftLine() {
    if (!amount) return;
    setDraftLines((prev) => [...prev, { category, month, amount }]);
    setAmount("");
  }

  async function createBudget(e: FormEvent) {
    e.preventDefault();
    if (!token || !companyId || !financialYearId) return;
    try {
      await api.createBudget(token, { company_id: Number(companyId), financial_year_id: Number(financialYearId), name, lines: draftLines });
      setName("");
      setDraftLines([]);
      refreshBudgets();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function submit(budget: Budget) {
    if (!token) return;
    await api.submitBudget(token, budget.id);
    refreshBudgets();
  }

  async function approve(budget: Budget) {
    if (!token) return;
    try {
      await api.approveBudget(token, budget.id);
      refreshBudgets();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function getSuggestion() {
    if (!token || !companyId || !financialYearId) return;
    try {
      setSuggestion(await api.suggestBudget(token, Number(companyId), Number(financialYearId)));
      setMessage(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-navy">Budgets</h1>
      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}
      {message && <div className="rounded-md bg-green-50 text-green-700 text-sm px-3 py-2">{message}</div>}

      <div className="flex items-center gap-3">
        <select value={companyId} aria-label="Company" onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")} className="input-v2 px-3 py-2 text-sm">
          <option value="">Select a company</option>
          {companies.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <select value={financialYearId} aria-label="Financial Year" onChange={(e) => setFinancialYearId(e.target.value ? Number(e.target.value) : "")} className="input-v2 px-3 py-2 text-sm">
          <option value="">All financial years</option>
          {financialYears.map((fy) => (
            <option key={fy.id} value={fy.id}>
              {fy.year}
            </option>
          ))}
        </select>
      </div>

      {companyId && financialYearId && (
        <div className="card-v2 p-4 space-y-3">
          <h2 className="font-medium text-navy">Create a budget</h2>
          <button onClick={getSuggestion} className="text-xs text-navy underline">
            Get AI suggestion from last year&apos;s actuals
          </button>
          {suggestion && (
            <div className="bg-slate-50 rounded-md p-3 text-xs space-y-1">
              {suggestion.ai_suggestion.suggestions.map((s: JsonReport) => (
                <p key={s.category}>
                  <span className="font-medium">{s.category}</span>: {s.suggested_monthly_amount}/mo -- {s.reasoning}
                </p>
              ))}
              <p className="text-text-secondary">AI suggestions always require review before use -- never auto-applied.</p>
            </div>
          )}
          <form onSubmit={createBudget} className="space-y-3">
            <input required value={name} aria-label="Name" onChange={(e) => setName(e.target.value)} placeholder="Budget name" className="input-v2 px-3 py-2 text-sm w-64" />
            <div className="flex items-end gap-2">
              <input value={category} aria-label="Category" onChange={(e) => setCategory(e.target.value)} placeholder="Category (e.g. Revenue, Rent)" className="input-v2 px-3 py-2 text-sm w-48" />
              <select value={month} aria-label="Month" onChange={(e) => setMonth(Number(e.target.value))} className="input-v2 px-2 py-2 text-sm">
                {MONTHS.map((m) => (
                  <option key={m} value={m}>
                    Month {m}
                  </option>
                ))}
              </select>
              <input value={amount} aria-label="Amount" onChange={(e) => setAmount(e.target.value)} placeholder="Amount" className="input-v2 px-3 py-2 text-sm w-32" />
              <button type="button" onClick={addDraftLine} className="input-v2 px-3 py-2 text-sm">
                Add line
              </button>
            </div>
            {draftLines.length > 0 && (
              <ul className="text-xs text-slate-600 space-y-0.5">
                {draftLines.map((l, i) => (
                  <li key={i}>
                    {l.category} / month {l.month}: {l.amount}
                  </li>
                ))}
              </ul>
            )}
            <button type="submit" className="rounded-md bg-navy text-white px-4 py-2 text-sm font-medium">
              Create budget
            </button>
          </form>
        </div>
      )}

      <div className="grid grid-cols-2 gap-6">
        <div className="card-v2 overflow-hidden">
          <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-text-secondary border-b border-border-subtle">
                <th className="px-4 py-2 font-medium">Name</th>
                <th className="px-4 py-2 font-medium">Version</th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium" />
              </tr>
            </thead>
            <tbody>
              {budgets.map((b) => (
                <tr key={b.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50 cursor-pointer" onClick={() => viewBudget(b)}>
                  <td className="px-4 py-2.5">{b.name}</td>
                  <td className="px-4 py-2.5">v{b.version}</td>
                  <td className="px-4 py-2.5">{b.status}</td>
                  <td className="px-4 py-2.5 text-xs">
                    {b.status === "DRAFT" && (
                      <button onClick={(e) => { e.stopPropagation(); submit(b); }} className="text-navy underline">
                        Submit
                      </button>
                    )}
                    {b.status === "SUBMITTED" && (
                      <button onClick={(e) => { e.stopPropagation(); approve(b); }} className="text-navy underline">
                        Approve
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {budgets.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-4 text-text-secondary">
                    No budgets yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          </div>
        </div>

        <div className="card-v2 p-4">
          {variance && selected ? (
            <div className="space-y-2 text-sm">
              <h3 className="font-medium text-navy">{variance.budget_name} -- actual vs budget</h3>
              {variance.lines.length === 0 && <p className="text-text-secondary">No lines in this budget.</p>}
              {variance.lines.map((l: JsonReport, i: number) => (
                <div key={i} className="flex items-center justify-between border-b border-slate-100 py-1">
                  <span>
                    {l.category} (month {l.month})
                  </span>
                  <span className="font-mono">
                    {l.actual} / {l.budgeted}{" "}
                    <span className={Number(l.variance) < 0 ? "text-error" : "text-green-700"}>
                      ({l.variance_pct !== null ? `${l.variance_pct}%` : "n/a"})
                    </span>
                  </span>
                </div>
              ))}
              <div className="flex items-center justify-between font-medium pt-2">
                <span>Total variance</span>
                <span className="font-mono">{variance.total_variance}</span>
              </div>
              <div className="flex items-center gap-2 pt-2 text-xs">
                <a href={api.budgetVsActualReportUrl(selected.id, "pdf")} className="input-v2 px-2 py-1">
                  Export PDF
                </a>
                <a href={api.budgetVsActualReportUrl(selected.id, "csv")} className="input-v2 px-2 py-1">
                  Export CSV
                </a>
              </div>
            </div>
          ) : (
            <p className="text-sm text-text-secondary">Select a budget to see actual vs budget.</p>
          )}
        </div>
      </div>
    </div>
  );
}

export default function BudgetsPage() {
  return (
    <AuthGuard>
      <Shell>
        <BudgetsContent />
      </Shell>
    </AuthGuard>
  );
}
