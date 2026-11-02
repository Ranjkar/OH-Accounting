"use client";

import { FormEvent, useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
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
      setMessage(
        `Imported ${batch.transaction_count} transaction(s), ${batch.duplicate_count} duplicate(s) skipped.`
      );
      setFile(null);
      api.listImportBatches(token, selectedAccountId).then(setBatches);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-navy">Banking</h1>
      <p className="text-sm text-slate-500">
        Live bank API access is not connected. Import bank statement files (CAMT.053/054, MT940, or CSV) to bring
        transactions in -- nothing here ever reads or stores online-banking login credentials.
      </p>

      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}
      {message && <div className="rounded-md bg-green-50 text-green-700 text-sm px-3 py-2">{message}</div>}

      <select
        value={companyId}
        onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")}
        className="rounded-md border border-slate-300 px-3 py-2 text-sm"
      >
        <option value="">Select a company</option>
        {companies.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </select>

      {companyId && (
        <form onSubmit={handleCreateAccount} className="bg-white rounded-lg border border-slate-200 p-4 flex items-end gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-slate-500">IBAN</label>
            <input
              required
              value={iban}
              onChange={(e) => setIban(e.target.value)}
              className="rounded-md border border-slate-300 px-3 py-2 text-sm"
              placeholder="NL91ABNA0417164300"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-slate-500">Account name</label>
            <input
              required
              value={accountName}
              onChange={(e) => setAccountName(e.target.value)}
              className="rounded-md border border-slate-300 px-3 py-2 text-sm"
              placeholder="Main business account"
            />
          </div>
          <button type="submit" className="rounded-md bg-navy text-white px-4 py-2 text-sm font-medium">
            Add bank account
          </button>
        </form>
      )}

      <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-slate-500 border-b border-slate-200">
              <th className="px-5 py-2 font-medium">IBAN</th>
              <th className="px-5 py-2 font-medium">Account name</th>
              <th className="px-5 py-2 font-medium">Status</th>
              <th className="px-5 py-2 font-medium" />
            </tr>
          </thead>
          <tbody>
            {accounts.map((a) => (
              <tr
                key={a.id}
                className={`border-b border-slate-100 last:border-0 hover:bg-slate-50 cursor-pointer ${
                  selectedAccountId === a.id ? "bg-slate-50" : ""
                }`}
                onClick={() => setSelectedAccountId(a.id)}
              >
                <td className="px-5 py-2.5 font-mono text-xs">{a.iban}</td>
                <td className="px-5 py-2.5">{a.account_name}</td>
                <td className="px-5 py-2.5 text-xs text-slate-500">{a.consent_status}</td>
                <td className="px-5 py-2.5 text-navy text-xs">Select</td>
              </tr>
            ))}
            {accounts.length === 0 && (
              <tr>
                <td colSpan={4} className="px-5 py-4 text-slate-500">
                  No bank accounts yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {selectedAccountId && (
        <div className="bg-white rounded-lg border border-slate-200 p-4 space-y-4">
          <h2 className="font-medium text-navy">Import a statement file</h2>
          <form onSubmit={handleImport} className="flex items-end gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-xs text-slate-500">Format</label>
              <select
                value={sourceFormat}
                onChange={(e) => setSourceFormat(e.target.value as BankSourceFormat)}
                className="rounded-md border border-slate-300 px-3 py-2 text-sm"
              >
                {SOURCE_FORMATS.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-slate-500">File</label>
              <input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-sm" />
            </div>
            <button type="submit" disabled={!file} className="rounded-md bg-navy text-white px-4 py-2 text-sm font-medium disabled:opacity-50">
              Import
            </button>
          </form>

          <h3 className="font-medium text-navy text-sm">Import history</h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b border-slate-200">
                <th className="px-2 py-2 font-medium">File</th>
                <th className="px-2 py-2 font-medium">Format</th>
                <th className="px-2 py-2 font-medium">Imported</th>
                <th className="px-2 py-2 font-medium">Duplicates</th>
                <th className="px-2 py-2 font-medium">Errors</th>
                <th className="px-2 py-2 font-medium">When</th>
              </tr>
            </thead>
            <tbody>
              {batches.map((b) => (
                <tr key={b.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-2 py-2">{b.original_filename}</td>
                  <td className="px-2 py-2">{b.source_format}</td>
                  <td className="px-2 py-2">{b.transaction_count}</td>
                  <td className="px-2 py-2">{b.duplicate_count}</td>
                  <td className="px-2 py-2">{b.error_count > 0 ? <span className="text-error">{b.error_count}</span> : 0}</td>
                  <td className="px-2 py-2 text-xs text-slate-500">{new Date(b.imported_at).toLocaleString()}</td>
                </tr>
              ))}
              {batches.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-2 py-3 text-slate-500">
                    No imports yet for this account.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
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
