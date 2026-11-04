"use client";

import { FormEvent, useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, ApiError, ASSIGNABLE_ROLES, TenantUser, UserInvitation, UserRole } from "@/lib/api";
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
  const [inviteResult, setInviteResult] = useState<{ email: string; token: string } | null>(null);
  const [inviteBusy, setInviteBusy] = useState(false);

  const isOwner = currentUser?.role === "owner";

  function refresh() {
    if (!token) return;
    Promise.all([api.listUsers(token), api.listUserInvitations(token)])
      .then(([u, inv]) => {
        setUsers(u);
        setInvitations(inv);
        setError(null);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Failed to load users"))
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
      setInviteError(e instanceof ApiError ? e.message : "Failed to create invitation");
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
      setError(e instanceof ApiError ? e.message : "Failed to change role");
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
      setError(e instanceof ApiError ? e.message : "Failed to update user status");
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
      setError(e instanceof ApiError ? e.message : "Failed to revoke sessions");
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
      setError(e instanceof ApiError ? e.message : "Failed to revoke invitation");
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
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary">Users &amp; Permissions</h1>
          <p className="text-sm text-text-secondary mt-1">
            Everyone in your organisation, their role, status, and company access. Role changes and
            activation/deactivation are enforced server-side regardless of what this page offers.
          </p>
        </div>
        <button onClick={() => setShowInviteForm((v) => !v)} className="btn-primary-v2 px-4 py-2 text-sm">
          {showInviteForm ? "Cancel" : "Invite user"}
        </button>
      </div>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      {showInviteForm && (
        <form onSubmit={handleInvite} className="card-v2 p-5 space-y-3">
          <h2 className="font-medium text-text-primary">Invite a new user</h2>
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1">
              <label htmlFor="invite-email" className="text-xs font-medium text-text-secondary">Email</label>
              <input
                id="invite-email"
                type="email"
                required
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                className="input-v2 px-3 py-2 text-sm w-64"
                placeholder="name@example.com"
              />
            </div>
            <div className="space-y-1">
              <label htmlFor="invite-role" className="text-xs font-medium text-text-secondary">Role</label>
              <select
                id="invite-role"
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value as UserRole)}
                className="input-v2 px-3 py-2 text-sm"
              >
                {ASSIGNABLE_ROLES.filter((r) => isOwner || !["owner", "admin"].includes(r)).map((r) => (
                  <option key={r} value={r}>
                    {r.charAt(0).toUpperCase() + r.slice(1)}
                  </option>
                ))}
              </select>
            </div>
            <button type="submit" disabled={inviteBusy} className="btn-primary-v2 px-4 py-2 text-sm disabled:opacity-50">
              {inviteBusy ? "Sending…" : "Send invitation"}
            </button>
          </div>
          {!isOwner && <p className="text-xs text-text-secondary">As an admin, you can invite accountants and viewers. Only an owner can invite another owner or admin.</p>}
          {inviteError && <p className="text-sm text-error">{inviteError}</p>}
          {inviteResult && (
            <div className="rounded-md bg-muted px-3 py-2 text-xs space-y-1">
              <p className="text-text-primary">
                Invitation created for <span className="font-medium">{inviteResult.email}</span>. No email provider is
                configured in this environment -- share this link with them directly:
              </p>
              <p className="font-mono break-all text-text-secondary">
                {typeof window !== "undefined" ? window.location.origin : ""}/users/invitations/accept?token={inviteResult.token}
              </p>
            </div>
          )}
        </form>
      )}

      <div className="card-v2 overflow-hidden">
        <div className="px-5 py-3 border-b border-border-subtle">
          <h2 className="text-sm font-medium text-text-primary">Team ({users.length})</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="table-v3">
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Role</th>
                <th>Status</th>
                <th>MFA</th>
                <th>Company access</th>
                <th>Joined</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {users.map((u) => {
                const options = assignableRolesFor(u);
                return (
                  <tr key={u.id}>
                    <td className="text-text-primary">{u.full_name}</td>
                    <td className="text-text-secondary">{u.email}</td>
                    <td>
                      {u.id !== currentUser?.id && options.length > 0 ? (
                        <select
                          aria-label={`Role for ${u.full_name}`}
                          value={u.role}
                          disabled={busyUserId === u.id}
                          onChange={(e) => handleRoleChange(u, e.target.value as UserRole)}
                          className="input-v2 px-2 py-1 text-xs"
                        >
                          {!ASSIGNABLE_ROLES.includes(u.role) && <option value={u.role}>{u.role}</option>}
                          {options.map((r) => (
                            <option key={r} value={r}>
                              {r}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <span className={`status-pill ${ROLE_PILL[u.role]}`}>{u.role}</span>
                      )}
                    </td>
                    <td>
                      <span className={`status-pill ${u.is_active ? "status-pill-success" : "status-pill-danger"}`}>
                        {u.is_active ? "Active" : "Inactive"}
                      </span>
                    </td>
                    <td className="text-text-secondary text-xs">{u.mfa_enabled ? "Enabled" : "—"}</td>
                    <td className="text-text-secondary text-xs">
                      {u.companies.length === 0 ? "—" : u.companies.map((c) => c.name).join(", ")}
                    </td>
                    <td className="text-text-secondary text-xs">{formatDate(u.created_at)}</td>
                    <td className="text-xs">
                      {u.id === currentUser?.id ? (
                        <span className="text-text-secondary">You</span>
                      ) : (
                        <div className="flex items-center gap-2 justify-end">
                          <button
                            onClick={() => handleRevokeSessions(u)}
                            disabled={busyUserId === u.id}
                            className="text-navy hover:underline disabled:opacity-50"
                          >
                            Revoke sessions
                          </button>
                          <button
                            onClick={() => handleToggleActive(u)}
                            disabled={busyUserId === u.id}
                            className={`hover:underline disabled:opacity-50 ${u.is_active ? "text-error" : "text-navy"}`}
                          >
                            {u.is_active ? "Deactivate" : "Activate"}
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
                    No users yet.
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
            <h2 className="text-sm font-medium text-text-primary">Invitations</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="table-v3">
              <thead>
                <tr>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Expires</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {invitations.map((inv) => (
                  <tr key={inv.id}>
                    <td className="text-text-primary">{inv.invited_email}</td>
                    <td className="text-text-secondary text-xs">{inv.intended_role}</td>
                    <td>
                      <span className={`status-pill ${INVITATION_PILL[inv.status]}`}>{inv.status}</span>
                    </td>
                    <td className="text-text-secondary text-xs">{formatDate(inv.expires_at)}</td>
                    <td className="text-xs">
                      {inv.status === "PENDING" && (
                        <button onClick={() => handleRevokeInvitation(inv)} className="text-error hover:underline">
                          Revoke
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
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
