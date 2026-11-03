"use client";

import { FormEvent, useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import GlassPageHeader from "@/components/glass/GlassPageHeader";
import GlassPanel from "@/components/glass/GlassPanel";
import GlassCard from "@/components/glass/GlassCard";
import GlassButton from "@/components/glass/GlassButton";
import { GlassInput, GlassSelect } from "@/components/glass/GlassInput";
import GlassTable from "@/components/glass/GlassTable";
import { GlassErrorState } from "@/components/glass/GlassLoadingState";
import { IconBank } from "@/components/glass/icons";
import { useAuth } from "@/lib/auth-context";
import { api, BankAccount, BankImportBatch, BankSourceFormat, Company } from "@/lib/api";

const SOURCE_FORMATS: BankSourceFormat[] = ["CAMT053", "CAMT054", "MT940", "CSV"];

function BankingContent() {
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [accounts, setAccounts] = useState<BankAccount[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null);
  const [batches, setBatches] = useState<BankImportBatch[]>([]);
  const [iban, setIban] = useState("");
  const [accountName, setAccountName] = useState("");
  const [sourceFormat, setSourceFormat] = useState<BankSourceFormat>("CAMT053");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  useEffect(() => {
    if (!token) return;
    api
      .listBankAccounts(token, companyId ? Number(companyId) : undefined)
      .then(setAccounts)
      .catch((e) => setError(e.message));
  }, [token, companyId]);

  useEffect(() => {
    if (!token || !selectedAccountId) return;
    api.listImportBatches(token, selectedAccountId).then(setBatches).catch((e) => setError(e.message));
  }, [token, selectedAccountId]);

  async function handleCreateAccount(e: FormEvent) {
    e.preventDefault();
    if (!token || !companyId) return;
    setError(null);
    try {
      await api.createBankAccount(token, { company_id: Number(companyId), iban, account_name: accountName });
      setIban("");
      setAccountName("");
      api.listBankAccounts(token, Number(companyId)).then(setAccounts);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function handleImport(e: FormEvent) {
    e.preventDefault();
    if (!token || !selectedAccountId || !file) return;
    setError(null);
    setMessage(null);
    try {
      const batch = await api.importBankStatement(token, selectedAccountId, sourceFormat, file);
      setMessage(`Imported ${batch.transaction_count} transaction(s), ${batch.duplicate_count} duplicate(s) skipped.`);
      setFile(null);
      api.listImportBatches(token, selectedAccountId).then(setBatches);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="space-y-5">
      <GlassPageHeader
        title="Banking"
        subtitle="Live bank API access is not connected. Import bank statement files (CAMT.053/054, MT940, or CSV) to bring transactions in -- nothing here ever reads or stores online-banking login credentials."
      />

      {error && <GlassErrorState message={error} />}
      {message && <div className="rounded-lg bg-green-500/10 border border-green-300/50 text-green-700 text-sm px-4 py-3">{message}</div>}

      <GlassSelect value={companyId} onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")}>
        <option value="">Select a company</option>
        {companies.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </GlassSelect>

      {companyId && (
        <GlassCard>
          <form onSubmit={handleCreateAccount} className="flex flex-wrap items-end gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-xs text-text-secondary">IBAN</label>
              <GlassInput required value={iban} onChange={(e) => setIban(e.target.value)} placeholder="NL91ABNA0417164300" />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-text-secondary">Account name</label>
              <GlassInput required value={accountName} onChange={(e) => setAccountName(e.target.value)} placeholder="Main business account" />
            </div>
            <GlassButton type="submit">Add bank account</GlassButton>
          </form>
        </GlassCard>
      )}

      <GlassPanel title="Bank Accounts">
        <GlassTable
          emptyMessage="No bank accounts yet."
          columns={[
            { key: "iban", header: "IBAN", render: (a) => <span className="font-mono text-xs">{a.iban}</span> },
            { key: "name", header: "Account name", render: (a) => a.account_name },
            { key: "status", header: "Status", render: (a) => <span className="text-xs text-text-secondary">{a.consent_status.replace(/_/g, " ")}</span> },
            {
              key: "action",
              header: "",
              render: (a) => (
                <button onClick={() => setSelectedAccountId(a.id)} className="text-brand-purple-600 hover:underline text-xs">
                  {selectedAccountId === a.id ? "Selected" : "Select"}
                </button>
              ),
            },
          ]}
          rows={accounts}
          rowKey={(a) => a.id}
        />
      </GlassPanel>

      {selectedAccountId && (
        <GlassCard className="space-y-4">
          <h2 className="font-medium text-text-primary flex items-center gap-2">
            <IconBank size={16} className="text-brand-purple-500" /> Import a statement file
          </h2>
          <form onSubmit={handleImport} className="flex flex-wrap items-end gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-xs text-text-secondary">Format</label>
              <GlassSelect value={sourceFormat} onChange={(e) => setSourceFormat(e.target.value as BankSourceFormat)}>
                {SOURCE_FORMATS.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </GlassSelect>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-text-secondary">File</label>
              <input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-sm" />
            </div>
            <GlassButton type="submit" disabled={!file}>
              Import
            </GlassButton>
          </form>

          <h3 className="font-medium text-text-primary text-sm pt-2 border-t border-white/40">Import history</h3>
          <GlassTable
            emptyMessage="No imports yet for this account."
            columns={[
              { key: "file", header: "File", render: (b) => b.original_filename },
              { key: "format", header: "Format", render: (b) => b.source_format },
              { key: "imported", header: "Imported", render: (b) => b.transaction_count },
              { key: "dup", header: "Duplicates", render: (b) => b.duplicate_count },
              { key: "errors", header: "Errors", render: (b) => (b.error_count > 0 ? <span className="value-negative">{b.error_count}</span> : 0) },
              { key: "when", header: "When", render: (b) => <span className="text-xs text-text-secondary">{new Date(b.imported_at).toLocaleString()}</span> },
            ]}
            rows={batches}
            rowKey={(b) => b.id}
          />
        </GlassCard>
      )}
    </div>
  );
}

export default function BankingPage() {
  return (
    <AuthGuard>
      <Shell>
        <BankingContent />
      </Shell>
    </AuthGuard>
  );
}
