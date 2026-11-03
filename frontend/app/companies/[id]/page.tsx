"use client";

import { FormEvent, Suspense, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import StatusBadge from "@/components/StatusBadge";
import { useAuth } from "@/lib/auth-context";
import { api, ApiError, Company, CompanyAccess, CompanyInvitation, FinancialYear, VatAccountingBasis } from "@/lib/api";

function TeamAccessSection({ companyId }: { companyId: number }) {
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
      setError(e instanceof ApiError ? e.message : "Failed to create invitation");
    }
  }

  async function handleRevokeAccess(userId: number) {
    if (!token) return;
    try {
      await api.revokeCompanyAccess(token, companyId, userId);
      refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to revoke access");
    }
  }

  async function handleRevokeInvitation(invitationId: number) {
    if (!token) return;
    try {
      await api.revokeCompanyInvitation(token, companyId, invitationId);
      refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to revoke invitation");
    }
  }

  const pendingInvitations = invitations.filter((i) => i.status === "PENDING");

  return (
    <div className="card-v2 p-5 space-y-4">
      <h2 className="text-sm font-medium text-navy">Team access</h2>
      <p className="text-xs text-text-secondary">
        Invite an accountant or other team member to access this company. No email provider is configured, so the invitation
        link below must be shared with them yourself (e.g. by email or chat) -- it is never sent automatically.
      </p>
      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <form onSubmit={handleInvite} className="flex items-end gap-3">
        <div className="space-y-1 flex-1 max-w-sm">
          <label htmlFor="invite-email" className="text-xs font-medium text-text-secondary">Invite by email</label>
          <input
            id="invite-email"
            type="email"
            required
            value={invitedEmail}
            onChange={(e) => setInvitedEmail(e.target.value)}
            placeholder="accountant@firm.nl"
            className="w-full input-v2 px-3 py-2 text-sm"
          />
        </div>
        <button type="submit" className="btn-primary-v2 px-4 py-2 text-sm">Send invitation</button>
      </form>

      {lastToken && (
        <div className="rounded-md bg-amber-50 border border-amber-200 text-xs px-3 py-2 space-y-1">
          <p className="font-medium text-pending">Invitation created -- share this link with the invited person:</p>
          <p className="font-mono break-all">{`${typeof window !== "undefined" ? window.location.origin : ""}/invitations/accept?token=${lastToken}`}</p>
        </div>
      )}

      <div>
        <h3 className="text-xs font-medium text-text-secondary mb-2">People with access</h3>
        <ul className="divide-y divide-slate-100 text-sm">
          {access.map((a) => (
            <li key={a.user_id} className="flex items-center justify-between py-2">
              <span>{a.full_name} <span className="text-text-secondary">({a.email}, {a.role})</span></span>
              <button onClick={() => handleRevokeAccess(a.user_id)} className="text-xs text-error hover:underline">Revoke</button>
            </li>
          ))}
        </ul>
      </div>

      {pendingInvitations.length > 0 && (
        <div>
          <h3 className="text-xs font-medium text-text-secondary mb-2">Pending invitations</h3>
          <ul className="divide-y divide-slate-100 text-sm">
            {pendingInvitations.map((i) => (
              <li key={i.id} className="flex items-center justify-between py-2">
                <span>{i.invited_email} <span className="text-text-secondary">({i.intended_role}, expires {new Date(i.expires_at).toLocaleDateString()})</span></span>
                <button onClick={() => handleRevokeInvitation(i.id)} className="text-xs text-error hover:underline">Revoke</button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function CompanyDetailContent({ companyId }: { companyId: number }) {
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
      setError(err instanceof Error ? err.message : "Failed to create financial year");
    }
  }

  async function handleBasisChange(basis: VatAccountingBasis) {
    if (!token) return;
    try {
      await api.updateCompany(token, companyId, { vat_accounting_basis: basis });
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update VAT accounting basis");
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
      setError(err instanceof Error ? err.message : "Failed to update pro-rata percentage");
    }
  }

  if (!company) return <p className="text-text-secondary">Loading…</p>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-navy">{company.name}</h1>
          <p className="text-sm text-text-secondary">
            {company.kvk_number ? `KVK ${company.kvk_number}` : "No KVK number"} ·{" "}
            {company.vat_number ?? "No VAT number"} · {company.vat_frequency} filing
          </p>
        </div>
        <a
          href={`/companies/${companyId}/workspace`}
          className="btn-primary-v2 px-4 py-2 text-sm"
        >
          Open workspace
        </a>
      </div>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="card-v2 p-4 flex items-end gap-6">
        <div className="space-y-1">
          <label className="text-xs font-medium text-text-secondary">VAT accounting basis</label>
          <select
            disabled={!canEdit}
            value={company.vat_accounting_basis}
            onChange={(e) => handleBasisChange(e.target.value as VatAccountingBasis)}
            className="input-v2 px-2.5 py-1.5 text-sm disabled:bg-slate-50"
          >
            <option value="invoice_based">Invoice-based</option>
            <option value="cash_based">Cash-based</option>
          </select>
        </div>
        <div className="space-y-1">
          <label className="text-xs font-medium text-text-secondary">Input VAT pro-rata % (mixed activities)</label>
          <div className="flex gap-2">
            <input
              disabled={!canEdit}
              value={proRata}
              onChange={(e) => setProRata(e.target.value)}
              placeholder="e.g. 80"
              className="w-24 input-v2 px-2.5 py-1.5 text-sm disabled:bg-slate-50"
            />
            {canEdit && (
              <button
                onClick={handleProRataSave}
                className="input-v2 px-3 py-1.5 text-sm hover:bg-slate-50 transition-colors"
              >
                Save
              </button>
            )}
          </div>
        </div>
      </div>

      {canManageAccess && <TeamAccessSection companyId={companyId} />}

      <form onSubmit={handleAddYear} className="flex items-end gap-3">
        <div className="space-y-1">
          <label className="text-sm font-medium text-slate-700">Add financial year</label>
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
          Generate VAT periods
        </button>
      </form>

      <div className="space-y-6">
        {years.map((fy) => (
          <div key={fy.id} className="card-v2">
            <div className="px-5 py-4 border-b border-border-subtle">
              <h2 className="font-medium text-navy">Financial year {fy.year}</h2>
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-text-secondary border-b border-border-subtle">
                  <th className="px-5 py-2 font-medium">Period</th>
                  <th className="px-5 py-2 font-medium">Start</th>
                  <th className="px-5 py-2 font-medium">End</th>
                  <th className="px-5 py-2 font-medium">Filing deadline</th>
                  <th className="px-5 py-2 font-medium">Payment deadline</th>
                  <th className="px-5 py-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {fy.vat_periods.map((p) => (
                  <tr key={p.id} className="border-b border-slate-100 last:border-0">
                    <td className="px-5 py-2.5">{p.label}</td>
                    <td className="px-5 py-2.5">{p.start_date}</td>
                    <td className="px-5 py-2.5">{p.end_date}</td>
                    <td className="px-5 py-2.5">{p.filing_deadline}</td>
                    <td className="px-5 py-2.5">{p.payment_deadline}</td>
                    <td className="px-5 py-2.5">
                      <StatusBadge status={p.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
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
