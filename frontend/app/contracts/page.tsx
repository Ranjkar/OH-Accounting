"use client";

import { FormEvent, Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import GlassPageHeader from "@/components/glass/GlassPageHeader";
import GlassPanel from "@/components/glass/GlassPanel";
import GlassStatCard from "@/components/glass/GlassStatCard";
import GlassButton from "@/components/glass/GlassButton";
import GlassModal from "@/components/glass/GlassModal";
import GlassEmptyState from "@/components/glass/GlassEmptyState";
import GlassLoadingState, { GlassErrorState } from "@/components/glass/GlassLoadingState";
import { GlassInput, GlassSelect } from "@/components/glass/GlassInput";
import ContractsTable from "@/components/contracts/ContractsTable";
import { useAuth } from "@/lib/auth-context";
import { useCompany } from "@/lib/company-context";
import { api, ApiError, CONTRACT_SIGNING_STATUSES, CONTRACT_STATUSES, Contract, ContractLanguage, ContractListFilters, ContractSigningStatus, ContractStatus } from "@/lib/api";

const CAN_CREATE = new Set(["owner", "admin", "accountant"]);
const CAN_ADMIN = new Set(["owner", "admin"]);

function ContractsContent() {
  const t = useTranslations("contracts");
  const tCommon = useTranslations("common");
  const { token, user } = useAuth();
  const { companies } = useCompany();
  const router = useRouter();
  const search = useSearchParams();
  const [rows, setRows] = useState<Contract[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [disabled, setDisabled] = useState(false);
  const [filters, setFilters] = useState<ContractListFilters>({ company_id: Number(search.get("company")) || undefined });
  const [createOpen, setCreateOpen] = useState(search.get("new") === "1");
  const [createCompany, setCreateCompany] = useState<number | "">(Number(search.get("company")) || "");
  const [createLanguage, setCreateLanguage] = useState<ContractLanguage>("nl");
  const [createStart, setCreateStart] = useState(new Date().toISOString().slice(0, 10));
  const [createBusy, setCreateBusy] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    api.listContracts(token, filters).then(setRows).catch((e) => {
      if (e instanceof ApiError && e.status === 404) setDisabled(true);
      else setError(e instanceof ApiError ? e.message : t("loadFailed"));
    });
  }, [token, filters, t]);

  useEffect(load, [load]);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    if (!token || !createCompany) return;
    setCreateBusy(true);
    setCreateError(null);
    try {
      const created = await api.createContract(token, { company_id: Number(createCompany), language: createLanguage, start_date: createStart });
      router.push(`/contracts/${created.id}`);
    } catch (err) {
      setCreateError(err instanceof ApiError ? err.message : t("create.failed"));
    } finally {
      setCreateBusy(false);
    }
  }

  if (disabled) {
    return (
      <div className="space-y-5">
        <GlassPageHeader title={t("title")} subtitle={t("subtitle")} />
        <GlassEmptyState title={t("featureDisabled")} description={t("featureDisabledHelp")} />
      </div>
    );
  }

  const count = (pred: (c: Contract) => boolean) => rows?.filter(pred).length ?? 0;

  return (
    <div className="space-y-5">
      <GlassPageHeader
        title={t("title")}
        subtitle={t("subtitle")}
        actions={
          <>
            {user && CAN_ADMIN.has(user.role) && <Link href="/contracts/templates" className="btn-secondary-v2 px-4 py-2 text-sm rounded-[0.6rem]">{t("templatesLink")}</Link>}
            {user && CAN_CREATE.has(user.role) && <GlassButton onClick={() => setCreateOpen(true)}>{t("newContract")}</GlassButton>}
          </>
        }
      />

      {error && <GlassErrorState message={error} />}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <GlassStatCard label={t("stats.awaiting")} value={count((c) => c.signing_status === "awaiting" || c.signing_status === "viewed")} tone="warning" />
        <GlassStatCard label={t("stats.renewalDue")} value={count((c) => c.status === "RENEWAL_DUE")} tone="warning" />
        <GlassStatCard label={t("stats.active")} value={count((c) => c.status === "ACTIVE" || c.status === "RENEWAL_DUE")} tone="success" />
        <GlassStatCard label={t("stats.drafts")} value={count((c) => c.status === "DRAFT" || c.status === "PENDING_APPROVAL" || c.status === "READY_TO_SEND")} />
      </div>

      <GlassPanel>
        <form className="px-4 sm:px-5 py-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3" onSubmit={(e) => e.preventDefault()}>
          <label className="space-y-1 text-xs font-medium text-text-secondary">
            <span>{t("filters.company")}</span>
            <GlassSelect value={filters.company_id ?? ""} onChange={(e) => setFilters({ ...filters, company_id: e.target.value ? Number(e.target.value) : undefined })} className="w-full">
              <option value="">{t("filters.all")}</option>
              {companies.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </GlassSelect>
          </label>
          <label className="space-y-1 text-xs font-medium text-text-secondary">
            <span>{t("filters.status")}</span>
            <GlassSelect value={filters.status ?? ""} onChange={(e) => setFilters({ ...filters, status: e.target.value as ContractStatus | "" })} className="w-full">
              <option value="">{t("filters.all")}</option>
              {CONTRACT_STATUSES.map((s) => <option key={s} value={s}>{t(`status.${s}`)}</option>)}
            </GlassSelect>
          </label>
          <label className="space-y-1 text-xs font-medium text-text-secondary">
            <span>{t("filters.signingStatus")}</span>
            <GlassSelect value={filters.signing_status ?? ""} onChange={(e) => setFilters({ ...filters, signing_status: e.target.value as ContractSigningStatus | "" })} className="w-full">
              <option value="">{t("filters.all")}</option>
              {CONTRACT_SIGNING_STATUSES.map((s) => <option key={s} value={s}>{t(`signing.${s}`)}</option>)}
            </GlassSelect>
          </label>
          <label className="space-y-1 text-xs font-medium text-text-secondary">
            <span>{t("filters.expiresAfter")}</span>
            <GlassInput type="date" value={filters.expires_after ?? ""} onChange={(e) => setFilters({ ...filters, expires_after: e.target.value || undefined })} />
          </label>
          <label className="space-y-1 text-xs font-medium text-text-secondary">
            <span>{t("filters.expiresBefore")}</span>
            <GlassInput type="date" value={filters.expires_before ?? ""} onChange={(e) => setFilters({ ...filters, expires_before: e.target.value || undefined })} />
          </label>
          <div className="sm:col-span-2 lg:col-span-5 flex justify-end">
            <button type="button" onClick={() => setFilters({})} className="text-xs text-navy hover:underline">{t("filters.reset")}</button>
          </div>
        </form>
        {rows === null ? <div className="p-5"><GlassLoadingState /></div> : <ContractsTable rows={rows} />}
      </GlassPanel>

      <GlassModal open={createOpen} onClose={() => setCreateOpen(false)} title={t("create.title")}>
        <form onSubmit={handleCreate} className="space-y-4" id="contract-create-form">
          <p className="text-sm text-text-secondary">{t("create.help")}</p>
          {createError && <GlassErrorState message={createError} />}
          <div className="space-y-1">
            <label htmlFor="contract-create-company" className="text-xs font-medium text-text-secondary">{t("create.company")}</label>
            <GlassSelect id="contract-create-company" required value={createCompany} onChange={(e) => setCreateCompany(e.target.value ? Number(e.target.value) : "")} className="w-full">
              <option value="">{tCommon("selectCompany")}</option>
              {companies.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </GlassSelect>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="space-y-1">
              <label htmlFor="contract-create-language" className="text-xs font-medium text-text-secondary">{t("create.language")}</label>
              <GlassSelect id="contract-create-language" value={createLanguage} onChange={(e) => setCreateLanguage(e.target.value as ContractLanguage)} className="w-full">
                <option value="nl">{t("languages.nl")}</option>
                <option value="en">{t("languages.en")}</option>
              </GlassSelect>
            </div>
            <div className="space-y-1">
              <label htmlFor="contract-create-start" className="text-xs font-medium text-text-secondary">{t("create.startDate")}</label>
              <GlassInput id="contract-create-start" type="date" required value={createStart} onChange={(e) => setCreateStart(e.target.value)} />
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <GlassButton type="button" variant="ghost" onClick={() => setCreateOpen(false)}>{tCommon("cancel")}</GlassButton>
            <GlassButton type="submit" loading={createBusy} disabled={!createCompany}>{t("create.submit")}</GlassButton>
          </div>
        </form>
      </GlassModal>
    </div>
  );
}

export default function ContractsPage() {
  return (
    <AuthGuard>
      <Shell>
        <Suspense>
          <ContractsContent />
        </Suspense>
      </Shell>
    </AuthGuard>
  );
}
