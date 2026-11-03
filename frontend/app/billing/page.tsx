"use client";

import { useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import GlassPageHeader from "@/components/glass/GlassPageHeader";
import GlassPanel from "@/components/glass/GlassPanel";
import GlassCard from "@/components/glass/GlassCard";
import GlassButton from "@/components/glass/GlassButton";
import GlassLoadingState, { GlassErrorState } from "@/components/glass/GlassLoadingState";
import { useAuth } from "@/lib/auth-context";
import { api, ApiError, Plan, Subscription } from "@/lib/api";

const STATUS_STYLE: Record<string, string> = {
  TRIALING: "bg-brand-purple-500/10 text-brand-purple-700 border border-brand-purple-300/50",
  ACTIVE: "bg-green-500/10 text-green-700 border border-green-300/50",
  PAST_DUE: "bg-amber-500/10 text-amber-700 border border-amber-300/50",
  CANCELED: "bg-slate-500/10 text-slate-700 border border-slate-300/50",
};

function BillingContent() {
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
      setError(e instanceof ApiError ? e.message : "Failed to start checkout");
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
      setError(e instanceof ApiError ? e.message : "Failed to cancel subscription");
    }
  }

  if (!subscription) return <GlassLoadingState />;

  return (
    <div className="space-y-5">
      <GlassPageHeader
        title="Billing & Subscription"
        subtitle="Sandbox billing only -- no real payment provider is connected, and no commercial price has been set for any plan. Checkout below is a stub that never charges a card. See docs/subscription-billing.md."
      />

      {error && <GlassErrorState message={error} />}

      <GlassPanel title="Current plan">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <p className="font-medium text-text-primary text-lg">{subscription.plan.name}</p>
            <p className="text-sm text-text-secondary">
              {subscription.companies_used} / {subscription.plan.company_limit} companies ·{" "}
              {subscription.users_used} / {subscription.plan.user_limit} users
            </p>
            {subscription.trial_ends_at && subscription.status === "TRIALING" && (
              <p className="text-xs text-text-secondary mt-1">Trial ends {new Date(subscription.trial_ends_at).toLocaleDateString()}</p>
            )}
          </div>
          <span className={`inline-flex rounded-full px-3 py-1 text-xs font-medium ${STATUS_STYLE[subscription.status]}`}>{subscription.status}</span>
        </div>
        {subscription.status !== "CANCELED" && isAdmin && (
          <div className="mt-4">
            <GlassButton variant="outline" onClick={handleCancel}>
              Cancel subscription
            </GlassButton>
          </div>
        )}
      </GlassPanel>

      {checkoutUrl && (
        <div className="rounded-md bg-amber-50 border border-amber-200 text-xs px-3 py-2 space-y-1">
          <p className="font-medium text-pending">Sandbox checkout session created (no real redirect for a stub provider):</p>
          <p className="font-mono break-all">{checkoutUrl}</p>
          <p className="text-text-secondary">A real integration would redirect here; completion is simulated via the webhook endpoint, not by visiting this URL.</p>
        </div>
      )}

      <GlassPanel title="Available plans">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {plans.map((p) => (
            <GlassCard key={p.code} className="space-y-3">
              <h3 className="font-medium text-text-primary">{p.name}</h3>
              <p className="text-xs text-text-secondary">{p.monthly_price_eur ? `€${p.monthly_price_eur}/month` : "Price not yet set -- contact sales"}</p>
              <ul className="text-xs text-text-secondary space-y-1">
                <li>Up to {p.company_limit} companies</li>
                <li>Up to {p.user_limit} users</li>
              </ul>
              {isAdmin && (
                <GlassButton
                  variant={p.code === subscription.plan.code ? "outline" : "primary"}
                  disabled={p.code === subscription.plan.code}
                  loading={busyPlan === p.code}
                  onClick={() => handleCheckout(p.code)}
                >
                  {p.code === subscription.plan.code ? "Current plan" : "Start sandbox checkout"}
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
