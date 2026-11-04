"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, Company, VatFrequency } from "@/lib/api";

function CompaniesContent() {
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [kvk, setKvk] = useState("");
  const [vat, setVat] = useState("");
  const [frequency, setFrequency] = useState<VatFrequency>("quarterly");
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }

  useEffect(refresh, [token]);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setError(null);
    try {
      await api.createCompany(token, {
        name,
        kvk_number: kvk || null,
        vat_number: vat || null,
        address: null,
        vat_frequency: frequency,
      });
      setName("");
      setKvk("");
      setVat("");
      setShowForm(false);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create company");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-text-primary">Companies</h1>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="btn-primary-v2 px-4 py-2 text-sm"
        >
          {showForm ? "Cancel" : "New company"}
        </button>
      </div>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      {showForm && (
        <form onSubmit={handleCreate} className="card-v2 p-5 space-y-4 max-w-lg">
          <div className="space-y-1">
            <label className="text-sm font-medium text-slate-700">Company name</label>
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full input-v2 px-3 py-2 text-sm"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <label className="text-sm font-medium text-slate-700">KVK number</label>
              <input
                value={kvk}
                onChange={(e) => setKvk(e.target.value)}
                className="w-full input-v2 px-3 py-2 text-sm"
              />
            </div>
            <div className="space-y-1">
              <label className="text-sm font-medium text-slate-700">VAT number</label>
              <input
                value={vat}
                onChange={(e) => setVat(e.target.value)}
                className="w-full input-v2 px-3 py-2 text-sm"
              />
            </div>
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium text-slate-700">VAT filing frequency</label>
            <select
              value={frequency}
              onChange={(e) => setFrequency(e.target.value as VatFrequency)}
              className="w-full input-v2 px-3 py-2 text-sm"
            >
              <option value="monthly">Monthly</option>
              <option value="quarterly">Quarterly</option>
              <option value="annual">Annual</option>
            </select>
          </div>
          <button
            type="submit"
            className="btn-primary-v2 px-4 py-2 text-sm"
          >
            Create company
          </button>
        </form>
      )}

      <div className="card-v2 divide-y divide-slate-100">
        {companies.length === 0 ? (
          <p className="px-5 py-4 text-sm text-text-secondary">No companies yet.</p>
        ) : (
          companies.map((c) => (
            <Link
              key={c.id}
              href={`/companies/${c.id}`}
              className="flex items-center justify-between px-5 py-3 hover:bg-slate-50"
            >
              <div>
                <p className="font-medium text-navy">{c.name}</p>
                <p className="text-sm text-text-secondary">
                  {c.kvk_number ? `KVK ${c.kvk_number}` : "No KVK number"} ·{" "}
                  {c.vat_frequency}
                </p>
              </div>
            </Link>
          ))
        )}
      </div>
    </div>
  );
}

export default function CompaniesPage() {
  return (
    <AuthGuard>
      <Shell>
        <CompaniesContent />
      </Shell>
    </AuthGuard>
  );
}
