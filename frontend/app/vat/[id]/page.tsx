"use client";

import { Suspense, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, Reconciliation, VatReturn } from "@/lib/api";
import { formatEUR } from "@/lib/format";

const BOX_CODES: { code: string; labelKey: string; net?: keyof VatReturn; vat?: keyof VatReturn }[] = [
  { code: "1a", labelKey: "box1a", net: "box_1a_net", vat: "box_1a_vat" },
  { code: "1b", labelKey: "box1b", net: "box_1b_net", vat: "box_1b_vat" },
  { code: "1c", labelKey: "box1c", net: "box_1c_net", vat: "box_1c_vat" },
  { code: "1d", labelKey: "box1d", vat: "box_1d_vat" },
  { code: "1e", labelKey: "box1e", net: "box_1e_net" },
  { code: "2a", labelKey: "box2a", net: "box_2a_net", vat: "box_2a_vat" },
  { code: "3a", labelKey: "box3a", net: "box_3a_net" },
  { code: "3b", labelKey: "box3b", net: "box_3b_net" },
  { code: "3c", labelKey: "box3c", net: "box_3c_net" },
  { code: "4a", labelKey: "box4a", net: "box_4a_net", vat: "box_4a_vat" },
  { code: "4b", labelKey: "box4b", net: "box_4b_net", vat: "box_4b_vat" },
];

const STATUS_STEPS: VatReturn["status"][] = ["draft", "needs_review", "ready_for_approval", "approved", "locked"];

