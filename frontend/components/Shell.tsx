"use client";

import Link from "next/link";
import { ReactNode } from "react";
import { useAuth } from "@/lib/auth-context";
import GlassSidebar, { useMobileNav } from "@/components/glass/GlassSidebar";
import GlassNavSearch from "@/components/glass/GlassNavSearch";
import CompanySwitcher from "@/components/glass/CompanySwitcher";
import { IconMenu, IconPlus, IconBell } from "@/components/glass/icons";

export default function Shell({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const { mobileOpen, setMobileOpen } = useMobileNav();

  return (
    <div className="flex-1 flex app-shell-v2 min-h-screen">
      <GlassSidebar mobileOpen={mobileOpen} onMobileClose={() => setMobileOpen(false)} />

      <div className="flex-1 flex flex-col min-w-0">
        <header className="glass-panel m-3 mb-0 sm:m-4 sm:mb-0 px-3 sm:px-5 py-3 flex items-center justify-between gap-3 flex-shrink-0 relative z-30">
          <div className="flex items-center gap-3 min-w-0">
            <button
              onClick={() => setMobileOpen(true)}
              aria-label="Open navigation"
              className="lg:hidden text-text-secondary hover:text-text-primary p-1.5 -ml-1"
            >
              <IconMenu size={20} />
            </button>
            <div className="hidden sm:flex items-center gap-2 text-sm text-text-secondary min-w-0">
              <span className="truncate">
                Welcome back{user ? `, ${user.full_name.split(" ")[0]}` : ""}
              </span>
            </div>
            <CompanySwitcher />
          </div>

          <div className="hidden md:flex items-center flex-1 max-w-sm">
            <GlassNavSearch />
          </div>

          <div className="flex items-center gap-2 flex-shrink-0">
            <button
              aria-label="Notifications (none yet)"
              title="No notification feed is wired up yet"
              className="relative text-text-secondary hover:text-text-primary p-2 rounded-lg hover:bg-white/50"
            >
              <IconBell size={18} />
            </button>
            <Link href="/sales/upload" className="btn-primary-v2 px-3 sm:px-4 py-2 text-sm inline-flex items-center gap-1.5">
              <IconPlus size={15} />
              <span className="hidden sm:inline">Create invoice</span>
            </Link>
          </div>
        </header>
        <main className="flex-1 p-3 sm:p-4 lg:p-6">{children}</main>
      </div>
    </div>
  );
}
