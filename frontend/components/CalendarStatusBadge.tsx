import { CalendarStatus } from "@/lib/api";

const STYLES: Record<CalendarStatus, string> = {
  completed: "bg-green-100 text-green-800",
  pending: "bg-amber-100 text-amber-800",
  upcoming: "bg-slate-100 text-slate-600",
  overdue: "bg-red-100 text-error",
};

export default function CalendarStatusBadge({ status }: { status: CalendarStatus }) {
  return (
    <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${STYLES[status]}`}>
      {status}
    </span>
  );
}
