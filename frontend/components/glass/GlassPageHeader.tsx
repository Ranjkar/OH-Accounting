"use client";

import { ReactNode } from "react";

interface GlassPageHeaderProps {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}

export default function GlassPageHeader({ title, subtitle, actions }: GlassPageHeaderProps) {
  return (
    <div className="flex items-start sm:items-center justify-between gap-3 flex-wrap">
      <div>
        <h1 className="text-2xl font-semibold text-text-primary">{title}</h1>
        {subtitle && <p className="text-sm text-text-secondary mt-1">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2 flex-wrap">{actions}</div>}
    </div>
  );
}
