"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import GlassCard from "@/components/glass/GlassCard";
import GlassButton from "@/components/glass/GlassButton";
import { GlassErrorState } from "@/components/glass/GlassLoadingState";
import { useAuth } from "@/lib/auth-context";
import { api, ApiError, CompanyAccess } from "@/lib/api";

function AcceptInvitationContent() {
  const t = useTranslations("companyInvitations.accept");
  const { token, user } = useAuth();
  const searchParams = useSearchParams();
  const tokenParam = searchParams.get("token") ?? "";
  const [result, setResult] = useState<CompanyAccess | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleAccept() {
    if (!token || !tokenParam) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await api.acceptCompanyInvitation(token, tokenParam));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("failed"));
    } finally {
      setBusy(false);
    }
  }

  const email = user?.email ?? result?.email ?? "";

  return (
    <div className="max-w-lg mx-auto space-y-5">
      <GlassCard className="space-y-4">
        <h1 className="text-lg font-semibold text-text-primary">{t("title")}</h1>
        {!tokenParam && <p className="text-sm text-text-secondary">{t("noToken")}</p>}
        {error && <GlassErrorState message={error} />}
        {result ? (
          <p className="text-sm text-green-700">
            {t.rich("accessGranted", { email, e: (chunks) => <span dir="ltr">{chunks}</span> })}
          </p>
        ) : (
          tokenParam && (
            <>
              <p className="text-sm text-text-secondary">
                {t.rich("invitedBody", { email, e: (chunks) => <span dir="ltr">{chunks}</span> })}
              </p>
              <GlassButton onClick={handleAccept} loading={busy}>
                {t("acceptButton")}
              </GlassButton>
            </>
          )
        )}
      </GlassCard>
    </div>
  );
}

export default function AcceptInvitationPage() {
  return (
    <AuthGuard>
      <Shell>
        <Suspense>
          <AcceptInvitationContent />
        </Suspense>
      </Shell>
    </AuthGuard>
  );
}
