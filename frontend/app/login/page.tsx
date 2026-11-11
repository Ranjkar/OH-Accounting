"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/auth-context";
import { ApiError } from "@/lib/api";
import LanguageSelector from "@/components/glass/LanguageSelector";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const t = useTranslations("auth");
  const tSettings = useTranslations("settings");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [mfaRequired, setMfaRequired] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const result = await login(email, password, mfaRequired ? mfaCode : undefined);
      if (result.mfaRequired) {
        setMfaRequired(true);
      } else {
        router.push("/");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("invalidCredentials"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-4 p-4 min-h-screen app-shell-v2">
      <form onSubmit={handleSubmit} className="glass-panel p-8 w-full max-w-sm space-y-5">
        <div className="flex flex-wrap items-center gap-3">
          <div className="w-10 h-10 rounded-xl hero-gradient-v2 flex items-center justify-center text-base font-bold text-white flex-shrink-0">O</div>
          <div>
            <h1 className="text-lg font-semibold text-text-primary">OnHolland Accounting</h1>
            <p className="text-sm text-text-secondary">{t("signInSubtitle")}</p>
          </div>
        </div>

        {error && (
          <div className="rounded-lg bg-red-500/10 border border-red-300/50 text-red-700 text-sm px-3 py-2" role="alert">
            {error}
          </div>
        )}

        <div className="space-y-1.5">
          <label htmlFor="login-email" className="text-sm font-medium text-text-primary">
            {t("emailLabel")}
          </label>
          <input
            id="login-email"
            type="email"
            required
            autoComplete="username"
            dir="ltr"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full input-v2 px-3 py-2 text-sm"
          />
        </div>
        <div className="space-y-1.5">
          <label htmlFor="login-password" className="text-sm font-medium text-text-primary">
            {t("passwordLabel")}
          </label>
          <input
            id="login-password"
            type="password"
            required
            disabled={mfaRequired}
            autoComplete="current-password"
            dir="ltr"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full input-v2 px-3 py-2 text-sm disabled:opacity-60"
          />
          <div className="flex justify-end">
            <Link href="/reset-password" className="text-xs text-navy hover:underline">
              {t("forgotPassword")}
            </Link>
          </div>
        </div>

        {mfaRequired && (
          <div className="space-y-1.5">
            <label htmlFor="login-mfa-code" className="text-sm font-medium text-text-primary">
              {t("mfaCodeLabel")}
            </label>
            <input
              id="login-mfa-code"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              required
              autoFocus
              dir="ltr"
              value={mfaCode}
              onChange={(e) => setMfaCode(e.target.value)}
              placeholder={tSettings("mfaDigitCode")}
              className="w-full input-v2 px-3 py-2 text-sm"
            />
            <p className="text-xs text-text-secondary">{t("mfaCodeHint")}</p>
          </div>
        )}

        <button type="submit" disabled={submitting} className="btn-primary-v2 w-full py-2 text-sm disabled:opacity-50">
          {submitting ? t("signingIn") : mfaRequired ? t("verifyCode") : t("signInButton")}
        </button>
      </form>
      <LanguageSelector />
    </div>
  );
}
