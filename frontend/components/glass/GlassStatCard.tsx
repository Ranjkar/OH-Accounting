"use client";

import Link from "next/link";
import { ReactNode } from "react";
import { IconAlertTriangle, IconCheckCircle } from "./icons";

interface GlassStatCardProps {
  label: string;
  value: string | number;
  tone?: "default" | "warning" | "error" | "success";
  href?: string;
  icon?: ReactNode;
  trend?: { direction: "up" | "down"; label: string } | null;
}

const TONE_CLASS: Record<string, string> = {
  default: "text-text-primary",
  warning: "value-warning",
  error: "value-negative",
  success: "value-positive",
};

// Never rely on colour alone to communicate status: a non-default tone
// also gets an icon, same principle as the ▲/▼ trend indicators below.
const TONE_ICON: Partial<Record<string, ReactNode>> = {
  warning: <IconAlertTriangle size={14} />,
  error: <IconAlertTriangle size={14} />,
  success: <IconCheckCircle size={14} />,
};

export default function GlassStatCard({ label, value, tone = "default", href, icon, trend }: GlassStatCardProps) {
  const content = (
    <div className="glass-panel card-v2-hover p-4 sm:p-5 h-full">
      <div className="flex items-start justify-between">
        <p className="text-label-v2">{label}</p>
        {icon && <span className="text-brand-purple-500" aria-hidden="true">{icon}</span>}
      </div>
      <p className={`mt-1.5 flex items-center gap-1.5 text-2xl font-semibold tabular-nums ${TONE_CLASS[tone]}`}>
        {TONE_ICON[tone] && <span aria-hidden="true">{TONE_ICON[tone]}</span>}
        {value}
      </p>
      {trend && (
        <p className={`text-helper-v2 mt-1 ${trend.direction === "up" ? "value-positive" : "value-negative"}`}>
          <span aria-hidden="true">{trend.direction === "up" ? "▲" : "▼"}</span> {trend.label}
        </p>
      )}
    </div>
  );
  return href ? (
    <Link href={href} className="block h-full">
      {content}
    </Link>
  ) : (
    content
  );
}
