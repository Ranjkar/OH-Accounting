import { TransactionApprovalStatus, TransactionPaymentStatus } from "@/lib/api";

const APPROVAL_STYLES: Record<TransactionApprovalStatus, string> = {
  DRAFT: "bg-slate-100 text-slate-600",
  APPROVED: "bg-green-100 text-green-800",
  LOCKED: "bg-navy text-white",
};

const PAYMENT_STYLES: Record<TransactionPaymentStatus, string> = {
  UNPAID: "bg-amber-100 text-amber-800",
  PARTIALLY_PAID: "bg-amber-100 text-amber-800",
  PAID: "bg-green-100 text-green-800",
  OVERDUE: "bg-red-100 text-error",
  UNKNOWN: "bg-slate-100 text-slate-600",
};

function Badge({ className, children }: { className: string; children: string }) {
  return <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${className}`}>{children}</span>;
}

export function ApprovalBadge({ status }: { status: TransactionApprovalStatus }) {
  return <Badge className={APPROVAL_STYLES[status]}>{status}</Badge>;
}

export function PaymentBadge({ status }: { status: TransactionPaymentStatus }) {
  return <Badge className={PAYMENT_STYLES[status]}>{status.replace("_", " ")}</Badge>;
}
