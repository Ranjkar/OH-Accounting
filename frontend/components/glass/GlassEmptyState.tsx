"use client";

import { ReactNode } from "react";

interface GlassEmptyStateProps {
  title: string;
  description?: string;
  icon?: ReactNode;
  action?: ReactNode;
}

export default function GlassEmptyState({ title, description, icon, action }: GlassEmptyStateProps) {
  return (
    <div className="glass-panel p-10 flex flex-col items-center text-center gap-2">
      {icon && <div className="text-text-secondary opacity-60 mb-1">{icon}</div>}
      <p className="font-medium text-text-primary">{title}</p>
      {description && <p className="text-sm text-text-secondary max-w-sm">{description}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}
