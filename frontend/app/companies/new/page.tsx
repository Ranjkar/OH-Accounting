"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import GlassPageHeader from "@/components/glass/GlassPageHeader";
import GlassButton from "@/components/glass/GlassButton";
import GlassLoadingState, { GlassErrorState } from "@/components/glass/GlassLoadingState";
import { useAuth } from "@/lib/auth-context";
import {
  api,
  ApiError,
  LegalFormDefinition,
  SetupDraft,
  SetupDraftData,
  SetupValidation,
  SetupValidationIssue,
  VatAccountingBasis,
  VatFrequency,
} from "@/lib/api";
import {
  DEFAULT_VAT_ACCOUNTING_BASIS,
  DEFAULT_VAT_FREQUENCY,
  SETUP_FIELDS,
  SETUP_STEPS,
  SetupStep,
  issueKey,
  validateSetupStep,
  withTaxDefaults,
} from "@/lib/company-setup";

/** KVK's `rechtsvorm` strings (Dutch, from the basisprofiel) -> our codes.
 * Substring match on the lower-cased value; anything unknown stays unset
 * so the user picks it explicitly -- never guessed. */
const KVK_LEGAL_FORM_MAP: [string, string][] = [
  ["eenmanszaak", "eenmanszaak"],
  ["vennootschap onder firma", "vof"],
  ["commanditaire", "cv"],
  ["maatschap", "maatschap"],
  ["besloten vennootschap", "bv"],
  ["naamloze vennootschap", "nv"],
  ["coöperatie", "cooperatie"],
  ["cooperatie", "cooperatie"],
  ["onderlinge waarborg", "owm"],
  ["stichting", "stichting"],
  ["vereniging van eigenaars", "vve"],
  ["vereniging", "vereniging"],
  ["rederij", "rederij"],
];

function mapKvkLegalForm(value: string | null): string | undefined {
  const v = (value ?? "").toLowerCase();
  return KVK_LEGAL_FORM_MAP.find(([needle]) => v.includes(needle))?.[1];
}

/** Which draft the wizard shows: the one named in ?draft=, else the most
 * recent open one (resume), else a brand new draft. */
async function resolveDraft(token: string, requestedId: number | null): Promise<{ resolved: SetupDraft; wasResumed: boolean }> {
  if (requestedId !== null) return { resolved: await api.getSetupDraft(token, requestedId), wasResumed: false };
  const open = await api.listSetupDrafts(token);
  if (open.length > 0) return { resolved: open[0], wasResumed: true };
  return { resolved: await api.createSetupDraft(token), wasResumed: false };
}

type WizardLoad = { resolved: SetupDraft; wasResumed: boolean; forms: LegalFormDefinition[] };

/** Control to focus when a step is blocked, keyed by the backend field name
 * so the message a screen reader hears sits on the input it refers to. */
const FIELD_ELEMENT_ID: Record<string, string> = {
  name: "setup-name",
  legal_form_code: "setup-legal-form",
  kvk_number: "setup-kvk",
  rsin: "setup-rsin",
  email: "setup-email",
  vat_registered: "setup-vat-registered",
  vat_number: "setup-vat-number",
  vat_frequency: "setup-vat-frequency",
  vat_accounting_basis: "setup-vat-basis",
  kor_participant: "setup-kor",
  financial_year: "setup-fy",
  bank_iban: "setup-iban",
  bank_account_name: "setup-bank-name",
};

/** Reverse of the above, so an input's aria-describedby can be derived from
 * its own id without repeating the field name at every call site. */
const ELEMENT_TO_FIELD: Record<string, string> = Object.fromEntries(
  Object.entries(FIELD_ELEMENT_ID).map(([field, id]) => [id, field])
);

const errorId = (id: string) => `${id}-error`;

