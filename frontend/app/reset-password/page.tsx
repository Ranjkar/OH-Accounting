"use client";

import { FormEvent, Suspense, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { api, ApiError } from "@/lib/api";
import { PASSWORD_MIN_LENGTH, passwordIssue } from "@/lib/password-policy";

/** Two modes in one page: without ?token= it emails a reset link (the
 * backend answers 204 whether or not the address exists, so the success
 * message is deliberately neutral), with a token it sets the new password. */
function ResetPasswordContent() {
  const t = useTranslations("auth");
  const tSettings = useTranslations("settings");
  const searchParams = useSearchParams();
  const resetToken = searchParams.get("token") ?? "";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [requested, setRequested] = useState(false);
  const [done, setDone] = useState(false);

  async function requestReset(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.requestPasswordReset(email);
      setRequested(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("resetFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function setNewPassword(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError(t("resetMismatch"));
      return;
    }
    // The account's address is unknown here, so the email-containment rule
    // can only be applied server-side; everything else is checked locally.
    const issue = passwordIssue(password);
    if (issue) {
      setError(tSettings(`passwordErrors.${issue}` as never, { min: PASSWORD_MIN_LENGTH } as never));
      return;
    }
    setBusy(true);
    try {
      await api.confirmPasswordReset(resetToken, password);
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("resetFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4">
      <div className="card-v2 p-6 w-full max-w-sm space-y-4">
        <div>
          <h1 className="text-lg font-semibold text-text-primary">{t("resetTitle")}</h1>
          <p className="text-sm text-text-secondary mt-1">
            {resetToken ? t("resetNewHelp") : t("resetRequestHelp")}
          </p>
        </div>

        {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2" role="alert">{error}</div>}

        {resetToken ? (
          done ? (
            <div className="space-y-3">
              <div className="rounded-md bg-green-50 text-green-700 text-sm px-3 py-2" role="status">{t("resetDone")}</div>
              <Link href="/login" className="btn-primary-v2 px-4 py-2 text-sm inline-block">{t("backToLogin")}</Link>
            </div>
          ) : (
            <form onSubmit={setNewPassword} className="space-y-4" noValidate={false}>
              <div className="space-y-1">
                <label htmlFor="reset-password" className="text-label-v2">{t("resetNewPasswordLabel")}</label>
                <input
                  id="reset-password"
                  type="password"
                  required
                  minLength={PASSWORD_MIN_LENGTH}
                  autoComplete="new-password"
                  dir="ltr"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="input-v2 px-3 py-2 text-sm w-full"
                />
                <p className="text-xs text-text-secondary">{tSettings("passwordPolicyHelp", { min: PASSWORD_MIN_LENGTH })}</p>
              </div>
              <div className="space-y-1">
                <label htmlFor="reset-confirm" className="text-label-v2">{t("resetConfirmLabel")}</label>
                <input
                  id="reset-confirm"
                  type="password"
                  required
                  minLength={PASSWORD_MIN_LENGTH}
                  autoComplete="new-password"
                  dir="ltr"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  className="input-v2 px-3 py-2 text-sm w-full"
                />
              </div>
              <button type="submit" disabled={busy} className="btn-primary-v2 px-4 py-2 text-sm w-full disabled:opacity-50">
                {busy ? t("resetWorking") : t("resetSubmit")}
              </button>
            </form>
          )
        ) : requested ? (
          <div className="space-y-3">
            <div className="rounded-md bg-green-50 text-green-700 text-sm px-3 py-2" role="status">{t("resetRequested")}</div>
            <Link href="/login" className="btn-outline-v2 px-4 py-2 text-sm inline-block">{t("backToLogin")}</Link>
          </div>
        ) : (
          <form onSubmit={requestReset} className="space-y-4">
            <div className="space-y-1">
              <label htmlFor="reset-email" className="text-label-v2">{t("resetEmailLabel")}</label>
              <input
                id="reset-email"
                type="email"
                required
                autoComplete="email"
                dir="ltr"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="input-v2 px-3 py-2 text-sm w-full"
              />
            </div>
            <button type="submit" disabled={busy} className="btn-primary-v2 px-4 py-2 text-sm w-full disabled:opacity-50">
              {busy ? t("resetWorking") : t("resetRequestButton")}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense>
      <ResetPasswordContent />
    </Suspense>
  );
}
