"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ReactNode } from "react";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/auth-context";
import GlassSidebar, { useMobileNav } from "@/components/glass/GlassSidebar";
import GlassNavSearch from "@/components/glass/GlassNavSearch";
import CompanySwitcher from "@/components/glass/CompanySwitcher";
import ThemeToggle from "@/components/glass/ThemeToggle";
import LanguageSelector from "@/components/glass/LanguageSelector";
import { IconMenu, IconPlus, IconBell, IconArrowLeft, IconArrowRight } from "@/components/glass/icons";

export default function Shell({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const { mobileOpen, setMobileOpen } = useMobileNav();
  const router = useRouter();
  const t = useTranslations("shell");

  return (
    <div className="flex-1 flex app-shell-v2 min-h-screen">
      <GlassSidebar mobileOpen={mobileOpen} onMobileClose={() => setMobileOpen(false)} />

      <div className="flex-1 flex flex-col min-w-0">
        <header className="h-[68px] border-b border-border bg-surface-page px-3 sm:px-5 flex items-center justify-between gap-3 flex-shrink-0 relative z-30">
          <div className="flex items-center gap-2 min-w-0">
            <button
              onClick={() => setMobileOpen(true)}
              aria-label={t("openNavigation")}
              className="lg:hidden text-text-secondary hover:text-text-primary p-1.5 -ms-1"
            >
              <IconMenu size={20} />
            </button>
            <div className="hidden lg:flex items-center gap-0.5 text-text-secondary">
              <button onClick={() => router.back()} aria-label={t("goBack")} className="p-1.5 rounded-lg hover:bg-muted hover:text-text-primary">
                <IconArrowLeft size={16} className="icon-directional" />
              </button>
              <button onClick={() => router.forward()} aria-label={t("goForward")} className="p-1.5 rounded-lg hover:bg-muted hover:text-text-primary">
                <IconArrowRight size={16} className="icon-directional" />
              </button>
            </div>
            <div className="hidden lg:block w-px h-5 bg-border mx-1" aria-hidden />
            <div className="hidden sm:flex items-center gap-2 text-sm text-text-secondary min-w-0">
              <span className="truncate">
                {t("welcomeBack", { name: user ? user.full_name.split(" ")[0] : "none" })}
              </span>
            </div>
            <CompanySwitcher />
          </div>

          <div className="hidden md:flex items-center flex-1 max-w-sm">
            <GlassNavSearch />
          </div>

          <div className="flex items-center gap-1.5 sm:gap-2 flex-shrink-0">
            <div className="hidden lg:block">
              <LanguageSelector compact />
            </div>
            <div className="hidden sm:block">
              <ThemeToggle compact />
            </div>
            <button
              aria-label={t("notifications")}
              title={t("notificationsUnavailable")}
              className="relative text-text-secondary hover:text-text-primary p-2 rounded-lg hover:bg-muted"
            >
              <IconBell size={18} />
            </button>
            <Link href="/sales/upload" className="btn-primary-v2 px-3 sm:px-4 py-2 text-sm inline-flex items-center gap-1.5">
              <IconPlus size={15} />
              <span className="hidden sm:inline">{t("createInvoice")}</span>
            </Link>
          </div>
        </header>
        <main className="flex-1 p-3 sm:p-4 lg:p-6">{children}</main>
      </div>
    </div>
  );
}
