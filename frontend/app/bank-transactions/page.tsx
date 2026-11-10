"use client";

import { useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { formatEUR } from "@/lib/format";
import { api, BankTransaction, BankTransactionDetail, Company, ReconciliationStatus } from "@/lib/api";

const STATUS_PILL_CLASS: Record<ReconciliationStatus, string> = {
  IMPORTED: "status-pill-neutral",
  UNMATCHED: "status-pill-warning",
  SUGGESTED_MATCH: "status-pill-info",
  MATCHED: "status-pill-success",
  PARTIALLY_MATCHED: "status-pill-warning",
  MANUALLY_RECONCILED: "status-pill-success",
  EXCLUDED: "status-pill-neutral",
};

const STATUS_FILTER_KEYS: { value: ReconciliationStatus | "all"; key: string }[] = [
  { value: "all", key: "all" },
  { value: "UNMATCHED", key: "unmatched" },
  { value: "SUGGESTED_MATCH", key: "suggestedMatch" },
  { value: "MATCHED", key: "matched" },
  { value: "PARTIALLY_MATCHED", key: "partiallyMatched" },
  { value: "EXCLUDED", key: "excluded" },
];

function BankTransactionsContent() {
  const t = useTranslations("banking");
  const tCommon = useTranslations("common");
  const locale = useLocale();
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [statusFilter, setStatusFilter] = useState<ReconciliationStatus | "all">("all");
  const [transactions, setTransactions] = useState<BankTransaction[]>([]);
  const [detail, setDetail] = useState<BankTransactionDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  function refresh() {
    if (!token) return;
    api
      .listBankTransactions(token, {
        company_id: companyId ? Number(companyId) : undefined,
        reconciliation_status: statusFilter === "all" ? undefined : statusFilter,
      })
      .then(setTransactions)
      .catch((e) => setError(e.message));
  }

  useEffect(refresh, [token, companyId, statusFilter]);

  async function openDetail(id: number) {
    if (!token) return;
    try {
      setDetail(await api.getBankTransaction(token, id));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function exclude(id: number) {
    if (!token) return;
    await api.excludeBankTransaction(token, id);
    refresh();
    setDetail(null);
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-text-primary">{t("title")}</h1>
      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="flex items-center gap-4">
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
        <div className="flex items-center gap-2 text-sm flex-wrap">
          {STATUS_FILTER_KEYS.map((f) => (
            <button
              key={f.value}
              onClick={() => setStatusFilter(f.value)}
              className={`rounded-full px-3 py-1 ${
                statusFilter === f.value ? "bg-navy-solid text-white" : "bg-surface-card border border-border text-text-secondary hover:bg-muted"
              }`}
            >
              {t(f.key as never)}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
        <div className="col-span-2 card-v2 overflow-hidden">
          <div className="overflow-x-auto">
          <table className="table-v3">
            <thead>
              <tr>
                <th>{tCommon("date")}</th>
                <th className="text-right">{tCommon("amount")}</th>
                <th>{t("counterparty")}</th>
                <th>{t("reference")}</th>
                <th>{tCommon("status")}</th>
              </tr>
            </thead>
            <tbody>
              {transactions.map((tx) => (
                <tr key={tx.id} className="cursor-pointer hover:bg-muted" onClick={() => openDetail(tx.id)}>
                  <td className="text-text-secondary">{tx.booking_date}</td>
                  <td className={`col-amount font-medium ${Number(tx.amount) < 0 ? "value-negative" : "value-positive"}`}>{formatEUR(tx.amount, locale)}</td>
                  <td className="text-text-primary">{tx.counterparty_name ?? "—"}</td>
                  <td className="text-xs text-text-secondary">{tx.payment_reference ?? "—"}</td>
                  <td><span className={`status-pill ${STATUS_PILL_CLASS[tx.reconciliation_status]}`}>{tx.reconciliation_status.replace(/_/g, " ").toLowerCase()}</span></td>
                </tr>
              ))}
              {transactions.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-4 text-text-secondary">
                    {t("noTransactionsMatchFilters")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          </div>
        </div>

        <div className="card-v2 p-4">
          {detail ? (
            <div className="space-y-3 text-sm">
              <h3 className="font-medium text-text-primary">{t("transactionNumber", { id: detail.id })}</h3>
              <p>{tCommon("amount")}: <span className="font-mono">{formatEUR(detail.amount, locale)}</span></p>
              <p>{tCommon("status")}: {detail.reconciliation_status}</p>
              <p>{t("counterparty")}: {detail.counterparty_name ?? "—"}</p>
              <p>{t("iban")}: <span dir="ltr">{detail.counterparty_iban ?? "—"}</span></p>
              <h4 className="font-medium text-navy mt-3">{t("candidateMatches")}</h4>
              {detail.matches.length === 0 && <p className="text-text-secondary">{t("noMatchesFound")}</p>}
              {detail.matches.map((m) => (
                <div key={m.id} className="rounded-md border border-border-subtle p-2">
                  <p>{t("invoiceMatchLine", { id: m.accounting_transaction_id, level: m.confidence_level, score: m.confidence_score })}</p>
                  <p className="text-xs text-text-secondary">{t("allocated")}: {formatEUR(m.allocated_amount, locale)} · {tCommon("status")}: {m.status}</p>
                </div>
              ))}
              {detail.reconciliation_status !== "EXCLUDED" && (
                <button onClick={() => exclude(detail.id)} className="input-v2 px-3 py-1.5 text-xs">
                  {t("excludeFromReconciliation")}
                </button>
              )}
              <p className="text-xs text-text-secondary">{t("goToReconciliationHint")}</p>
            </div>
          ) : (
            <p className="text-sm text-text-secondary">{t("selectTransactionToSeeDetails")}</p>
          )}
        </div>
      </div>
    </div>
  );
}

export default function BankTransactionsPage() {
  return (
    <AuthGuard>
      <Shell>
        <BankTransactionsContent />
      </Shell>
    </AuthGuard>
  );
}
