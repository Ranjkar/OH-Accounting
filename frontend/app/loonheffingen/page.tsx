"use client";

import { useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import GlassPageHeader from "@/components/glass/GlassPageHeader";
import GlassPanel from "@/components/glass/GlassPanel";
import GlassCard from "@/components/glass/GlassCard";
import GlassButton from "@/components/glass/GlassButton";
import { GlassSelect, GlassInput } from "@/components/glass/GlassInput";
import GlassEmptyState from "@/components/glass/GlassEmptyState";
import { GlassErrorState } from "@/components/glass/GlassLoadingState";
import { IconTax } from "@/components/glass/icons";
import { useAuth } from "@/lib/auth-context";
import { api, Company, JsonReport } from "@/lib/api";

const STATUS_TONE: Record<string, string> = {
  DRAFT: "bg-slate-200 text-slate-700",
  VALIDATION: "bg-amber-100 text-amber-700",
  ACCOUNTANT_REVIEW: "bg-amber-100 text-amber-700",
  APPROVED: "bg-blue-100 text-blue-700",
  READY_FOR_SUBMISSION: "bg-blue-100 text-blue-700",
  SUBMITTED: "bg-indigo-100 text-indigo-700",
  ACCEPTED: "bg-green-100 text-green-700",
  REJECTED: "bg-red-100 text-red-700",
};

function StatusBadge({ status }: { status: string }) {
  return <span className={`text-xs font-medium rounded-full px-2.5 py-1 ${STATUS_TONE[status] ?? "bg-slate-200 text-slate-700"}`}>{status.replace(/_/g, " ")}</span>;
}

function LoonheffingenContent() {
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [runs, setRuns] = useState<JsonReport[]>([]);
  const [selectedRun, setSelectedRun] = useState<JsonReport | null>(null);
  const [declaration, setDeclaration] = useState<JsonReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submissionRef, setSubmissionRef] = useState("");
  const [responseRef, setResponseRef] = useState("");
  const [rejectionReason, setRejectionReason] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  useEffect(() => {
    if (!token || !companyId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setRuns([]);
      return;
    }
    api.listPayrollRuns(token, Number(companyId)).then(setRuns).catch((e) => setError(e.message));
  }, [token, companyId]);

  async function selectRun(run: JsonReport) {
    setSelectedRun(run);
    setDeclaration(null);
    setError(null);
  }

  async function createDeclaration() {
    if (!token || !selectedRun) return;
    setBusy(true);
    setError(null);
    try {
      setDeclaration(await api.createLoonheffingenDeclaration(token, selectedRun.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create declaration");
    } finally {
      setBusy(false);
    }
  }

  async function act(action: (token: string, id: number) => Promise<JsonReport>) {
    if (!token || !declaration) return;
    setBusy(true);
    setError(null);
    try {
      setDeclaration(await action(token, declaration.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <GlassPageHeader
        title="Payroll Tax (Loonheffingen)"
        subtitle="Draft → Validation → Accountant Review → Approved → Ready for Submission → Submitted → Accepted/Rejected. There is no live SBR/Digipoort connection -- submission and government response are only ever recorded from what you explicitly tell this system happened outside it."
      />

      {error && <GlassErrorState message={error} />}

      <GlassSelect aria-label="Company" value={companyId} onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")}>
        <option value="">Select a company</option>
        {companies.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </GlassSelect>

      {companyId && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <GlassPanel title="Payroll runs">
            {runs.length === 0 ? (
              <GlassEmptyState title="No payroll runs yet" description="Create one from Payroll Runs & Payslips first." icon={<IconTax size={28} />} />
            ) : (
              <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-text-secondary border-b border-border">
                    <th className="px-4 py-2 font-medium">Period</th>
                    <th className="px-4 py-2 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((run) => (
                    <tr
                      key={run.id}
                      onClick={() => selectRun(run)}
                      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectRun(run); } }}
                      tabIndex={0}
                      role="button"
                      className={`border-b border-border last:border-0 cursor-pointer hover:bg-muted ${selectedRun?.id === run.id ? "bg-muted" : ""}`}
                    >
                      <td className="px-4 py-2.5">
                        {run.period_type} {run.period_number}/{run.period_year}
                      </td>
                      <td className="px-4 py-2.5">{run.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            )}
          </GlassPanel>

          <GlassCard>
            {!selectedRun ? (
              <p className="text-sm text-text-secondary">Select a payroll run to view or create its declaration.</p>
            ) : !declaration ? (
              <div className="space-y-3">
                <p className="text-sm text-text-primary">
                  Run: {selectedRun.period_type} {selectedRun.period_number}/{selectedRun.period_year}
                </p>
                <GlassButton onClick={createDeclaration} disabled={busy} size="sm">
                  {busy ? "Creating…" : "Create declaration"}
                </GlassButton>
              </div>
            ) : (
              <div className="space-y-4 text-sm">
                <div className="flex items-center justify-between">
                  <h3 className="font-medium text-text-primary">Declaration #{declaration.id}</h3>
                  <StatusBadge status={String(declaration.status)} />
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <p className="flex justify-between"><span className="text-text-secondary">Gross wages</span><span className="font-mono">€{String(declaration.total_gross_wages)}</span></p>
                  <p className="flex justify-between"><span className="text-text-secondary">Wage tax withheld</span><span className="font-mono">€{String(declaration.total_wage_tax_withheld)}</span></p>
                  <p className="flex justify-between"><span className="text-text-secondary">Employer premiums</span><span className="font-mono">€{String(declaration.total_employer_premiums)}</span></p>
                  <p className="flex justify-between font-medium"><span>Total payable</span><span className="font-mono">€{String(declaration.total_payable)}</span></p>
                </div>
                {declaration.validation_errors && <GlassErrorState message={String(declaration.validation_errors)} />}

                <div className="flex flex-wrap gap-2 pt-2 border-t border-border">
                  {["DRAFT", "VALIDATION"].includes(String(declaration.status)) && (
                    <GlassButton size="sm" disabled={busy} onClick={() => act(api.validateLoonheffingenDeclaration)}>
                      Run validation
                    </GlassButton>
                  )}
                  {declaration.status === "ACCOUNTANT_REVIEW" && (
                    <GlassButton size="sm" disabled={busy} onClick={() => act(api.approveLoonheffingenDeclaration)}>
                      Approve
                    </GlassButton>
                  )}
                  {declaration.status === "APPROVED" && (
                    <GlassButton size="sm" disabled={busy} onClick={() => act(api.markLoonheffingenReadyForSubmission)}>
                      Mark ready for submission
                    </GlassButton>
                  )}
                </div>

                {declaration.status === "READY_FOR_SUBMISSION" && (
                  <div className="flex items-end gap-2 pt-2 border-t border-border">
                    <GlassInput aria-label="Submission reference" placeholder="SBR/Digipoort kenmerk from your filing software" value={submissionRef} onChange={(e) => setSubmissionRef(e.target.value)} className="flex-1" />
                    <GlassButton
                      size="sm"
                      disabled={busy || !submissionRef.trim()}
                      onClick={() => act((t, id) => api.recordLoonheffingenSubmission(t, id, submissionRef))}
                    >
                      Record submission
                    </GlassButton>
                  </div>
                )}

                {declaration.status === "SUBMITTED" && (
                  <div className="space-y-2 pt-2 border-t border-border">
                    <GlassInput aria-label="Government response reference" placeholder="Belastingdienst response reference" value={responseRef} onChange={(e) => setResponseRef(e.target.value)} />
                    <GlassInput aria-label="Rejection reason" placeholder="Rejection reason (only if rejecting)" value={rejectionReason} onChange={(e) => setRejectionReason(e.target.value)} />
                    <div className="flex gap-2">
                      <GlassButton
                        size="sm"
                        disabled={busy || !responseRef.trim()}
                        onClick={() => act((t, id) => api.recordLoonheffingenGovernmentResponse(t, id, { accepted: true, response_reference: responseRef }))}
                      >
                        Record accepted
                      </GlassButton>
                      <GlassButton
                        variant="danger"
                        size="sm"
                        disabled={busy || !responseRef.trim() || !rejectionReason.trim()}
                        onClick={() => act((t, id) => api.recordLoonheffingenGovernmentResponse(t, id, { accepted: false, response_reference: responseRef, rejection_reason: rejectionReason }))}
                      >
                        Record rejected
                      </GlassButton>
                    </div>
                  </div>
                )}
              </div>
            )}
          </GlassCard>
        </div>
      )}
    </div>
  );
}

export default function LoonheffingenPage() {
  return (
    <AuthGuard>
      <Shell>
        <LoonheffingenContent />
      </Shell>
    </AuthGuard>
  );
}
