"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import ThemeToggle from "@/components/glass/ThemeToggle";
import LanguageSelector from "@/components/glass/LanguageSelector";
import { api, ApiError, ASSIGNABLE_ROLES, Company } from "@/lib/api";
import { IconChevronRight } from "@/components/glass/icons";

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

      <MfaSection />

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
