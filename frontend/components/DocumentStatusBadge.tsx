import { DocumentStatus } from "@/lib/api";

const STYLES: Record<DocumentStatus, string> = {
  pending: "bg-slate-100 text-slate-600",
  processing: "bg-slate-100 text-slate-600",
  extracted: "bg-amber-100 text-amber-800",
  needs_review: "bg-amber-200 text-amber-900",
  approved: "bg-green-100 text-green-800",
  rejected: "bg-red-100 text-error",
  failed: "bg-red-100 text-error",
};

const LABELS: Record<DocumentStatus, string> = {
  pending: "Pending",
  processing: "Processing…",
  extracted: "Ready for review",
  needs_review: "Needs review",
  approved: "Approved",
  rejected: "Rejected",
  failed: "Failed",
};

export default function DocumentStatusBadge({ status }: { status: DocumentStatus }) {
  return (
    <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${STYLES[status]}`}>
      {LABELS[status]}
    </span>
  );
}
