"use client";

import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import GlassTable from "@/components/glass/GlassTable";
import { Contract } from "@/lib/api";
import { formatDate, formatEUR } from "@/lib/format";
import { ContractStatusPill, SigningStatusPill } from "./ContractStatusPill";

export function feeLabel(c: Pick<Contract, "monthly_fee" | "fee_description">, locale: string, t: (key: "perMonth" | "feeUnset", values?: Record<string, string>) => string): string {
  if (c.monthly_fee !== null) return t("perMonth", { amount: formatEUR(c.monthly_fee, locale) });
  return c.fee_description ?? t("feeUnset");
}

export default function ContractsTable({ rows, showCompany = true }: { rows: Contract[]; showCompany?: boolean }) {
  const t = useTranslations("contracts");
  const locale = useLocale();
  const router = useRouter();
  const columns = [
    { key: "reference", header: t("columns.reference"), render: (c: Contract) => <span className="font-medium text-text-primary" dir="ltr">{c.reference}</span> },
    ...(showCompany ? [{ key: "company", header: t("columns.company"), render: (c: Contract) => <span>{c.company_name ?? c.company_id}</span> }] : []),
    { key: "status", header: t("columns.status"), render: (c: Contract) => (
      <span className="inline-flex flex-wrap gap-1"><ContractStatusPill status={c.status} />{c.renewal_disabled && <span className="status-pill status-pill-neutral">{t("renewalDisabledBadge")}</span>}</span>
    ) },
    { key: "term", header: t("columns.term"), render: (c: Contract) => <span className="whitespace-nowrap">{formatDate(c.start_date, locale)} – {formatDate(c.end_date, locale)}</span> },
    { key: "fee", header: t("columns.fee"), render: (c: Contract) => <span>{feeLabel(c, locale, t as never)}</span> },
    { key: "signing", header: t("columns.signing"), render: (c: Contract) => <SigningStatusPill status={c.signing_status} /> },
    { key: "expiry", header: t("columns.expiry"), render: (c: Contract) => (
      <span className="whitespace-nowrap">{formatDate(c.end_date, locale)}{c.days_until_expiry !== null && <span className="block text-xs text-text-secondary">{t("expiresIn", { n: c.days_until_expiry })}</span>}</span>
    ) },
  ];
  return <GlassTable columns={columns} rows={rows} rowKey={(c) => c.id} onRowClick={(c) => router.push(`/contracts/${c.id}`)} emptyMessage={t("empty")} />;
}
