"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, Company, SetupDraft, VatFrequency } from "@/lib/api";
import { SETUP_STEPS } from "@/lib/company-setup";
import { formatRelativeDate } from "@/lib/format";

const FREQUENCY_KEY: Record<VatFrequency, string> = { monthly: "frequencyMonthly", quarterly: "frequencyQuarterly", annual: "frequencyAnnual" };

function CompaniesContent() {
  const t = useTranslations("companies");
  const tSetup = useTranslations("companySetup");
  const locale = useLocale();
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [drafts, setDrafts] = useState<SetupDraft[]>([]);
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    if (!token) return;
    api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
    // Unfinished wizard setups, so one started on a phone can be resumed here.
    // Admin-only endpoint: for anyone else an empty list is the right answer,
    // not an error banner on an otherwise healthy page.
    api.listSetupDrafts(token).then(setDrafts).catch(() => setDrafts([]));
  }

  useEffect(refresh, [token]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold text-text-primary">{t("title")}</h1>
        <Link href="/companies/new" className="btn-primary-v2 px-4 py-2 text-sm">
          {t("newCompany")}
        </Link>
      </div>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      {drafts.length > 0 && (
        <div className="card-v2 overflow-hidden">
          <div className="px-5 py-3 border-b border-border-subtle">
            <h2 className="text-sm font-medium text-text-primary">{tSetup("drafts.title")}</h2>
          </div>
          <div className="divide-y divide-border">
            {drafts.map((d) => (
              <Link
                key={d.id}
                href={`/companies/new?draft=${d.id}`}
                className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-5 py-3 hover:bg-muted"
              >
                <div className="min-w-0">
                  <p className="font-medium text-navy truncate">{d.data?.name?.trim() || tSetup("drafts.unnamed")}</p>
                  <p className="text-xs text-text-secondary">
                    {tSetup("stepOf", { current: Math.min((d.current_step ?? 0) + 1, SETUP_STEPS.length), total: SETUP_STEPS.length })}
                    {" · "}
                    {tSetup("drafts.lastEdited", { date: formatRelativeDate(d.updated_at, locale) })}
                  </p>
                </div>
                <span className="text-sm font-medium text-navy whitespace-nowrap">
                  {tSetup("drafts.resume")} <span className="icon-directional" style={{ display: "inline-block" }}>→</span>
                </span>
              </Link>
            ))}
          </div>
        </div>
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
