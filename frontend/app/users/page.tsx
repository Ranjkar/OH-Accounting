"use client";

import { FormEvent, useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import GlassModal from "@/components/glass/GlassModal";
import { useAuth } from "@/lib/auth-context";
import { api, ApiError, ASSIGNABLE_ROLES, Company, TenantUser, UserInvitation, UserRole } from "@/lib/api";
import { formatDate } from "@/lib/format";

const ROLE_PILL: Record<UserRole, string> = {
  owner: "status-pill-info",
  admin: "status-pill-info",
  accountant: "status-pill-neutral",
  viewer: "status-pill-neutral",
  customer: "status-pill-neutral",
  employee: "status-pill-neutral",
};

const INVITATION_PILL: Record<string, string> = {
  PENDING: "status-pill-warning",
  ACCEPTED: "status-pill-success",
  REVOKED: "status-pill-neutral",
  EXPIRED: "status-pill-danger",
};

function UsersContent() {
  const t = useTranslations("users");
  const locale = useLocale();
  const tCommon = useTranslations("common");
  const { token, user: currentUser } = useAuth();
  const [users, setUsers] = useState<TenantUser[]>([]);
  const [invitations, setInvitations] = useState<UserInvitation[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyUserId, setBusyUserId] = useState<number | null>(null);

  const [showInviteForm, setShowInviteForm] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<UserRole>("accountant");
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [inviteResult, setInviteResult] = useState<{ email: string; token: string | null } | null>(null);
  const [inviteBusy, setInviteBusy] = useState(false);

  const [companies, setCompanies] = useState<Company[]>([]);
  const [manageUser, setManageUser] = useState<TenantUser | null>(null);
  const [selectedCompanyIds, setSelectedCompanyIds] = useState<number[]>([]);
  const [manageBusy, setManageBusy] = useState(false);
  const [manageError, setManageError] = useState<string | null>(null);

  const isOwner = currentUser?.role === "owner";

  function refresh() {
    if (!token) return;
    Promise.all([api.listUsers(token), api.listUserInvitations(token), api.listCompanies(token)])
      .then(([u, inv, c]) => {
        setUsers(u);
        setInvitations(inv);
        setCompanies(c);
        setError(null);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : t("loadFailed")))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, [token]);

  async function handleInvite(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setInviteBusy(true);
    setInviteError(null);
    try {
      const result = await api.createUserInvitation(token, inviteEmail, inviteRole);
      setInviteResult({ email: inviteEmail, token: result.raw_token });
      setInviteEmail("");
      setInviteRole("accountant");
      refresh();
    } catch (e) {
      setInviteError(e instanceof ApiError ? e.message : t("inviteFailed"));
    } finally {
      setInviteBusy(false);
    }
  }

  async function handleRoleChange(targetUser: TenantUser, role: UserRole) {
    if (!token || role === targetUser.role) return;
    setBusyUserId(targetUser.id);
    setError(null);
    try {
      await api.updateUserRole(token, targetUser.id, role);
      refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("roleChangeFailed"));
    } finally {
      setBusyUserId(null);
    }
  }

  async function handleToggleActive(targetUser: TenantUser) {
    if (!token) return;
    setBusyUserId(targetUser.id);
    setError(null);
    try {
      if (targetUser.is_active) await api.deactivateUser(token, targetUser.id);
      else await api.activateUser(token, targetUser.id);
      refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("statusUpdateFailed"));
    } finally {
      setBusyUserId(null);
    }
  }

  async function handleRevokeSessions(targetUser: TenantUser) {
    if (!token) return;
    setBusyUserId(targetUser.id);
    setError(null);
    try {
      await api.revokeUserSessions(token, targetUser.id);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("revokeSessionsFailed"));
    } finally {
      setBusyUserId(null);
    }
  }

  async function handleRevokeInvitation(invitation: UserInvitation) {
    if (!token) return;
    try {
      await api.revokeUserInvitation(token, invitation.id);
      refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("revokeInvitationFailed"));
    }
  }

  async function handleResendInvitation(invitation: UserInvitation) {
    if (!token) return;
    setBusyUserId(invitation.id);
    setError(null);
    try {
      const result = await api.resendUserInvitation(token, invitation.id);
      // Without an email provider the backend hands back the raw token so
      // the link can be shared by hand, exactly like a fresh invitation.
      if (result.raw_token) setInviteResult({ email: invitation.invited_email, token: result.raw_token });
      refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("resendFailed"));
    } finally {
      setBusyUserId(null);
    }
  }

  function openManage(targetUser: TenantUser) {
    setManageUser(targetUser);
    setSelectedCompanyIds(targetUser.companies.map((c) => c.id));
    setManageError(null);
  }

  async function saveCompanies() {
    if (!token || !manageUser) return;
    setManageBusy(true);
    setManageError(null);
    try {
      await api.setUserCompanyAccess(token, manageUser.id, selectedCompanyIds);
      setManageUser(null);
      refresh();
    } catch (e) {
      setManageError(e instanceof ApiError ? e.message : t("companiesSaveFailed"));
    } finally {
      setManageBusy(false);
    }
  }

  // Which roles this acting user is allowed to assign to someone else --
  // the backend is the real enforcement, this just avoids offering an
  // option that would only come back as a 403.
  function assignableRolesFor(targetUser: TenantUser): UserRole[] {
    const privileged: UserRole[] = ["owner", "admin"];
    if (isOwner) return ASSIGNABLE_ROLES;
    if (privileged.includes(targetUser.role)) return [];
    return ASSIGNABLE_ROLES.filter((r) => !privileged.includes(r));
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary">{t("title")}</h1>
          <p className="text-sm text-text-secondary mt-1">{t("subtitle")}</p>
        </div>
        <button onClick={() => setShowInviteForm((v) => !v)} className="btn-primary-v2 px-4 py-2 text-sm">
          {showInviteForm ? tCommon("cancel") : t("inviteUser")}
        </button>
      </div>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      {showInviteForm && (
        <form onSubmit={handleInvite} className="card-v2 p-5 space-y-3">
          <h2 className="font-medium text-text-primary">{t("inviteNewUser")}</h2>
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1">
              <label htmlFor="invite-email" className="text-xs font-medium text-text-secondary">{t("emailHeader")}</label>
              <input
                id="invite-email"
                type="email"
                required
                dir="ltr"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                className="input-v2 px-3 py-2 text-sm w-64"
                placeholder={t("emailPlaceholder")}
              />
            </div>
            <div className="space-y-1">
              <label htmlFor="invite-role" className="text-xs font-medium text-text-secondary">{tCommon("role")}</label>
              <select
                id="invite-role"
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value as UserRole)}
                className="input-v2 px-3 py-2 text-sm"
              >
                {ASSIGNABLE_ROLES.filter((r) => isOwner || !["owner", "admin"].includes(r)).map((r) => (
                  <option key={r} value={r}>
                    {t(`roles.${r}` as never)}
                  </option>
                ))}
              </select>
            </div>
            <button type="submit" disabled={inviteBusy} className="btn-primary-v2 px-4 py-2 text-sm disabled:opacity-50">
              {inviteBusy ? tCommon("sending") : t("sendInvitation")}
            </button>
          </div>
          {!isOwner && <p className="text-xs text-text-secondary">{t("adminInviteNote")}</p>}
          {inviteError && <p className="text-sm text-error">{inviteError}</p>}
          {inviteResult && (
            <div className="rounded-md bg-muted px-3 py-2 text-xs space-y-1">
              <p className="text-text-primary">
                {t("invitationCreatedFor")} <span className="font-medium" dir="ltr">{inviteResult.email}</span>.{" "}
                {inviteResult.token ? t("noEmailProviderShareLink") : t("invitationEmailed")}
              </p>
              {inviteResult.token && (
                <p className="font-mono break-all text-text-secondary" dir="ltr">
                  {typeof window !== "undefined" ? window.location.origin : ""}/users/invitations/accept?token={inviteResult.token}
                </p>
              )}
            </div>
          )}
        </form>
      )}

      <div className="card-v2 overflow-hidden">
        <div className="px-5 py-3 border-b border-border-subtle">
          <h2 className="text-sm font-medium text-text-primary">{t("teamCount", { count: users.length })}</h2>
        </div>
        <div className="overflow-x-auto" tabIndex={0}>
          <table className="table-v3">
            <thead>
              <tr>
                <th>{t("nameHeader")}</th>
                <th>{t("emailHeader")}</th>
                <th>{tCommon("role")}</th>
                <th>{tCommon("status")}</th>
                <th>{t("mfa")}</th>
                <th>{t("companyAccess")}</th>
                <th>{t("joined")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {users.map((u) => {
                const options = assignableRolesFor(u);
                return (
                  <tr key={u.id}>
                    <td className="text-text-primary">{u.full_name}</td>
                    <td className="text-text-secondary" dir="ltr">{u.email}</td>
                    <td>
                      {u.id !== currentUser?.id && options.length > 0 ? (
                        <select
                          aria-label={`${tCommon("role")}: ${u.full_name}`}
                          value={u.role}
                          disabled={busyUserId === u.id}
                          onChange={(e) => handleRoleChange(u, e.target.value as UserRole)}
                          className="input-v2 px-2 py-1 text-xs"
                        >
                          {!ASSIGNABLE_ROLES.includes(u.role) && <option value={u.role}>{u.role}</option>}
                          {options.map((r) => (
                            <option key={r} value={r}>
                              {t(`roles.${r}` as never)}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <span className={`status-pill ${ROLE_PILL[u.role]}`}>{ASSIGNABLE_ROLES.includes(u.role) ? t(`roles.${u.role}` as never) : u.role}</span>
                      )}
                    </td>
                    <td>
                      <span className={`status-pill ${u.is_active ? "status-pill-success" : "status-pill-danger"}`}>
                        {u.is_active ? tCommon("active") : tCommon("inactive")}
                      </span>
                    </td>
                    <td className="text-text-secondary text-xs">{u.mfa_enabled ? tCommon("enabled") : "—"}</td>
                    <td className="text-text-secondary text-xs">
                      {u.companies.length === 0 ? "—" : u.companies.map((c) => c.name).join(", ")}
                    </td>
                    <td className="text-text-secondary text-xs">{formatDate(u.created_at, locale)}</td>
                    <td className="text-xs">
                      {u.id === currentUser?.id ? (
                        <span className="text-text-secondary">{t("you")}</span>
                      ) : (
                        <div className="flex items-center gap-2 justify-end">
                          <button
                            onClick={() => openManage(u)}
                            disabled={busyUserId === u.id}
                            className="text-navy hover:underline disabled:opacity-50"
                          >
                            {t("manageCompanies")}
                          </button>
                          <button
                            onClick={() => handleRevokeSessions(u)}
                            disabled={busyUserId === u.id}
                            className="text-navy hover:underline disabled:opacity-50"
                          >
                            {t("revokeSessions")}
                          </button>
                          <button
                            onClick={() => handleToggleActive(u)}
                            disabled={busyUserId === u.id}
                            className={`hover:underline disabled:opacity-50 ${u.is_active ? "text-error" : "text-navy"}`}
                          >
                            {u.is_active ? t("deactivate") : t("activate")}
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
              {!loading && users.length === 0 && (
                <tr>
                  <td colSpan={8} className="text-text-secondary">
                    {t("noUsersYet")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {invitations.length > 0 && (
        <div className="card-v2 overflow-hidden">
          <div className="px-5 py-3 border-b border-border-subtle">
            <h2 className="text-sm font-medium text-text-primary">{t("invitations")}</h2>
          </div>
          <div className="overflow-x-auto" tabIndex={0}>
            <table className="table-v3">
              <thead>
                <tr>
                  <th>{t("emailHeader")}</th>
                  <th>{tCommon("role")}</th>
                  <th>{tCommon("status")}</th>
                  <th>{t("expires")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {invitations.map((inv) => (
                  <tr key={inv.id}>
                    <td className="text-text-primary" dir="ltr">{inv.invited_email}</td>
                    <td className="text-text-secondary text-xs">{ASSIGNABLE_ROLES.includes(inv.intended_role) ? t(`roles.${inv.intended_role}` as never) : inv.intended_role}</td>
                    <td>
                      <span className={`status-pill ${INVITATION_PILL[inv.status]}`}>{t(`invitationStatus.${inv.status.toLowerCase()}` as never)}</span>
                    </td>
                    <td className="text-text-secondary text-xs">{formatDate(inv.expires_at, locale)}</td>
                    <td className="text-xs">
                      {inv.status === "PENDING" && (
                        <div className="flex items-center gap-2 justify-end">
                          <button
                            onClick={() => handleResendInvitation(inv)}
                            disabled={busyUserId === inv.id}
                            className="text-navy hover:underline disabled:opacity-50"
                          >
                            {t("resend")}
                          </button>
                          <button onClick={() => handleRevokeInvitation(inv)} className="text-error hover:underline">
                            {t("revoke")}
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <GlassModal
        open={manageUser !== null}
        onClose={() => setManageUser(null)}
        title={manageUser ? t("manageCompaniesFor", { name: manageUser.full_name }) : ""}
        footer={
          <>
            <button type="button" onClick={() => setManageUser(null)} disabled={manageBusy} className="btn-outline-v2 px-4 py-2 text-sm disabled:opacity-50">
              {tCommon("cancel")}
            </button>
            <button type="button" onClick={() => void saveCompanies()} disabled={manageBusy} className="btn-primary-v2 px-4 py-2 text-sm disabled:opacity-50">
              {manageBusy ? tCommon("saving") : tCommon("save")}
            </button>
          </>
        }
      >
        <div className="space-y-3">
          {manageError && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2" role="alert">{manageError}</div>}
          <p className="text-xs text-text-secondary">{t("manageCompaniesHelp")}</p>
          <div className="space-y-2">
            {companies.map((c) => (
              <label key={c.id} className="flex items-center gap-3 text-sm">
                <input
                  type="checkbox"
                  className="h-5 w-5"
                  checked={selectedCompanyIds.includes(c.id)}
                  onChange={(e) => setSelectedCompanyIds((ids) => (e.target.checked ? [...ids, c.id] : ids.filter((id) => id !== c.id)))}
                />
                <span className="text-text-primary">{c.name}</span>
              </label>
            ))}
            {companies.length === 0 && <p className="text-sm text-text-secondary">{t("noCompaniesToAssign")}</p>}
          </div>
        </div>
      </GlassModal>
    </div>
  );
}

export default function UsersPage() {
  return (
    <AuthGuard>
      <Shell>
        <UsersContent />
      </Shell>
    </AuthGuard>
  );
}
