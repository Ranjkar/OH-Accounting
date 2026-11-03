"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import GlassCard from "@/components/glass/GlassCard";
import GlassButton from "@/components/glass/GlassButton";
import { GlassErrorState } from "@/components/glass/GlassLoadingState";
import { useAuth } from "@/lib/auth-context";
import { api, ApiError, CompanyAccess } from "@/lib/api";

function AcceptInvitationContent() {
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
      setError(e instanceof ApiError ? e.message : "Failed to accept invitation");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-lg mx-auto space-y-5">
      <GlassCard className="space-y-4">
        <h1 className="text-lg font-semibold text-text-primary">Company access invitation</h1>
        {!tokenParam && <p className="text-sm text-text-secondary">No invitation token was provided in this link.</p>}
        {error && <GlassErrorState message={error} />}
        {result ? (
          <p className="text-sm text-green-700">
            Access granted -- signed in as {user?.email ?? result.email} now has access to this company. You can find it in your company list.
          </p>
        ) : (
          tokenParam && (
            <>
              <p className="text-sm text-text-secondary">
                You have been invited to access a company&apos;s books. Accept below with the account you are currently signed in as
                ({user?.email}) -- the invitation must have been addressed to this exact email.
              </p>
              <GlassButton onClick={handleAccept} loading={busy}>
                Accept invitation
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
