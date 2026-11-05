"use client";

import { FormEvent, Suspense, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, CompanyWorkspace, NoteType } from "@/lib/api";
import { formatEUR } from "@/lib/format";

const NOTE_TYPE_KEY: Record<NoteType, string> = {
  INTERNAL: "noteTypeInternal",
  CUSTOMER_QUESTION: "noteTypeCustomerQuestion",
  MISSING_DOCUMENT_REQUEST: "noteTypeMissingDocumentRequest",
};

function WorkspaceContent({ companyId }: { companyId: number }) {
  const t = useTranslations("companies.workspace");
  const tCommon = useTranslations("common");
  const { token, user } = useAuth();
  const router = useRouter();
  const canEdit = user?.role === "admin" || user?.role === "accountant";

  const [workspace, setWorkspace] = useState<CompanyWorkspace | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [noteType, setNoteType] = useState<NoteType>("INTERNAL");
  const [noteBody, setNoteBody] = useState("");

  function refresh() {
    if (!token) return;
    api.getCompanyWorkspace(token, companyId).then(setWorkspace).catch((e) => setError(e.message));
  }

  useEffect(refresh, [token, companyId]);

  async function handleAddNote(e: FormEvent) {
    e.preventDefault();
    if (!token || !noteBody.trim()) return;
    try {
      await api.createNote(token, companyId, { note_type: noteType, body: noteBody });
      setNoteBody("");
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("addNoteFailed"));
    }
  }

  async function handleResolve(noteId: number) {
    if (!token) return;
    try {
      await api.updateNoteStatus(token, noteId, "RESOLVED");
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("updateNoteFailed"));
    }
  }

  if (!workspace) return <p className="text-text-secondary">{tCommon("loading")}</p>;

  return (
    <div className="space-y-6">
      <div>
        <button onClick={() => router.push(`/companies/${companyId}`)} className="text-sm text-navy hover:underline">
          {t("backToCompanySettings")}
        </button>
        <h1 className="text-2xl font-semibold text-navy mt-1">{t("workspaceHeading", { company: workspace.company_name })}</h1>
        <p className="text-sm text-text-secondary">
          {t("filingAndBasis", { frequency: workspace.vat_frequency, basis: workspace.vat_accounting_basis.replace("_", "-") })}
        </p>
      </div>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="card-v2 p-4">
          <p className="text-xs text-text-secondary">{t("financialYears")}</p>
          <p className="text-2xl font-semibold text-navy mt-1">{workspace.financial_year_count}</p>
        </div>
        <div className="card-v2 p-4">
          <p className="text-xs text-text-secondary">{t("transactions")}</p>
          <p className="text-2xl font-semibold text-navy mt-1">{workspace.transaction_count}</p>
        </div>
        <div className="card-v2 p-4">
          <p className="text-xs text-text-secondary">{t("documentsAwaitingApproval")}</p>
          <p className="text-2xl font-semibold text-pending mt-1">{workspace.documents_awaiting_approval}</p>
        </div>
        <div className="card-v2 p-4">
          <p className="text-xs text-text-secondary">{t("openCustomerQuestions")}</p>
          <p className="text-2xl font-semibold text-pending mt-1">{workspace.open_customer_questions}</p>
        </div>
      </div>

      <div className="card-v2">
        <div className="px-5 py-3 border-b border-border-subtle">
          <h2 className="text-sm font-medium text-text-primary">{t("periodCompleteness")}</h2>
        </div>
        <div className="divide-y divide-border">
          {workspace.period_completeness.map((p) => (
            <div key={p.vat_period_id} className="px-5 py-4">
              <div className="flex items-center justify-between mb-2">
                <p className="font-medium text-navy text-sm">{p.label}</p>
                <span className="text-xs text-text-secondary">{t("filingDeadlineOn", { date: p.filing_deadline })}</span>
              </div>
              <div className="overflow-x-auto">
              <table className="table-v3">
                <tbody>
                  {p.rows.map((row) => (
                    <tr key={row.requirement}>
                      <td className="text-text-secondary w-48">{row.requirement}</td>
                      <td className="w-32">
                        <span className={`status-pill ${row.complete ? "status-pill-success" : "status-pill-warning"}`}>
                          {row.complete ? t("complete") : t("pending")}
                        </span>
                      </td>
                      <td className="text-text-secondary text-xs">{row.detail}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="card-v2">
        <div className="px-5 py-3 border-b border-border-subtle">
          <h2 className="text-sm font-medium text-text-primary">{t("notesAndCustomerQuestions")}</h2>
        </div>
        <div className="divide-y divide-border">
          {workspace.notes.length === 0 ? (
            <p className="px-5 py-4 text-sm text-text-secondary">{t("noNotesYet")}</p>
          ) : (
            workspace.notes.map((note) => (
              <div key={note.id} className="px-5 py-3 flex items-start justify-between gap-4">
                <div>
                  <p className="text-xs text-text-secondary">
                    {t(NOTE_TYPE_KEY[note.note_type] as never)} · {note.status === "RESOLVED" ? t("noteStatusResolved") : t("noteStatusOpen")} · {new Date(note.created_at).toLocaleDateString()}
                  </p>
                  <p className="text-sm text-text-primary mt-1">{note.body}</p>
                </div>
                {canEdit && note.status !== "RESOLVED" && (
                  <button onClick={() => handleResolve(note.id)} className="text-xs text-navy hover:underline whitespace-nowrap">
                    {t("markResolved")}
                  </button>
                )}
              </div>
            ))
          )}
        </div>
        {canEdit && (
          <form onSubmit={handleAddNote} className="px-5 py-3 border-t border-border flex items-end gap-3">
            <select
              value={noteType}
              aria-label={t("noteTypeLabel")}
              onChange={(e) => setNoteType(e.target.value as NoteType)}
              className="input-v2 px-2 py-1.5 text-sm"
            >
              <option value="INTERNAL">{t("noteTypeInternal")}</option>
              <option value="CUSTOMER_QUESTION">{t("noteTypeCustomerQuestion")}</option>
              <option value="MISSING_DOCUMENT_REQUEST">{t("noteTypeMissingDocumentRequest")}</option>
            </select>
            <input
              value={noteBody}
              onChange={(e) => setNoteBody(e.target.value)}
              placeholder={t("writeNotePlaceholder")}
              className="flex-1 input-v2 px-3 py-1.5 text-sm"
            />
            <button
              type="submit"
              className="btn-primary-v2 px-4 py-2 text-sm"
            >
              {t("addNoteButton")}
            </button>
          </form>
        )}
      </div>

      <div className="card-v2">
        <div className="px-5 py-3 border-b border-border-subtle">
          <h2 className="text-sm font-medium text-text-primary">{t("vatReturns")}</h2>
        </div>
        {workspace.vat_returns.length === 0 ? (
          <p className="px-5 py-4 text-sm text-text-secondary">{t("noVatReturnsYet")}</p>
        ) : (
          <div className="overflow-x-auto">
          <table className="table-v3">
            <thead>
              <tr>
                <th>{t("colPeriod")}</th>
                <th>{t("colStatus")}</th>
                <th className="text-right">{t("colNetPayable")}</th>
              </tr>
            </thead>
            <tbody>
              {workspace.vat_returns.map((vr) => (
                <tr key={vr.id}>
                  <td>
                    <a href={`/vat/${vr.id}`} className="text-navy hover:underline">
                      {vr.period_label}
                    </a>
                  </td>
                  <td className="text-text-secondary capitalize">{vr.status.replaceAll("_", " ")}</td>
                  <td className="col-amount">{formatEUR(vr.net_payable)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </div>
    </div>
  );
}

function WorkspaceRoute() {
  const params = useParams<{ id: string }>();
  return (
    <AuthGuard>
      <Shell>
        <WorkspaceContent companyId={Number(params.id)} />
      </Shell>
    </AuthGuard>
  );
}

export default function CompanyWorkspacePage() {
  return (
    <Suspense>
      <WorkspaceRoute />
    </Suspense>
  );
}
