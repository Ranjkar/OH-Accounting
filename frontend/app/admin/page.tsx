"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import GlassPageHeader from "@/components/glass/GlassPageHeader";
import GlassPanel from "@/components/glass/GlassPanel";
import GlassTable from "@/components/glass/GlassTable";
import GlassLoadingState, { GlassErrorState } from "@/components/glass/GlassLoadingState";
import { useAuth } from "@/lib/auth-context";
import { api, PlatformOverviewRow } from "@/lib/api";

function AdminContent() {
  const t = useTranslations("admin");
  const { token, user } = useAuth();
  const [rows, setRows] = useState<PlatformOverviewRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    api.getPlatformOverview(token).then((r) => setRows(r.tenants)).catch((e) => setError(e.message));
  }, [token]);

  if (!user?.is_platform_admin) {
    return <GlassErrorState message={t("platformAdminOnly")} />;
  }

  return (
    <div className="space-y-5">
      <GlassPageHeader title={t("title")} subtitle={t("subtitle")} />
      {error && <GlassErrorState message={error} />}
      {!rows ? (
        <GlassLoadingState />
      ) : (
        <GlassPanel title={t("customerAccounts", { count: rows.length })}>
          <GlassTable
            emptyMessage={t("noTenantsYet")}
            columns={[
              { key: "name", header: t("account"), render: (r) => r.tenant_name },
              { key: "plan", header: t("plan"), render: (r) => r.plan_code ?? "—" },
              { key: "status", header: t("status"), render: (r) => r.subscription_status ?? "—" },
              { key: "companies", header: t("companies"), render: (r) => r.companies_used },
              { key: "users", header: t("users"), render: (r) => r.users_used },
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
