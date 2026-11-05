"use client";

import { FormEvent, Suspense, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { ApprovalBadge, PaymentBadge } from "@/components/TransactionBadges";
import { useAuth } from "@/lib/auth-context";
import { api, TransactionDetail } from "@/lib/api";
import { formatEUR } from "@/lib/format";

function TransactionDetailContent({ transactionId }: { transactionId: number }) {
  const t = useTranslations("ledger");
  const tCommon = useTranslations("common");
  const locale = useLocale();
  const { token, user } = useAuth();
  const router = useRouter();
  const canEdit = user?.role === "admin" || user?.role === "accountant";

  const [transaction, setTransaction] = useState<TransactionDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [paymentAmount, setPaymentAmount] = useState("");
  const [paymentDate, setPaymentDate] = useState("");
  const [paymentReference, setPaymentReference] = useState("");

  function refresh() {
    if (!token) return;
    api.getTransaction(token, transactionId).then(setTransaction).catch((e) => setError(e.message));
  }

  useEffect(refresh, [token, transactionId]);

  async function handleRecordPayment(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setError(null);
    try {
      await api.recordPayment(token, transactionId, {
        amount: paymentAmount,
        payment_date: paymentDate,
        reference: paymentReference || undefined,
      });
      setPaymentAmount("");
      setPaymentDate("");
      setPaymentReference("");
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("recordPaymentFailed"));
    }
  }

  async function handleApprove() {
    if (!token) return;
    try {
      await api.approveTransaction(token, transactionId);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("approveFailed"));
    }
  }

  if (!transaction) return <p className="text-text-secondary">{tCommon("loading")}</p>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <button onClick={() => router.push("/ledger")} className="text-sm text-navy hover:underline">
            {t("backToLedger")}
          </button>
          <h1 className="text-xl font-semibold text-navy mt-1">
            {transaction.transaction_type.replaceAll("_", " ")} · {transaction.counterparty_name ?? t("noCounterparty")}
          </h1>
        </div>
        <div className="flex gap-2">
          <ApprovalBadge status={transaction.approval_status} />
          <PaymentBadge status={transaction.payment_status} />
        </div>
      </div>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="card-v2 p-4">
          <p className="text-xs text-text-secondary">{t("netVatGross")}</p>
          <p className="text-lg font-semibold text-navy mt-1">
            {formatEUR(transaction.net_amount, locale)} / {formatEUR(transaction.vat_amount, locale)} / {formatEUR(transaction.gross_amount, locale)} {transaction.currency}
          </p>
        </div>
        <div className="card-v2 p-4">
          <p className="text-xs text-text-secondary">{t("paidRemaining")}</p>
          <p className="text-lg font-semibold text-navy mt-1">
            {formatEUR(transaction.amount_paid, locale)} / {formatEUR(transaction.remaining_balance, locale)}
          </p>
        </div>
        <div className="card-v2 p-4">
          <p className="text-xs text-text-secondary">{tCommon("date")}</p>
          <p className="text-sm text-navy mt-1">
            {t("invoiceDateLabel", { date: transaction.invoice_date })}
            {transaction.due_date && <> · {t("dueDateLabel", { date: transaction.due_date })}</>}
          </p>
        </div>
      </div>

      <div className="card-v2">
        <div className="px-5 py-3 border-b border-border-subtle">
          <h2 className="text-sm font-medium text-text-primary">{t("lineItems")}</h2>
        </div>
        <div className="overflow-x-auto">
        <table className="table-v3">
          <thead>
            <tr>
              <th>#</th>
              <th>{tCommon("description")}</th>
              <th className="text-right">{t("net")}</th>
              <th className="text-right">{t("rate")}</th>
              <th className="text-right">{t("vat")}</th>
              <th>{t("treatment")}</th>
              <th>{t("eligibility")}</th>
              <th className="text-right">{t("deductible")}</th>
            </tr>
          </thead>
          <tbody>
            {transaction.line_items.map((l) => (
              <tr key={l.line_number}>
                <td className="text-text-secondary">{l.line_number}</td>
                <td className="text-text-primary">{l.description ?? "—"}</td>
                <td className="col-amount">{formatEUR(l.net_amount, locale)}</td>
                <td className="text-right text-text-secondary">{l.vat_rate}%</td>
                <td className="col-amount">{formatEUR(l.vat_amount, locale)}</td>
                <td className="text-xs text-text-secondary">{l.vat_treatment.replaceAll("_", " ")}</td>
                <td className="text-xs text-text-secondary">{l.input_vat_eligibility ?? "—"}</td>
                <td className="col-amount">{l.deductible_vat_amount != null ? formatEUR(l.deductible_vat_amount, locale) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      </div>

      <div className="card-v2">
        <div className="px-5 py-3 border-b border-border-subtle">
          <h2 className="text-sm font-medium text-text-primary">{t("payments")}</h2>
        </div>
        {transaction.payments.length > 0 && (
          <div className="overflow-x-auto">
          <table className="table-v3">
            <tbody>
              {transaction.payments.map((p) => (
                <tr key={p.id}>
                  <td className="text-text-secondary">{p.payment_date}</td>
                  <td className="col-amount">{formatEUR(p.amount, locale)}</td>
                  <td className="text-text-secondary">{p.reference ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
        {canEdit && (
          <form onSubmit={handleRecordPayment} className="px-5 py-3 flex items-end gap-3 border-t border-border">
            <div className="space-y-1">
              <label className="text-xs font-medium text-text-secondary">{tCommon("amount")}</label>
              <input
                required
                value={paymentAmount}
                onChange={(e) => setPaymentAmount(e.target.value)}
                className="w-28 input-v2 px-2 py-1.5 text-sm"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-text-secondary">{tCommon("date")}</label>
              <input
                type="date"
                required
                value={paymentDate}
                onChange={(e) => setPaymentDate(e.target.value)}
                className="input-v2 px-2 py-1.5 text-sm"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-text-secondary">{t("reference")}</label>
              <input
                value={paymentReference}
                onChange={(e) => setPaymentReference(e.target.value)}
                className="input-v2 px-2 py-1.5 text-sm"
              />
            </div>
            <button
              type="submit"
              className="btn-primary-v2 px-4 py-2 text-sm"
            >
              {t("recordPayment")}
            </button>
          </form>
        )}
      </div>

      {canEdit && transaction.approval_status === "DRAFT" && (
        <button
          onClick={handleApprove}
          className="rounded-md bg-green-600 text-white px-4 py-2 text-sm font-medium hover:bg-green-700 transition-colors"
        >
          {t("approveTransaction")}
        </button>
      )}
    </div>
  );
}

function TransactionDetailRoute() {
  const params = useParams<{ id: string }>();
  return (
    <AuthGuard>
      <Shell>
        <TransactionDetailContent transactionId={Number(params.id)} />
      </Shell>
    </AuthGuard>
  );
}

export default function TransactionDetailPage() {
  return (
    <Suspense>
      <TransactionDetailRoute />
    </Suspense>
  );
}
