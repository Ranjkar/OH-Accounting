"use client";

import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { api, Company } from "./api";
import { useAuth } from "./auth-context";

const STORAGE_KEY = "selected-company-id";

interface CompanyState {
  companies: Company[];
  selectedCompanyId: number | null;
  selectedCompany: Company | null;
  setSelectedCompanyId: (id: number | null) => void;
  loading: boolean;
}

const CompanyContext = createContext<CompanyState | null>(null);

export function CompanyProvider({ children }: { children: ReactNode }) {
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [selectedCompanyId, setSelectedCompanyIdState] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) {
      // Signed out -- nothing selectable until the next sign-in.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setCompanies([]);
      setLoading(false);
      return;
    }
    api
      .listCompanies(token)
      .then((list) => {
        setCompanies(list);
        setSelectedCompanyIdState((current) => {
          if (current && list.some((c) => c.id === current)) return current;
          let stored: number | null = null;
          try {
            const raw = localStorage.getItem(STORAGE_KEY);
            stored = raw ? Number(raw) : null;
          } catch {
            stored = null;
          }
          if (stored && list.some((c) => c.id === stored)) return stored;
          return list[0]?.id ?? null;
        });
      })
      .finally(() => setLoading(false));
  }, [token]);

  function setSelectedCompanyId(id: number | null) {
    setSelectedCompanyIdState(id);
    try {
      if (id) localStorage.setItem(STORAGE_KEY, String(id));
      else localStorage.removeItem(STORAGE_KEY);
    } catch {
      // Private-browsing/blocked storage -- selection still works for this session.
    }
  }

  const selectedCompany = companies.find((c) => c.id === selectedCompanyId) ?? null;

  return (
    <CompanyContext.Provider value={{ companies, selectedCompanyId, selectedCompany, setSelectedCompanyId, loading }}>
      {children}
    </CompanyContext.Provider>
  );
}

export function useCompany() {
  const ctx = useContext(CompanyContext);
  if (!ctx) throw new Error("useCompany must be used within CompanyProvider");
  return ctx;
}
