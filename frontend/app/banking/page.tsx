"use client";

import { FormEvent, useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
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
import { navigateAway } from "@/lib/navigation";
import { api, BankAccount, BankImportBatch, BankSourceFormat, Company, OpenBankingBank, OpenBankingStatus, ProviderAccountCandidate } from "@/lib/api";

const SOURCE_FORMATS: BankSourceFormat[] = ["CAMT053", "CAMT054", "MT940", "CSV"];

function BankingContent() {
  const t = useTranslations("banking");
  const locale = useLocale();
  const tCommon = useTranslations("common");
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
  const [obStatus, setObStatus] = useState<OpenBankingStatus | null>(null);
  const [banks, setBanks] = useState<OpenBankingBank[] | null>(null);
  const [bankQuery, setBankQuery] = useState("");
  const [candidates, setCandidates] = useState<ProviderAccountCandidate[] | null>(null);
  const [chosenCandidate, setChosenCandidate] = useState<string | null>(null);

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  // Which adapter is live is shown before anyone is asked to consent to
  // anything -- a sandbox connection must never look like a real one.
  useEffect(() => {
    if (token) api.openBankingStatus(token).then(setObStatus).catch(() => setObStatus(null));
  }, [token]);

  // The bank redirects back to /banking?ob_account=<id>&<provider params>.
  // Finish the consent with exactly those params, then clean the address bar
  // so a reload cannot replay the one-time callback.
  useEffect(() => {
    if (!token) return;
    const params = new URLSearchParams(window.location.search);
    const accountId = Number(params.get("ob_account"));
    const returned = params.has("stub_consent_id") || params.has("code") || params.has("error");
    if (!Number.isInteger(accountId) || accountId <= 0 || !returned) return;
    const callbackParams: Record<string, unknown> = {};
    params.forEach((value, key) => {
      if (key !== "ob_account") callbackParams[key] = value;
    });
    window.history.replaceState(null, "", "/banking");
    api
      .completeOpenBanking(token, accountId, callbackParams)
      .then(({ candidates: pending }) => {
        setSelectedAccountId(accountId);
        setCandidates(pending.length ? pending : null);
        setMessage(pending.length ? t("chooseAccount") : t("connectedOk"));
        return api.listBankAccounts(token, companyId ? Number(companyId) : undefined).then(setAccounts);
      })
      .catch((e) => setError(e instanceof Error ? e.message : t("connectFailed")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
    try {
      const res = await api.listBanks(token);
      setBanks(res.banks);
      setBankQuery("");
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function searchBanks(query: string) {
    setBankQuery(query);
    if (!token) return;
    try {
      const res = await api.listBanks(token, query || undefined);
      setBanks(res.banks);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function pickBank(bankId: string) {
    if (!token || !selectedAccountId) return;
    setError(null);
    setObBusy(true);
    try {
      // The account id rides along in our own redirect URI so the return
      // trip knows which consent to finish; the backend only accepts
      // same-origin redirect URIs.
      const redirectUri = `${window.location.origin}/banking?ob_account=${selectedAccountId}`;
      const { authorization_url } = await api.connectOpenBanking(token, selectedAccountId, redirectUri, bankId);
      setAuthorizationUrl(authorization_url);
      // The authorization URL is the bank's consent screen; the sandbox stub
      // redirects straight back here carrying its consent id.
      navigateAway(authorization_url);
    } catch (e) {
      setError((e as Error).message);
      setObBusy(false);
    }
  }

  async function handleCompleteOpenBanking() {
    if (!token || !selectedAccountId) return;
    setError(null);
    setObBusy(true);
    try {
      const { candidates: pending } = await api.completeOpenBanking(token, selectedAccountId);
      setCandidates(pending.length ? pending : null);
      setAuthorizationUrl(null);
      setMessage(pending.length ? t("chooseAccount") : t("sandboxConsentCompleted"));
      await refreshSelectedAccount();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setObBusy(false);
    }
  }

  async function chooseCandidate(providerAccountId: string) {
    if (!token || !selectedAccountId) return;
    setError(null);
    setObBusy(true);
    try {
      await api.selectOpenBankingAccount(token, selectedAccountId, providerAccountId);
      setCandidates(null);
      setMessage(t("connectedOk"));
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
      setMessage(t("syncedResult", { count: batch.transaction_count, duplicates: batch.duplicate_count }));
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
      setMessage(t("importedResult", { count: batch.transaction_count, duplicates: batch.duplicate_count }));
      setFile(null);
      api.listImportBatches(token, selectedAccountId).then(setBatches);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="space-y-5">
      <GlassPageHeader
        title={t("accountsPageTitle")}
        subtitle={t("accountsPageSubtitle")}
      />

      {error && <GlassErrorState message={error} />}
      {message && <div className="rounded-lg bg-green-500/10 border border-green-300/50 text-green-700 text-sm px-4 py-3">{message}</div>}
      {obStatus && (
        <p
          className={`text-xs px-3 py-2 rounded-md border ${obStatus.is_sandbox ? "bg-amber-50 border-amber-200 text-pending" : "bg-green-50 border-green-200 text-green-700"}`}
          role="status"
        >
          {obStatus.is_sandbox ? t("sandboxNotice") : t("liveNotice", { provider: obStatus.provider })}
        </p>
      )}

      <GlassSelect aria-label={tCommon("company")} value={companyId} onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")}>
        <option value="">{tCommon("selectCompany")}</option>
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
              <label htmlFor="bank-iban" className="text-label-v2">{t("iban")}</label>
              <GlassInput id="bank-iban" dir="ltr" required value={iban} onChange={(e) => setIban(e.target.value)} placeholder="NL91ABNA0417164300" />
            </div>
            <div className="flex flex-col gap-1">
              <label htmlFor="bank-account-name" className="text-label-v2">{t("accountName")}</label>
              <GlassInput id="bank-account-name" required value={accountName} onChange={(e) => setAccountName(e.target.value)} placeholder={t("accountNamePlaceholder")} />
            </div>
            <GlassButton type="submit">{t("addBankAccount")}</GlassButton>
          </form>
        </GlassCard>
      )}

      <GlassPanel title={t("bankAccountsTitle")}>
        <GlassTable
          emptyMessage={t("noBankAccountsYet")}
          columns={[
            { key: "iban", header: t("iban"), render: (a) => <span className="font-mono text-xs" dir="ltr">{a.iban}</span> },
            { key: "name", header: t("accountName"), render: (a) => a.account_name },
            { key: "status", header: tCommon("status"), render: (a) => <span className="text-xs text-text-secondary">{a.consent_status.replace(/_/g, " ")}</span> },
            {
              key: "action",
              header: "",
              render: (a) => (
                <button onClick={() => setSelectedAccountId(a.id)} className="text-brand-purple-600 hover:underline text-xs">
                  {selectedAccountId === a.id ? t("selected") : t("select")}
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
            <IconBank size={16} className="text-brand-purple-500" /> {t("openBankingConnectionTitle")}
          </h2>
          <p className="text-xs text-text-secondary">
            {t("openBankingConnectionDescription")}
          </p>
          <div className="flex items-center gap-3 text-sm">
            <span className="text-text-secondary">{tCommon("status")}:</span>
            <span className="inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium bg-brand-purple-500/10 text-brand-purple-700 border border-brand-purple-300/50">
              {selectedAccount.consent_status.replace(/_/g, " ")}
            </span>
            {selectedAccount.provider_name && <span className="text-text-secondary text-xs">{t("viaProvider", { provider: selectedAccount.provider_name })}</span>}
          </div>
          {selectedAccount.consent_status === "CONNECTED" && selectedAccount.consent_expires_at && (
            <p className="text-xs text-text-secondary">
              {t("consentExpires", { date: new Date(selectedAccount.consent_expires_at).toLocaleDateString(locale) })}
            </p>
          )}
          {selectedAccount.last_synced_at && (
            <p className="text-xs text-text-secondary">{t("lastSynced", { date: new Date(selectedAccount.last_synced_at).toLocaleString(locale) })}</p>
          )}
          {selectedAccount.last_sync_error && <p className="text-xs value-negative">{t("lastSyncError", { message: selectedAccount.last_sync_error })}</p>}
          {authorizationUrl && (
            <p className="text-xs text-text-secondary break-all">
              {t("sandboxAuthUrlLabel")} <span dir="ltr">{authorizationUrl}</span>
            </p>
          )}

          {(candidates ?? selectedAccount.pending_provider_accounts) && (
            <div className="space-y-2 rounded-md border border-border p-3">
              <p className="text-sm font-medium text-text-primary">{t("chooseAccount")}</p>
              <div className="space-y-2">
                {(candidates ?? selectedAccount.pending_provider_accounts)!.map((c) => (
                  <label key={c.provider_account_id} className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
                    <input
                      type="radio"
                      name="ob-candidate"
                      value={c.provider_account_id}
                      checked={chosenCandidate === c.provider_account_id}
                      onChange={() => setChosenCandidate(c.provider_account_id)}
                      className="h-4 w-4"
                    />
                    <span className="text-text-primary">{c.account_name}</span>
                    <span className="text-xs text-text-secondary font-mono" dir="ltr">
                      {c.iban_masked} · {c.currency}
                    </span>
                  </label>
                ))}
              </div>
              <GlassButton onClick={() => chosenCandidate && chooseCandidate(chosenCandidate)} disabled={!chosenCandidate} loading={obBusy}>
                {t("selectAccountButton")}
              </GlassButton>
            </div>
          )}

          {banks !== null && (
            <div className="space-y-2 rounded-md border border-border p-3">
              <div className="space-y-1">
                <label htmlFor="ob-bank-search" className="text-label-v2">{t("chooseBank")}</label>
                <input
                  id="ob-bank-search"
                  value={bankQuery}
                  onChange={(e) => void searchBanks(e.target.value)}
                  placeholder={t("bankSearchPlaceholder")}
                  className="input-v2 px-3 py-2 text-sm w-full"
                />
              </div>
              <ul className="max-h-56 overflow-y-auto divide-y divide-border-subtle">
                {banks.map((b) => (
                  <li key={b.id}>
                    <button
                      type="button"
                      onClick={() => void pickBank(b.id)}
                      disabled={obBusy}
                      className="w-full text-start px-3 py-2 hover:bg-muted disabled:opacity-50 flex flex-wrap items-center justify-between gap-x-3"
                    >
                      <span className="text-sm font-medium text-text-primary">{b.name}</span>
                      <span className="text-xs text-text-secondary font-mono" dir="ltr">{b.bic}</span>
                    </button>
                  </li>
                ))}
                {banks.length === 0 && <li className="px-3 py-2 text-sm text-text-secondary">{t("noBanksFound")}</li>}
              </ul>
              <button type="button" onClick={() => setBanks(null)} disabled={obBusy} className="btn-outline-v2 px-3 py-1.5 text-xs disabled:opacity-50">
                {tCommon("cancel")}
              </button>
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            {selectedAccount.consent_status === "NOT_CONNECTED" && (
              <GlassButton onClick={handleConnectOpenBanking} loading={obBusy}>
                {t("connect")}
              </GlassButton>
            )}
            {selectedAccount.consent_status === "PENDING" && (
              <GlassButton onClick={handleCompleteOpenBanking} loading={obBusy}>
                {t("completeSandboxConsent")}
              </GlassButton>
            )}
            {selectedAccount.consent_status === "CONNECTED" && (
              <GlassButton onClick={handleSyncOpenBanking} loading={obBusy}>
                {t("syncNow")}
              </GlassButton>
            )}
            {(selectedAccount.consent_status === "CONNECTED" || selectedAccount.consent_status === "PENDING") && (
              <GlassButton variant="outline" onClick={handleDisconnectOpenBanking} loading={obBusy}>
                {t("disconnect")}
              </GlassButton>
            )}
          </div>
        </GlassCard>
      )}

      {selectedAccountId && (
        <GlassCard className="space-y-4">
          <h2 className="font-medium text-text-primary flex items-center gap-2">
            <IconBank size={16} className="text-brand-purple-500" /> {t("importStatementFileTitle")}
          </h2>
          <form onSubmit={handleImport} className="flex flex-wrap items-end gap-3">
            <div className="flex flex-col gap-1">
              <label htmlFor="bank-source-format" className="text-label-v2">{t("format")}</label>
              <GlassSelect id="bank-source-format" value={sourceFormat} onChange={(e) => setSourceFormat(e.target.value as BankSourceFormat)}>
                {SOURCE_FORMATS.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </GlassSelect>
            </div>
            <div className="flex flex-col gap-1">
              <label htmlFor="bank-import-file" className="text-label-v2">{t("file")}</label>
              <input id="bank-import-file" type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-sm" />
            </div>
            <GlassButton type="submit" disabled={!file}>
              {t("importStatement")}
            </GlassButton>
          </form>

          <h3 className="font-medium text-text-primary text-sm pt-2 border-t border-border">{t("importHistory")}</h3>
          <GlassTable
            emptyMessage={t("noImportsYet")}
            columns={[
              { key: "file", header: t("file"), render: (b) => b.original_filename },
              { key: "format", header: t("format"), render: (b) => b.source_format },
              { key: "imported", header: t("imported"), render: (b) => b.transaction_count },
              { key: "dup", header: t("duplicates"), render: (b) => b.duplicate_count },
              { key: "errors", header: t("errors"), render: (b) => (b.error_count > 0 ? <span className="value-negative">{b.error_count}</span> : 0) },
              { key: "when", header: t("when"), render: (b) => <span className="text-xs text-text-secondary">{new Date(b.imported_at).toLocaleString(locale)}</span> },
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