function WizardContent() {
  const t = useTranslations("companySetup");
  const tCommon = useTranslations("common");
  const tCompanies = useTranslations("companies");
  const locale = useLocale();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { token } = useAuth();

  const [draft, setDraft] = useState<SetupDraft | null>(null);
  const [data, setData] = useState<SetupDraftData>({});
  const [stepIndex, setStepIndex] = useState(0);
  const [legalForms, setLegalForms] = useState<LegalFormDefinition[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [resumed, setResumed] = useState(false);
  const [kvkBusy, setKvkBusy] = useState(false);
  const [validation, setValidation] = useState<SetupValidation | null>(null);
  const [completing, setCompleting] = useState(false);
  const [stepErrors, setStepErrors] = useState<Record<string, string>>({});
  const headingRef = useRef<HTMLHeadingElement>(null);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Mirrors of the state the save timers and the unmount flush need. Reading
  // these instead of the state values keeps a debounced save from writing a
  // stale draft (or a stale step) that the user has already moved past.
  const draftRef = useRef<SetupDraft | null>(null);
  const dataRef = useRef<SetupDraftData>({});
  const stepRef = useRef(0);
  const dirtyRef = useRef(false);
  /** The single in-flight load, shared across StrictMode's double effect run. */
  const loadRef = useRef<Promise<WizardLoad> | null>(null);

  const step: SetupStep = SETUP_STEPS[stepIndex];
  const selectedForm = useMemo(() => legalForms.find((f) => f.code.toLowerCase() === (data.legal_form_code ?? "").toLowerCase()) ?? null, [legalForms, data.legal_form_code]);
  const formLabel = (f: LegalFormDefinition) => (locale.startsWith("nl") ? f.name_nl : f.name_en);
  const fieldLabel = (field: string) => ((SETUP_FIELDS as readonly string[]).includes(field) ? t(`fields.${field}` as never) : field);

  const persist = useCallback(
    async (next: SetupDraftData, nextStep: number) => {
      const target = draftRef.current;
      if (!token || !target) return;
      if (saveTimer.current) {
        clearTimeout(saveTimer.current);
        saveTimer.current = null;
      }
      setSaving(true);
      try {
        const saved = await api.updateSetupDraft(token, target.id, next, nextStep);
        draftRef.current = saved;
        setDraft(saved);
        // Only clear the flag when nothing was typed while this was in flight.
        if (dataRef.current === next) {
          dirtyRef.current = false;
          setDirty(false);
        }
      } catch (e) {
        setError(e instanceof ApiError ? e.message : t("saveFailed"));
      } finally {
        setSaving(false);
      }
    },
    [token, t]
  );

  // Load (or resume) the draft and the legal-form registry. An open draft is
  // resumed rather than duplicated, so a setup started on a phone survives a
  // reload, a closed tab, or moving to a laptop.
  useEffect(() => {
    if (!token) return;
    const authToken = token;
    let cancelled = false;
    const requested = Number(searchParams.get("draft"));

    // React StrictMode runs this effect twice on the same instance in
    // development. Sharing the in-flight promise makes the second run reuse
    // the first one's result instead of creating an orphaned draft.
    loadRef.current ??= Promise.all([
      resolveDraft(authToken, Number.isInteger(requested) && requested > 0 ? requested : null),
      api.listLegalFormDefinitions(authToken),
    ]).then(([{ resolved, wasResumed }, forms]) => ({ resolved, wasResumed, forms }));

    loadRef.current
      .then(({ resolved, wasResumed, forms }) => {
        if (cancelled) return;
        // withTaxDefaults records the frequency/basis the selects display, so a
        // draft that looks complete on screen is also complete for the server.
        const initial = withTaxDefaults(resolved.data ?? {});
        draftRef.current = resolved;
        dataRef.current = initial;
        stepRef.current = Math.max(0, Math.min(resolved.current_step ?? 0, SETUP_STEPS.length - 1));
        setDraft(resolved);
        setData(initial);
        setStepIndex(stepRef.current);
        setLegalForms(forms);
        setResumed(wasResumed);
        if (searchParams.get("draft") !== String(resolved.id)) router.replace(`/companies/new?draft=${resolved.id}`);
        if (resolved.completed_at && resolved.created_company_id) router.replace(`/companies/${resolved.created_company_id}`);
      })
      .catch((e) => {
        loadRef.current = null; // let a retry re-resolve instead of replaying this failure
        if (!cancelled) setError(e instanceof ApiError ? e.message : t("loadFailed"));
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  // Flush a pending debounced save when leaving the page, and warn before a
  // real unload while answers are still only in the browser.
  useEffect(() => {
    return () => {
      if (saveTimer.current) clearTimeout(saveTimer.current);
      if (dirtyRef.current && token && draftRef.current) {
        void api.updateSetupDraft(token, draftRef.current.id, dataRef.current, stepRef.current).catch(() => {});
      }
    };
  }, [token]);

  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const scheduleSave = useCallback(
    (next: SetupDraftData, nextStep: number) => {
      dirtyRef.current = true;
      setDirty(true);
      if (saveTimer.current) clearTimeout(saveTimer.current);
      saveTimer.current = setTimeout(() => {
        saveTimer.current = null;
        void persist(next, nextStep);
      }, 800);
    },
    [persist]
  );

  function update(patch: Partial<SetupDraftData>) {
    const next = { ...dataRef.current, ...patch };
    dataRef.current = next;
    setData(next);
    scheduleSave(next, stepRef.current);
    setStepErrors({});
  }

  /** Moving between steps clears the review verdict, so the verdict for the
   * step being entered has to be handed in -- setting it before this call
   * would just be wiped. */
  function goTo(index: number, review: SetupValidation | null = null) {
    const nextIndex = Math.max(0, Math.min(index, SETUP_STEPS.length - 1));
    if (saveTimer.current) {
      clearTimeout(saveTimer.current);
      saveTimer.current = null;
    }
    stepRef.current = nextIndex;
    setStepIndex(nextIndex);
    setValidation(review);
    void persist(dataRef.current, nextIndex);
    setTimeout(() => headingRef.current?.focus(), 0);
  }

  async function next() {
    // Same conditional rules the server enforces on /complete, applied to the
    // step on screen so a missing answer is caught before the review step.
    const issues = validateSetupStep(step, dataRef.current, selectedForm);
    setStepErrors(issues);
    const firstField = Object.keys(issues)[0];
    if (firstField) {
      const el = document.getElementById(FIELD_ELEMENT_ID[firstField] ?? "");
      el?.focus();
      el?.scrollIntoView({ block: "center", behavior: "smooth" });
      return;
    }
    const nextIndex = stepIndex + 1;
    let review: SetupValidation | null = null;
    if (SETUP_STEPS[nextIndex] === "review" && token && draftRef.current) {
      try {
        review = await api.validateSetupDraft(token, draftRef.current.id, dataRef.current, nextIndex);
      } catch (e) {
        setError(e instanceof ApiError ? e.message : t("saveFailed"));
      }
    }
    goTo(nextIndex, review);
  }

  async function lookupKvk() {
    if (!token || !data.kvk_number) return;
    setKvkBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await api.lookupKvk(token, data.kvk_number.replace(/\D/g, ""));
      const mapped = mapKvkLegalForm(result.legal_form);
      update({
        kvk_number: result.kvk_number,
        kvk_verified: true,
        name: data.name?.trim() ? data.name : result.name,
        address: data.address?.trim() ? data.address : (result.address ?? undefined),
        business_activity: data.business_activity?.trim() ? data.business_activity : (result.sbi_activity ?? undefined),
        legal_form_code: data.legal_form_code || mapped,
      });
      setNotice(result.is_test_data ? t("kvk.prefilledTestData", { name: result.name }) : t("kvk.prefilled", { name: result.name }));
    } catch (e) {
      setError(e instanceof ApiError && e.status === 404 ? t("kvk.notFound") : t("kvk.lookupFailed"));
    } finally {
      setKvkBusy(false);
    }
  }

  async function complete() {
    const target = draftRef.current;
    if (!token || !target) return;
    setCompleting(true);
    setError(null);
    try {
      await persist(dataRef.current, stepRef.current);
      const result = await api.completeSetupDraft(token, target.id);
      router.push(`/companies/${result.company.id}${result.already_completed ? "?setup=existing" : "?setup=done"}`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 422) {
        // The server is the authority on completeness: show its verdict per field.
        setValidation(await api.validateSetupDraft(token, target.id, dataRef.current, stepRef.current).catch(() => null));
        setError(t("errors.incomplete"));
      } else {
        setError(e instanceof ApiError ? e.message : t("completeFailed"));
      }
    } finally {
      setCompleting(false);
    }
  }

  /** Abandon the answers on screen and start a fresh draft. The old draft is
   * left open on purpose -- it stays resumable from /companies. */
  async function startOver() {
    if (!token) return;
    setError(null);
    try {
      const fresh = await api.createSetupDraft(token);
      if (saveTimer.current) {
        clearTimeout(saveTimer.current);
        saveTimer.current = null;
      }
      draftRef.current = fresh;
      dataRef.current = {};
      stepRef.current = 0;
      dirtyRef.current = false;
      loadRef.current = null; // the URL now points at this draft, so re-resolve from it
      setDraft(fresh);
      setData({});
      setStepIndex(0);
      setDirty(false);
      setValidation(null);
      setStepErrors({});
      setNotice(null);
      setResumed(false);
      router.replace(`/companies/new?draft=${fresh.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("saveFailed"));
    }
  }

  async function discard() {
    const target = draftRef.current;
    if (!token || !target) return;
    if (saveTimer.current) {
      clearTimeout(saveTimer.current);
      saveTimer.current = null;
    }
    dirtyRef.current = false;
    setDirty(false);
    try {
      await api.deleteSetupDraft(token, target.id);
      router.push("/companies");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("saveFailed"));
    }
  }

  if (error && !draft) return <GlassErrorState message={error} />;
  if (!draft) return <GlassLoadingState />;

  const issueFor = (field: string): SetupValidationIssue | undefined => validation?.issues.find((i) => i.field === field);
  const issueText = (issue: SetupValidationIssue): string => {
    const key = issueKey(issue.field, issue.code);
    if (key) return t(key as never);
    // No dedicated sentence for this combination. Fall back to the translated
    // code label rather than the server's English message, so a Dutch user is
    // never shown untranslated text (see docs/untranslated-backend-messages-inventory.md).
    const code = ["required", "invalid", "duplicate"].includes(issue.code) ? t(`issueCodes.${issue.code}` as never) : issue.message;
    return `${fieldLabel(issue.field)}: ${code}`;
  };
  /** Inline message for a locally-blocked field, wired to its input through
   * aria-describedby so the reason is announced, not just shown. */
  const fieldError = (field: string, id: string) => {
    const code = stepErrors[field];
    if (!code) return null;
    const key = issueKey(field, code);
    return (
      <p id={errorId(id)} className="text-xs text-error" role="alert">
        {key ? t(key as never) : `${fieldLabel(field)}: ${t(`issueCodes.${code}` as never)}`}
      </p>
    );
  };
  const describedBy = (id: string, helpId?: string) =>
    [stepErrors[ELEMENT_TO_FIELD[id] ?? ""] ? errorId(id) : null, helpId].filter(Boolean).join(" ") || undefined;
  const currentYear = new Date().getFullYear();
  const kvkRequired = !!selectedForm?.requires_kvk_registration;
  const rsinRecommended = !!selectedForm?.has_legal_personality;

  return (
    <div className="space-y-5 max-w-2xl">
      <GlassPageHeader
        title={t("title")}
        subtitle={t("subtitle")}
        actions={
          <Link href="/companies" className="btn-ghost-v2 px-3 py-2 text-sm">
            {t("saveAndExit")}
          </Link>
        }
      />

      {resumed && (
        <div className="rounded-lg border border-border bg-brand-purple-50 px-4 py-3 text-sm flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <span className="text-text-primary">{t("resumedDraft")}</span>
          <button type="button" onClick={() => void startOver()} className="font-medium text-navy hover:underline">
            {t("startNewSetup")}
          </button>
        </div>
      )}

      {/* Progress: a bar plus "step n of 4" on phones (the four labels do not
          fit at 320px), the labelled clickable stepper from sm up. */}
      <div className="space-y-2">
        <div
          className="h-1.5 w-full overflow-hidden rounded-full bg-muted"
          role="progressbar"
          aria-label={t("progressLabel")}
          aria-valuemin={1}
          aria-valuemax={SETUP_STEPS.length}
          aria-valuenow={stepIndex + 1}
          aria-valuetext={t("stepOf", { current: stepIndex + 1, total: SETUP_STEPS.length })}
        >
          <div
            className="h-full rounded-full bg-navy-solid transition-[width] duration-200 motion-reduce:transition-none"
            style={{ width: `${((stepIndex + 1) / SETUP_STEPS.length) * 100}%` }}
          />
        </div>
        <p className="sm:hidden text-xs font-medium text-text-secondary">
          {t("stepOf", { current: stepIndex + 1, total: SETUP_STEPS.length })} · {t(`steps.${step}` as never)}
        </p>
        <ol className="hidden sm:grid grid-cols-4 gap-1 sm:gap-2 text-xs" aria-label={t("progressLabel")}>
          {SETUP_STEPS.map((s, i) => {
            const state = i < stepIndex ? "done" : i === stepIndex ? "current" : "todo";
            return (
              <li key={s} aria-current={state === "current" ? "step" : undefined} className="min-w-0">
                <button
                  type="button"
                  onClick={() => i < stepIndex && goTo(i)}
                  disabled={i > stepIndex}
                  className={`w-full text-start rounded-lg px-2 py-2 border ${
                    state === "current" ? "border-navy bg-brand-purple-50 text-text-primary" : state === "done" ? "border-border text-text-secondary hover:bg-muted" : "border-border text-text-muted"
                  } disabled:cursor-default`}
                >
                  <span className="block font-semibold tabular-nums">{i + 1}/{SETUP_STEPS.length}</span>
                  <span className="block truncate">{t(`steps.${s}` as never)}</span>
                </button>
              </li>
            );
          })}
        </ol>
      </div>

      <div className="flex items-center justify-between gap-3 text-xs text-text-secondary" role="status" aria-live="polite">
        <span>{saving ? tCommon("saving") : dirty ? t("unsavedChanges") : t("draftSaved")}</span>
        <span>{t("draftId", { id: draft.id })}</span>
      </div>

      {error && <GlassErrorState message={error} />}
      {notice && <div className="rounded-lg bg-green-500/10 border border-green-300/50 text-green-700 text-sm px-4 py-3" role="status">{notice}</div>}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (step === "review") void complete();
          else void next();
        }}
        className="card-v2 p-4 sm:p-6 space-y-5"
        noValidate
      >
        <h2 ref={headingRef} tabIndex={-1} className="text-section-heading outline-none">
          {t(`steps.${step}` as never)}
        </h2>

        {step === "details" && (
          <fieldset className="space-y-4">
            <legend className="sr-only">{t("steps.details")}</legend>
            <div className="space-y-1">
              <label htmlFor="setup-kvk" className="text-sm font-medium text-text-primary">
                {tCompanies("kvkNumberLabel")}
                {selectedForm && !kvkRequired && <span className="text-text-secondary font-normal"> ({tCommon("optional")})</span>}
              </label>
              <div className="flex flex-wrap gap-2">
                <input
                  id="setup-kvk"
                  inputMode="numeric"
                  autoComplete="off"
                  dir="ltr"
                  maxLength={8}
                  value={data.kvk_number ?? ""}
                  onChange={(e) => update({ kvk_number: e.target.value.replace(/\D/g, ""), kvk_verified: false })}
                  aria-required={kvkRequired || undefined}
                  aria-invalid={!!stepErrors.kvk_number}
                  aria-describedby={describedBy("setup-kvk", "setup-kvk-help")}
                  className="input-v2 px-3 py-2 text-sm flex-1 min-w-[10rem]"
                />
                <GlassButton type="button" variant="secondary" onClick={lookupKvk} loading={kvkBusy} disabled={(data.kvk_number ?? "").length !== 8}>
                  {t("kvk.lookup")}
                </GlassButton>
              </div>
              <p id="setup-kvk-help" className="text-xs text-text-secondary">
                {data.kvk_verified ? t("kvk.verified") : t("kvk.help")}
              </p>
              {fieldError("kvk_number", "setup-kvk")}
            </div>

            <div className="space-y-1">
              <label htmlFor="setup-name" className="text-sm font-medium text-text-primary">{tCompanies("companyNameLabel")}</label>
              <input
                id="setup-name"
                required
                autoComplete="organization"
                value={data.name ?? ""}
                onChange={(e) => update({ name: e.target.value })}
                aria-invalid={!!stepErrors.name}
                aria-describedby={describedBy("setup-name")}
                className="w-full input-v2 px-3 py-2 text-sm"
              />
              {fieldError("name", "setup-name")}
            </div>

            <div className="space-y-1">
              <label htmlFor="setup-legal-form" className="text-sm font-medium text-text-primary">{t("legalForm")}</label>
              <select
                id="setup-legal-form"
                required
                value={(data.legal_form_code ?? "").toLowerCase()}
                onChange={(e) => update({ legal_form_code: e.target.value || undefined })}
                aria-invalid={!!stepErrors.legal_form_code}
                aria-describedby={describedBy("setup-legal-form")}
                className="w-full input-v2 px-3 py-2 text-sm"
              >
                <option value="">{t("selectLegalForm")}</option>
                {legalForms.map((f) => (
                  <option key={f.code} value={f.code.toLowerCase()}>{formLabel(f)}</option>
                ))}
              </select>
              {selectedForm?.notes && <p className="text-xs text-text-secondary">{selectedForm.notes}</p>}
              {fieldError("legal_form_code", "setup-legal-form")}
            </div>

            {selectedForm?.has_legal_personality && (
              <div className="space-y-1">
                <label htmlFor="setup-rsin" className="text-sm font-medium text-text-primary">
                  RSIN{" "}
                  <span className="text-text-secondary font-normal">
                    ({rsinRecommended ? t("review.recommended") : tCommon("optional")})
                  </span>
                </label>
                <input
                  id="setup-rsin"
                  inputMode="numeric"
                  dir="ltr"
                  maxLength={9}
                  value={data.rsin ?? ""}
                  onChange={(e) => update({ rsin: e.target.value.replace(/\D/g, "") })}
                  aria-invalid={!!stepErrors.rsin}
                  aria-describedby={describedBy("setup-rsin", "setup-rsin-help")}
                  className="w-full input-v2 px-3 py-2 text-sm"
                />
                <p id="setup-rsin-help" className="text-xs text-text-secondary">{t("rsinHelp")}</p>
                {fieldError("rsin", "setup-rsin")}
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1">
                <label htmlFor="setup-address" className="text-sm font-medium text-text-primary">{t("address")} <span className="text-text-secondary font-normal">({tCommon("optional")})</span></label>
                <input id="setup-address" autoComplete="street-address" value={data.address ?? ""} onChange={(e) => update({ address: e.target.value })} className="w-full input-v2 px-3 py-2 text-sm" />
              </div>
              <div className="space-y-1">
                <label htmlFor="setup-activity" className="text-sm font-medium text-text-primary">{t("businessActivity")} <span className="text-text-secondary font-normal">({tCommon("optional")})</span></label>
                <input id="setup-activity" value={data.business_activity ?? ""} onChange={(e) => update({ business_activity: e.target.value })} className="w-full input-v2 px-3 py-2 text-sm" />
              </div>
              <div className="space-y-1">
                <label htmlFor="setup-email" className="text-sm font-medium text-text-primary">{tCommon("email")} <span className="text-text-secondary font-normal">({tCommon("optional")})</span></label>
                <input
                  id="setup-email"
                  type="email"
                  inputMode="email"
                  autoComplete="email"
                  dir="ltr"
                  value={data.email ?? ""}
                  onChange={(e) => update({ email: e.target.value })}
                  aria-invalid={!!stepErrors.email}
                  aria-describedby={describedBy("setup-email")}
                  className="w-full input-v2 px-3 py-2 text-sm"
                />
                {fieldError("email", "setup-email")}
              </div>
              <div className="space-y-1">
                <label htmlFor="setup-phone" className="text-sm font-medium text-text-primary">{t("phone")} <span className="text-text-secondary font-normal">({tCommon("optional")})</span></label>
                <input id="setup-phone" type="tel" inputMode="tel" autoComplete="tel" dir="ltr" value={data.phone ?? ""} onChange={(e) => update({ phone: e.target.value })} className="w-full input-v2 px-3 py-2 text-sm" />
              </div>
            </div>
          </fieldset>
        )}

        {step === "tax" && (
          <fieldset className="space-y-5">
            <legend className="sr-only">{t("steps.tax")}</legend>
            <div className="space-y-2">
              <p id="setup-vat-registered-label" className="text-sm font-medium text-text-primary">{t("vatRegisteredQuestion")}</p>
              <p className="text-xs text-text-secondary">{t("vatRegisteredHelp")}</p>
              <div
                id="setup-vat-registered"
                role="radiogroup"
                tabIndex={-1}
                aria-labelledby="setup-vat-registered-label"
                aria-invalid={!!stepErrors.vat_registered}
                aria-describedby={describedBy("setup-vat-registered")}
                className="flex flex-wrap gap-2"
              >
                {[true, false].map((value) => (
                  <button
                    key={String(value)}
                    type="button"
                    role="radio"
                    aria-checked={data.vat_registered === value}
                    onClick={() =>
                      update(
                        value
                          ? {
                              vat_registered: true,
                              vat_frequency: data.vat_frequency ?? DEFAULT_VAT_FREQUENCY,
                              vat_accounting_basis: data.vat_accounting_basis ?? DEFAULT_VAT_ACCOUNTING_BASIS,
                            }
                          : { vat_registered: false, kor_participant: false }
                      )
                    }
                    className={`pill-v2 px-4 py-2 text-sm border ${data.vat_registered === value ? "bg-navy-solid text-white border-navy-solid" : "border-border text-text-primary hover:bg-muted"}`}
                  >
                    {value ? tCommon("yes") : tCommon("no")}
                  </button>
                ))}
              </div>
              {fieldError("vat_registered", "setup-vat-registered")}
            </div>

            {data.vat_registered && (
              <>
                <div className="space-y-1">
                  <label htmlFor="setup-vat-number" className="text-sm font-medium text-text-primary">{tCompanies("vatNumberLabel")}</label>
                  <input
                    id="setup-vat-number"
                    dir="ltr"
                    autoComplete="off"
                    placeholder="NL000099998B57"
                    value={data.vat_number ?? ""}
                    onChange={(e) => update({ vat_number: e.target.value.toUpperCase() })}
                    aria-required
                    aria-invalid={!!stepErrors.vat_number}
                    aria-describedby={describedBy("setup-vat-number")}
                    className="w-full input-v2 px-3 py-2 text-sm"
                  />
                  {fieldError("vat_number", "setup-vat-number")}
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <label htmlFor="setup-vat-frequency" className="text-sm font-medium text-text-primary">{tCompanies("vatFrequencyLabel")}</label>
                    <select
                      id="setup-vat-frequency"
                      value={data.vat_frequency ?? DEFAULT_VAT_FREQUENCY}
                      onChange={(e) => update({ vat_frequency: e.target.value as VatFrequency })}
                      aria-invalid={!!stepErrors.vat_frequency}
                      aria-describedby={describedBy("setup-vat-frequency")}
                      className="w-full input-v2 px-3 py-2 text-sm"
                    >
                      <option value="monthly">{tCompanies("frequencyMonthly")}</option>
                      <option value="quarterly">{tCompanies("frequencyQuarterly")}</option>
                      <option value="annual">{tCompanies("frequencyAnnual")}</option>
                    </select>
                    {fieldError("vat_frequency", "setup-vat-frequency")}
                  </div>
                  <div className="space-y-1">
                    <label htmlFor="setup-vat-basis" className="text-sm font-medium text-text-primary">{tCompanies("detail.vatAccountingBasisLabel")}</label>
                    <select
                      id="setup-vat-basis"
                      value={data.vat_accounting_basis ?? DEFAULT_VAT_ACCOUNTING_BASIS}
                      onChange={(e) => update({ vat_accounting_basis: e.target.value as VatAccountingBasis })}
                      aria-invalid={!!stepErrors.vat_accounting_basis}
                      aria-describedby={describedBy("setup-vat-basis")}
                      className="w-full input-v2 px-3 py-2 text-sm"
                    >
                      <option value="invoice_based">{tCompanies("detail.invoiceBased")}</option>
                      <option value="cash_based">{tCompanies("detail.cashBased")}</option>
                    </select>
                    {fieldError("vat_accounting_basis", "setup-vat-basis")}
                  </div>
                </div>
                <label className="flex items-start gap-3 text-sm" htmlFor="setup-kor">
                  <input
                    id="setup-kor"
                    type="checkbox"
                    checked={!!data.kor_participant}
                    onChange={(e) => update({ kor_participant: e.target.checked })}
                    aria-invalid={!!stepErrors.kor_participant}
                    aria-describedby={describedBy("setup-kor")}
                    className="mt-1 h-5 w-5"
                  />
                  <span>
                    <span className="font-medium text-text-primary">{t("korLabel")}</span>
                    <span className="block text-xs text-text-secondary">{t("korHelp")}</span>
                  </span>
                </label>
                {fieldError("kor_participant", "setup-kor")}
              </>
            )}

            <div className="space-y-1">
              <label htmlFor="setup-fy" className="text-sm font-medium text-text-primary">{t("firstFinancialYear")}</label>
              <select
                id="setup-fy"
                required
                value={data.financial_year ?? ""}
                onChange={(e) => update({ financial_year: e.target.value ? Number(e.target.value) : undefined })}
                aria-invalid={!!stepErrors.financial_year}
                aria-describedby={describedBy("setup-fy", "setup-fy-help")}
                className="w-full sm:w-48 input-v2 px-3 py-2 text-sm"
              >
                <option value="">{t("selectYear")}</option>
                {[currentYear + 1, currentYear, currentYear - 1, currentYear - 2].map((y) => (
                  <option key={y} value={y}>{y}</option>
                ))}
              </select>
              <p id="setup-fy-help" className="text-xs text-text-secondary">{t("financialYearHelp")}</p>
              {fieldError("financial_year", "setup-fy")}
            </div>
          </fieldset>
        )}

        {step === "banking" && (
          <fieldset className="space-y-4">
            <legend className="sr-only">{t("steps.banking")}</legend>
            <p className="text-sm text-text-secondary">{t("bankingIntro")}</p>
            <div className="space-y-1">
              <label htmlFor="setup-iban" className="text-sm font-medium text-text-primary">IBAN</label>
              <input
                id="setup-iban"
                dir="ltr"
                inputMode="text"
                autoComplete="off"
                placeholder="NL91 ABNA 0417 1643 00"
                value={data.bank_iban ?? ""}
                onChange={(e) => update({ bank_iban: e.target.value.toUpperCase(), bank_skipped: false })}
                aria-invalid={!!stepErrors.bank_iban}
                aria-describedby={describedBy("setup-iban")}
                className="w-full input-v2 px-3 py-2 text-sm font-mono"
              />
              {fieldError("bank_iban", "setup-iban")}
            </div>
            <div className="space-y-1">
              <label htmlFor="setup-bank-name" className="text-sm font-medium text-text-primary">{t("bankAccountName")}</label>
              <input
                id="setup-bank-name"
                autoComplete="off"
                value={data.bank_account_name ?? ""}
                onChange={(e) => update({ bank_account_name: e.target.value })}
                aria-required={!!data.bank_iban || undefined}
                aria-invalid={!!stepErrors.bank_account_name}
                aria-describedby={describedBy("setup-bank-name")}
                className="w-full input-v2 px-3 py-2 text-sm"
              />
              {fieldError("bank_account_name", "setup-bank-name")}
            </div>
            <p className="text-xs text-text-secondary">{t("bankingLater")}</p>
            <GlassButton type="button" variant="ghost" onClick={() => { update({ bank_iban: undefined, bank_account_name: undefined, bank_skipped: true }); void next(); }}>
              {t("skipBanking")}
            </GlassButton>
          </fieldset>
        )}

        {step === "review" && (
          <div className="space-y-4">
            {validation && !validation.ok && (
              <div className="rounded-lg bg-red-500/10 border border-red-300/50 text-sm px-4 py-3" role="alert">
                <p className="font-medium text-error mb-1">{t("review.missingTitle")}</p>
                <ul className="list-disc ps-5 space-y-0.5 text-error">
                  {validation.issues.map((i) => (
                    <li key={`${i.field}-${i.code}`}>{issueText(i)}</li>
                  ))}
                </ul>
              </div>
            )}
            {validation && validation.warnings.length > 0 && (
              <div className="rounded-lg bg-amber-50 border border-amber-200 text-sm px-4 py-3 text-pending">
                <ul className="list-disc ps-5 space-y-0.5">
                  {validation.warnings.map((w) => (
                    <li key={w.field}>{fieldLabel(w.field)}: {t("review.recommended")}</li>
                  ))}
                </ul>
              </div>
            )}
            {validation?.ok && <div className="rounded-lg bg-green-500/10 border border-green-300/50 text-green-700 text-sm px-4 py-3" role="status">{t("review.allGood")}</div>}

            <dl className="divide-y divide-border text-sm">
              {[
                ["name", data.name],
                ["legal_form_code", selectedForm ? formLabel(selectedForm) : data.legal_form_code],
                ["kvk_number", data.kvk_number ? `${data.kvk_number}${data.kvk_verified ? ` · ${t("kvk.verifiedShort")}` : ""}` : null],
                ["rsin", data.rsin],
                ["address", data.address],
                ["business_activity", data.business_activity],
                ["email", data.email],
                ["phone", data.phone],
                ["vat_registered", data.vat_registered === undefined ? null : data.vat_registered ? tCommon("yes") : tCommon("no")],
                ["vat_number", data.vat_registered ? data.vat_number : null],
                ["vat_frequency", data.vat_registered ? tCompanies(`frequency${(data.vat_frequency ?? DEFAULT_VAT_FREQUENCY)[0].toUpperCase()}${(data.vat_frequency ?? DEFAULT_VAT_FREQUENCY).slice(1)}` as never) : null],
                ["vat_accounting_basis", data.vat_registered ? tCompanies(data.vat_accounting_basis === "cash_based" ? "detail.cashBased" : "detail.invoiceBased") : null],
                ["kor_participant", data.vat_registered ? (data.kor_participant ? tCommon("yes") : tCommon("no")) : null],
                ["financial_year", data.financial_year],
                ["bank_iban", data.bank_skipped ? t("review.bankSkipped") : data.bank_iban],
                ["bank_account_name", data.bank_skipped ? null : data.bank_account_name],
              ]
                .filter(([, v]) => v !== null && v !== undefined && v !== "")
                .map(([field, value]) => (
                  <div key={field as string} className="py-2 flex flex-wrap justify-between gap-x-4 gap-y-1">
                    <dt className="text-text-secondary">{fieldLabel(field as string)}</dt>
                    <dd className={`font-medium text-text-primary ${issueFor(field as string) ? "text-error" : ""}`} dir={["kvk_number", "rsin", "vat_number", "bank_iban", "email", "phone"].includes(field as string) ? "ltr" : undefined}>
                      {String(value)}
                    </dd>
                  </div>
                ))}
            </dl>
            <p className="text-xs text-text-secondary">{t("review.confirmHelp")}</p>
          </div>
        )}

        {/* Sticky so Next/Create stays within reach of the thumb on a phone
            instead of below a screenful of fields. No negative margins: they
            would let the bar overhang the end of the document and clip. */}
        <div className="sticky bottom-0 z-10 flex flex-wrap items-center justify-between gap-3 border-t border-border bg-surface-card/95 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] backdrop-blur-sm">
          <div className="flex flex-wrap gap-2">
            {stepIndex > 0 && (
              <GlassButton type="button" variant="secondary" onClick={() => goTo(stepIndex - 1)}>
                {tCommon("previous")}
              </GlassButton>
            )}
            <GlassButton type="button" variant="ghost" onClick={discard}>
              {t("discardDraft")}
            </GlassButton>
          </div>
          {step === "review" ? (
            <GlassButton type="submit" className="ms-auto" loading={completing} disabled={!!validation && !validation.ok}>
              {t("createCompany")}
            </GlassButton>
          ) : (
            <GlassButton type="submit" className="ms-auto">{tCommon("next")}</GlassButton>
          )}
        </div>
      </form>
    </div>
  );
}

export default function NewCompanyPage() {
  return (
    <AuthGuard>
      <Shell>
        <Suspense>
          <WizardContent />
        </Suspense>
      </Shell>
    </AuthGuard>
  );
}
