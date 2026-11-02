import { VatPeriodStatus } from "@/lib/api";

const STYLES: Record<VatPeriodStatus, string> = {
  paid: "bg-green-100 text-green-800",
  filed: "bg-amber-100 text-amber-800",
  open: "bg-amber-100 text-amber-800",
};

const LABELS: Record<VatPeriodStatus, string> = {
  paid: "Paid",
  filed: "Filed",
  open: "Open",
};

export default function StatusBadge({ status }: { status: VatPeriodStatus }) {
  return (
    <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${STYLES[status]}`}>
      {LABELS[status]}
    </span>
  );
}
