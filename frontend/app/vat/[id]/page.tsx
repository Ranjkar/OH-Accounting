"use client";

import { Suspense, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, Reconciliation, VatReturn } from "@/lib/api";

const BOX_ROWS: { code: string; label: string; net?: keyof VatReturn; vat?: keyof VatReturn }[] = [
  { code: "1a", label: "Domestic sales, high rate (21%)", net: "box_1a_net", vat: "box_1a_vat" },
  { code: "1b", label: "Domestic sales, low rate (9%)", net: "box_1b_net", vat: "box_1b_vat" },
  { code: "1c", label: "Domestic sales, other rate", net: "box_1c_net", vat: "box_1c_vat" },
  { code: "1d", label: "Private use correction", vat: "box_1d_vat" },
  { code: "1e", label: "Domestic zero-rated / exempt sales", net: "box_1e_net" },
  { code: "2a", label: "Domestic reverse-charge received", net: "box_2a_net", vat: "box_2a_vat" },
  { code: "3a", label: "Export (outside EU)", net: "box_3a_net" },
  { code: "3b", label: "EU supply", net: "box_3b_net" },
  { code: "3c", label: "EU distance sale", net: "box_3c_net" },
  { code: "4a", label: "Import (outside EU)", net: "box_4a_net", vat: "box_4a_vat" },
  { code: "4b", label: "EU acquisition", net: "box_4b_net", vat: "box_4b_vat" },
];

const STATUS_STEPS: VatReturn["status"][] = ["draft", "needs_review", "ready_for_approval", "approved", "locked"];

