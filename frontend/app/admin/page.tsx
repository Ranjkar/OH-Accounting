"use client";

import { useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import GlassPageHeader from "@/components/glass/GlassPageHeader";
import GlassPanel from "@/components/glass/GlassPanel";
import GlassTable from "@/components/glass/GlassTable";
import GlassLoadingState, { GlassErrorState } from "@/components/glass/GlassLoadingState";
import { useAuth } from "@/lib/auth-context";
import { api, PlatformOverviewRow } from "@/lib/api";

function AdminContent() {
  const { token, user } = useAuth();
  const [rows, setRows] = useState<PlatformOverviewRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    api.getPlatformOverview(token).then((r) => setRows(r.tenants)).catch((e) => setError(e.message));
  }, [token]);

  if (!user?.is_platform_admin) {
    return <GlassErrorState message="Platform admin only." />;
  }

  return (
    <div className="space-y-5">
      <GlassPageHeader
        title="Platform Overview"
        subtitle="Cross-tenant subscription, usage, and plan status for every customer account on this platform. Deliberately shows only counts -- never a customer's financial records, documents, or ledger entries."
      />
      {error && <GlassErrorState message={error} />}
      {!rows ? (
        <GlassLoadingState />
      ) : (
        <GlassPanel title={`Customer accounts (${rows.length})`}>
          <GlassTable
            emptyMessage="No tenants yet."
            columns={[
              { key: "name", header: "Account", render: (r) => r.tenant_name },
              { key: "plan", header: "Plan", render: (r) => r.plan_code ?? "—" },
              { key: "status", header: "Status", render: (r) => r.subscription_status ?? "—" },
              { key: "companies", header: "Companies", render: (r) => r.companies_used },
              { key: "users", header: "Users", render: (r) => r.users_used },
            ]}
            rows={rows}
            rowKey={(r) => r.tenant_id}
          />
        </GlassPanel>
      )}
    </div>
  );
}

export default function AdminPage() {
  return (
    <AuthGuard>
      <Shell>
        <AdminContent />
      </Shell>
    </AuthGuard>
  );
}
