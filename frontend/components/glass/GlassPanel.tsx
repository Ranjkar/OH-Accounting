"use client";

import { ReactNode } from "react";

interface GlassPanelProps {
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}

/** A glass panel with an optional header row -- for list/table sections. */
export default function GlassPanel({ title, subtitle, actions, children, className = "", bodyClassName = "" }: GlassPanelProps) {
  return (
    <div className={`glass-panel overflow-hidden ${className}`}>
      {(title || actions) && (
        <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-white/40">
          <div>
            {title && <h2 className="text-card-heading">{title}</h2>}
            {subtitle && <p className="text-helper-v2 mt-0.5">{subtitle}</p>}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      )}
      <div className={bodyClassName}>{children}</div>
    </div>
  );
}
