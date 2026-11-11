"use client";

import { FormEvent, ReactNode, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import GlassPageHeader from "@/components/glass/GlassPageHeader";
import GlassPanel from "@/components/glass/GlassPanel";
import GlassButton from "@/components/glass/GlassButton";
import GlassLoadingState, { GlassErrorState } from "@/components/glass/GlassLoadingState";
import { GlassInput, GlassSelect } from "@/components/glass/GlassInput";
import { useAuth } from "@/lib/auth-context";
import { api, ApiError, ContractClause, ContractLanguage, ContractSettings, ContractTemplateVersion } from "@/lib/api";
import { formatDate } from "@/lib/format";

const PLACEHOLDERS = "{provider_name} {client_name} {client_kvk} {client_vat} {client_address} {client_representative} {start_date} {end_date} {term_months} {services} {fee} {payment_terms_days} {notice_period_days} {reference}";
const LANGS: ContractLanguage[] = ["nl", "en"];
const TEMPLATE_PILL = { APPROVED: "status-pill-success", DRAFT: "status-pill-warning", RETIRED: "status-pill-neutral" } as const;

function Field({ id, label, help, children }: { id: string; label: string; help?: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="text-xs font-medium text-text-secondary">{label}</label>
      {children}
      {help && <p id={`${id}-help`} className="text-xs text-text-secondary">{help}</p>}
    </div>
  );
}

function SettingsForm({ initial, onSaved, onError }: { initial: ContractSettings; onSaved: (s: ContractSettings, msg: string) => void; onError: (msg: string) => void }) {
  const t = useTranslations("contracts.templates");
  const tc = useTranslations("contracts");
  const { token } = useAuth();
  const [form, setForm] = useState(initial);
  const [reminderDays, setReminderDays] = useState(initial.reminder_days.join(", "));
  const [busy, setBusy] = useState<string | null>(null);

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setBusy("save");
    try {
      const days = reminderDays.split(/[,\s]+/).map(Number).filter((n) => Number.isInteger(n) && n > 0);
      const saved = await api.updateContractSettings(token, {
        reminder_days: days,
        signing_link_expire_days: form.signing_link_expire_days,
        signing_reminder_days: form.signing_reminder_days,
        auto_create_on_company_create: form.auto_create_on_company_create,
        default_language: form.default_language,
        notification_email: form.notification_email || null,
        reply_to_email: form.reply_to_email || null,
      });
      setForm(saved);
      setReminderDays(saved.reminder_days.join(", "));
      onSaved(saved, t("settingsSaved"));
    } catch (err) {
      onError(err instanceof ApiError ? err.message : t("saveFailed"));
    } finally {
      setBusy(null);
    }
  }

  async function runScheduler() {
    if (!token) return;
    setBusy("scheduler");
    try {
      const result = await api.runContractScheduler(token);
      onSaved(form, t("schedulerRan", { summary: Object.entries(result).map(([k, v]) => `${k}=${v}`).join(", ") }));
    } catch (err) {
      onError(err instanceof ApiError ? err.message : t("schedulerFailed"));
    } finally {
      setBusy(null);
    }
  }

  return (
    <form onSubmit={save} className="px-5 py-4 space-y-3">
      <Field id="cs-reminders" label={t("reminderDays")} help={t("reminderDaysHelp")}>
        <GlassInput id="cs-reminders" dir="ltr" aria-describedby="cs-reminders-help" value={reminderDays} onChange={(e) => setReminderDays(e.target.value)} />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field id="cs-expiry" label={t("linkExpiry")}><GlassInput id="cs-expiry" type="number" min={1} max={90} value={form.signing_link_expire_days} onChange={(e) => setForm({ ...form, signing_link_expire_days: Number(e.target.value) })} /></Field>
        <Field id="cs-signrem" label={t("signingReminder")}><GlassInput id="cs-signrem" type="number" min={1} max={60} value={form.signing_reminder_days} onChange={(e) => setForm({ ...form, signing_reminder_days: Number(e.target.value) })} /></Field>
      </div>
      <Field id="cs-lang" label={t("defaultLanguage")}>
        <GlassSelect id="cs-lang" className="w-full" value={form.default_language} onChange={(e) => setForm({ ...form, default_language: e.target.value as ContractLanguage })}>
          <option value="nl">{tc("languages.nl")}</option>
          <option value="en">{tc("languages.en")}</option>
        </GlassSelect>
      </Field>
      <Field id="cs-notify" label={t("notificationEmail")}><GlassInput id="cs-notify" type="email" dir="ltr" value={form.notification_email ?? ""} onChange={(e) => setForm({ ...form, notification_email: e.target.value })} /></Field>
      <Field id="cs-replyto" label={t("replyTo")}><GlassInput id="cs-replyto" type="email" dir="ltr" value={form.reply_to_email ?? ""} onChange={(e) => setForm({ ...form, reply_to_email: e.target.value })} /></Field>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" className="w-4 h-4" checked={form.auto_create_on_company_create} onChange={(e) => setForm({ ...form, auto_create_on_company_create: e.target.checked })} />
        {t("autoCreate")}
      </label>
      <GlassButton type="submit" loading={busy === "save"}>{t("saveSettings")}</GlassButton>
      <div className="text-xs text-text-secondary border-t border-border pt-3 space-y-1">
        <p className="font-medium text-text-primary">{t("flags")}</p>
        <p className="flex justify-between gap-2"><span className="font-mono" dir="ltr">{t("featureFlag")}</span><span>{form.feature_enabled ? t("enabled") : t("disabled")}</span></p>
        <p className="flex justify-between gap-2"><span className="font-mono" dir="ltr">{t("automationFlag")}</span><span>{form.email_automation_enabled ? t("enabled") : t("disabled")}</span></p>
        <p>{t("automationHelp")}</p>
        <p className="flex justify-between gap-2"><span>{t("provider")}</span><span className="font-mono" dir="ltr">{form.signing_provider}</span></p>
      </div>
      <GlassButton type="button" variant="outline" size="sm" loading={busy === "scheduler"} onClick={runScheduler}>{t("runScheduler")}</GlassButton>
    </form>
  );
}

