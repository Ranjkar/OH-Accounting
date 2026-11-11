"use client";

import { ChangeEvent, FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import ThemeToggle from "@/components/glass/ThemeToggle";
import LanguageSelector from "@/components/glass/LanguageSelector";
import { api, ApiError, ASSIGNABLE_ROLES, Company } from "@/lib/api";
import { PASSWORD_MIN_LENGTH, passwordIssue } from "@/lib/password-policy";
import { IconChevronRight } from "@/components/glass/icons";

const PROFILE_FIELDS = ["first_name", "last_name", "display_name", "phone", "address_line", "postal_code", "city", "country"] as const;
type ProfileField = (typeof PROFILE_FIELDS)[number];
type ProfileForm = Record<ProfileField, string>;

const EMPTY_PROFILE: ProfileForm = {
  first_name: "", last_name: "", display_name: "", phone: "", address_line: "", postal_code: "", city: "", country: "",
};

/** Personal details. The backend endpoint only ever touches these fields, so
 * nothing here can change the caller's own authority. */
function ProfileSection() {
  const t = useTranslations("settings");
  const tCommon = useTranslations("common");
  const { token, user, refreshUser } = useAuth();
  // The form starts as a view of the signed-in user and only becomes its own
  // state once edited -- no effect needed to mirror the user into inputs.
  const [edited, setEdited] = useState<ProfileForm | null>(null);
  const form: ProfileForm =
    edited ??
    (user
      ? {
          first_name: user.first_name ?? "",
          last_name: user.last_name ?? "",
          display_name: user.display_name ?? "",
          phone: user.phone ?? "",
          address_line: user.address_line ?? "",
          postal_code: user.postal_code ?? "",
          city: user.city ?? "",
          country: user.country ?? "",
        }
      : EMPTY_PROFILE);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const set = (field: ProfileField) => (e: ChangeEvent<HTMLInputElement>) => {
    const value = field === "country" ? e.target.value.toUpperCase().slice(0, 2) : e.target.value;
    setEdited({ ...form, [field]: value });
    setSaved(false);
  };

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      await api.updateMyProfile(
        token,
        Object.fromEntries(PROFILE_FIELDS.map((f) => [f, form[f].trim() || null])) as Partial<Record<ProfileField, string | null>>
      );
      await refreshUser();
      setSaved(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("profileSaveFailed"));
    } finally {
      setBusy(false);
    }
  }

  const field = (name: ProfileField, label: string, props: { type?: string; dir?: string; autoComplete?: string; maxLength?: number; pattern?: string } = {}) => (
    <div className="space-y-1">
      <label htmlFor={`profile-${name}`} className="text-label-v2">{label}</label>
      <input
        id={`profile-${name}`}
        value={form[name]}
        onChange={set(name)}
        type={props.type ?? "text"}
        dir={props.dir}
        autoComplete={props.autoComplete}
        maxLength={props.maxLength}
        className="input-v2 px-3 py-2 text-sm w-full"
      />
    </div>
  );

  return (
    <form onSubmit={save} className="card-v2 p-5 space-y-4">
      <div>
        <h2 className="text-sm font-medium text-text-primary">{t("profileTitle")}</h2>
        <p className="text-xs text-text-secondary mt-0.5">{t("profileHelp")}</p>
      </div>
      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2" role="alert">{error}</div>}
      {saved && <div className="rounded-md bg-green-50 text-green-700 text-sm px-3 py-2" role="status">{t("profileSaved")}</div>}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {field("first_name", t("firstName"), { autoComplete: "given-name" })}
        {field("last_name", t("lastName"), { autoComplete: "family-name" })}
        {field("display_name", t("displayName"), { autoComplete: "nickname" })}
        {field("phone", t("phoneLabel"), { type: "tel", dir: "ltr", autoComplete: "tel", maxLength: 50 })}
        <div className="sm:col-span-2">{field("address_line", t("addressLine"), { autoComplete: "street-address", maxLength: 255 })}</div>
        {field("postal_code", t("postalCode"), { autoComplete: "postal-code", maxLength: 20 })}
        {field("city", t("city"), { autoComplete: "address-level2", maxLength: 100 })}
        {field("country", t("country"), { maxLength: 2 })}
      </div>
      <button type="submit" disabled={busy} className="btn-primary-v2 px-4 py-2 text-sm disabled:opacity-50">
        {busy ? tCommon("saving") : t("saveProfile")}
      </button>
    </form>
  );
}

