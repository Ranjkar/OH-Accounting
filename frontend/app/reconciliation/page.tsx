"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, BankTransactionDetail, Company } from "@/lib/api";
import { formatEUR } from "@/lib/format";

function ReconciliationContent() {
  const t = useTranslations("reconciliation");
  const tCommon = useTranslations("common");
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [queue, setQueue] = useState<BankTransactionDetail[]>([]);
  const [approvedQueue, setApprovedQueue] = useState<BankTransactionDetail[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [reasonById, setReasonById] = useState<Record<number, string>>({});

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  function loadQueue(reconciliationStatus: "SUGGESTED_MATCH" | "MATCHED", matchStatus: "SUGGESTED" | "APPROVED") {
    if (!token) return Promise.resolve([] as BankTransactionDetail[]);
    return api
      .listBankTransactions(token, { company_id: companyId ? Number(companyId) : undefined, reconciliation_status: reconciliationStatus })
      .then((txs) => Promise.all(txs.map((t) => api.getBankTransaction(token, t.id))))
      .then((details) => details.filter((d) => d.matches.some((m) => m.status === matchStatus)));
  }

  function refresh() {
    if (!token) return;
    loadQueue("SUGGESTED_MATCH", "SUGGESTED").then(setQueue).catch((e) => setError(e.message));
    loadQueue("MATCHED", "APPROVED").then(setApprovedQueue).catch((e) => setError(e.message));
  }

  useEffect(refresh, [token, companyId]);

  async function approve(matchId: number) {
    if (!token) return;
    try {
      await api.approveMatch(token, matchId);
      setMessage(t("matchApprovedMessage"));
      refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function reject(matchId: number) {
    if (!token) return;
    await api.rejectMatch(token, matchId);
    refresh();
  }

  async function reverse(matchId: number) {
    if (!token) return;
    const reason = reasonById[matchId];
    if (!reason) {
      setError(t("reasonRequiredError"));
      return;
    }
    try {
      await api.reverseMatch(token, matchId, reason);
      setMessage(t("matchReversedMessage"));
      refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function bulkApprove() {
    if (!token || !companyId) return;
    try {
      const approved = await api.bulkApproveHighConfidence(token, Number(companyId));
      setMessage(t("bulkApprovedMessage", { count: approved.length }));
      refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-text-primary">{t("title")}</h1>
        <button
          onClick={bulkApprove}
          disabled={!companyId}
          className="rounded-md bg-navy-solid text-white px-4 py-2 text-sm font-medium disabled:opacity-50"
        >
          {t("bulkApprove")}
        </button>
      </div>
      <p className="text-sm text-text-secondary">
        {t("explainer")}
      </p>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}
      {message && <div className="rounded-md bg-green-50 text-green-700 text-sm px-3 py-2">{message}</div>}

      <select
        value={companyId}
        aria-label={tCommon("company")}
        onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")}
        className="input-v2 px-3 py-2 text-sm"
      >
        <option value="">{tCommon("allCompanies")}</option>
        {companies.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </select>

      <div className="space-y-4">
        {queue.map((tx) => (
          <div key={tx.id} className="card-v2 p-4 space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span dir="ltr">
                {t("bankTxLabel", { id: tx.id })} · {tx.booking_date} · <span className="font-mono">{formatEUR(tx.amount)}</span> · {tx.counterparty_name ?? "—"}
              </span>
            </div>
            {tx.matches
              .filter((m) => m.status === "SUGGESTED")
              .map((m) => (
                <div key={m.id} className="rounded-md border border-border-subtle p-3 flex items-center justify-between gap-3 text-sm">
                  <div>
                    <p dir="ltr">
                      {t("invoiceLabel", { id: m.accounting_transaction_id })} · <span className="font-semibold">{m.confidence_level}</span> ({m.confidence_score})
                    </p>
                    <p className="text-xs text-text-secondary">{t("allocatedLabel", { amount: formatEUR(m.allocated_amount) })}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <button onClick={() => approve(m.id)} className="btn-primary-v2 px-3 py-1.5 text-xs">
                      {t("approve")}
                    </button>
                    <button onClick={() => reject(m.id)} className="input-v2 px-3 py-1.5 text-xs">
                      {t("reject")}
                    </button>
                  </div>
                </div>
              ))}
          </div>
        ))}
        {queue.length === 0 && <p className="text-sm text-text-secondary">{t("noneAwaitingReview")}</p>}
      </div>

      <h2 className="text-lg font-semibold text-text-primary mt-8">{t("approvedMatches")}</h2>
      <div className="space-y-4">
        {approvedQueue.map((tx) => (
          <div key={tx.id} className="card-v2 p-4 space-y-2">
            <div className="text-sm" dir="ltr">
              {t("bankTxLabel", { id: tx.id })} · {tx.booking_date} · <span className="font-mono">{formatEUR(tx.amount)}</span> · {tx.counterparty_name ?? "—"}
            </div>
            {tx.matches
              .filter((m) => m.status === "APPROVED")
              .map((m) => (
                <div key={m.id} className="rounded-md border border-border-subtle p-3 flex items-center justify-between gap-3 text-sm">
                  <p dir="ltr">
                    {t("invoiceLabel", { id: m.accounting_transaction_id })} · {t("allocatedShort", { amount: formatEUR(m.allocated_amount) })}
                  </p>
                  <div className="flex items-center gap-2">
                    <input
                      placeholder={t("reversalReason")}
                      value={reasonById[m.id] ?? ""}
                      onChange={(e) => setReasonById((prev) => ({ ...prev, [m.id]: e.target.value }))}
                      className="input-v2 px-2 py-1 text-xs w-32"
                    />
                    <button onClick={() => reverse(m.id)} className="input-v2 px-3 py-1.5 text-xs">
                      {t("reverse")}
                    </button>
                  </div>
                </div>
              ))}
          </div>
        ))}
        {approvedQueue.length === 0 && <p className="text-sm text-text-secondary">{t("noApprovedMatchesYet")}</p>}
      </div>
    </div>
  );
}

export default function ReconciliationPage() {
  return (
    <AuthGuard>
      <Shell>
        <ReconciliationContent />
      </Shell>
    </AuthGuard>
  );
}
