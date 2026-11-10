"use client";

import { FormEvent, useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, Budget, BudgetStatus, Company, FinancialYear, JsonReport } from "@/lib/api";
import { formatEUR } from "@/lib/format";

const BUDGET_STATUS_PILL: Record<BudgetStatus, string> = {
  DRAFT: "status-pill-neutral",
  SUBMITTED: "status-pill-info",
  APPROVED: "status-pill-success",
};

const MONTHS = Array.from({ length: 12 }, (_, i) => i + 1);

function BudgetsContent() {
  const t = useTranslations("budgets");
  const tCommon = useTranslations("common");
  const locale = useLocale();
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
      <h1 className="text-2xl font-semibold text-text-primary">{t("title")}</h1>
      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}
      {message && <div className="rounded-md bg-green-50 text-green-700 text-sm px-3 py-2">{message}</div>}

      <div className="flex flex-wrap items-center gap-3">
        <select value={companyId} aria-label={tCommon("company")} onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")} className="input-v2 px-3 py-2 text-sm">
          <option value="">{tCommon("selectCompany")}</option>
          {companies.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <select value={financialYearId} aria-label={t("financialYear")} onChange={(e) => setFinancialYearId(e.target.value ? Number(e.target.value) : "")} className="input-v2 px-3 py-2 text-sm">
          <option value="">{t("allFinancialYears")}</option>
          {financialYears.map((fy) => (
            <option key={fy.id} value={fy.id}>
              {fy.year}
            </option>
          ))}
        </select>
      </div>

      {companyId && financialYearId && (
        <div className="card-v2 p-4 space-y-3">
          <h2 className="font-medium text-text-primary">{t("createBudget")}</h2>
          <button onClick={getSuggestion} className="text-xs text-navy underline">
            {t("getAiSuggestion")}
          </button>
          {suggestion && (
            <div className="bg-muted rounded-md p-3 text-xs space-y-1">
              {suggestion.ai_suggestion.suggestions.map((s: JsonReport) => (
                <p key={s.category}>
                  <span className="font-medium">{s.category}</span>: {formatEUR(s.suggested_monthly_amount, locale)}{t("perMonthSuffix")} -- {s.reasoning}
                </p>
              ))}
              <p className="text-text-secondary">{t("aiSuggestionReviewNotice")}</p>
            </div>
          )}
          <form onSubmit={createBudget} className="space-y-3">
            <input required value={name} aria-label={tCommon("name")} onChange={(e) => setName(e.target.value)} placeholder={t("budgetName")} className="input-v2 px-3 py-2 text-sm w-64" />
            <div className="flex flex-wrap items-end gap-2">
              <input value={category} aria-label={t("category")} onChange={(e) => setCategory(e.target.value)} placeholder={t("categoryPlaceholder")} className="input-v2 px-3 py-2 text-sm w-48" />
              <select value={month} aria-label={t("month")} onChange={(e) => setMonth(Number(e.target.value))} className="input-v2 px-2 py-2 text-sm">
                {MONTHS.map((m) => (
                  <option key={m} value={m}>
                    {t("monthNumber", { month: m })}
                  </option>
                ))}
              </select>
              <input inputMode="decimal" value={amount} aria-label={tCommon("amount")} onChange={(e) => setAmount(e.target.value)} placeholder={tCommon("amount")} className="input-v2 px-3 py-2 text-sm w-32" />
              <button type="button" onClick={addDraftLine} className="input-v2 px-3 py-2 text-sm">
                {t("addLine")}
              </button>
            </div>
            {draftLines.length > 0 && (
              <ul className="text-xs text-text-secondary space-y-0.5">
                {draftLines.map((l, i) => (
                  <li key={i}>
                    {t("draftLineSummary", { category: l.category, month: l.month, amount: formatEUR(l.amount, locale) })}
                  </li>
                ))}
              </ul>
            )}
            <button type="submit" className="rounded-md bg-navy-solid text-white px-4 py-2 text-sm font-medium">
              {t("createBudget")}
            </button>
          </form>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card-v2 overflow-hidden">
          <div className="overflow-x-auto" tabIndex={0}>
          <table className="table-v3">
            <thead>
              <tr>
                <th>{tCommon("name")}</th>
                <th>{t("version")}</th>
                <th>{tCommon("status")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {budgets.map((b) => (
                <tr key={b.id} className="cursor-pointer hover:bg-muted" onClick={() => viewBudget(b)}>
                  <td className="text-text-primary">{b.name}</td>
                  <td className="text-text-secondary">v{b.version}</td>
                  <td><span className={`status-pill ${BUDGET_STATUS_PILL[b.status]}`}>{t(`status.${b.status.toLowerCase()}` as never)}</span></td>
                  <td className="text-xs">
                    {b.status === "DRAFT" && (
                      <button onClick={(e) => { e.stopPropagation(); submit(b); }} className="text-navy hover:underline">
                        {t("submit")}
                      </button>
                    )}
                    {b.status === "SUBMITTED" && (
                      <button onClick={(e) => { e.stopPropagation(); approve(b); }} className="text-navy hover:underline">
                        {t("approve")}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {budgets.length === 0 && (
                <tr>
                  <td colSpan={4} className="text-text-secondary">
                    {t("noBudgetsYet")}
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
              <h3 className="font-medium text-text-primary">{t("actualVsBudget", { name: variance.budget_name })}</h3>
              {variance.lines.length === 0 && <p className="text-text-secondary">{t("noLinesInBudget")}</p>}
              {variance.lines.map((l: JsonReport, i: number) => (
                <div key={i} className="flex items-center justify-between border-b border-border py-1">
                  <span>
                    {t("categoryMonthLabel", { category: l.category, month: l.month })}
                  </span>
                  <span className="font-mono tabular-nums">
                    {formatEUR(l.actual, locale)} / {formatEUR(l.budgeted, locale)}{" "}
                    <span className={Number(l.variance) < 0 ? "value-negative" : "value-positive"}>
                      ({l.variance_pct !== null ? `${l.variance_pct}%` : t("notApplicable")})
                    </span>
                  </span>
                </div>
              ))}
              <div className="flex items-center justify-between font-medium pt-2">
                <span>{t("totalVariance")}</span>
                <span className="font-mono tabular-nums">{formatEUR(variance.total_variance, locale)}</span>
              </div>
              <div className="flex items-center gap-2 pt-2 text-xs">
                <a href={api.budgetVsActualReportUrl(selected.id, "pdf")} className="input-v2 px-2 py-1">
                  {tCommon("export")} PDF
                </a>
                <a href={api.budgetVsActualReportUrl(selected.id, "csv")} className="input-v2 px-2 py-1">
                  {tCommon("export")} CSV
                </a>
              </div>
            </div>
          ) : (
            <p className="text-sm text-text-secondary">{t("selectBudgetToSeeVariance")}</p>
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
