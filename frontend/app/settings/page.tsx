"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, ApiError, Company } from "@/lib/api";

function MfaSection() {
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
      setError(e instanceof ApiError ? e.message : "Failed to start MFA setup");
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
      setMessage("MFA is now enabled on your account.");
      await refreshUser();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Invalid code");
    }
  }

  async function handleDisable(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setError(null);
    try {
      await api.mfaDisable(token, disableCode);
      setDisableCode("");
      setMessage("MFA has been disabled on your account.");
      await refreshUser();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Invalid code");
    }
  }

  return (
    <div className="card-v2 p-5 space-y-4">
      <h2 className="text-sm font-medium text-navy">Two-factor authentication (MFA)</h2>
      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}
      {message && <div className="rounded-md bg-green-50 text-green-700 text-sm px-3 py-2">{message}</div>}

      {user?.mfa_enabled ? (
        <div className="space-y-3">
          <p className="text-sm text-text-secondary">MFA is currently <span className="font-medium text-navy">enabled</span> on your account. Disabling it requires a current code from your authenticator app -- there is no recovery-code fallback in this build, so a lost device requires an operator to clear it directly.</p>
          <form onSubmit={handleDisable} className="flex items-end gap-3">
            <div className="space-y-1">
              <label htmlFor="mfa-disable-code" className="text-label-v2">Current code</label>
              <input id="mfa-disable-code" required value={disableCode} onChange={(e) => setDisableCode(e.target.value)} placeholder="6-digit code" className="input-v2 px-3 py-2 text-sm w-40" />
            </div>
            <button type="submit" className="btn-danger-v2 px-4 py-2 text-sm">Disable MFA</button>
          </form>
        </div>
      ) : setupSecret ? (
        <form onSubmit={handleEnable} className="space-y-3">
          <p className="text-sm text-text-secondary">
            Add this account to your authenticator app (Google Authenticator, 1Password, etc.) using this setup key, then enter the 6-digit code it shows to confirm:
          </p>
          <p className="font-mono text-xs break-all rounded-md bg-slate-50 px-3 py-2">{setupSecret}</p>
          <p className="text-xs text-text-secondary break-all">{provisioningUri}</p>
          <div className="flex items-end gap-3">
            <div className="space-y-1">
              <label htmlFor="mfa-enable-code" className="text-label-v2">Code from app</label>
              <input id="mfa-enable-code" required autoFocus value={code} onChange={(e) => setCode(e.target.value)} placeholder="6-digit code" className="input-v2 px-3 py-2 text-sm w-40" />
            </div>
            <button type="submit" className="btn-primary-v2 px-4 py-2 text-sm">Confirm and enable</button>
            <button type="button" onClick={() => { setSetupSecret(null); setProvisioningUri(null); }} className="btn-outline-v2 px-4 py-2 text-sm">Cancel</button>
          </div>
        </form>
      ) : (
        <div className="space-y-2">
          <p className="text-sm text-text-secondary">MFA is currently <span className="font-medium text-navy">not enabled</span>. Enabling it requires a code at every future login, verified with a time-based one-time code (TOTP) -- no SMS, no third-party MFA provider.</p>
          <button onClick={startSetup} className="btn-primary-v2 px-4 py-2 text-sm">Set up MFA</button>
        </div>
      )}
    </div>
  );
}

function SettingsContent() {
  const { token, user } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-navy">Settings</h1>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="card-v2 p-5">
        <h2 className="text-sm font-medium text-navy mb-3">Account</h2>
        <dl className="text-sm space-y-2">
          <div className="flex justify-between max-w-sm">
            <dt className="text-text-secondary">Name</dt>
            <dd className="text-navy font-medium">{user?.full_name}</dd>
          </div>
          <div className="flex justify-between max-w-sm">
            <dt className="text-text-secondary">Email</dt>
            <dd className="text-navy font-medium">{user?.email}</dd>
          </div>
          <div className="flex justify-between max-w-sm">
            <dt className="text-text-secondary">Role</dt>
            <dd className="text-navy font-medium capitalize">{user?.role}</dd>
          </div>
        </dl>
      </div>

      <MfaSection />

      <div className="card-v2">
        <div className="px-5 py-3 border-b border-border-subtle">
          <h2 className="text-sm font-medium text-navy">Company VAT settings</h2>
        </div>
        <div className="divide-y divide-slate-100">
          {companies.map((c) => (
            <Link key={c.id} href={`/companies/${c.id}`} className="flex items-center justify-between px-5 py-3 hover:bg-slate-50">
              <div>
                <p className="font-medium text-navy text-sm">{c.name}</p>
                <p className="text-xs text-text-secondary">
                  {c.vat_accounting_basis.replace("_", "-")} accounting · {c.vat_frequency} filing
                  {c.input_vat_pro_rata_percentage ? ` · ${c.input_vat_pro_rata_percentage}% pro-rata` : ""}
                </p>
              </div>
              <span className="text-xs text-navy">Edit →</span>
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
