"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, Company } from "@/lib/api";

function SettingsContent() {
  const { token, user } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-navy">Settings</h1>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="bg-white rounded-lg border border-slate-200 p-5">
        <h2 className="text-sm font-medium text-navy mb-3">Account</h2>
        <dl className="text-sm space-y-2">
          <div className="flex justify-between max-w-sm">
            <dt className="text-slate-500">Name</dt>
            <dd className="text-navy font-medium">{user?.full_name}</dd>
          </div>
          <div className="flex justify-between max-w-sm">
            <dt className="text-slate-500">Email</dt>
            <dd className="text-navy font-medium">{user?.email}</dd>
          </div>
          <div className="flex justify-between max-w-sm">
            <dt className="text-slate-500">Role</dt>
            <dd className="text-navy font-medium capitalize">{user?.role}</dd>
          </div>
        </dl>
      </div>

      <div className="bg-white rounded-lg border border-slate-200">
        <div className="px-5 py-3 border-b border-slate-200">
          <h2 className="text-sm font-medium text-navy">Company VAT settings</h2>
        </div>
        <div className="divide-y divide-slate-100">
          {companies.map((c) => (
            <Link key={c.id} href={`/companies/${c.id}`} className="flex items-center justify-between px-5 py-3 hover:bg-slate-50">
              <div>
                <p className="font-medium text-navy text-sm">{c.name}</p>
                <p className="text-xs text-slate-500">
                  {c.vat_accounting_basis.replace("_", "-")} accounting · {c.vat_frequency} filing
                  {c.input_vat_pro_rata_percentage ? ` · ${c.input_vat_pro_rata_percentage}% pro-rata` : ""}
                </p>
              </div>
              <span className="text-xs text-navy">Edit →</span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <AuthGuard>
      <Shell>
        <SettingsContent />
      </Shell>
    </AuthGuard>
  );
}