/** Password, verified email change and session control. Password changes and
 * session revocation rotate the JWT (the server bumps token_version), so the
 * fresh token from the response replaces the one in the auth context. */
function SecuritySection() {
  const t = useTranslations("settings");
  const tCommon = useTranslations("common");
  const { token, user, refreshUser, rotateToken } = useAuth();

  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [pwBusy, setPwBusy] = useState(false);
  const [pwError, setPwError] = useState<string | null>(null);
  const [pwDone, setPwDone] = useState(false);

  const [newEmail, setNewEmail] = useState("");
  const [emailPassword, setEmailPassword] = useState("");
  const [emailBusy, setEmailBusy] = useState(false);
  const [emailError, setEmailError] = useState<string | null>(null);

  const [askRevoke, setAskRevoke] = useState(false);
  const [revokeBusy, setRevokeBusy] = useState(false);
  const [revokeError, setRevokeError] = useState<string | null>(null);
  const [revokeDone, setRevokeDone] = useState(false);

  function localPasswordError(): string | null {
    if (next !== confirm) return t("passwordErrors.mismatch");
    if (next && next === current) return t("passwordErrors.sameAsCurrent");
    const issue = passwordIssue(next, user?.email);
    return issue ? t(`passwordErrors.${issue}` as never, { min: PASSWORD_MIN_LENGTH } as never) : null;
  }

  async function changePassword(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    const local = localPasswordError();
    if (local) {
      setPwError(local);
      return;
    }
    setPwBusy(true);
    setPwError(null);
    setPwDone(false);
    try {
      const { access_token } = await api.changeMyPassword(token, current, next, confirm);
      rotateToken(access_token);
      setCurrent("");
      setNext("");
      setConfirm("");
      setPwDone(true);
    } catch (err) {
      setPwError(err instanceof ApiError ? err.message : t("passwordChangeFailed"));
    } finally {
      setPwBusy(false);
    }
  }

  async function requestEmailChange(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setEmailBusy(true);
    setEmailError(null);
    try {
      await api.requestEmailChange(token, newEmail, emailPassword);
      await refreshUser();
      setNewEmail("");
      setEmailPassword("");
    } catch (err) {
      setEmailError(err instanceof ApiError ? err.message : t("emailChangeFailed"));
    } finally {
      setEmailBusy(false);
    }
  }

  async function cancelEmailChange() {
    if (!token) return;
    setEmailBusy(true);
    setEmailError(null);
    try {
      await api.cancelEmailChange(token);
      await refreshUser();
    } catch (err) {
      setEmailError(err instanceof ApiError ? err.message : t("emailChangeFailed"));
    } finally {
      setEmailBusy(false);
    }
  }

  async function revokeOtherSessions() {
    if (!token) return;
    setRevokeBusy(true);
    setRevokeError(null);
    setRevokeDone(false);
    try {
      const { access_token } = await api.revokeOtherSessions(token);
      rotateToken(access_token);
      setRevokeDone(true);
      setAskRevoke(false);
    } catch (err) {
      setRevokeError(err instanceof ApiError ? err.message : t("revokeSessionsFailed"));
    } finally {
      setRevokeBusy(false);
    }
  }

  return (
    <div className="card-v2 divide-y divide-border-subtle">
      <form onSubmit={changePassword} className="p-5 space-y-4">
        <div>
          <h2 className="text-sm font-medium text-text-primary">{t("changePasswordTitle")}</h2>
          <p className="text-xs text-text-secondary mt-0.5">{t("passwordPolicyHelp", { min: PASSWORD_MIN_LENGTH })}</p>
        </div>
        {pwError && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2" role="alert">{pwError}</div>}
        {pwDone && <div className="rounded-md bg-green-50 text-green-700 text-sm px-3 py-2" role="status">{t("passwordChanged")}</div>}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="space-y-1">
            <label htmlFor="pw-current" className="text-label-v2">{t("currentPasswordLabel")}</label>
            <input id="pw-current" type="password" required autoComplete="current-password" dir="ltr" value={current} onChange={(e) => setCurrent(e.target.value)} className="input-v2 px-3 py-2 text-sm w-full" />
          </div>
          <div className="space-y-1">
            <label htmlFor="pw-new" className="text-label-v2">{t("newPasswordLabel")}</label>
            <input id="pw-new" type="password" required autoComplete="new-password" dir="ltr" value={next} onChange={(e) => { setNext(e.target.value); setPwDone(false); }} className="input-v2 px-3 py-2 text-sm w-full" />
          </div>
          <div className="space-y-1">
            <label htmlFor="pw-confirm" className="text-label-v2">{t("confirmPasswordLabel")}</label>
            <input id="pw-confirm" type="password" required autoComplete="new-password" dir="ltr" value={confirm} onChange={(e) => setConfirm(e.target.value)} className="input-v2 px-3 py-2 text-sm w-full" />
          </div>
        </div>
        <button type="submit" disabled={pwBusy} className="btn-primary-v2 px-4 py-2 text-sm disabled:opacity-50">
          {pwBusy ? tCommon("saving") : t("changePasswordButton")}
        </button>
      </form>

      <div className="p-5 space-y-4">
        <div>
          <h2 className="text-sm font-medium text-text-primary">{t("emailChangeTitle")}</h2>
          <p className="text-xs text-text-secondary mt-0.5">{t("emailChangeHelp")}</p>
        </div>
        {emailError && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2" role="alert">{emailError}</div>}
        {user?.pending_email ? (
          <div className="rounded-md bg-amber-50 border border-amber-200 text-sm px-3 py-2 space-y-2" role="status">
            <p className="text-pending">{t("emailChangeRequested", { email: user.pending_email })}</p>
            <button type="button" onClick={() => void cancelEmailChange()} disabled={emailBusy} className="btn-outline-v2 px-3 py-1.5 text-xs disabled:opacity-50">
              {t("emailChangeCancel")}
            </button>
          </div>
        ) : (
          <form onSubmit={requestEmailChange} className="flex flex-wrap items-end gap-3">
            <div className="space-y-1">
              <label htmlFor="email-new" className="text-label-v2">{t("newEmailLabel")}</label>
              <input id="email-new" type="email" required dir="ltr" autoComplete="email" value={newEmail} onChange={(e) => setNewEmail(e.target.value)} className="input-v2 px-3 py-2 text-sm w-64 max-w-full" />
            </div>
            <div className="space-y-1">
              <label htmlFor="email-password" className="text-label-v2">{t("emailPasswordLabel")}</label>
              <input id="email-password" type="password" required autoComplete="current-password" dir="ltr" value={emailPassword} onChange={(e) => setEmailPassword(e.target.value)} className="input-v2 px-3 py-2 text-sm w-48 max-w-full" />
            </div>
            <button type="submit" disabled={emailBusy} className="btn-primary-v2 px-4 py-2 text-sm disabled:opacity-50">
              {emailBusy ? tCommon("saving") : t("emailChangeButton")}
            </button>
          </form>
        )}
      </div>

      <div className="p-5 space-y-3">
        <div>
          <h2 className="text-sm font-medium text-text-primary">{t("sessionsTitle")}</h2>
          <p className="text-xs text-text-secondary mt-0.5">{t("sessionsHelp")}</p>
        </div>
        {revokeError && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2" role="alert">{revokeError}</div>}
        {revokeDone && <div className="rounded-md bg-green-50 text-green-700 text-sm px-3 py-2" role="status">{t("sessionsRevoked")}</div>}
        {askRevoke ? (
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm text-text-primary">{t("revokeOthersConfirm")}</p>
            <button type="button" onClick={() => void revokeOtherSessions()} disabled={revokeBusy} className="btn-danger-v2 px-4 py-2 text-sm disabled:opacity-50">
              {revokeBusy ? tCommon("sending") : t("revokeOthersButton")}
            </button>
            <button type="button" onClick={() => setAskRevoke(false)} disabled={revokeBusy} className="btn-outline-v2 px-4 py-2 text-sm disabled:opacity-50">
              {tCommon("cancel")}
            </button>
          </div>
        ) : (
          <button type="button" onClick={() => setAskRevoke(true)} className="btn-outline-v2 px-4 py-2 text-sm">
            {t("revokeOthersButton")}
          </button>
        )}
      </div>
    </div>
  );
}

function MfaSection() {
  const t = useTranslations("settings");
  const tCommon = useTranslations("common");
  const { token, user, refreshUser } = useAuth();
  const [setupSecret, setSetupSecret] = useState<string | null>(null);
  const [provisioningUri, setProvisioningUri] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [disableCode, setDisableCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function startSetup() {
    if (!token) return;
    setError(null);
    try {
      const { secret, provisioning_uri } = await api.mfaSetup(token);
      setSetupSecret(secret);
      setProvisioningUri(provisioning_uri);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("mfaSetupFailed"));
    }
  }

  async function handleEnable(e: FormEvent) {
    e.preventDefault();
    if (!token || !setupSecret) return;
    setError(null);
    try {
      await api.mfaEnable(token, setupSecret, code);
      setSetupSecret(null);
      setProvisioningUri(null);
      setCode("");
      setMessage(t("mfaEnabledSuccess"));
      await refreshUser();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("mfaInvalidCode"));
    }
  }

  async function handleDisable(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setError(null);
    try {
      await api.mfaDisable(token, disableCode);
      setDisableCode("");
      setMessage(t("mfaDisabledSuccess"));
      await refreshUser();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("mfaInvalidCode"));
    }
  }

  return (
    <div className="card-v2 p-5 space-y-4">
      <h2 className="text-sm font-medium text-text-primary">{t("mfaTitle")}</h2>
      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}
      {message && <div className="rounded-md bg-green-50 text-green-700 text-sm px-3 py-2">{message}</div>}

      {user?.mfa_enabled ? (
        <div className="space-y-3">
          <p className="text-sm text-text-secondary">
            {t.rich("mfaEnabledBody", { status: (chunks) => <span className="font-medium text-navy">{chunks}</span> })}
          </p>
          <form onSubmit={handleDisable} className="flex flex-wrap items-end gap-3">
            <div className="space-y-1">
              <label htmlFor="mfa-disable-code" className="text-label-v2">{t("mfaCurrentCode")}</label>
              <input id="mfa-disable-code" required value={disableCode} onChange={(e) => setDisableCode(e.target.value)} placeholder={t("mfaDigitCode")} className="input-v2 px-3 py-2 text-sm w-40" />
            </div>
            <button type="submit" className="btn-danger-v2 px-4 py-2 text-sm">{t("mfaDisable")}</button>
          </form>
        </div>
      ) : setupSecret ? (
        <form onSubmit={handleEnable} className="space-y-3">
          <p className="text-sm text-text-secondary">{t("mfaSetupInstructions")}</p>
          <p className="font-mono text-xs break-all rounded-md bg-muted px-3 py-2" dir="ltr">{setupSecret}</p>
          <p className="text-xs text-text-secondary break-all" dir="ltr">{provisioningUri}</p>
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1">
              <label htmlFor="mfa-enable-code" className="text-label-v2">{t("mfaCodeFromApp")}</label>
              <input id="mfa-enable-code" required autoFocus value={code} onChange={(e) => setCode(e.target.value)} placeholder={t("mfaDigitCode")} className="input-v2 px-3 py-2 text-sm w-40" />
            </div>
            <button type="submit" className="btn-primary-v2 px-4 py-2 text-sm">{t("mfaConfirmEnable")}</button>
            <button type="button" onClick={() => { setSetupSecret(null); setProvisioningUri(null); }} className="btn-outline-v2 px-4 py-2 text-sm">{tCommon("cancel")}</button>
          </div>
        </form>
      ) : (
        <div className="space-y-2">
          <p className="text-sm text-text-secondary">
            {t.rich("mfaNotEnabledBody", { status: (chunks) => <span className="font-medium text-navy">{chunks}</span> })}
          </p>
          <button onClick={startSetup} className="btn-primary-v2 px-4 py-2 text-sm">{t("mfaSetUp")}</button>
        </div>
      )}
    </div>
  );
}

