"use client";

import { FormEvent, Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

function AcceptUserInvitationContent() {
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
      setError("Passwords do not match");
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
      setError(e instanceof ApiError ? e.message : "Failed to accept this invitation");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4">
      <div className="card-v2 p-6 w-full max-w-sm space-y-4">
        <div>
          <h1 className="text-lg font-semibold text-text-primary">Join OnHolland</h1>
          <p className="text-sm text-text-secondary mt-1">You&apos;ve been invited to join an organisation. Set up your account below.</p>
        </div>

        {!token && <p className="text-sm text-error">No invitation token was provided in this link.</p>}
        {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

        {token && !done && (
          <form onSubmit={handleSubmit} className="space-y-3">
            <div className="space-y-1">
              <label htmlFor="full-name" className="text-xs font-medium text-text-secondary">Full name</label>
              <input id="full-name" required value={fullName} onChange={(e) => setFullName(e.target.value)} className="input-v2 w-full px-3 py-2 text-sm" />
            </div>
            <div className="space-y-1">
              <label htmlFor="password" className="text-xs font-medium text-text-secondary">Password</label>
              <input id="password" type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} className="input-v2 w-full px-3 py-2 text-sm" />
            </div>
            <div className="space-y-1">
              <label htmlFor="confirm-password" className="text-xs font-medium text-text-secondary">Confirm password</label>
              <input id="confirm-password" type="password" required minLength={8} value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} className="input-v2 w-full px-3 py-2 text-sm" />
            </div>
            <button type="submit" disabled={busy} className="btn-primary-v2 w-full px-4 py-2 text-sm disabled:opacity-50">
              {busy ? "Creating account…" : "Create account & sign in"}
            </button>
          </form>
        )}

        {done && <p className="text-sm text-green-700">Account created -- signing you in…</p>}

        <p className="text-xs text-text-secondary text-center">
          Already have an account? <Link href="/login" className="text-navy hover:underline">Sign in</Link>
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
