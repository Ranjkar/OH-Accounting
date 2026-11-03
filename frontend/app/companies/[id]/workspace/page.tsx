"use client";

import { FormEvent, Suspense, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, CompanyWorkspace, NoteType } from "@/lib/api";

const NOTE_TYPE_LABELS: Record<NoteType, string> = {
  INTERNAL: "Internal note",
  CUSTOMER_QUESTION: "Customer question",
  MISSING_DOCUMENT_REQUEST: "Missing document request",
};

function WorkspaceContent({ companyId }: { companyId: number }) {
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
      setError(err instanceof Error ? err.message : "Failed to add note");
    }
  }

  async function handleResolve(noteId: number) {
    if (!token) return;
    try {
      await api.updateNoteStatus(token, noteId, "RESOLVED");
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update note");
    }
  }

  if (!workspace) return <p className="text-text-secondary">Loading…</p>;

  return (
    <div className="space-y-6">
      <div>
        <button onClick={() => router.push(`/companies/${companyId}`)} className="text-sm text-navy hover:underline">
          ← Back to company settings
        </button>
        <h1 className="text-2xl font-semibold text-navy mt-1">{workspace.company_name} — Workspace</h1>
        <p className="text-sm text-text-secondary">
          {workspace.vat_frequency} filing · {workspace.vat_accounting_basis.replace("_", "-")} VAT accounting
        </p>
      </div>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="card-v2 p-4">
          <p className="text-xs text-text-secondary">Financial years</p>
          <p className="text-2xl font-semibold text-navy mt-1">{workspace.financial_year_count}</p>
        </div>
        <div className="card-v2 p-4">
          <p className="text-xs text-text-secondary">Transactions</p>
          <p className="text-2xl font-semibold text-navy mt-1">{workspace.transaction_count}</p>
        </div>
        <div className="card-v2 p-4">
          <p className="text-xs text-text-secondary">Documents awaiting approval</p>
          <p className="text-2xl font-semibold text-pending mt-1">{workspace.documents_awaiting_approval}</p>
        </div>
        <div className="card-v2 p-4">
          <p className="text-xs text-text-secondary">Open customer questions</p>
          <p className="text-2xl font-semibold text-pending mt-1">{workspace.open_customer_questions}</p>
        </div>
      </div>

      <div className="card-v2">
        <div className="px-5 py-3 border-b border-border-subtle">
          <h2 className="text-sm font-medium text-navy">Period completeness</h2>
        </div>
        <div className="divide-y divide-slate-100">
          {workspace.period_completeness.map((p) => (
            <div key={p.vat_period_id} className="px-5 py-4">
              <div className="flex items-center justify-between mb-2">
                <p className="font-medium text-navy text-sm">{p.label}</p>
                <span className="text-xs text-text-secondary">Filing deadline {p.filing_deadline}</span>
              </div>
              <table className="w-full text-sm">
                <tbody>
                  {p.rows.map((row) => (
                    <tr key={row.requirement} className="border-b border-slate-50 last:border-0">
                      <td className="py-1 pr-4 text-slate-600 w-48">{row.requirement}</td>
                      <td className="py-1 pr-4 w-32">
                        <span className={row.complete ? "text-approved font-medium" : "text-pending font-medium"}>
                          {row.complete ? "Complete" : "Pending"}
                        </span>
                      </td>
                      <td className="py-1 text-text-secondary text-xs">{row.detail}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      </div>

      <div className="card-v2">
        <div className="px-5 py-3 border-b border-border-subtle">
          <h2 className="text-sm font-medium text-navy">Notes &amp; customer questions</h2>
        </div>
        <div className="divide-y divide-slate-100">
          {workspace.notes.length === 0 ? (
            <p className="px-5 py-4 text-sm text-text-secondary">No notes yet.</p>
          ) : (
            workspace.notes.map((note) => (
              <div key={note.id} className="px-5 py-3 flex items-start justify-between gap-4">
                <div>
                  <p className="text-xs text-text-secondary">
                    {NOTE_TYPE_LABELS[note.note_type]} · {note.status} · {new Date(note.created_at).toLocaleDateString()}
                  </p>
                  <p className="text-sm text-slate-800 mt-1">{note.body}</p>
                </div>
                {canEdit && note.status !== "RESOLVED" && (
                  <button onClick={() => handleResolve(note.id)} className="text-xs text-navy hover:underline whitespace-nowrap">
                    Mark resolved
                  </button>
                )}
              </div>
            ))
          )}
        </div>
        {canEdit && (
          <form onSubmit={handleAddNote} className="px-5 py-3 border-t border-slate-100 flex items-end gap-3">
            <select
              value={noteType}
              aria-label="Note Type"
              onChange={(e) => setNoteType(e.target.value as NoteType)}
              className="input-v2 px-2 py-1.5 text-sm"
            >
              <option value="INTERNAL">Internal note</option>
              <option value="CUSTOMER_QUESTION">Customer question</option>
              <option value="MISSING_DOCUMENT_REQUEST">Missing document request</option>
            </select>
            <input
              value={noteBody}
              onChange={(e) => setNoteBody(e.target.value)}
              placeholder="Write a note…"
              className="flex-1 input-v2 px-3 py-1.5 text-sm"
            />
            <button
              type="submit"
              className="btn-primary-v2 px-4 py-2 text-sm"
            >
              Add
            </button>
          </form>
        )}
      </div>

      <div className="card-v2">
        <div className="px-5 py-3 border-b border-border-subtle">
          <h2 className="text-sm font-medium text-navy">VAT returns</h2>
        </div>
        {workspace.vat_returns.length === 0 ? (
          <p className="px-5 py-4 text-sm text-text-secondary">No VAT returns computed yet.</p>
        ) : (
          <table className="w-full text-sm">
            <tbody>
              {workspace.vat_returns.map((vr) => (
                <tr key={vr.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-5 py-2.5">
                    <a href={`/vat/${vr.id}`} className="text-navy hover:underline">
                      {vr.period_label}
                    </a>
                  </td>
                  <td className="px-5 py-2.5 capitalize">{vr.status.replaceAll("_", " ")}</td>
                  <td className="px-5 py-2.5">{vr.net_payable}</td>
                </tr>
              ))}
            </tbody>
          </table>
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
