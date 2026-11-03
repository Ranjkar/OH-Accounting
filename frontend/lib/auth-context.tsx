"use client";

import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { useRouter } from "next/navigation";
import { api, User } from "./api";

interface AuthState {
  token: string | null;
  user: User | null;
  loading: boolean;
  login: (email: string, password: string, mfaCode?: string) => Promise<{ mfaRequired: boolean }>;
  logout: () => void;
  refreshUser: () => Promise<void>;
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

  function logout() {
    localStorage.removeItem("token");
    setToken(null);
    setUser(null);
    router.push("/login");
  }

  async function refreshUser() {
    if (!token) return;
    setUser(await api.me(token));
  }

  return (
    <AuthContext.Provider value={{ token, user, loading, login, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
