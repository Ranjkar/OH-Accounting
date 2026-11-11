"use client";

/** Public signing portal (Phase 26). No AuthGuard/Shell: the link token is the
 * credential. Simple electronic signature only -- the page never calls it
 * advanced or qualified. Structure follows WCAG 2.2 AA: one h1, labelled
 * controls with described-by help, explicit checkbox consent, error region
 * announced via role=alert, focus moved to the confirmation heading, 44px
 * targets, no colour-only meaning, works at 320px and with 200% zoom. */

import { FormEvent, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import LanguageSelector from "@/components/glass/LanguageSelector";
import { api, ApiError, SigningPage } from "@/lib/api";
import { formatDate } from "@/lib/format";

type LoadError = "notFound" | "expired" | "withdrawn" | "generic";

function classify(e: unknown): LoadError {
  if (!(e instanceof ApiError)) return "generic";
  if (e.status === 404) return "notFound";
  if (e.status === 410) return /withdrawn|ingetrokken/i.test(e.message) ? "withdrawn" : "expired";
  return "generic";
}

export default function SignContractPage() {
  const params = useParams<{ token: string }>();
  const signToken = params.token;
  const t = useTranslations("contracts.sign");
  const locale = useLocale();
  const [page, setPage] = useState<SigningPage | null>(null);
  const [loadError, setLoadError] = useState<LoadError | null>(null);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [signError, setSignError] = useState<string | null>(null);
  const doneHeading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (!signToken) return;
    api.getSigningPage(signToken).then(setPage).catch((e) => setLoadError(classify(e)));
  }, [signToken]);

  useEffect(() => {
    if (page?.already_signed) doneHeading.current?.focus();
  }, [page?.already_signed]);

  async function handleSign(e: FormEvent) {
    e.preventDefault();
    setSignError(null);
    if (!consent) {
      setSignError(t("consentRequired"));
      return;
    }
    setBusy(true);
    try {
      setPage(await api.signContract(signToken, { full_name: fullName, email, consent }));
    } catch (err) {
      setSignError(err instanceof ApiError ? err.message : t("signFailed"));
    } finally {
      setBusy(false);
    }
  }

  const header = (
    <header className="border-b border-border bg-surface-page">
      <div className="max-w-3xl mx-auto px-4 py-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span aria-hidden="true" className="inline-flex w-8 h-8 rounded-lg items-center justify-center text-white font-bold" style={{ background: "var(--navy-solid)" }}>O</span>
          <span className="font-semibold text-text-primary">{t("brand")}</span>
        </div>
        <LanguageSelector />
      </div>
    </header>
  );

  if (loadError) {
    return (
      <main className="min-h-screen bg-background text-foreground">
        {header}
        <div className="max-w-3xl mx-auto px-4 py-10">
          <div className="card-v2 p-6 space-y-2" role="alert">
            <h1 className="text-xl font-semibold text-text-primary">{t("errorTitle")}</h1>
            <p className="text-sm text-text-secondary">{t(loadError)}</p>
          </div>
        </div>
      </main>
    );
  }

  if (!page) {
    return (
      <main className="min-h-screen bg-background text-foreground">
        {header}
        <p className="max-w-3xl mx-auto px-4 py-10 text-text-secondary" role="status">{t("loading")}</p>
      </main>
    );
  }

  const { content } = page;

  return (
    <main className="min-h-screen bg-background text-foreground">
      {header}
      <div className="max-w-3xl mx-auto px-4 py-6 sm:py-10 space-y-6">
        {page.already_signed ? (
          <section className="card-v2 p-6 space-y-4" aria-labelledby="sign-done-title">
            <h1 id="sign-done-title" ref={doneHeading} tabIndex={-1} className="text-2xl font-semibold text-text-primary focus:outline-none">{t("doneTitle")}</h1>
            <p className="text-sm text-text-primary">{t("doneBody", { reference: page.reference, date: page.signed_at ? new Date(page.signed_at).toLocaleString(locale) : "" })}</p>
            <a href={api.signingPdfUrl(signToken)} className="btn-primary-v2 inline-flex items-center px-5 py-3 text-sm min-h-[44px]" download>{t("download")}</a>
            {page.signed_pdf_sha256 && (
              <dl className="text-xs text-text-secondary space-y-1">
                <dt className="font-medium">{t("hashLabel")}</dt>
                <dd className="font-mono break-all" dir="ltr">{page.signed_pdf_sha256}</dd>
                <dd>{t("hashHelp")}</dd>
              </dl>
            )}
          </section>
        ) : (
          <section className="card-v2 p-6 space-y-2" aria-labelledby="sign-title">
            <p className="text-xs uppercase tracking-wide text-text-secondary">{t("reference")} <span dir="ltr">{page.reference}</span></p>
            <h1 id="sign-title" className="text-2xl font-semibold text-text-primary">{content.title}</h1>
            <p className="text-sm text-text-secondary">{t("intro")}</p>
            <p className="text-xs text-text-secondary">{t("expiresOn", { date: formatDate(page.expires_at, locale) })}</p>
          </section>
        )}

        <section className="card-v2 p-6" aria-labelledby="sign-summary">
          <h2 id="sign-summary" className="text-sm font-medium text-text-primary mb-3">{t("summary")}</h2>
          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 text-sm">
            <div><dt className="text-text-secondary">{t("client")}</dt><dd className="font-medium">{content.client.name}</dd></div>
            <div><dt className="text-text-secondary">{t("provider")}</dt><dd className="font-medium">{content.provider.name}</dd></div>
            <div><dt className="text-text-secondary">{t("term")}</dt><dd className="font-medium">{content.term.text}</dd></div>
            <div><dt className="text-text-secondary">{t("fee")}</dt><dd className="font-medium">{content.fees.fee_text}</dd></div>
            <div><dt className="text-text-secondary">{t("paymentTerms")}</dt><dd>{content.fees.payment_terms_text}</dd></div>
            <div><dt className="text-text-secondary">{t("noticePeriod")}</dt><dd>{content.fees.notice_period_text}</dd></div>
            <div><dt className="text-text-secondary">{t("kvk")}</dt><dd dir="ltr">{content.client.kvk_number ?? "—"}</dd></div>
            <div><dt className="text-text-secondary">{t("vat")}</dt><dd dir="ltr">{content.client.vat_number ?? "—"}</dd></div>
            <div className="sm:col-span-2"><dt className="text-text-secondary">{t("address")}</dt><dd>{content.client.address ?? "—"}</dd></div>
            <div className="sm:col-span-2"><dt className="text-text-secondary">{t("representative")}</dt><dd>{content.client.representative ?? "—"}</dd></div>
          </dl>
          <h3 className="text-sm font-medium text-text-primary mt-4 mb-1">{t("services")}</h3>
          <ul className="list-disc ps-5 text-sm space-y-0.5">{content.services.map((s) => <li key={s.code}>{s.label}</li>)}</ul>
        </section>

        <section className="card-v2 p-6" aria-labelledby="sign-clauses">
          <h2 id="sign-clauses" className="text-sm font-medium text-text-primary mb-3">{t("clauses")}</h2>
          <div className="space-y-4 text-sm leading-relaxed">
            {content.clauses.map((c, i) => (
              <article key={c.key ?? i}>
                <h3 className="font-semibold text-text-primary">{c.heading}</h3>
                <p className="text-text-primary whitespace-pre-line">{c.body}</p>
              </article>
            ))}
          </div>
          <p className="mt-4 text-xs text-text-secondary">{t("legalNote")}</p>
          <a href={api.signingPdfUrl(signToken)} className="mt-3 inline-flex items-center text-sm text-navy hover:underline min-h-[44px]" target="_blank" rel="noopener">{t("downloadDraft")}</a>
        </section>

        {!page.already_signed && (
          <form onSubmit={handleSign} className="card-v2 p-6 space-y-5" aria-labelledby="sign-form-title" noValidate>
            <h2 id="sign-form-title" className="text-sm font-medium text-text-primary">{t("signerDetails")}</h2>
            <p className="text-sm text-text-secondary">{t("signerFor", { client: content.client.name, name: page.signer_name })}</p>
            {signError && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2" role="alert" id="sign-error">{signError}</div>}
            <div className="space-y-1">
              <label htmlFor="sign-name" className="block text-sm font-medium text-text-primary">{t("fullName")}</label>
              <input id="sign-name" name="full_name" autoComplete="name" required value={fullName} onChange={(e) => setFullName(e.target.value)} aria-describedby="sign-name-help" className="input-v2 w-full px-3 py-2.5 text-base min-h-[44px]" />
              <p id="sign-name-help" className="text-xs text-text-secondary">{t("fullNameHelp", { name: page.signer_name })}</p>
            </div>
            <div className="space-y-1">
              <label htmlFor="sign-email" className="block text-sm font-medium text-text-primary">{t("email")}</label>
              <input id="sign-email" name="email" type="email" autoComplete="email" inputMode="email" required value={email} onChange={(e) => setEmail(e.target.value)} aria-describedby="sign-email-help" className="input-v2 w-full px-3 py-2.5 text-base min-h-[44px]" dir="ltr" />
              <p id="sign-email-help" className="text-xs text-text-secondary">{t("emailHelp", { hint: page.signer_email_hint })}</p>
            </div>
            <div className="rounded-md border border-border p-3 text-xs text-text-secondary space-y-1">
              <p className="font-medium text-text-primary">{t("assurance")}</p>
              <p>{page.assurance_notice}</p>
              <p>{t("privacy")}</p>
            </div>
            <div className="flex items-start gap-3">
              <input id="sign-consent" type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} aria-describedby="sign-consent-detail" className="mt-1 w-5 h-5 shrink-0" />
              <div>
                <label htmlFor="sign-consent" className="text-sm font-medium text-text-primary">{t("consentLabel")}</label>
                <p id="sign-consent-detail" className="text-xs text-text-secondary mt-1">{t("consentDetail", { text: page.consent_text })}</p>
              </div>
            </div>
            <button type="submit" disabled={busy || !consent} aria-busy={busy || undefined} className="btn-primary-v2 w-full sm:w-auto px-6 py-3 text-base min-h-[44px] disabled:opacity-50 disabled:cursor-not-allowed">
              {busy ? t("signing") : t("signButton")}
            </button>
          </form>
        )}
      </div>
    </main>
  );
}
