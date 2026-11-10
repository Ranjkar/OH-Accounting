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
        <h1 className="text-page-title">{title}</h1>
        {subtitle && <p className="text-secondary-v2 mt-1 max-w-3xl">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2 flex-wrap">{actions}</div>}
    </div>
  );
}
