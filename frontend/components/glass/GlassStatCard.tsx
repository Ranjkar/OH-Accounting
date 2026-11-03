"use client";

import Link from "next/link";
import { ReactNode } from "react";

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

export default function GlassStatCard({ label, value, tone = "default", href, icon, trend }: GlassStatCardProps) {
  const content = (
    <div className="glass-panel card-v2-hover p-4 sm:p-5 h-full">
      <div className="flex items-start justify-between">
        <p className="text-xs text-text-secondary">{label}</p>
        {icon && <span className="text-brand-purple-500">{icon}</span>}
      </div>
      <p className={`text-2xl font-semibold mt-1.5 ${TONE_CLASS[tone]}`}>{value}</p>
      {trend && (
        <p className={`text-xs mt-1 ${trend.direction === "up" ? "value-positive" : "value-negative"}`}>
          {trend.direction === "up" ? "▲" : "▼"} {trend.label}
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
