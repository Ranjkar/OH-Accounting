"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { api, ApiError } from "@/lib/api";

/** The emailed verification link is the credential, so the confirmation runs
 * as soon as the page opens -- the visitor may not be signed in here. */
function VerifyEmailContent() {
  const t = useTranslations("auth");
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const [state, setState] = useState<"working" | "done" | "failed">(() => (token ? "working" : "failed"));
  const [error, setError] = useState<string | null>(null);
  // The token is single-use: a StrictMode double effect run would spend it
  // twice and report the second (failed) attempt to the user.
  const attempted = useRef(false);

  useEffect(() => {
    if (!token || attempted.current) return;
    attempted.current = true;
    api
      .confirmEmailChange(token)
      .then(() => setState("done"))
      .catch((e) => {
        setState("failed");
        setError(e instanceof ApiError ? e.message : t("verifyFailed"));
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4">
      <div className="card-v2 p-6 w-full max-w-sm space-y-4">
        <h1 className="text-lg font-semibold text-text-primary">{t("verifyTitle")}</h1>
        {state === "working" && <p className="text-sm text-text-secondary" role="status">{t("verifyWorking")}</p>}
        {state === "done" && (
          <div className="rounded-md bg-green-50 text-green-700 text-sm px-3 py-2" role="status">
            {t("verifySuccess")}
          </div>
        )}
        {state === "failed" && (
          <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2" role="alert">
            {error ?? (token ? t("verifyFailed") : t("verifyMissingToken"))}
          </div>
        )}
        {state !== "working" && (
          <Link href="/login" className="btn-primary-v2 px-4 py-2 text-sm inline-block">
            {t("backToLogin")}
          </Link>
        )}
      </div>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense>
      <VerifyEmailContent />
    </Suspense>
  );
}
