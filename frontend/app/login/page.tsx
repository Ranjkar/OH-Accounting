"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { ApiError } from "@/lib/api";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      router.push("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex-1 flex items-center justify-center p-4 min-h-screen app-shell-v2">
      <form onSubmit={handleSubmit} className="glass-panel p-8 w-full max-w-sm space-y-5">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl hero-gradient-v2 flex items-center justify-center text-base font-bold text-white flex-shrink-0">O</div>
          <div>
            <h1 className="text-lg font-semibold text-text-primary">OnHolland Accounting</h1>
            <p className="text-sm text-text-secondary">Sign in to your account</p>
          </div>
        </div>

        {error && (
          <div className="rounded-lg bg-red-500/10 border border-red-300/50 text-red-700 text-sm px-3 py-2" role="alert">
            {error}
          </div>
        )}

        <div className="space-y-1.5">
          <label htmlFor="login-email" className="text-sm font-medium text-text-primary">
            Email
          </label>
          <input
            id="login-email"
            type="email"
            required
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full input-v2 px-3 py-2 text-sm"
          />
        </div>
        <div className="space-y-1.5">
          <label htmlFor="login-password" className="text-sm font-medium text-text-primary">
            Password
          </label>
          <input
            id="login-password"
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full input-v2 px-3 py-2 text-sm"
          />
        </div>

        <button type="submit" disabled={submitting} className="btn-primary-v2 w-full py-2 text-sm disabled:opacity-50">
          {submitting ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
