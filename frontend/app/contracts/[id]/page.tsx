"use client";

import { FormEvent, ReactNode, Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import GlassPanel from "@/components/glass/GlassPanel";
import GlassButton from "@/components/glass/GlassButton";
import GlassModal from "@/components/glass/GlassModal";
import GlassLoadingState, { GlassErrorState } from "@/components/glass/GlassLoadingState";
import { GlassInput, GlassSelect } from "@/components/glass/GlassInput";
import { ContractStatusPill, SigningStatusPill } from "@/components/contracts/ContractStatusPill";
import { feeLabel } from "@/components/contracts/ContractsTable";
import { useAuth } from "@/lib/auth-context";
import { api, ApiError, ContractDetail, ContractLanguage, ContractUpdatePayload } from "@/lib/api";
import { formatDate } from "@/lib/format";

const ADMIN = new Set(["owner", "admin"]);
const EDITOR = new Set(["owner", "admin", "accountant"]);
type DialogKind = "cancel" | "terminate" | "non-renewal" | "return-to-draft";

function Field({ id, label, children }: { id: string; label: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="text-xs font-medium text-text-secondary">{label}</label>
      {children}
    </div>
  );
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex flex-wrap justify-between gap-x-4 gap-y-0.5 py-1.5 text-sm">
      <dt className="text-text-secondary">{label}</dt>
      <dd className="font-medium text-text-primary text-end">{value ?? "—"}</dd>
    </div>
  );
}