function VatReturnDetailContent({ vatReturnId }: { vatReturnId: number }) {
  const t = useTranslations("vat");
  const tBoxes = useTranslations("vat.boxDescriptions");
  const tStatus = useTranslations("vat.status");
  const { token, user } = useAuth();
  const router = useRouter();
  const locale = useLocale();
  const canEdit = user?.role === "admin" || user?.role === "accountant";

  const [vatReturn, setVatReturn] = useState<VatReturn | null>(null);
  const [reconciliation, setReconciliation] = useState<Reconciliation | null>(null);
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    if (!token) return;
    api.getReconciliation(token, vatReturnId).then((r) => {
      setReconciliation(r);
      setVatReturn(r.vat_return);
    }).catch((e) => setError(e.message));
  }

  useEffect(refresh, [token, vatReturnId]);

  async function handleAction(action: () => Promise<VatReturn>) {
    setError(null);
    try {
      await action();
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("actionFailed"));
    }
  }

  if (!vatReturn || !reconciliation) return <p className="text-text-secondary">{t("loadingEllipsis")}</p>;

  const stepIndex = STATUS_STEPS.indexOf(vatReturn.status);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <button onClick={() => router.push("/vat")} className="text-sm text-navy hover:underline">
            <span className="icon-directional" style={{ display: "inline-block" }}>←</span> {t("backToVatOverview")}
          </button>
          <h1 className="text-xl font-semibold text-text-primary mt-1">{t("vatReturnHeading")} — <span dir="ltr">{vatReturn.rules_version}</span></h1>
        </div>
        <span className="text-xs uppercase font-medium text-text-secondary">{tStatus(vatReturn.status as never)}</span>
      </div>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="flex flex-wrap items-center gap-2 text-xs">
        {STATUS_STEPS.map((step, i) => (
          <span
            key={step}
            className={`rounded-full px-3 py-1 ${
              i <= stepIndex ? "bg-navy-solid text-white" : "bg-muted text-text-secondary"
            }`}
          >
            {tStatus(step as never)}
          </span>
        ))}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="card-v2 p-4">
          <p className="text-xs text-text-secondary">{t("salesNet")}</p>
          <p className="text-lg font-semibold text-navy mt-1">{formatEUR(reconciliation.sales_total_net, locale)}</p>
        </div>
        <div className="card-v2 p-4">
          <p className="text-xs text-text-secondary">{t("purchasesNet")}</p>
          <p className="text-lg font-semibold text-navy mt-1">{formatEUR(reconciliation.purchases_total_net, locale)}</p>
        </div>
        <div className="card-v2 p-4">
          <p className="text-xs text-text-secondary">{t("netPayable")} (5a − 5b)</p>
          <p className="text-lg font-semibold text-navy mt-1">{formatEUR(vatReturn.net_payable, locale)}</p>
        </div>
      </div>

      <div className="card-v2">
        <div className="px-5 py-3 border-b border-border-subtle flex items-center justify-between">
          <h2 className="text-sm font-medium text-text-primary">{t("declarationPreview")}</h2>
          <div className="flex flex-wrap gap-2">
            {(["pdf", "xlsx", "csv"] as const).map((fmt) => (
              <button
                key={fmt}
                onClick={() =>
                  token &&
                  api
                    .downloadReport(token, api.vatReturnReportUrl(vatReturn.id, fmt), `vat-return-${vatReturn.id}.${fmt}`)
                    .catch((e) => setError(e instanceof Error ? e.message : t("downloadFailed")))
                }
                className="input-v2 px-3 py-1 text-xs font-medium uppercase hover:bg-muted transition-colors"
              >
                {fmt}
              </button>
            ))}
          </div>
        </div>
        <div className="overflow-x-auto" tabIndex={0}>
        <table className="table-v3">
          <thead>
            <tr>
              <th>{t("boxColumn")}</th>
              <th>{t("descriptionColumn")}</th>
              <th className="text-right">{t("netColumn")}</th>
              <th className="text-right">{t("vatColumn")}</th>
            </tr>
          </thead>
          <tbody>
            {BOX_CODES.map((row) => (
              <tr key={row.code}>
                <td className="font-medium text-navy">{row.code}</td>
                <td className="text-text-primary">{tBoxes(row.labelKey as never)}</td>
                <td className="col-amount">{row.net ? formatEUR(vatReturn[row.net] as string, locale) : "—"}</td>
                <td className="col-amount">{row.vat ? formatEUR(vatReturn[row.vat] as string, locale) : "—"}</td>
              </tr>
            ))}
            <tr className="bg-muted font-medium">
              <td>5a</td>
              <td className="text-text-primary">{t("totalVatPayable")}</td>
              <td></td>
              <td className="col-amount">{formatEUR(vatReturn.box_5a_vat, locale)}</td>
            </tr>
            <tr className="bg-muted font-medium">
              <td>5b</td>
              <td className="text-text-primary">{t("deductibleInputVat")}</td>
              <td></td>
              <td className="col-amount">{formatEUR(vatReturn.box_5b_vat, locale)}</td>
            </tr>
            <tr className="bg-navy-solid text-white font-medium">
              <td>5g</td>
              <td>{t("finalTotal")} (5a − 5b)</td>
              <td></td>
              <td className="col-amount">{formatEUR(vatReturn.net_payable, locale)}</td>
            </tr>
          </tbody>
        </table>
        </div>
      </div>

      <div className="card-v2 p-5 space-y-3">
        <h2 className="text-sm font-medium text-text-primary">{t("reconciliationChecks")}</h2>
        {reconciliation.pending_documents.length === 0 &&
        reconciliation.duplicate_documents.length === 0 &&
        reconciliation.validation_errors.length === 0 &&
        reconciliation.unresolved_fx_transaction_ids.length === 0 ? (
          <p className="text-sm text-green-700">{t("noOutstandingIssues")}</p>
        ) : (
          <div className="space-y-2 text-sm">
            {reconciliation.pending_documents.map((d) => (
              <div key={`pending-${d.id}`} className="rounded-md border border-amber-200 bg-amber-50 text-pending px-3 py-2">
                {t("documentNotApproved", { name: d.original_filename, status: d.status })}
              </div>
            ))}
            {reconciliation.duplicate_documents.map((d) => (
              <div key={`dup-${d.id}`} className="rounded-md border border-red-200 bg-red-50 text-error px-3 py-2">
                {t("duplicateOf", { name: d.original_filename, id: d.duplicate_of_document_id ?? "—" })}
              </div>
            ))}
            {reconciliation.validation_errors.map((v, i) => (
              <div key={`val-${i}`} className="rounded-md border border-red-200 bg-red-50 text-error px-3 py-2">
                {v.rule_code}: {v.message}
              </div>
            ))}
            {reconciliation.unresolved_fx_transaction_ids.map((id) => (
              <div key={`fx-${id}`} className="rounded-md border border-red-200 bg-red-50 text-error px-3 py-2">
                {t("fxRateNeeded", { id })}
              </div>
            ))}
          </div>
        )}
      </div>

      {canEdit && (
        <div className="flex flex-wrap gap-2">
          {vatReturn.status === "draft" || vatReturn.status === "needs_review" ? (
            <>
              <button
                onClick={() => handleAction(() => api.recalculateVatReturn(token!, vatReturn.id))}
                className="input-v2 px-4 py-2 text-sm font-medium hover:bg-muted transition-colors"
              >
                {t("recalculate")}
              </button>
              <button
                onClick={() => handleAction(() => api.submitVatReturnForApproval(token!, vatReturn.id))}
                className="btn-primary-v2 px-4 py-2 text-sm"
              >
                {t("submitForApproval")}
              </button>
            </>
          ) : vatReturn.status === "ready_for_approval" ? (
            <button
              onClick={() => handleAction(() => api.approveVatReturn(token!, vatReturn.id))}
              className="rounded-md bg-green-600 text-white px-4 py-2 text-sm font-medium hover:bg-green-700 transition-colors"
            >
              {t("approveReturn")}
            </button>
          ) : vatReturn.status === "approved" ? (
            <button
              onClick={() => handleAction(() => api.lockVatReturn(token!, vatReturn.id))}
              className="btn-primary-v2 px-4 py-2 text-sm"
            >
              {t("lockPeriod")}
            </button>
          ) : (
            <p className="text-sm text-text-secondary">{t("periodLocked")}</p>
          )}
        </div>
      )}
    </div>
  );
}

function VatReturnDetailRoute() {
  const params = useParams<{ id: string }>();
  return (
    <AuthGuard>
      <Shell>
        <VatReturnDetailContent vatReturnId={Number(params.id)} />
      </Shell>
    </AuthGuard>
  );
}

export default function VatReturnDetailPage() {
  return (
    <Suspense>
      <VatReturnDetailRoute />
    </Suspense>
  );
}