function TemplatesContent() {
  const t = useTranslations("contracts.templates");
  const tc = useTranslations("contracts");
  const tAdmin = useTranslations("admin");
  const locale = useLocale();
  const { token, user } = useAuth();
  const [versions, setVersions] = useState<ContractTemplateVersion[] | null>(null);
  const [settings, setSettings] = useState<ContractSettings | null>(null);
  const [draft, setDraft] = useState<ContractTemplateVersion | null>(null);
  const [lang, setLang] = useState<ContractLanguage>("nl");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const loadVersions = useCallback(() => {
    if (!token) return;
    api.listContractTemplates(token)
      .then((list) => { setVersions(list); setDraft((d) => d ?? structuredClone(list[0])); })
      .catch((e) => setError(e instanceof ApiError ? e.message : tc("loadFailed")));
  }, [token, tc]);

  useEffect(() => {
    loadVersions();
    if (token) api.getContractSettings(token).then(setSettings).catch(() => undefined);
  }, [token, loadVersions]);

  if (!user || (user.role !== "owner" && user.role !== "admin")) return <GlassErrorState message={tAdmin("platformAdminOnly")} />;

  async function approve(versionId: number) {
    if (!token) return;
    setBusy(`approve-${versionId}`);
    setError(null);
    try {
      await api.approveContractTemplateVersion(token, versionId);
      loadVersions();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("saveFailed"));
    } finally {
      setBusy(null);
    }
  }

  async function saveVersion(e: FormEvent) {
    e.preventDefault();
    if (!token || !draft) return;
    setBusy("save");
    setError(null);
    setNotice(null);
    try {
      const created = await api.createContractTemplateVersion(token, {
        content: draft.content,
        default_services: draft.default_services,
        default_monthly_fee: draft.default_monthly_fee || null,
        default_payment_terms_days: draft.default_payment_terms_days,
        default_notice_period_days: draft.default_notice_period_days,
        default_term_months: draft.default_term_months,
        change_note: draft.change_note,
      });
      setNotice(t("saved", { n: created.version_no }));
      setDraft(structuredClone(created));
      loadVersions();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("saveFailed"));
    } finally {
      setBusy(null);
    }
  }

  function setClause(i: number, patch: Partial<ContractClause>) {
    if (!draft) return;
    const block = draft.content[lang];
    setDraft({ ...draft, content: { ...draft.content, [lang]: { ...block, clauses: block.clauses.map((c, j) => (j === i ? { ...c, ...patch } : c)) } } });
  }

  function setService(i: number, key: "code" | "nl" | "en", value: string) {
    if (!draft) return;
    setDraft({ ...draft, default_services: draft.default_services.map((s, j) => (j === i ? { ...s, [key]: value } : s)) });
  }

  const intOrNull = (v: string) => (v === "" ? null : Number(v));

  return (
    <div className="space-y-5">
      <GlassPageHeader title={t("title")} subtitle={t("subtitle")} actions={<Link href="/contracts" className="btn-secondary-v2 px-4 py-2 text-sm rounded-[0.6rem]">{tc("title")}</Link>} />
      <div className="rounded-md bg-amber-50 border border-amber-200 text-sm px-3 py-2 text-pending" role="note">{t("legalNotice")}</div>
      {error && <GlassErrorState message={error} />}
      {notice && <div className="rounded-md bg-green-50 text-green-800 text-sm px-3 py-2" role="status">{notice}</div>}

      {versions === null ? (
        <GlassLoadingState />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          <div className="space-y-5">
            <GlassPanel title={t("versions")} subtitle={t("approveHelp")}>
              <ul className="divide-y divide-border text-sm">
                {versions.map((v) => (
                  <li key={v.id} className="px-5 py-3 space-y-1">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <button type="button" className="font-medium text-navy hover:underline" onClick={() => setDraft(structuredClone(v))}>{t("version", { n: v.version_no })}</button>
                      <span className={`status-pill ${TEMPLATE_PILL[v.status]}`}>{t(`status.${v.status}`)}</span>
                    </div>
                    <p className="text-xs text-text-secondary">{t("createdAt", { date: formatDate(v.created_at, locale) })}{v.change_note && <> · {v.change_note}</>}</p>
                    {v.status === "DRAFT" && <GlassButton size="sm" variant="outline" loading={busy === `approve-${v.id}`} onClick={() => approve(v.id)}>{t("approve")}</GlassButton>}
                  </li>
                ))}
              </ul>
            </GlassPanel>
            {settings && (
              <GlassPanel title={t("settings")}>
                <SettingsForm initial={settings} onSaved={(s, msg) => { setSettings(s); setNotice(msg); setError(null); }} onError={(msg) => { setError(msg); setNotice(null); }} />
              </GlassPanel>
            )}
          </div>

          {draft && (
            <form onSubmit={saveVersion} className="lg:col-span-2 space-y-5">
              <GlassPanel
                title={t("editing", { n: draft.version_no })}
                actions={
                  <div role="tablist" className="inline-flex gap-1">
                    {LANGS.map((l) => (
                      <button key={l} type="button" role="tab" aria-selected={lang === l} onClick={() => setLang(l)} className={`pill-v2 px-3 py-1.5 text-sm font-medium ${lang === l ? "btn-primary-v2" : "text-text-secondary hover:text-text-primary"}`}>
                        {tc(`languages.${l}`)}
                      </button>
                    ))}
                  </div>
                }
              >
                <div className="px-5 py-4 space-y-4">
                  <Field id="tpl-title" label={t("heading")}>
                    <GlassInput id="tpl-title" value={draft.content[lang].title} onChange={(e) => setDraft({ ...draft, content: { ...draft.content, [lang]: { ...draft.content[lang], title: e.target.value } } })} />
                  </Field>
                  <p className="text-xs text-text-secondary font-mono break-words" dir="ltr">{t("placeholders", { list: PLACEHOLDERS })}</p>
                  <h3 className="text-sm font-medium text-text-primary">{t("clauses", { lang: tc(`languages.${lang}`) })}</h3>
                  {draft.content[lang].clauses.map((c, i) => (
                    <div key={c.key ?? i} className="space-y-1 border-t border-border-subtle pt-3">
                      <Field id={`tpl-h-${i}`} label={t("heading")}><GlassInput id={`tpl-h-${i}`} value={c.heading} onChange={(e) => setClause(i, { heading: e.target.value })} /></Field>
                      <Field id={`tpl-b-${i}`} label={t("body")}>
                        <textarea id={`tpl-b-${i}`} rows={4} className="input-v2 w-full px-3 py-2 text-sm" value={c.body} onChange={(e) => setClause(i, { body: e.target.value })} />
                      </Field>
                    </div>
                  ))}
                </div>
              </GlassPanel>

              <GlassPanel title={t("defaults")}>
                <div className="px-5 py-4 space-y-3">
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <Field id="tpl-fee" label={t("defaultFee")}><GlassInput id="tpl-fee" type="number" step="0.01" min={0} dir="ltr" value={draft.default_monthly_fee ?? ""} onChange={(e) => setDraft({ ...draft, default_monthly_fee: e.target.value || null })} /></Field>
                    <Field id="tpl-pay" label={t("paymentTerms")}><GlassInput id="tpl-pay" type="number" min={0} max={365} value={draft.default_payment_terms_days ?? ""} onChange={(e) => setDraft({ ...draft, default_payment_terms_days: intOrNull(e.target.value) })} /></Field>
                    <Field id="tpl-notice" label={t("noticePeriod")}><GlassInput id="tpl-notice" type="number" min={0} max={365} value={draft.default_notice_period_days ?? ""} onChange={(e) => setDraft({ ...draft, default_notice_period_days: intOrNull(e.target.value) })} /></Field>
                    <Field id="tpl-months" label={t("termMonths")}><GlassInput id="tpl-months" type="number" min={1} max={60} value={draft.default_term_months} onChange={(e) => setDraft({ ...draft, default_term_months: Number(e.target.value) })} /></Field>
                  </div>
                  <div className="space-y-1">
                    <p className="text-xs font-medium text-text-secondary">{t("defaultServices")}</p>
                    {draft.default_services.map((s, i) => (
                      <div key={i} className="grid grid-cols-3 gap-2">
                        <GlassInput aria-label="code" dir="ltr" value={s.code} onChange={(e) => setService(i, "code", e.target.value)} />
                        <GlassInput aria-label="NL" value={s.nl} onChange={(e) => setService(i, "nl", e.target.value)} />
                        <GlassInput aria-label="EN" value={s.en} onChange={(e) => setService(i, "en", e.target.value)} />
                      </div>
                    ))}
                  </div>
                  <Field id="tpl-note" label={t("changeNote")}><GlassInput id="tpl-note" value={draft.change_note ?? ""} onChange={(e) => setDraft({ ...draft, change_note: e.target.value })} /></Field>
                  <GlassButton type="submit" loading={busy === "save"}>{t("newVersion")}</GlassButton>
                </div>
              </GlassPanel>
            </form>
          )}
        </div>
      )}
    </div>
  );
}

export default function ContractTemplatesPage() {
  return (
    <AuthGuard>
      <Shell>
        <TemplatesContent />
      </Shell>
    </AuthGuard>
  );
}
