"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
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
  DRAFT: "status-pill-neutral",
  VALIDATION: "status-pill-warning",
  ACCOUNTANT_REVIEW: "status-pill-warning",
  APPROVED: "status-pill-info",
  READY_FOR_SUBMISSION: "status-pill-info",
  SUBMITTED: "status-pill-info",
  ACCEPTED: "status-pill-success",
  REJECTED: "status-pill-danger",
};

function StatusBadge({ status }: { status: string }) {
  return <span className={`status-pill ${STATUS_TONE[status] ?? "status-pill-neutral"}`}>{status.replace(/_/g, " ")}</span>;
}

function LoonheffingenContent() {
  const t = useTranslations("payroll");
  const tCommon = useTranslations("common");
  const tErrors = useTranslations("errors");
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
      setError(e instanceof Error ? e.message : t("createDeclarationFailed"));
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
      setError(e instanceof Error ? e.message : tErrors("generic"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <GlassPageHeader title={t("loonheffingenTitle")} subtitle={t("loonheffingenSubtitle")} />

      {error && <GlassErrorState message={error} />}

      <GlassSelect aria-label={tCommon("company")} value={companyId} onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")}>
        <option value="">{tCommon("selectCompany")}</option>
        {companies.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </GlassSelect>

      {companyId && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <GlassPanel title={t("payrollRuns")}>
            {runs.length === 0 ? (
              <GlassEmptyState title={t("noPayrollRunsYet")} description={t("createOneFromPayrollFirst")} icon={<IconTax size={28} />} />
            ) : (
              <div className="overflow-x-auto">
              <table className="table-v3">
                <thead>
                  <tr>
                    <th>{t("period")}</th>
                    <th>{tCommon("status")}</th>
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
                      className={`cursor-pointer hover:bg-muted ${selectedRun?.id === run.id ? "bg-muted" : ""}`}
                    >
                      <td className="text-text-primary">
                        {run.period_type} {run.period_number}/{run.period_year}
                      </td>
                      <td className="text-text-secondary">{run.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            )}
          </GlassPanel>

          <GlassCard>
            {!selectedRun ? (
              <p className="text-sm text-text-secondary">{t("selectRunPrompt")}</p>
            ) : !declaration ? (
              <div className="space-y-3">
                <p className="text-sm text-text-primary">
                  {t("runLabel", { type: selectedRun.period_type, number: selectedRun.period_number, year: selectedRun.period_year })}
                </p>
                <GlassButton onClick={createDeclaration} disabled={busy} size="sm">
                  {busy ? t("creatingEllipsis") : t("createDeclaration")}
                </GlassButton>
              </div>
            ) : (
              <div className="space-y-4 text-sm">
                <div className="flex items-center justify-between">
                  <h3 className="font-medium text-text-primary">{t("declarationHash", { id: declaration.id })}</h3>
                  <StatusBadge status={String(declaration.status)} />
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <p className="flex justify-between"><span className="text-text-secondary">{t("grossWages")}</span><span className="font-mono">€{String(declaration.total_gross_wages)}</span></p>
                  <p className="flex justify-between"><span className="text-text-secondary">{t("wageTaxWithheld")}</span><span className="font-mono">€{String(declaration.total_wage_tax_withheld)}</span></p>
                  <p className="flex justify-between"><span className="text-text-secondary">{t("employerPremiums")}</span><span className="font-mono">€{String(declaration.total_employer_premiums)}</span></p>
                  <p className="flex justify-between font-medium"><span>{t("totalPayable")}</span><span className="font-mono">€{String(declaration.total_payable)}</span></p>
                </div>
                {declaration.validation_errors && <GlassErrorState message={String(declaration.validation_errors)} />}

                <div className="flex flex-wrap gap-2 pt-2 border-t border-border">
                  {["DRAFT", "VALIDATION"].includes(String(declaration.status)) && (
                    <GlassButton size="sm" disabled={busy} onClick={() => act(api.validateLoonheffingenDeclaration)}>
                      {t("runValidation")}
                    </GlassButton>
                  )}
                  {declaration.status === "ACCOUNTANT_REVIEW" && (
                    <GlassButton size="sm" disabled={busy} onClick={() => act(api.approveLoonheffingenDeclaration)}>
                      {t("approveDeclaration")}
                    </GlassButton>
                  )}
                  {declaration.status === "APPROVED" && (
                    <GlassButton size="sm" disabled={busy} onClick={() => act(api.markLoonheffingenReadyForSubmission)}>
                      {t("markReadyForSubmission")}
                    </GlassButton>
                  )}
                </div>

                {declaration.status === "READY_FOR_SUBMISSION" && (
                  <div className="flex items-end gap-2 pt-2 border-t border-border">
                    <GlassInput aria-label={t("submissionReference")} placeholder={t("submissionReferencePlaceholder")} value={submissionRef} onChange={(e) => setSubmissionRef(e.target.value)} className="flex-1" />
                    <GlassButton
                      size="sm"
                      disabled={busy || !submissionRef.trim()}
                      onClick={() => act((tok, id) => api.recordLoonheffingenSubmission(tok, id, submissionRef))}
                    >
                      {t("recordSubmission")}
                    </GlassButton>
                  </div>
                )}

                {declaration.status === "SUBMITTED" && (
                  <div className="space-y-2 pt-2 border-t border-border">
                    <GlassInput aria-label={t("governmentResponseReference")} placeholder={t("governmentResponseReferencePlaceholder")} value={responseRef} onChange={(e) => setResponseRef(e.target.value)} />
                    <GlassInput aria-label={t("rejectionReason")} placeholder={t("rejectionReasonPlaceholder")} value={rejectionReason} onChange={(e) => setRejectionReason(e.target.value)} />
                    <div className="flex gap-2">
                      <GlassButton
                        size="sm"
                        disabled={busy || !responseRef.trim()}
                        onClick={() => act((tok, id) => api.recordLoonheffingenGovernmentResponse(tok, id, { accepted: true, response_reference: responseRef }))}
                      >
                        {t("recordAccepted")}
                      </GlassButton>
                      <GlassButton
                        variant="danger"
                        size="sm"
                        disabled={busy || !responseRef.trim() || !rejectionReason.trim()}
                        onClick={() => act((tok, id) => api.recordLoonheffingenGovernmentResponse(tok, id, { accepted: false, response_reference: responseRef, rejection_reason: rejectionReason }))}
                      >
                        {t("recordRejected")}
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
