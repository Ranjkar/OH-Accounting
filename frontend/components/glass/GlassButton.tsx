"use client";

import { ButtonHTMLAttributes, ReactNode } from "react";

interface GlassButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "outline" | "ghost" | "danger" | "success";
  size?: "sm" | "md";
  loading?: boolean;
  children: ReactNode;
}

const SIZE = { sm: "px-3 py-1.5 text-xs", md: "px-4 py-2 text-sm" };

const VARIANT_CLASS: Record<string, string> = {
  primary: "btn-primary-v2",
  secondary: "btn-secondary-v2",
  outline: "btn-outline-v2",
  ghost: "btn-ghost-v2",
  danger: "btn-danger-v2",
  success: "btn-success-v2",
};

function Spinner() {
  return (
    <svg className="animate-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="3" opacity="0.25" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

export default function GlassButton({ variant = "primary", size = "md", loading = false, className = "", children, disabled, ...rest }: GlassButtonProps) {
  const base = "inline-flex items-center justify-center gap-2 font-medium rounded-[0.6rem] disabled:opacity-50 disabled:cursor-not-allowed";
  return (
    <button
      className={`${base} ${SIZE[size]} ${VARIANT_CLASS[variant]} ${className}`}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading && <Spinner />}
      {children}
    </button>
  );
}
