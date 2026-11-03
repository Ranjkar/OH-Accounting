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
  const [authorizationUrl, setAuthorizationUrl] = useState<string | null>(null);
  const [obBusy, setObBusy] = useState(false);

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

  const selectedAccount = accounts.find((a) => a.id === selectedAccountId) ?? null;

  async function refreshSelectedAccount() {
    if (!token || !companyId) return;
    const refreshed = await api.listBankAccounts(token, Number(companyId));
    setAccounts(refreshed);
  }

  async function handleConnectOpenBanking() {
    if (!token || !selectedAccountId) return;
    setError(null);
    setObBusy(true);
    try {
      const { authorization_url } = await api.connectOpenBanking(token, selectedAccountId, window.location.href);
      setAuthorizationUrl(authorization_url);
      await refreshSelectedAccount();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setObBusy(false);
    }
  }

  async function handleCompleteOpenBanking() {
    if (!token || !selectedAccountId) return;
    setError(null);
    setObBusy(true);
    try {
      await api.completeOpenBanking(token, selectedAccountId);
      setAuthorizationUrl(null);
      setMessage("Sandbox consent completed -- connection is now CONNECTED.");
      await refreshSelectedAccount();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setObBusy(false);
    }
  }

  async function handleSyncOpenBanking() {
    if (!token || !selectedAccountId) return;
    setError(null);
    setObBusy(true);
    try {
      const batch = await api.syncOpenBanking(token, selectedAccountId);
      setMessage(`Synced ${batch.transaction_count} transaction(s), ${batch.duplicate_count} duplicate(s) skipped.`);
      await refreshSelectedAccount();
      api.listImportBatches(token, selectedAccountId).then(setBatches);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setObBusy(false);
    }
  }

  async function handleDisconnectOpenBanking() {
    if (!token || !selectedAccountId) return;
    setError(null);
    setObBusy(true);
    try {
      await api.disconnectOpenBanking(token, selectedAccountId);
      setAuthorizationUrl(null);
      await refreshSelectedAccount();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setObBusy(false);
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

      <GlassSelect aria-label="Company" value={companyId} onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")}>
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
              <label htmlFor="bank-iban" className="text-label-v2">IBAN</label>
              <GlassInput id="bank-iban" required value={iban} onChange={(e) => setIban(e.target.value)} placeholder="NL91ABNA0417164300" />
            </div>
            <div className="flex flex-col gap-1">
              <label htmlFor="bank-account-name" className="text-label-v2">Account name</label>
              <GlassInput id="bank-account-name" required value={accountName} onChange={(e) => setAccountName(e.target.value)} placeholder="Main business account" />
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

      {selectedAccount && (
        <GlassCard className="space-y-3">
          <h2 className="font-medium text-text-primary flex items-center gap-2">
            <IconBank size={16} className="text-brand-purple-500" /> Open Banking connection (sandbox stub provider)
          </h2>
          <p className="text-xs text-text-secondary">
            No authorised AISP agreement exists for this project yet -- see docs/open-banking.md. This connects to a stub
            provider for development; manual file import above always works regardless of connection status.
          </p>
          <div className="flex items-center gap-3 text-sm">
            <span className="text-text-secondary">Status:</span>
            <span className="inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium bg-brand-purple-500/10 text-brand-purple-700 border border-brand-purple-300/50">
              {selectedAccount.consent_status.replace(/_/g, " ")}
            </span>
            {selectedAccount.provider_name && <span className="text-text-secondary text-xs">via {selectedAccount.provider_name}</span>}
          </div>
          {selectedAccount.last_synced_at && (
            <p className="text-xs text-text-secondary">Last synced: {new Date(selectedAccount.last_synced_at).toLocaleString()}</p>
          )}
          {selectedAccount.last_sync_error && <p className="text-xs value-negative">Last sync error: {selectedAccount.last_sync_error}</p>}
          {authorizationUrl && (
            <p className="text-xs text-text-secondary break-all">
              Sandbox authorization URL (no real bank redirect for a stub provider): {authorizationUrl}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            {selectedAccount.consent_status === "NOT_CONNECTED" && (
              <GlassButton onClick={handleConnectOpenBanking} loading={obBusy}>
                Connect
              </GlassButton>
            )}
            {selectedAccount.consent_status === "PENDING" && (
              <GlassButton onClick={handleCompleteOpenBanking} loading={obBusy}>
                Complete sandbox consent
              </GlassButton>
            )}
            {selectedAccount.consent_status === "CONNECTED" && (
              <GlassButton onClick={handleSyncOpenBanking} loading={obBusy}>
                Sync now
              </GlassButton>
            )}
            {(selectedAccount.consent_status === "CONNECTED" || selectedAccount.consent_status === "PENDING") && (
              <GlassButton variant="outline" onClick={handleDisconnectOpenBanking} loading={obBusy}>
                Disconnect
              </GlassButton>
            )}
          </div>
        </GlassCard>
      )}

      {selectedAccountId && (
        <GlassCard className="space-y-4">
          <h2 className="font-medium text-text-primary flex items-center gap-2">
            <IconBank size={16} className="text-brand-purple-500" /> Import a statement file
          </h2>
          <form onSubmit={handleImport} className="flex flex-wrap items-end gap-3">
            <div className="flex flex-col gap-1">
              <label htmlFor="bank-source-format" className="text-label-v2">Format</label>
              <GlassSelect id="bank-source-format" value={sourceFormat} onChange={(e) => setSourceFormat(e.target.value as BankSourceFormat)}>
                {SOURCE_FORMATS.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </GlassSelect>
            </div>
            <div className="flex flex-col gap-1">
              <label htmlFor="bank-import-file" className="text-label-v2">File</label>
              <input id="bank-import-file" type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-sm" />
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
