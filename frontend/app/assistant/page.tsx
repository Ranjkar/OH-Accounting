"use client";

import { FormEvent, useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, AssistantResponse, Company } from "@/lib/api";

function AssistantContent() {
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
      setError(err instanceof Error ? err.message : "The assistant could not answer that");
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
      <h1 className="text-2xl font-semibold text-navy">Accountant Assistant</h1>
      <p className="text-sm text-text-secondary max-w-2xl">
        The assistant explains and summarizes using the figures already computed by the accounting engine. It
        cannot change, approve, or lock any record, and it is instructed never to state a number that isn&apos;t
        in the underlying facts.
      </p>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="card-v2 p-5 space-y-4">
        <select
          value={companyId}
          aria-label="Company"
          onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")}
          className="input-v2 px-3 py-2 text-sm"
        >
          <option value="">Select a company…</option>
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
            className="input-v2 px-3 py-1.5 text-sm hover:bg-slate-50 transition-colors disabled:opacity-50"
          >
            Summarize financial position
          </button>
          <button
            disabled={!companyId || loading}
            onClick={() => companyId && run(() => api.assistantMissingDocuments(token!, Number(companyId)))}
            className="input-v2 px-3 py-1.5 text-sm hover:bg-slate-50 transition-colors disabled:opacity-50"
          >
            Identify missing documents
          </button>
        </div>

        <form onSubmit={handleAsk} className="flex items-end gap-3">
          <div className="flex-1 space-y-1">
            <label className="text-xs font-medium text-text-secondary">Ask a question</label>
            <input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="e.g. Why does this company have overdue payments?"
              className="w-full input-v2 px-3 py-2 text-sm"
            />
          </div>
          <button
            type="submit"
            disabled={!companyId || loading}
            className="btn-primary-v2 px-4 py-2 text-sm disabled:opacity-50"
          >
            {loading ? "Thinking…" : "Ask"}
          </button>
        </form>
      </div>

      {response && (
        <div className="card-v2 p-5 space-y-4">
          <div className="whitespace-pre-wrap text-sm text-slate-800">{response.answer}</div>
          <div className="rounded-md bg-amber-50 border border-amber-200 text-pending text-xs px-3 py-2">
            {response.disclaimer}
          </div>
          <details className="text-xs text-text-secondary">
            <summary className="cursor-pointer hover:text-navy">View underlying facts (what the assistant was given)</summary>
            <pre className="mt-2 overflow-x-auto bg-slate-50 rounded-md p-3 text-xs">{JSON.stringify(response.facts, null, 2)}</pre>
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
