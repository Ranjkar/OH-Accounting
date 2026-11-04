"use client";

import { FormEvent, Suspense, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { ApprovalBadge, PaymentBadge } from "@/components/TransactionBadges";
import { useAuth } from "@/lib/auth-context";
import { api, TransactionDetail } from "@/lib/api";

function TransactionDetailContent({ transactionId }: { transactionId: number }) {
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
      setError(err instanceof Error ? err.message : "Failed to record payment");
    }
  }

  async function handleApprove() {
    if (!token) return;
    try {
      await api.approveTransaction(token, transactionId);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to approve");
    }
  }

  if (!transaction) return <p className="text-text-secondary">Loading…</p>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <button onClick={() => router.push("/ledger")} className="text-sm text-navy hover:underline">
            ← Back to ledger
          </button>
          <h1 className="text-xl font-semibold text-navy mt-1">
            {transaction.transaction_type.replaceAll("_", " ")} · {transaction.counterparty_name ?? "No counterparty"}
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
          <p className="text-xs text-text-secondary">Net / VAT / Gross</p>
          <p className="text-lg font-semibold text-navy mt-1">
            {transaction.net_amount} / {transaction.vat_amount} / {transaction.gross_amount} {transaction.currency}
          </p>
        </div>
        <div className="card-v2 p-4">
          <p className="text-xs text-text-secondary">Paid / Remaining</p>
          <p className="text-lg font-semibold text-navy mt-1">
            {transaction.amount_paid} / {transaction.remaining_balance}
          </p>
        </div>
        <div className="card-v2 p-4">
          <p className="text-xs text-text-secondary">Dates</p>
          <p className="text-sm text-navy mt-1">
            Invoice {transaction.invoice_date}
            {transaction.due_date && <> · Due {transaction.due_date}</>}
          </p>
        </div>
      </div>

      <div className="card-v2">
        <div className="px-5 py-3 border-b border-border-subtle">
          <h2 className="text-sm font-medium text-text-primary">Line items</h2>
        </div>
        <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-text-secondary border-b border-border-subtle">
              <th className="px-5 py-2 font-medium">#</th>
              <th className="px-5 py-2 font-medium">Description</th>
              <th className="px-5 py-2 font-medium">Net</th>
              <th className="px-5 py-2 font-medium">Rate</th>
              <th className="px-5 py-2 font-medium">VAT</th>
              <th className="px-5 py-2 font-medium">Treatment</th>
              <th className="px-5 py-2 font-medium">Eligibility</th>
              <th className="px-5 py-2 font-medium">Deductible</th>
            </tr>
          </thead>
          <tbody>
            {transaction.line_items.map((l) => (
              <tr key={l.line_number} className="border-b border-border last:border-0">
                <td className="px-5 py-2.5">{l.line_number}</td>
                <td className="px-5 py-2.5">{l.description ?? "—"}</td>
                <td className="px-5 py-2.5">{l.net_amount}</td>
                <td className="px-5 py-2.5">{l.vat_rate}%</td>
                <td className="px-5 py-2.5">{l.vat_amount}</td>
                <td className="px-5 py-2.5 text-xs">{l.vat_treatment.replaceAll("_", " ")}</td>
                <td className="px-5 py-2.5 text-xs">{l.input_vat_eligibility ?? "—"}</td>
                <td className="px-5 py-2.5">{l.deductible_vat_amount ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      </div>

      <div className="card-v2">
        <div className="px-5 py-3 border-b border-border-subtle">
          <h2 className="text-sm font-medium text-text-primary">Payments</h2>
        </div>
        {transaction.payments.length > 0 && (
          <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <tbody>
              {transaction.payments.map((p) => (
                <tr key={p.id} className="border-b border-border last:border-0">
                  <td className="px-5 py-2">{p.payment_date}</td>
                  <td className="px-5 py-2">{p.amount}</td>
                  <td className="px-5 py-2 text-text-secondary">{p.reference ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
        {canEdit && (
          <form onSubmit={handleRecordPayment} className="px-5 py-3 flex items-end gap-3 border-t border-border">
            <div className="space-y-1">
              <label className="text-xs font-medium text-text-secondary">Amount</label>
              <input
                required
                value={paymentAmount}
                onChange={(e) => setPaymentAmount(e.target.value)}
                className="w-28 input-v2 px-2 py-1.5 text-sm"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-text-secondary">Date</label>
              <input
                type="date"
                required
                value={paymentDate}
                onChange={(e) => setPaymentDate(e.target.value)}
                className="input-v2 px-2 py-1.5 text-sm"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-text-secondary">Reference</label>
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
              Record payment
            </button>
          </form>
        )}
      </div>

      {canEdit && transaction.approval_status === "DRAFT" && (
        <button
          onClick={handleApprove}
          className="rounded-md bg-green-600 text-white px-4 py-2 text-sm font-medium hover:bg-green-700 transition-colors"
        >
          Approve transaction
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
