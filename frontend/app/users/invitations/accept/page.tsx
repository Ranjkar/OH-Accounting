"use client";

import { FormEvent, Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

function AcceptUserInvitationContent() {
  const t = useTranslations("users.acceptInvitation");
  const searchParams = useSearchParams();
  const router = useRouter();
  const { login } = useAuth();
  const token = searchParams.get("token") ?? "";

  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    if (password !== confirmPassword) {
      setError(t("passwordMismatch"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const created = await api.acceptUserInvitation(token, fullName, password);
      setDone(true);
      // Sign the new account straight in, matching the UX of any other
      // signup flow -- no need to make them type their new password twice.
      await login(created.email, password);
      router.push("/");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("failedToAcceptInvitation"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4">
      <div className="card-v2 p-6 w-full max-w-sm space-y-4">
        <div>
          <h1 className="text-lg font-semibold text-text-primary">{t("title")}</h1>
          <p className="text-sm text-text-secondary mt-1">{t("subtitle")}</p>
        </div>

        {!token && <p className="text-sm text-error">{t("noToken")}</p>}
        {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

        {token && !done && (
          <form onSubmit={handleSubmit} className="space-y-3">
            <div className="space-y-1">
              <label htmlFor="full-name" className="text-xs font-medium text-text-secondary">{t("fullNameLabel")}</label>
              <input id="full-name" required value={fullName} onChange={(e) => setFullName(e.target.value)} className="input-v2 w-full px-3 py-2 text-sm" />
            </div>
            <div className="space-y-1">
              <label htmlFor="password" className="text-xs font-medium text-text-secondary">{t("passwordLabel")}</label>
              <input id="password" type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} className="input-v2 w-full px-3 py-2 text-sm" />
            </div>
            <div className="space-y-1">
              <label htmlFor="confirm-password" className="text-xs font-medium text-text-secondary">{t("confirmPasswordLabel")}</label>
              <input id="confirm-password" type="password" required minLength={8} value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} className="input-v2 w-full px-3 py-2 text-sm" />
            </div>
            <button type="submit" disabled={busy} className="btn-primary-v2 w-full px-4 py-2 text-sm disabled:opacity-50">
              {busy ? t("creatingAccount") : t("createAccountButton")}
            </button>
          </form>
        )}

        {done && <p className="text-sm text-green-700">{t("accountCreatedSigningIn")}</p>}

        <p className="text-xs text-text-secondary text-center">
          {t("alreadyHaveAccount")} <Link href="/login" className="text-navy hover:underline">{t("signIn")}</Link>
        </p>
      </div>
    </div>
  );
}

export default function AcceptUserInvitationPage() {
  return (
    <Suspense>
      <AcceptUserInvitationContent />
    </Suspense>
  );
}
