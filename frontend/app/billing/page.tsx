"use client";

import { useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import GlassPageHeader from "@/components/glass/GlassPageHeader";
import GlassPanel from "@/components/glass/GlassPanel";
import GlassCard from "@/components/glass/GlassCard";
import GlassButton from "@/components/glass/GlassButton";
import GlassLoadingState, { GlassErrorState } from "@/components/glass/GlassLoadingState";
import { useAuth } from "@/lib/auth-context";
import { api, ApiError, Plan, Subscription } from "@/lib/api";
import { formatDate, formatEUR } from "@/lib/format";

const STATUS_STYLE: Record<string, string> = {
  TRIALING: "status-pill-info",
  ACTIVE: "status-pill-success",
  PAST_DUE: "status-pill-warning",
  CANCELED: "status-pill-neutral",
};

function BillingContent() {
  const t = useTranslations("billing");
  const locale = useLocale();
  const { token, user } = useAuth();
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [checkoutUrl, setCheckoutUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyPlan, setBusyPlan] = useState<string | null>(null);
  const isAdmin = user?.role === "admin";

  function refresh() {
    if (!token) return;
    api.getSubscription(token).then(setSubscription).catch((e) => setError(e.message));
    api.listPlans(token).then(setPlans).catch((e) => setError(e.message));
  }

  useEffect(refresh, [token]);

  async function handleCheckout(planCode: string) {
    if (!token) return;
    setError(null);
    setBusyPlan(planCode);
    try {
      const { checkout_url } = await api.createCheckout(token, planCode);
      setCheckoutUrl(checkout_url);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("checkoutFailed"));
    } finally {
      setBusyPlan(null);
    }
  }

  async function handleCancel() {
    if (!token) return;
    setError(null);
    try {
      await api.cancelSubscription(token);
      refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("cancelFailed"));
    }
  }

  if (!subscription) return <GlassLoadingState />;

  return (
    <div className="space-y-5">
      <GlassPageHeader title={t("title")} subtitle={t("sandboxNotice")} />

      {error && <GlassErrorState message={error} />}

      <GlassPanel title={t("currentPlan")}>
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <p className="font-medium text-text-primary text-lg">{subscription.plan.name}</p>
            <p className="text-sm text-text-secondary">
              {t("companiesUsed", { used: subscription.companies_used, limit: subscription.plan.company_limit })} ·{" "}
              {t("usersUsed", { used: subscription.users_used, limit: subscription.plan.user_limit })}
            </p>
            {subscription.trial_ends_at && subscription.status === "TRIALING" && (
              <p className="text-xs text-text-secondary mt-1">{t("trialEnds", { date: formatDate(subscription.trial_ends_at, locale) })}</p>
            )}
          </div>
          <span className={`status-pill ${STATUS_STYLE[subscription.status]}`}>{t(`status.${subscription.status}` as never)}</span>
        </div>
        {subscription.status !== "CANCELED" && isAdmin && (
          <div className="mt-4">
            <GlassButton variant="outline" onClick={handleCancel}>
              {t("cancelSubscription")}
            </GlassButton>
          </div>
        )}
      </GlassPanel>

      {checkoutUrl && (
        <div className="rounded-md bg-amber-50 border border-amber-200 text-xs px-3 py-2 space-y-1">
          <p className="font-medium text-pending">{t("sandboxCheckoutCreated")}</p>
          <p className="font-mono break-all" dir="ltr">{checkoutUrl}</p>
          <p className="text-text-secondary">{t("sandboxCheckoutExplanation")}</p>
        </div>
      )}

      <GlassPanel title={t("availablePlans")}>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {plans.map((p) => (
            <GlassCard key={p.code} className="space-y-3">
              <h3 className="font-medium text-text-primary">{p.name}</h3>
              <p className="text-xs text-text-secondary">{p.monthly_price_eur ? `${formatEUR(p.monthly_price_eur, locale)}${t("perMonth")}` : t("priceNotSet")}</p>
              <ul className="text-xs text-text-secondary space-y-1">
                <li>{t("upTo", { count: p.company_limit })}</li>
                <li>{t("upToUsers", { count: p.user_limit })}</li>
              </ul>
              {isAdmin && (
                <GlassButton
                  variant={p.code === subscription.plan.code ? "outline" : "primary"}
                  disabled={p.code === subscription.plan.code}
                  loading={busyPlan === p.code}
                  onClick={() => handleCheckout(p.code)}
                >
                  {p.code === subscription.plan.code ? t("currentPlanButton") : t("startSandboxCheckout")}
                </GlassButton>
              )}
            </GlassCard>
          ))}
        </div>
      </GlassPanel>
    </div>
  );
}

export default function BillingPage() {
  return (
    <AuthGuard>
      <Shell>
        <BillingContent />
      </Shell>
    </AuthGuard>
  );
}