/** Editable while DRAFT only; the backend refuses edits in any other status. */
function TermsForm({ contract, onSaved, onCancel }: { contract: ContractDetail; onSaved: (c: ContractDetail) => void; onCancel: () => void }) {
  const t = useTranslations("contracts.detail");
  const tc = useTranslations("contracts");
  const { token } = useAuth();
  const [form, setForm] = useState<ContractUpdatePayload>({
    language: contract.language,
    start_date: contract.start_date,
    term_months: contract.term_months,
    services: contract.services,
    monthly_fee: contract.monthly_fee,
    fee_description: contract.fee_description,
    payment_terms_days: contract.payment_terms_days,
    notice_period_days: contract.notice_period_days,
    signer_name: contract.signer_name,
    signer_email: contract.signer_email,
    signer_title: contract.signer_title,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const patch = (p: Partial<ContractUpdatePayload>) => setForm((f) => ({ ...f, ...p }));
  const services = form.services ?? [];
  const intOrNull = (v: string) => (v === "" ? null : Number(v));

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      onSaved(await api.updateContract(token, contract.id, { ...form, monthly_fee: form.monthly_fee === "" ? null : form.monthly_fee, services: services.filter((s) => s.label.trim()) }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("actionFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="px-5 py-4 space-y-4" aria-label={t("editTerms")}>
      {error && <GlassErrorState message={error} />}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <Field id="ct-language" label={t("language")}>
          <GlassSelect id="ct-language" value={form.language} onChange={(e) => patch({ language: e.target.value as ContractLanguage })} className="w-full">
            <option value="nl">{tc("languages.nl")}</option>
            <option value="en">{tc("languages.en")}</option>
          </GlassSelect>
        </Field>
        <Field id="ct-start" label={t("startDate")}><GlassInput id="ct-start" type="date" value={form.start_date ?? ""} onChange={(e) => patch({ start_date: e.target.value })} /></Field>
        <Field id="ct-months" label={t("termMonths")}><GlassInput id="ct-months" type="number" min={1} max={60} value={form.term_months ?? 12} onChange={(e) => patch({ term_months: Number(e.target.value) })} /></Field>
      </div>
      <fieldset className="space-y-2">
        <legend className="text-xs font-medium text-text-secondary">{t("services")}</legend>
        {services.map((s, i) => (
          <div key={i} className="flex gap-2">
            <GlassInput aria-label={t("serviceLabel")} value={s.label} onChange={(e) => patch({ services: services.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)) })} />
            <GlassButton type="button" variant="ghost" size="sm" onClick={() => patch({ services: services.filter((_, j) => j !== i) })}>{t("removeService")}</GlassButton>
          </div>
        ))}
        <GlassButton type="button" variant="outline" size="sm" onClick={() => patch({ services: [...services, { code: `custom_${Date.now()}`, label: "" }] })}>{t("addService")}</GlassButton>
      </fieldset>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <Field id="ct-fee" label={t("monthlyFee")}><GlassInput id="ct-fee" type="number" step="0.01" min={0} inputMode="decimal" dir="ltr" value={form.monthly_fee ?? ""} onChange={(e) => patch({ monthly_fee: e.target.value })} /></Field>
        <Field id="ct-pay" label={t("paymentTerms")}><GlassInput id="ct-pay" type="number" min={0} max={365} value={form.payment_terms_days ?? ""} onChange={(e) => patch({ payment_terms_days: intOrNull(e.target.value) })} /></Field>
        <Field id="ct-notice" label={t("noticePeriod")}><GlassInput id="ct-notice" type="number" min={0} max={365} value={form.notice_period_days ?? ""} onChange={(e) => patch({ notice_period_days: intOrNull(e.target.value) })} /></Field>
      </div>
      <Field id="ct-feedesc" label={t("feeDescription")}><GlassInput id="ct-feedesc" value={form.fee_description ?? ""} onChange={(e) => patch({ fee_description: e.target.value || null })} /></Field>
      <fieldset className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <legend className="text-xs font-medium text-text-secondary mb-1">{t("signer")}</legend>
        <Field id="ct-signer-name" label={t("signerName")}><GlassInput id="ct-signer-name" value={form.signer_name ?? ""} onChange={(e) => patch({ signer_name: e.target.value || null })} /></Field>
        <Field id="ct-signer-email" label={t("signerEmail")}><GlassInput id="ct-signer-email" type="email" dir="ltr" value={form.signer_email ?? ""} onChange={(e) => patch({ signer_email: e.target.value || null })} /></Field>
        <Field id="ct-signer-title" label={t("signerTitle")}><GlassInput id="ct-signer-title" value={form.signer_title ?? ""} onChange={(e) => patch({ signer_title: e.target.value || null })} /></Field>
      </fieldset>
      <div className="flex justify-end gap-2">
        <GlassButton type="button" variant="ghost" onClick={onCancel}>{t("cancelEdit")}</GlassButton>
        <GlassButton type="submit" loading={busy}>{t("save")}</GlassButton>
      </div>
    </form>
  );
}

function ContractDetailContent({ contractId }: { contractId: number }) {
  const t = useTranslations("contracts.detail");
  const tc = useTranslations("contracts");
  const locale = useLocale();
  const { token, user } = useAuth();
  const [contract, setContract] = useState<ContractDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [signingLink, setSigningLink] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [dialog, setDialog] = useState<DialogKind | null>(null);
  const [reason, setReason] = useState("");
  const [effectiveDate, setEffectiveDate] = useState(new Date().toISOString().slice(0, 10));
  const [verified, setVerified] = useState<Record<number, boolean>>({});

  const load = useCallback(() => {
    if (!token) return;
    api.getContract(token, contractId).then(setContract).catch((e) => setError(e instanceof ApiError ? e.message : t("actionFailed")));
  }, [token, contractId, t]);
  useEffect(load, [load]);

  const isAdmin = !!user && ADMIN.has(user.role);
  const isEditor = !!user && EDITOR.has(user.role);

  async function perform(name: string, fn: () => Promise<unknown>) {
    if (!token) return;
    setBusy(name);
    setError(null);
    setNotice(null);
    try {
      await fn();
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("actionFailed"));
    } finally {
      setBusy(null);
      setDialog(null);
      setReason("");
    }
  }

  const transition = (name: "submit" | "approve" | "return-to-draft" | "cancel" | "terminate" | "non-renewal", body?: Record<string, unknown>) =>
    perform(name, () => api.contractAction(token!, contractId, name, body));

  const sendForSignature = (resend: boolean) =>
    perform(resend ? "resend" : "send", async () => {
      const result = await api.sendContract(token!, contractId, resend);
      setSigningLink(result.signing_link);
      if (result.email_sent) setNotice(t("emailQueued", { email: result.invitation.signer_email }));
    });

  const download = (url: string, filename: string) => perform("download", () => api.downloadReport(token!, url, filename));
  const verify = (versionId: number) =>
    perform(`verify-${versionId}`, async () => {
      const result = await api.verifyContractVersion(token!, contractId, versionId);
      setVerified((v) => ({ ...v, [versionId]: result.valid }));
    });

  function confirmDialog() {
    if (dialog === "cancel") transition("cancel", { reason: reason || null });
    else if (dialog === "terminate") transition("terminate", { reason: reason || null, effective_date: effectiveDate });
    else if (dialog === "non-renewal") transition("non-renewal", { disabled: true, reason: reason || null });
    else if (dialog === "return-to-draft") transition("return-to-draft", { reason: reason || null });
  }

  if (error && !contract) return <GlassErrorState message={error} />;
  if (!contract) return <GlassLoadingState />;
  const c = contract;
  const s = c.status;
  const closed = s === "CANCELLED" || s === "TERMINATED" || s === "EXPIRED";
  const dialogTitle: Record<DialogKind, string> = { cancel: t("cancel"), terminate: t("terminate"), "non-renewal": t("nonRenewal"), "return-to-draft": t("returnToDraft") };

  return (
    <div className="space-y-5">
      <div>
        <Link href="/contracts" className="text-sm text-navy hover:underline">{t("back")}</Link>
        <div className="flex flex-wrap items-center justify-between gap-3 mt-1">
          <div>
            <h1 className="text-2xl font-semibold text-text-primary" dir="ltr">{c.reference}</h1>
            <p className="text-sm text-text-secondary">
              <Link href={`/companies/${c.company_id}/workspace`} className="text-navy hover:underline">{c.company_name}</Link> · {t(`source.${c.created_source}`)}
              {c.renews_contract_id && <> · <Link href={`/contracts/${c.renews_contract_id}`} className="text-navy hover:underline">{t("renews", { reference: c.renews_reference ?? "" })}</Link></>}
              {c.renewal_contract_id && <> · <Link href={`/contracts/${c.renewal_contract_id}`} className="text-navy hover:underline">{t("renewedBy", { reference: c.renewal_reference ?? "" })}</Link></>}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <ContractStatusPill status={s} />
            <SigningStatusPill status={c.signing_status} />
            {c.renewal_disabled && <span className="status-pill status-pill-neutral">{tc("renewalDisabledBadge")}</span>}
          </div>
        </div>
      </div>

      {error && <GlassErrorState message={error} />}
      {notice && <div className="rounded-md bg-green-50 text-green-800 text-sm px-3 py-2" role="status">{notice}</div>}
      {signingLink && (
        <div className="rounded-md bg-amber-50 border border-amber-200 text-xs px-3 py-2 space-y-1" role="status">
          <p className="font-medium text-pending">{t("linkFallback")}</p>
          <p className="font-mono break-all select-all" dir="ltr" data-testid="signing-link">{signingLink}</p>
          <p className="text-text-secondary">{t("linkFallbackHelp")}</p>
        </div>
      )}
      {s === "DRAFT" && c.approval_missing.length > 0 && (
        <div className="rounded-md bg-amber-50 border border-amber-200 text-sm px-3 py-2 text-pending">
          {t("approvalMissing", { fields: c.approval_missing.map((f) => t(`fields.${f}` as never)).join(", ") })}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2 space-y-5">
          <GlassPanel title={t("terms")} subtitle={t("termsHelp")} actions={isEditor && s === "DRAFT" && !editing ? <GlassButton size="sm" variant="outline" onClick={() => setEditing(true)}>{t("editTerms")}</GlassButton> : undefined}>
            {editing ? (
              <TermsForm contract={c} onSaved={(updated) => { setContract(updated); setEditing(false); }} onCancel={() => setEditing(false)} />
            ) : (
              <dl className="px-5 py-3 divide-y divide-border-subtle">
                <Row label={t("language")} value={tc(`languages.${c.language}`)} />
                <Row label={t("startDate")} value={formatDate(c.start_date, locale)} />
                <Row label={t("endDate")} value={formatDate(c.end_date, locale)} />
                <Row label={t("termMonths")} value={c.term_months} />
                <Row label={t("monthlyFee")} value={feeLabel(c, locale, tc as never)} />
                <Row label={t("paymentTerms")} value={c.payment_terms_days !== null ? tc("days", { n: c.payment_terms_days }) : null} />
                <Row label={t("noticePeriod")} value={c.notice_period_days !== null ? tc("days", { n: c.notice_period_days }) : null} />
                <Row label={t("services")} value={<ul>{c.services.map((x) => <li key={x.code}>{x.label}</li>)}</ul>} />
                <Row label={t("signerName")} value={c.signer_name} />
                <Row label={t("signerEmail")} value={c.signer_email && <span dir="ltr">{c.signer_email}</span>} />
                <Row label={t("signerTitle")} value={c.signer_title} />
              </dl>
            )}
          </GlassPanel>

          <GlassPanel title={t("documents")} actions={<GlassButton size="sm" variant="ghost" onClick={() => download(api.contractPreviewPdfUrl(c.id), `${c.reference}-preview.pdf`)}>{t("preview")}</GlassButton>}>
            {c.versions.length === 0 ? (
              <p className="px-5 py-4 text-sm text-text-secondary">—</p>
            ) : (
              <ul className="divide-y divide-border">
                {c.versions.map((v) => (
                  <li key={v.id} className="px-5 py-3 flex flex-wrap items-center justify-between gap-2 text-sm">
                    <div className="min-w-0">
                      <p className="font-medium">v{v.version_no} · {t(`kind.${v.kind}`)} · {formatDate(v.created_at, locale)}</p>
                      <p className="text-xs text-text-secondary font-mono break-all" dir="ltr">{t("hash")}: {v.pdf_sha256}</p>
                      {verified[v.id] !== undefined && (
                        <p className={`text-xs ${verified[v.id] ? "text-green-700" : "text-error"}`} role="status">{verified[v.id] ? t("verified") : t("tampered")}</p>
                      )}
                    </div>
                    <div className="flex gap-2">
                      <GlassButton size="sm" variant="outline" onClick={() => verify(v.id)} loading={busy === `verify-${v.id}`}>{t("verify")}</GlassButton>
                      <GlassButton size="sm" onClick={() => download(api.contractVersionPdfUrl(c.id, v.id), `${c.reference}-v${v.version_no}.pdf`)}>{t("download")}</GlassButton>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </GlassPanel>

          {c.signature && (
            <GlassPanel title={t("signature")}>
              <dl className="px-5 py-3 divide-y divide-border-subtle">
                <Row label={t("signedBy")} value={c.signature.signer_name_typed} />
                <Row label={t("signerEmail")} value={<span dir="ltr">{c.signature.signer_email}</span>} />
                <Row label={t("signedAt")} value={new Date(c.signature.signed_at).toLocaleString(locale)} />
                <Row label={t("method")} value={t("methodSimple")} />
                <Row label={t("documentHash")} value={<span className="font-mono text-xs break-all" dir="ltr">{c.signature.document_sha256}</span>} />
                <Row label={t("consentText")} value={<span className="text-xs font-normal">{c.signature.consent_text}</span>} />
              </dl>
            </GlassPanel>
          )}

          <GlassPanel title={t("timeline")}>
            <ol className="divide-y divide-border">
              {[...c.events].reverse().map((e) => (
                <li key={e.id} className="px-5 py-2.5 text-sm flex flex-wrap justify-between gap-x-4 gap-y-0.5">
                  <span>
                    <span className="font-medium text-text-primary">{t.has(`events.${e.event_type}` as never) ? t(`events.${e.event_type}` as never) : e.event_type}</span>
                    <span className="text-text-secondary"> · {e.actor_type === "system" ? t("actorSystem") : e.actor_type === "signer" ? t("actorSigner") : e.actor_name ?? ""}</span>
                    {typeof e.data?.reason === "string" && e.data.reason && <span className="block text-xs text-text-secondary">{e.data.reason}</span>}
                  </span>
                  <time dateTime={e.created_at} className="text-xs text-text-secondary whitespace-nowrap">{new Date(e.created_at).toLocaleString(locale)}</time>
                </li>
              ))}
            </ol>
          </GlassPanel>
        </div>

        <div className="space-y-5">
          <GlassPanel title={t("actions")}>
            <div className="px-5 py-4 flex flex-col gap-2">
              {isEditor && s === "DRAFT" && <GlassButton onClick={() => transition("submit")} loading={busy === "submit"} disabled={!!busy}>{t("submit")}</GlassButton>}
              {isAdmin && (s === "DRAFT" || s === "PENDING_APPROVAL") && (
                <>
                  <GlassButton onClick={() => transition("approve")} loading={busy === "approve"} disabled={!!busy || c.approval_missing.length > 0}>{t("approve")}</GlassButton>
                  <p className="text-xs text-text-secondary">{t("approveHelp")}</p>
                </>
              )}
              {isAdmin && (s === "PENDING_APPROVAL" || s === "READY_TO_SEND") && <GlassButton variant="outline" onClick={() => setDialog("return-to-draft")} disabled={!!busy}>{t("returnToDraft")}</GlassButton>}
              {isAdmin && s === "READY_TO_SEND" && <GlassButton onClick={() => sendForSignature(false)} loading={busy === "send"} disabled={!!busy}>{t("send")}</GlassButton>}
              {isAdmin && (s === "SENT" || s === "VIEWED") && <GlassButton variant="outline" onClick={() => sendForSignature(true)} loading={busy === "resend"} disabled={!!busy}>{t("resend")}</GlassButton>}
              {isAdmin && ["DRAFT", "PENDING_APPROVAL", "READY_TO_SEND", "SENT", "VIEWED"].includes(s) && <GlassButton variant="danger" onClick={() => setDialog("cancel")} disabled={!!busy}>{t("cancel")}</GlassButton>}
              {isAdmin && ["SIGNED", "ACTIVE", "RENEWAL_DUE"].includes(s) && <GlassButton variant="danger" onClick={() => setDialog("terminate")} disabled={!!busy}>{t("terminate")}</GlassButton>}
              {isEditor && ["SIGNED", "ACTIVE", "RENEWAL_DUE", "EXPIRED"].includes(s) && !c.renewal_contract_id && !c.renewal_disabled && (
                <GlassButton variant="secondary" onClick={() => perform("renewal", () => api.createContractRenewal(token!, contractId))} loading={busy === "renewal"} disabled={!!busy}>{t("createRenewal")}</GlassButton>
              )}
              {c.renewal_contract_id && <Link href={`/contracts/${c.renewal_contract_id}`} className="btn-secondary-v2 inline-flex justify-center px-4 py-2 text-sm rounded-[0.6rem]">{t("openRenewal")}</Link>}
              {isAdmin && !closed && (c.renewal_disabled ? (
                <GlassButton variant="ghost" onClick={() => transition("non-renewal", { disabled: false })} disabled={!!busy}>{t("enableRenewal")}</GlassButton>
              ) : (
                <GlassButton variant="ghost" onClick={() => setDialog("non-renewal")} disabled={!!busy}>{t("nonRenewal")}</GlassButton>
              ))}
            </div>
          </GlassPanel>

          <GlassPanel title={t("invitations")}>
            {c.invitations.length === 0 ? (
              <p className="px-5 py-4 text-sm text-text-secondary">—</p>
            ) : (
              <ul className="divide-y divide-border text-sm">
                {[...c.invitations].reverse().map((i) => (
                  <li key={i.id} className="px-5 py-2.5 space-y-0.5">
                    <p className="font-medium"><span dir="ltr">{i.signer_email}</span> <span className="status-pill status-pill-neutral ms-1">{t(`invitationStatus.${i.status}`)}</span></p>
                    <p className="text-xs text-text-secondary">
                      {formatDate(i.created_at, locale)} · {t("expiresOn", { date: formatDate(i.expires_at, locale) })}
                      {i.first_viewed_at && <> · {t("viewedOn", { date: formatDate(i.first_viewed_at, locale) })}</>}
                      {i.email_status && <> · {t("emailStatus", { status: i.email_status })}</>}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </GlassPanel>
        </div>
      </div>

      <GlassModal
        open={dialog !== null}
        onClose={() => setDialog(null)}
        title={dialog ? dialogTitle[dialog] : ""}
        footer={
          <>
            <GlassButton variant="ghost" onClick={() => setDialog(null)}>{t("cancelEdit")}</GlassButton>
            <GlassButton variant={dialog === "cancel" || dialog === "terminate" ? "danger" : "primary"} loading={busy !== null} onClick={confirmDialog}>{t("confirm")}</GlassButton>
          </>
        }
      >
        <div className="space-y-3">
          {dialog === "terminate" && (
            <Field id="ct-effective" label={t("effectiveDate")}><GlassInput id="ct-effective" type="date" value={effectiveDate} onChange={(e) => setEffectiveDate(e.target.value)} /></Field>
          )}
          <Field id="ct-reason" label={t("reason")}><GlassInput id="ct-reason" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} /></Field>
        </div>
      </GlassModal>
    </div>
  );
}

function ContractRoute() {
  const params = useParams<{ id: string }>();
  return (
    <AuthGuard>
      <Shell>
        <ContractDetailContent contractId={Number(params.id)} />
      </Shell>
    </AuthGuard>
  );
}

export default function ContractDetailPage() {
  return (
    <Suspense>
      <ContractRoute />
    </Suspense>
  );
}
