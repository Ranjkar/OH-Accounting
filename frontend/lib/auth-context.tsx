"use client";

import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { useRouter } from "next/navigation";
import { api, User } from "./api";

interface AuthState {
  token: string | null;
  user: User | null;
  loading: boolean;
  login: (email: string, password: string, mfaCode?: string) => Promise<{ mfaRequired: boolean }>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  /** Swap in a freshly issued token. Password changes, "sign out everywhere
   * else" and email confirmation bump the server-side token_version, which
   * invalidates the token already in hand -- keeping the old one would log
   * the user out of the very device they just acted on. */
  rotateToken: (newToken: string) => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    const stored = localStorage.getItem("token");
    const restore = stored
      ? api
          .me(stored)
          .then((u) => {
            setToken(stored);
            setUser(u);
          })
          .catch(() => localStorage.removeItem("token"))
      : Promise.resolve();
    restore.finally(() => setLoading(false));
  }, []);

  async function login(email: string, password: string, mfaCode?: string) {
    const { access_token, mfa_required } = await api.login(email, password, mfaCode);
    if (!access_token) {
      return { mfaRequired: mfa_required };
    }
    const u = await api.me(access_token);
    localStorage.setItem("token", access_token);
    setToken(access_token);
    setUser(u);
    return { mfaRequired: false };
  }

  async function logout() {
    // Phase 17.3 (audit 6.13): revoke server-side, not just locally.
    // POST /auth/logout bumps the user's token_version, which makes the
    // backend reject every token ever issued for this account. Before this,
    // "Log out" only removed the token from localStorage -- so a JWT copied
    // beforehand (XSS, a shared device, browser history, an intercepting
    // proxy) stayed valid for its full 24-hour lifetime.
    //
    // Fall back to localStorage in case state has not hydrated yet, so a
    // logout pressed early still revokes the stored token.
    const current = token ?? localStorage.getItem("token");
    try {
      if (current) {
        await api.logout(current);
      }
    } catch {
      // Deliberately swallowed. The user asked to leave; a network failure
      // or an already-expired token (401) must not strand them on an
      // authenticated page. Local state is cleared below either way, and if
      // the revocation call never landed the token still expires on its own.
    } finally {
      localStorage.removeItem("token");
      setToken(null);
      setUser(null);
      router.push("/login");
    }
  }

  async function refreshUser() {
    if (!token) return;
    setUser(await api.me(token));
  }

  function rotateToken(newToken: string) {
    localStorage.setItem("token", newToken);
    setToken(newToken);
  }

  return (
    <AuthContext.Provider value={{ token, user, loading, login, logout, refreshUser, rotateToken }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