function VatReturnDetailContent({ vatReturnId }: { vatReturnId: number }) {
  const { token, user } = useAuth();
  const router = useRouter();
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
      setError(err instanceof Error ? err.message : "Action failed");
    }
  }

  if (!vatReturn || !reconciliation) return <p className="text-text-secondary">Loading…</p>;

  const stepIndex = STATUS_STEPS.indexOf(vatReturn.status);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <button onClick={() => router.push("/vat")} className="text-sm text-navy hover:underline">
            ← Back to VAT overview
          </button>
          <h1 className="text-xl font-semibold text-navy mt-1">VAT Return — {vatReturn.rules_version}</h1>
        </div>
        <span className="text-xs uppercase font-medium text-text-secondary">{vatReturn.status.replaceAll("_", " ")}</span>
      </div>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="flex items-center gap-2 text-xs">
        {STATUS_STEPS.map((step, i) => (
          <span
            key={step}
            className={`rounded-full px-3 py-1 ${
              i <= stepIndex ? "bg-navy text-white" : "bg-slate-100 text-text-secondary"
            }`}
          >
            {step.replaceAll("_", " ")}
          </span>
        ))}
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div className="card-v2 p-4">
          <p className="text-xs text-text-secondary">Sales (net)</p>
          <p className="text-lg font-semibold text-navy mt-1">{reconciliation.sales_total_net}</p>
        </div>
        <div className="card-v2 p-4">
          <p className="text-xs text-text-secondary">Purchases (net)</p>
          <p className="text-lg font-semibold text-navy mt-1">{reconciliation.purchases_total_net}</p>
        </div>
        <div className="card-v2 p-4">
          <p className="text-xs text-text-secondary">Net VAT payable (5a − 5b)</p>
          <p className="text-lg font-semibold text-navy mt-1">{vatReturn.net_payable}</p>
        </div>
      </div>

      <div className="card-v2">
        <div className="px-5 py-3 border-b border-border-subtle flex items-center justify-between">
          <h2 className="text-sm font-medium text-navy">Declaration preview</h2>
          <div className="flex gap-2">
            {(["pdf", "xlsx", "csv"] as const).map((fmt) => (
              <button
                key={fmt}
                onClick={() =>
                  token &&
                  api
                    .downloadReport(token, api.vatReturnReportUrl(vatReturn.id, fmt), `vat-return-${vatReturn.id}.${fmt}`)
                    .catch((e) => setError(e instanceof Error ? e.message : "Download failed"))
                }
                className="input-v2 px-3 py-1 text-xs font-medium uppercase hover:bg-slate-50 transition-colors"
              >
                {fmt}
              </button>
            ))}
          </div>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-text-secondary border-b border-border-subtle">
              <th className="px-5 py-2 font-medium">Box</th>
              <th className="px-5 py-2 font-medium">Description</th>
              <th className="px-5 py-2 font-medium">Net</th>
              <th className="px-5 py-2 font-medium">VAT</th>
            </tr>
          </thead>
          <tbody>
            {BOX_ROWS.map((row) => (
              <tr key={row.code} className="border-b border-slate-100 last:border-0">
                <td className="px-5 py-2 font-medium text-navy">{row.code}</td>
                <td className="px-5 py-2">{row.label}</td>
                <td className="px-5 py-2">{row.net ? vatReturn[row.net] : "—"}</td>
                <td className="px-5 py-2">{row.vat ? vatReturn[row.vat] : "—"}</td>
              </tr>
            ))}
            <tr className="border-b border-slate-100 bg-slate-50 font-medium">
              <td className="px-5 py-2">5a</td>
              <td className="px-5 py-2">Total VAT payable</td>
              <td className="px-5 py-2"></td>
              <td className="px-5 py-2">{vatReturn.box_5a_vat}</td>
            </tr>
            <tr className="border-b border-slate-100 bg-slate-50 font-medium">
              <td className="px-5 py-2">5b</td>
              <td className="px-5 py-2">Deductible input VAT</td>
              <td className="px-5 py-2"></td>
              <td className="px-5 py-2">{vatReturn.box_5b_vat}</td>
            </tr>
            <tr className="bg-navy text-white font-medium">
              <td className="px-5 py-2">5g</td>
              <td className="px-5 py-2">Final total (5a − 5b)</td>
              <td className="px-5 py-2"></td>
              <td className="px-5 py-2">{vatReturn.net_payable}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="card-v2 p-5 space-y-3">
        <h2 className="text-sm font-medium text-navy">Reconciliation checks</h2>
        {reconciliation.pending_documents.length === 0 &&
        reconciliation.duplicate_documents.length === 0 &&
        reconciliation.validation_errors.length === 0 &&
        reconciliation.unresolved_fx_transaction_ids.length === 0 ? (
          <p className="text-sm text-green-700">No outstanding issues.</p>
        ) : (
          <div className="space-y-2 text-sm">
            {reconciliation.pending_documents.map((d) => (
              <div key={`pending-${d.id}`} className="rounded-md border border-amber-200 bg-amber-50 text-pending px-3 py-2">
                Document not yet approved: {d.original_filename} ({d.status})
              </div>
            ))}
            {reconciliation.duplicate_documents.map((d) => (
              <div key={`dup-${d.id}`} className="rounded-md border border-red-200 bg-red-50 text-error px-3 py-2">
                Duplicate: {d.original_filename} (of document #{d.duplicate_of_document_id})
              </div>
            ))}
            {reconciliation.validation_errors.map((v, i) => (
              <div key={`val-${i}`} className="rounded-md border border-red-200 bg-red-50 text-error px-3 py-2">
                {v.rule_code}: {v.message}
              </div>
            ))}
            {reconciliation.unresolved_fx_transaction_ids.map((id) => (
              <div key={`fx-${id}`} className="rounded-md border border-red-200 bg-red-50 text-error px-3 py-2">
                Transaction #{id} needs an FX rate before it can be included in this return.
              </div>
            ))}
          </div>
        )}
      </div>

      {canEdit && (
        <div className="flex gap-2">
          {vatReturn.status === "draft" || vatReturn.status === "needs_review" ? (
            <>
              <button
                onClick={() => handleAction(() => api.recalculateVatReturn(token!, vatReturn.id))}
                className="input-v2 px-4 py-2 text-sm font-medium hover:bg-slate-50 transition-colors"
              >
                Recalculate
              </button>
              <button
                onClick={() => handleAction(() => api.submitVatReturnForApproval(token!, vatReturn.id))}
                className="btn-primary-v2 px-4 py-2 text-sm"
              >
                Submit for approval
              </button>
            </>
          ) : vatReturn.status === "ready_for_approval" ? (
            <button
              onClick={() => handleAction(() => api.approveVatReturn(token!, vatReturn.id))}
              className="rounded-md bg-green-600 text-white px-4 py-2 text-sm font-medium hover:bg-green-700 transition-colors"
            >
              Approve
            </button>
          ) : vatReturn.status === "approved" ? (
            <button
              onClick={() => handleAction(() => api.lockVatReturn(token!, vatReturn.id))}
              className="btn-primary-v2 px-4 py-2 text-sm"
            >
              Lock period
            </button>
          ) : (
            <p className="text-sm text-text-secondary">This period is locked.</p>
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
