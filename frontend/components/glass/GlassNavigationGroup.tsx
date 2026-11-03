"use client";

import Link from "next/link";
import { ComponentType, SVGProps } from "react";
import { IconChevronDown } from "./icons";
import type { NavLeaf } from "./navConfig";

interface GlassNavigationGroupProps {
  label: string;
  icon: ComponentType<SVGProps<SVGSVGElement> & { size?: number }>;
  items: NavLeaf[];
  open: boolean;
  onToggle: () => void;
  collapsedRail: boolean;
  isActive: (href: string) => boolean;
  onNavigate?: () => void;
}

export default function GlassNavigationGroup({ label, icon: Icon, items, open, onToggle, collapsedRail, isActive, onNavigate }: GlassNavigationGroupProps) {
  const groupHasActive = items.some((i) => i.href && isActive(i.href));

  if (collapsedRail) {
    return (
      <div className="relative group px-2">
        <button
          type="button"
          onClick={onToggle}
          title={label}
          aria-label={label}
          className={`nav-item-v2 w-full flex items-center justify-center p-2.5 ${groupHasActive ? "active" : ""}`}
        >
          <Icon size={18} />
        </button>
        {/* Flyout on hover for collapsed rail */}
        <div className="absolute left-full top-0 ml-2 hidden group-hover:block z-50 min-w-[14rem] glass-panel-dark p-2">
          <p className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-text-on-dark-secondary">{label}</p>
          {items.map((item) => (
            <NavLeafLink key={item.label} item={item} active={!!item.href && isActive(item.href)} onNavigate={onNavigate} />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="w-full flex items-center gap-2.5 px-3 py-2 text-left"
      >
        <Icon size={16} className="text-text-on-dark-secondary flex-shrink-0" />
        <span className="flex-1 text-[11px] font-semibold uppercase tracking-wider text-text-on-dark-secondary truncate">{label}</span>
        <IconChevronDown size={14} className={`text-text-on-dark-secondary transition-transform duration-150 ${open ? "" : "-rotate-90"}`} />
      </button>
      {open && (
        <div className="space-y-0.5 pb-1">
          {items.map((item) => (
            <NavLeafLink key={item.label} item={item} active={!!item.href && isActive(item.href)} onNavigate={onNavigate} />
          ))}
        </div>
      )}
    </div>
  );
}

function NavLeafLink({ item, active, onNavigate }: { item: NavLeaf; active: boolean; onNavigate?: () => void }) {
  if (item.unavailable) {
    return (
      <div
        title={item.unavailable}
        aria-disabled="true"
        className="flex items-center gap-2.5 pl-9 pr-3 py-1.5 text-sm text-[#5b5770] cursor-not-allowed"
      >
        <span className="truncate">{item.label}</span>
        <span className="text-[9px] uppercase tracking-wide bg-white/5 text-[#8b87a0] rounded px-1.5 py-0.5 flex-shrink-0">Soon</span>
      </div>
    );
  }
  return (
    <Link
      href={item.href!}
      onClick={onNavigate}
      className={`nav-item-v2 flex items-center gap-2.5 pl-9 pr-3 py-1.5 text-sm ${active ? "active" : ""}`}
      aria-current={active ? "page" : undefined}
    >
      <span className="truncate">{item.label}</span>
    </Link>
  );
}
