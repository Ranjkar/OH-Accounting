"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import GlassNavigationGroup from "./GlassNavigationGroup";
import { EMPLOYEE_ROLE_NAV_GROUPS, NAV_GROUPS, PLATFORM_ADMIN_NAV_GROUP } from "./navConfig";
import { IconCollapse, IconExpand, IconLogout, IconX } from "./icons";

const OPEN_GROUPS_KEY = "onholland.nav.openGroups";
const COLLAPSED_KEY = "onholland.nav.collapsed";

interface GlassSidebarProps {
  mobileOpen: boolean;
  onMobileClose: () => void;
}

export default function GlassSidebar({ mobileOpen, onMobileClose }: GlassSidebarProps) {
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({});
  const [hydrated, setHydrated] = useState(false);

  const baseGroups = user?.role === "employee" ? EMPLOYEE_ROLE_NAV_GROUPS : NAV_GROUPS;
  const groups = user?.is_platform_admin ? [...baseGroups, PLATFORM_ADMIN_NAV_GROUP] : baseGroups;

  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  // Reading persisted UI prefs from localStorage after mount, and
  // auto-expanding the active route's group on navigation, are both
  // one-shot syncs from an external system (the browser's storage / the
  // router) into local UI state -- not state that can be derived during
  // render, since localStorage isn't available during SSR. Intentional,
  // not the "replicate derivable state" anti-pattern the lint rule targets.
  useEffect(() => {
    try {
      const storedCollapsed = localStorage.getItem(COLLAPSED_KEY);
      const storedOpen = localStorage.getItem(OPEN_GROUPS_KEY);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      if (storedCollapsed) setCollapsed(storedCollapsed === "1");
      if (storedOpen) {
        setOpenGroups(JSON.parse(storedOpen));
      } else {
        const activeGroup = groups.find((g) => g.items.some((i) => i.href && isActive(i.href)));
        setOpenGroups(activeGroup ? { [activeGroup.label]: true } : { [groups[0]?.label]: true });
      }
    } catch {
      // localStorage unavailable (private mode etc.) -- fall back to all-open for the active group only.
    } finally {
      setHydrated(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-expand whichever group contains the current route, every navigation.
  useEffect(() => {
    if (!hydrated) return;
    const activeGroup = groups.find((g) => g.items.some((i) => i.href && isActive(i.href)));
    if (activeGroup && !openGroups[activeGroup.label]) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setOpenGroups((prev) => ({ ...prev, [activeGroup.label]: true }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname, hydrated]);

  function toggleGroup(label: string) {
    setOpenGroups((prev) => {
      const next = { ...prev, [label]: !prev[label] };
      try {
        localStorage.setItem(OPEN_GROUPS_KEY, JSON.stringify(next));
      } catch {
        /* ignore */
      }
      return next;
    });
  }

  function toggleCollapsed() {
    setCollapsed((c) => {
      try {
        localStorage.setItem(COLLAPSED_KEY, c ? "0" : "1");
      } catch {
        /* ignore */
      }
      return !c;
    });
  }

  const content = (
    <>
      <div className="flex items-center gap-2 px-4 py-5 flex-shrink-0">
        <div className="w-8 h-8 rounded-lg hero-gradient-v2 flex items-center justify-center text-sm font-bold text-white flex-shrink-0">O</div>
        {!collapsed && <span className="font-semibold tracking-tight text-sidebar-text">OnHolland</span>}
        <button onClick={onMobileClose} aria-label="Close navigation" className="ml-auto lg:hidden text-sidebar-text-secondary hover:text-sidebar-text p-1">
          <IconX size={18} />
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto glass-scroll px-2 space-y-1 pb-4" aria-label="Main navigation">
        {groups.map((group) => (
          <GlassNavigationGroup
            key={group.label}
            label={group.label}
            icon={group.icon}
            items={group.items}
            open={!!openGroups[group.label]}
            onToggle={() => toggleGroup(group.label)}
            collapsedRail={collapsed}
            isActive={isActive}
            onNavigate={onMobileClose}
          />
        ))}
      </nav>

      <div className="px-2 pb-4 pt-2 border-t border-sidebar-border space-y-1 flex-shrink-0">
        {user && (
          <div className={`flex items-center gap-2.5 px-3 py-2 ${collapsed ? "justify-center" : ""}`}>
            <div className="w-7 h-7 rounded-full bg-navy text-white text-xs font-semibold flex items-center justify-center flex-shrink-0">
              {user.full_name.slice(0, 1).toUpperCase()}
            </div>
            {!collapsed && (
              <div className="min-w-0">
                <p className="text-sm text-sidebar-text truncate">{user.full_name}</p>
                <p className="text-xs text-sidebar-text-secondary truncate capitalize">{user.role}</p>
              </div>
            )}
          </div>
        )}
        <button onClick={logout} className="nav-item-v2 w-full flex items-center gap-2.5 px-3 py-2 text-sm text-left">
          <IconLogout size={16} className="flex-shrink-0" />
          {!collapsed && <span>Log out</span>}
        </button>
        <button
          onClick={toggleCollapsed}
          className="nav-item-v2 hidden lg:flex w-full items-center gap-2.5 px-3 py-2 text-sm text-left"
          aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
        >
          {collapsed ? <IconExpand size={16} /> : <IconCollapse size={16} />}
          {!collapsed && <span>Collapse</span>}
        </button>
      </div>
    </>
  );

  return (
    <>
      {/* Desktop/tablet rail */}
      <aside
        className={`nav-rail-v2 hidden lg:flex flex-col flex-shrink-0 transition-all duration-150 ${collapsed ? "w-16" : "w-72"}`}
      >
        {content}
      </aside>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <div className="absolute inset-0 bg-black/50" onClick={onMobileClose} aria-hidden />
          <aside className="nav-rail-v2 relative flex flex-col w-72 h-full">{content}</aside>
        </div>
      )}
    </>
  );
}

export function useMobileNav() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const pathname = usePathname();
  // Closing the drawer on navigation syncs UI state to the router, an
  // external system -- not state derivable during render.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMobileOpen(false);
  }, [pathname]);
  return { mobileOpen, setMobileOpen };
}
