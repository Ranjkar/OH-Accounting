"use client";

import { ButtonHTMLAttributes, ReactNode } from "react";

interface GlassButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md";
  children: ReactNode;
}

const SIZE = { sm: "px-3 py-1.5 text-xs", md: "px-4 py-2 text-sm" };

export default function GlassButton({ variant = "primary", size = "md", className = "", children, ...rest }: GlassButtonProps) {
  const base = "inline-flex items-center justify-center gap-2 font-medium rounded-[0.6rem] disabled:opacity-50 disabled:cursor-not-allowed";
  const variantClass = {
    primary: "btn-primary-v2",
    secondary: "btn-secondary-v2",
    ghost: "text-text-secondary hover:text-text-primary hover:bg-white/50",
    danger: "bg-red-600 text-white hover:bg-red-700 shadow-sm",
  }[variant];
  return (
    <button className={`${base} ${SIZE[size]} ${variantClass} ${className}`} {...rest}>
      {children}
    </button>
  );
}
