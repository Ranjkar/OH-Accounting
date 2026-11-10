"use client";

import { HTMLAttributes, ReactNode } from "react";

interface GlassCardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  hover?: boolean;
  dark?: boolean;
  padding?: "none" | "sm" | "md" | "lg";
}

const PADDING = { none: "", sm: "p-3", md: "p-4 sm:p-5", lg: "p-6 sm:p-8" };

export default function GlassCard({ children, hover = false, dark = false, padding = "md", className = "", ...rest }: GlassCardProps) {
  return (
    <div
      className={`${dark ? "glass-panel-dark" : "glass-panel"} ${hover ? "card-v2-hover" : ""} ${PADDING[padding]} ${className}`}
      {...rest}
    >
      {children}
    </div>
  );
}
