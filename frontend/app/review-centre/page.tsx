"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import GlassPageHeader from "@/components/glass/GlassPageHeader";
import GlassPanel from "@/components/glass/GlassPanel";
import GlassButton from "@/components/glass/GlassButton";
import { GlassSelect } from "@/components/glass/GlassInput";
import GlassTable from "@/components/glass/GlassTable";
import GlassLoadingState, { GlassErrorState } from "@/components/glass/GlassLoadingState";
import { useAuth } from "@/lib/auth-context";
import { useCompany } from "@/lib/company-context";
import { api, AnomalyFlag, BankTransaction, DocumentSummary } from "@/lib/api";
import { formatEUR } from "@/lib/format";

function AcknowledgeDismiss({ anomaly, onChange }: { anomaly: AnomalyFlag; onChange: (a: AnomalyFlag) => void }) {
  const { token } = useAuth();
  const [busy, setBusy] = useState(false);

  async function act(action: "acknowledge" | "dismiss") {
    if (!token) return;
    setBusy(true);
    try {
      const updated = action === "acknowledge" ? await api.acknowledgeAnomaly(token, anomaly.id) : await api.dismissAnomaly(token, anomaly.id);
      onChange(updated);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex gap-2">
      <button disabled={busy} onClick={() => act("acknowledge")} className="text-xs text-brand-purple-600 hover:underline disabled:opacity-50">
        Acknowledge
      </button>
      <button disabled={busy} onClick={() => act("dismiss")} className="text-xs text-text-secondary hover:underline disabled:opacity-50">
        Dismiss
      </button>
    </div>
  );
}

function ReviewCentreContent() {
  const { token } = useAuth();
  const { companies, selectedCompanyId, setSelectedCompanyId } = useCompany();
  const companyId = selectedCompanyId ?? "";
  const setCompanyId = (id: number | "") => setSelectedCompanyId(id === "" ? null : id);
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [anomalies, setAnomalies] = useState<AnomalyFlag[]>([]);
  const [suggestedMatches, setSuggestedMatches] = useState<BankTransaction[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function loadQueues(id: number) {
    if (!token) return;
    setError(null);
    setLoading(true);
    Promise.all([
      api.listDocuments(token, { company_id: id, status_filter: "needs_review" }),
      api.listDocuments(token, { company_id: id, status_filter: "extracted" }),
      api.listAnomalies(token, id, "OPEN"),
      api.listBankTransactions(token, { company_id: id, reconciliation_status: "SUGGESTED_MATCH" }),
    ])
      .then(([needsReview, extracted, anomalyFlags, matches]) => {
        setDocuments([...needsReview, ...extracted]);
        setAnomalies(anomalyFlags);
        setSuggestedMatches(matches);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    if (!token || !companyId) return;
    // Loading the review queues for a newly selected company -- syncing to
    // the companyId change, not derivable during render.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadQueues(Number(companyId));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, companyId]);

  return (
    <div className="space-y-5">
      <GlassPageHeader
        title="Review & Approval Centre"
        subtitle="Everything in this company that is waiting on a human decision -- documents with extracted data to confirm, anomaly flags to investigate, and bank transactions with a suggested match to approve. Nothing here is approved or dismissed automatically."
      />

      {error && <GlassErrorState message={error} />}

      <GlassSelect aria-label="Company" value={companyId} onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")}>
        <option value="">Select a company</option>
        {companies.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </GlassSelect>

      {loading && <GlassLoadingState />}

      {companyId && !loading && (
        <>
          <GlassPanel title={`Documents awaiting review (${documents.length})`}>
            <GlassTable
              emptyMessage="No documents waiting on review for this company."
              columns={[
                { key: "file", header: "File", render: (d) => d.original_filename },
                { key: "type", header: "Type", render: (d) => d.document_type ?? "Unclassified" },
                { key: "status", header: "Status", render: (d) => <span className="text-xs text-text-secondary">{d.status.replace(/_/g, " ")}</span> },
                {
                  key: "confidence",
                  header: "Confidence",
                  render: (d) => (d.classification_confidence != null ? `${Math.round(d.classification_confidence * 100)}%` : "—"),
                },
                { key: "action", header: "", render: (d) => <Link href={`/documents/${d.id}`} className="text-xs text-brand-purple-600 hover:underline">Review →</Link> },
              ]}
              rows={documents}
              rowKey={(d) => d.id}
            />
          </GlassPanel>

          <GlassPanel title={`Anomaly flags to investigate (${anomalies.length})`}>
            <GlassTable
              emptyMessage="No open anomaly flags for this company."
              columns={[
                { key: "rule", header: "Rule", render: (a) => <span className="font-mono text-xs">{a.rule_code}</span> },
                { key: "severity", header: "Severity", render: (a) => <span className={a.severity === "critical" ? "value-negative" : a.severity === "warning" ? "value-warning" : "text-text-secondary"}>{a.severity}</span> },
                { key: "message", header: "Reason", render: (a) => <span className="text-xs">{a.message}</span> },
                { key: "action", header: "", render: (a) => <AcknowledgeDismiss anomaly={a} onChange={(updated) => setAnomalies((prev) => prev.filter((x) => x.id !== updated.id))} /> },
              ]}
              rows={anomalies}
              rowKey={(a) => a.id}
            />
          </GlassPanel>

          <GlassPanel title={`Suggested bank-transaction matches (${suggestedMatches.length})`}>
            <GlassTable
              emptyMessage="No suggested matches awaiting approval."
              columns={[
                { key: "date", header: "Date", render: (t) => t.booking_date },
                { key: "amount", header: "Amount", render: (t) => <span className="font-mono text-xs">{formatEUR(t.amount)} {t.currency}</span> },
                { key: "counterparty", header: "Counterparty", render: (t) => t.counterparty_name ?? "—" },
                { key: "action", header: "", render: () => <Link href="/reconciliation" className="text-xs text-brand-purple-600 hover:underline">Review in Reconciliation →</Link> },
              ]}
              rows={suggestedMatches}
              rowKey={(t) => t.id}
            />
          </GlassPanel>

          <GlassPanel title="Other review queues">
            <ul className="text-sm space-y-2">
              <li><Link href="/loonheffingen" className="text-brand-purple-600 hover:underline">Payroll tax declarations</Link> -- Draft/Validation/Review/Approval lifecycle</li>
              <li><Link href="/vat" className="text-brand-purple-600 hover:underline">VAT returns</Link> -- open vs. filed periods</li>
              <li><Link href="/batches" className="text-brand-purple-600 hover:underline">Upload batches</Link> -- bulk document processing status</li>
            </ul>
          </GlassPanel>

          <div className="flex justify-end">
            <GlassButton variant="outline" onClick={() => loadQueues(Number(companyId))}>
              Refresh
            </GlassButton>
          </div>
        </>
      )}
    </div>
  );
}

export default function ReviewCentrePage() {
  return (
    <AuthGuard>
      <Shell>
        <ReviewCentreContent />
      </Shell>
    </AuthGuard>
  );
}