function SettingsContent() {
  const t = useTranslations("settings");
  const tRoles = useTranslations("users.roles");
  const { token, user } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-text-primary">{t("title")}</h1>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="card-v2 p-5">
        <h2 className="text-sm font-medium text-text-primary mb-3">{t("account")}</h2>
        <dl className="text-sm space-y-2">
          <div className="flex justify-between max-w-sm">
            <dt className="text-text-secondary">{t("accountName")}</dt>
            <dd className="text-navy font-medium">{user?.full_name}</dd>
          </div>
          <div className="flex justify-between max-w-sm">
            <dt className="text-text-secondary">{t("accountEmail")}</dt>
            <dd className="text-navy font-medium" dir="ltr">{user?.email}</dd>
          </div>
          <div className="flex justify-between max-w-sm">
            <dt className="text-text-secondary">{t("accountRole")}</dt>
            <dd className="text-navy font-medium capitalize">
              {user && (ASSIGNABLE_ROLES as string[]).includes(user.role) ? tRoles(user.role as never) : user?.role}
            </dd>
          </div>
        </dl>
      </div>

      <ProfileSection />

      <SecuritySection />

      <MfaSection />

      <div className="card-v2 p-5 space-y-3">
        <div>
          <h2 className="text-sm font-medium text-text-primary">{t("appearance")}</h2>
          <p className="text-xs text-text-secondary mt-0.5">{t("appearanceDescription")}</p>
        </div>
        <ThemeToggle />
      </div>

      <div className="card-v2 p-5 space-y-3">
        <div>
          <h2 className="text-sm font-medium text-text-primary">{t("languageRegion")}</h2>
          <p className="text-xs text-text-secondary mt-0.5">{useTranslations("language")("description")}</p>
        </div>
        <LanguageSelector />
      </div>

      <div className="card-v2">
        <div className="px-5 py-3 border-b border-border-subtle">
          <h2 className="text-sm font-medium text-text-primary">{t("companyVatSettings")}</h2>
        </div>
        <div className="divide-y divide-border">
          {companies.map((c) => (
            <Link key={c.id} href={`/companies/${c.id}`} className="flex items-center justify-between px-5 py-3 hover:bg-muted">
              <div>
                <p className="font-medium text-navy text-sm">{c.name}</p>
                <p className="text-xs text-text-secondary">
                  {c.vat_accounting_basis.replace("_", "-")} {t("vatAccounting")} · {c.vat_frequency} {t("vatFiling")}
                  {c.input_vat_pro_rata_percentage ? ` · ${c.input_vat_pro_rata_percentage}% ${t("vatProRata")}` : ""}
                </p>
              </div>
              <span className="text-xs text-navy inline-flex items-center gap-0.5">
                {t("editLink")} <IconChevronRight size={12} className="icon-directional" />
              </span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <AuthGuard>
      <Shell>
        <SettingsContent />
      </Shell>
    </AuthGuard>
  );
}
