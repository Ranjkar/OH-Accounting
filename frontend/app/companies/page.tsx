"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, Company, VatFrequency } from "@/lib/api";

const FREQUENCY_KEY: Record<VatFrequency, string> = { monthly: "frequencyMonthly", quarterly: "frequencyQuarterly", annual: "frequencyAnnual" };

function CompaniesContent() {
  const t = useTranslations("companies");
  const tCommon = useTranslations("common");
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
      setError(err instanceof Error ? err.message : t("createFailed"));
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-text-primary">{t("title")}</h1>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="btn-primary-v2 px-4 py-2 text-sm"
        >
          {showForm ? tCommon("cancel") : t("newCompany")}
        </button>
      </div>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      {showForm && (
        <form onSubmit={handleCreate} className="card-v2 p-5 space-y-4 max-w-lg">
          <div className="space-y-1">
            <label className="text-sm font-medium text-text-primary">{t("companyNameLabel")}</label>
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full input-v2 px-3 py-2 text-sm"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <label className="text-sm font-medium text-text-primary">{t("kvkNumberLabel")}</label>
              <input
                value={kvk}
                onChange={(e) => setKvk(e.target.value)}
                className="w-full input-v2 px-3 py-2 text-sm"
                dir="ltr"
              />
            </div>
            <div className="space-y-1">
              <label className="text-sm font-medium text-text-primary">{t("vatNumberLabel")}</label>
              <input
                value={vat}
                onChange={(e) => setVat(e.target.value)}
                className="w-full input-v2 px-3 py-2 text-sm"
                dir="ltr"
              />
            </div>
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium text-text-primary">{t("vatFrequencyLabel")}</label>
            <select
              value={frequency}
              onChange={(e) => setFrequency(e.target.value as VatFrequency)}
              className="w-full input-v2 px-3 py-2 text-sm"
            >
              <option value="monthly">{t("frequencyMonthly")}</option>
              <option value="quarterly">{t("frequencyQuarterly")}</option>
              <option value="annual">{t("frequencyAnnual")}</option>
            </select>
          </div>
          <button
            type="submit"
            className="btn-primary-v2 px-4 py-2 text-sm"
          >
            {t("createCompany")}
          </button>
        </form>
      )}

      <div className="card-v2 divide-y divide-border">
        {companies.length === 0 ? (
          <p className="px-5 py-4 text-sm text-text-secondary">{t("noCompaniesYet")}</p>
        ) : (
          companies.map((c) => (
            <Link
              key={c.id}
              href={`/companies/${c.id}`}
              className="flex items-center justify-between px-5 py-3 hover:bg-muted"
            >
              <div>
                <p className="font-medium text-navy">{c.name}</p>
                <p className="text-sm text-text-secondary">
                  {c.kvk_number ? <span dir="ltr">{t("kvkWithNumber", { number: c.kvk_number })}</span> : t("noKvkNumber")} ·{" "}
                  {t(FREQUENCY_KEY[c.vat_frequency] as never)}
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
