"use client";

import { FormEvent, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, AssistantResponse, Company } from "@/lib/api";

function AssistantContent() {
  const t = useTranslations("assistant");
  const tCommon = useTranslations("common");
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [question, setQuestion] = useState("");
  const [response, setResponse] = useState<AssistantResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  async function run(action: () => Promise<AssistantResponse>) {
    setError(null);
    setLoading(true);
    setResponse(null);
    try {
      setResponse(await action());
    } catch (err) {
      setError(err instanceof Error ? err.message : t("couldNotAnswer"));
    } finally {
      setLoading(false);
    }
  }

  async function handleAsk(e: FormEvent) {
    e.preventDefault();
    if (!token || !companyId || !question.trim()) return;
    await run(() => api.askAssistant(token, { company_id: Number(companyId), question }));
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-text-primary">{t("title")}</h1>
      <p className="text-sm text-text-secondary max-w-2xl">
        {t("pageExplainer")}
      </p>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="card-v2 p-5 space-y-4">
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

        <div className="flex flex-wrap gap-2">
          <button
            disabled={!companyId || loading}
            onClick={() => companyId && run(() => api.assistantCompanySummary(token!, Number(companyId)))}
            className="input-v2 px-3 py-1.5 text-sm hover:bg-muted transition-colors disabled:opacity-50"
          >
            {t("summarizeFinancialPosition")}
          </button>
          <button
            disabled={!companyId || loading}
            onClick={() => companyId && run(() => api.assistantMissingDocuments(token!, Number(companyId)))}
            className="input-v2 px-3 py-1.5 text-sm hover:bg-muted transition-colors disabled:opacity-50"
          >
            {t("identifyMissingDocuments")}
          </button>
        </div>

        <form onSubmit={handleAsk} className="flex items-end gap-3">
          <div className="flex-1 space-y-1">
            <label className="text-xs font-medium text-text-secondary">{t("askAQuestion")}</label>
            <input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder={t("askExamplePlaceholder")}
              className="w-full input-v2 px-3 py-2 text-sm"
            />
          </div>
          <button
            type="submit"
            disabled={!companyId || loading}
            className="btn-primary-v2 px-4 py-2 text-sm disabled:opacity-50"
          >
            {loading ? t("thinking") : t("ask")}
          </button>
        </form>
      </div>

      {response && (
        <div className="card-v2 p-5 space-y-4">
          <div className="whitespace-pre-wrap text-sm text-text-primary">{response.answer}</div>
          <div className="rounded-md bg-amber-50 border border-amber-200 text-pending text-xs px-3 py-2">
            {response.disclaimer}
          </div>
          <details className="text-xs text-text-secondary">
            <summary className="cursor-pointer hover:text-navy">{t("viewUnderlyingFacts")}</summary>
            <pre className="mt-2 overflow-x-auto bg-muted rounded-md p-3 text-xs" dir="ltr">{JSON.stringify(response.facts, null, 2)}</pre>
          </details>
        </div>
      )}
    </div>
  );
}

export default function AssistantPage() {
  return (
    <AuthGuard>
      <Shell>
        <AssistantContent />
      </Shell>
    </AuthGuard>
  );
}
