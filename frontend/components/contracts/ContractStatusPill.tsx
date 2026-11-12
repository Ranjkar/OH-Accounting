"use client";

import { useTranslations } from "next-intl";
import { ContractSigningStatus, ContractStatus } from "@/lib/api";

const STATUS_TONE: Record<ContractStatus, string> = {
  DRAFT: "status-pill-neutral",
  PENDING_APPROVAL: "status-pill-warning",
  READY_TO_SEND: "status-pill-info",
  SENT: "status-pill-info",
  VIEWED: "status-pill-info",
  SIGNED: "status-pill-success",
  ACTIVE: "status-pill-success",
  RENEWAL_DUE: "status-pill-warning",
  EXPIRED: "status-pill-neutral",
  CANCELLED: "status-pill-danger",
  TERMINATED: "status-pill-danger",
};

const SIGNING_TONE: Record<ContractSigningStatus, string> = {
  not_sent: "status-pill-neutral",
  awaiting: "status-pill-warning",
  viewed: "status-pill-info",
  signed: "status-pill-success",
  expired: "status-pill-danger",
  withdrawn: "status-pill-neutral",
};

export function ContractStatusPill({ status }: { status: ContractStatus }) {
  const t = useTranslations("contracts.status");
  return <span className={`status-pill ${STATUS_TONE[status]}`}>{t(status)}</span>;
}

export function SigningStatusPill({ status }: { status: ContractSigningStatus }) {
  const t = useTranslations("contracts.signing");
  return <span className={`status-pill ${SIGNING_TONE[status]}`}>{t(status)}</span>;
}
