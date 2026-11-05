"use client";

import { FormEvent, Suspense, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import StatusBadge from "@/components/StatusBadge";
import { useAuth } from "@/lib/auth-context";
import { api, ApiError, Company, CompanyAccess, CompanyInvitation, FinancialYear, VatAccountingBasis } from "@/lib/api";

function TeamAccessSection({ companyId }: { companyId: number }) {
  const t = useTranslations("companies.teamAccess");
  const tRoles = useTranslations("users.roles");
  const { token } = useAuth();
  const [access, setAccess] = useState<CompanyAccess[]>([]);
  const [invitations, setInvitations] = useState<CompanyInvitation[]>([]);
  const [invitedEmail, setInvitedEmail] = useState("");
  const [lastToken, setLastToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    if (!token) return;
    api.listCompanyAccess(token, companyId).then(setAccess).catch((e) => setError(e.message));
    api.listCompanyInvitations(token, companyId).then(setInvitations).catch((e) => setError(e.message));
  }

  useEffect(refresh, [token, companyId]);

  async function handleInvite(e: FormEvent) {
    e.preventDefault();
    if (!token || !invitedEmail.trim()) return;
    setError(null);
    try {
      const { raw_token } = await api.createCompanyInvitation(token, companyId, invitedEmail);
      setLastToken(raw_token);
      setInvitedEmail("");
      refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("createInvitationFailed"));
    }
  }

  async function handleRevokeAccess(userId: number) {
    if (!token) return;
    try {
      await api.revokeCompanyAccess(token, companyId, userId);
      refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("revokeAccessFailed"));
    }
  }

  async function handleRevokeInvitation(invitationId: number) {
    if (!token) return;
    try {
      await api.revokeCompanyInvitation(token, companyId, invitationId);
      refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("revokeInvitationFailed"));
    }
  }

  const pendingInvitations = invitations.filter((i) => i.status === "PENDING");

  return (
    <div className="card-v2 p-5 space-y-4">
      <h2 className="text-sm font-medium text-text-primary">{t("title")}</h2>
      <p className="text-xs text-text-secondary">{t("intro")}</p>
      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <form onSubmit={handleInvite} className="flex items-end gap-3">
        <div className="space-y-1 flex-1 max-w-sm">
          <label htmlFor="invite-email" className="text-xs font-medium text-text-secondary">{t("inviteByEmail")}</label>
          <input
            id="invite-email"
            type="email"
            required
            value={invitedEmail}
            onChange={(e) => setInvitedEmail(e.target.value)}
            placeholder="accountant@firm.nl"
            className="w-full input-v2 px-3 py-2 text-sm"
            dir="ltr"
          />
        </div>
        <button type="submit" className="btn-primary-v2 px-4 py-2 text-sm">{t("sendInvitation")}</button>
      </form>

      {lastToken && (
        <div className="rounded-md bg-amber-50 border border-amber-200 text-xs px-3 py-2 space-y-1">
          <p className="font-medium text-pending">{t("invitationCreated")}</p>
          <p className="font-mono break-all" dir="ltr">{`${typeof window !== "undefined" ? window.location.origin : ""}/invitations/accept?token=${lastToken}`}</p>
        </div>
      )}

      <div>
        <h3 className="text-xs font-medium text-text-secondary mb-2">{t("peopleWithAccess")}</h3>
        <ul className="divide-y divide-border text-sm">
          {access.map((a) => (
            <li key={a.user_id} className="flex items-center justify-between py-2">
              <span>{a.full_name} <span className="text-text-secondary">(<span dir="ltr">{a.email}</span>, {tRoles.has(a.role as never) ? tRoles(a.role as never) : a.role})</span></span>
              <button onClick={() => handleRevokeAccess(a.user_id)} className="text-xs text-error hover:underline">{t("revoke")}</button>
            </li>
          ))}
        </ul>
      </div>

      {pendingInvitations.length > 0 && (
        <div>
          <h3 className="text-xs font-medium text-text-secondary mb-2">{t("pendingInvitations")}</h3>
          <ul className="divide-y divide-border text-sm">
            {pendingInvitations.map((i) => (
              <li key={i.id} className="flex items-center justify-between py-2">
                <span><span dir="ltr">{i.invited_email}</span> <span className="text-text-secondary">({tRoles.has(i.intended_role as never) ? tRoles(i.intended_role as never) : i.intended_role}, {t("expiresOn", { date: new Date(i.expires_at).toLocaleDateString() })})</span></span>
                <button onClick={() => handleRevokeInvitation(i.id)} className="text-xs text-error hover:underline">{t("revoke")}</button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

const FREQUENCY_KEY: Record<string, string> = { monthly: "frequencyMonthly", quarterly: "frequencyQuarterly", annual: "frequencyAnnual" };

function CompanyDetailContent({ companyId }: { companyId: number }) {
  const t = useTranslations("companies.detail");
  const tCompanies = useTranslations("companies");
  const tCommon = useTranslations("common");
  const { token, user } = useAuth();
  const canEdit = user?.role === "admin";
  const canManageAccess = user?.role === "admin" || user?.role === "customer";
  const [company, setCompany] = useState<Company | null>(null);
  const [years, setYears] = useState<FinancialYear[]>([]);
  const [newYear, setNewYear] = useState(new Date().getFullYear());
  const [error, setError] = useState<string | null>(null);
  const [proRata, setProRata] = useState("");

  function refresh() {
    if (!token) return;
    api.getCompany(token, companyId).then((c) => {
      setCompany(c);
      setProRata(c.input_vat_pro_rata_percentage ?? "");
    }).catch((e) => setError(e.message));
    api.listFinancialYears(token, companyId).then(setYears).catch((e) => setError(e.message));
  }

  useEffect(refresh, [token, companyId]);

  async function handleAddYear(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setError(null);
    try {
      await api.createFinancialYear(token, companyId, newYear);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("createYearFailed"));
    }
  }

  async function handleBasisChange(basis: VatAccountingBasis) {
    if (!token) return;
    try {
      await api.updateCompany(token, companyId, { vat_accounting_basis: basis });
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("updateBasisFailed"));
    }
  }

  async function handleProRataSave() {
    if (!token) return;
    try {
      await api.updateCompany(token, companyId, {
        input_vat_pro_rata_percentage: proRata === "" ? null : Number(proRata),
      });
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("updateProRataFailed"));
    }
  }

  if (!company) return <p className="text-text-secondary">{tCommon("loading")}</p>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary">{company.name}</h1>
          <p className="text-sm text-text-secondary">
            {company.kvk_number ? <span dir="ltr">{t("kvkWithNumber", { number: company.kvk_number })}</span> : t("noKvkNumber")} ·{" "}
            {company.vat_number ? <span dir="ltr">{company.vat_number}</span> : t("noVatNumber")} · {t("filingFrequency", { frequency: tCompanies(FREQUENCY_KEY[company.vat_frequency] as never) })}
          </p>
        </div>
        <a
          href={`/companies/${companyId}/workspace`}
          className="btn-primary-v2 px-4 py-2 text-sm"
        >
          {t("openWorkspace")}
        </a>
      </div>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="card-v2 p-4 flex items-end gap-6">
        <div className="space-y-1">
          <label className="text-xs font-medium text-text-secondary">{t("vatAccountingBasisLabel")}</label>
          <select
            disabled={!canEdit}
            value={company.vat_accounting_basis}
            onChange={(e) => handleBasisChange(e.target.value as VatAccountingBasis)}
            className="input-v2 px-2.5 py-1.5 text-sm disabled:bg-muted"
          >
            <option value="invoice_based">{t("invoiceBased")}</option>
            <option value="cash_based">{t("cashBased")}</option>
          </select>
        </div>
        <div className="space-y-1">
          <label className="text-xs font-medium text-text-secondary">{t("proRataLabel")}</label>
          <div className="flex gap-2">
            <input
              disabled={!canEdit}
              value={proRata}
              onChange={(e) => setProRata(e.target.value)}
              placeholder={t("proRataPlaceholder")}
              className="w-24 input-v2 px-2.5 py-1.5 text-sm disabled:bg-muted"
            />
            {canEdit && (
              <button
                onClick={handleProRataSave}
                className="input-v2 px-3 py-1.5 text-sm hover:bg-muted transition-colors"
              >
                {tCommon("save")}
              </button>
            )}
          </div>
        </div>
      </div>

      {canManageAccess && <TeamAccessSection companyId={companyId} />}

      <form onSubmit={handleAddYear} className="flex items-end gap-3">
        <div className="space-y-1">
          <label className="text-sm font-medium text-text-primary">{t("addFinancialYear")}</label>
          <input
            type="number"
            value={newYear}
            onChange={(e) => setNewYear(Number(e.target.value))}
            className="w-32 input-v2 px-3 py-2 text-sm"
          />
        </div>
        <button
          type="submit"
          className="btn-primary-v2 px-4 py-2 text-sm"
        >
          {t("generateVatPeriods")}
        </button>
      </form>

      <div className="space-y-6">
        {years.map((fy) => (
          <div key={fy.id} className="card-v2">
            <div className="px-5 py-4 border-b border-border-subtle">
              <h2 className="font-medium text-text-primary">{t("financialYearHeading", { year: fy.year })}</h2>
            </div>
            <div className="overflow-x-auto">
            <table className="table-v3">
              <thead>
                <tr>
                  <th>{t("colPeriod")}</th>
                  <th>{t("colStart")}</th>
                  <th>{t("colEnd")}</th>
                  <th>{t("colFilingDeadline")}</th>
                  <th>{t("colPaymentDeadline")}</th>
                  <th>{t("colStatus")}</th>
                </tr>
              </thead>
              <tbody>
                {fy.vat_periods.map((p) => (
                  <tr key={p.id}>
                    <td className="text-text-primary">{p.label}</td>
                    <td className="text-text-secondary">{p.start_date}</td>
                    <td className="text-text-secondary">{p.end_date}</td>
                    <td className="text-text-secondary">{p.filing_deadline}</td>
                    <td className="text-text-secondary">{p.payment_deadline}</td>
                    <td>
                      <StatusBadge status={p.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function CompanyDetailRoute() {
  const params = useParams<{ id: string }>();
  const companyId = Number(params.id);

  return (
    <AuthGuard>
      <Shell>
        <CompanyDetailContent companyId={companyId} />
      </Shell>
    </AuthGuard>
  );
}

export default function CompanyDetailPage() {
  return (
    <Suspense>
      <CompanyDetailRoute />
    </Suspense>
  );
}
