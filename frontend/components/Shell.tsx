"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode, useState } from "react";
import { useAuth } from "@/lib/auth-context";

interface NavItem {
  href: string;
  label: string;
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    label: "Main",
    items: [
      { href: "/", label: "Dashboard" },
      { href: "/companies", label: "Companies" },
      { href: "/documents", label: "Documents" },
      { href: "/banking", label: "Banking" },
      { href: "/bank-transactions", label: "Transactions" },
      { href: "/reconciliation", label: "Reconciliation" },
    ],
  },
  {
    label: "Accounting",
    items: [
      { href: "/sales/upload", label: "Sales invoices" },
      { href: "/purchases/upload", label: "Purchase invoices" },
      { href: "/batches", label: "Batches" },
      { href: "/ledger", label: "General ledger" },
      { href: "/vat", label: "VAT returns" },
      { href: "/profit-and-loss", label: "Profit & Loss" },
      { href: "/balance-sheet", label: "Balance Sheet" },
      { href: "/budgets", label: "Budgets" },
    ],
  },
  {
    label: "Tax & payroll",
    items: [
      { href: "/tax-centre", label: "Tax Centre" },
      { href: "/tax-optimization", label: "Tax Optimisation" },
      { href: "/legal-structure", label: "Legal Structure Calculator" },
      { href: "/employees", label: "Employees" },
      { href: "/payroll", label: "Salarisadministratie" },
      { href: "/working-hours", label: "Working Hours" },
      { href: "/entrepreneur-hours", label: "Entrepreneur Hours" },
    ],
  },
  {
    label: "Intelligence",
    items: [
      { href: "/assistant", label: "AI Assistant" },
      { href: "/automation", label: "Automation Centre" },
      { href: "/cash-flow", label: "Cash Flow" },
      { href: "/forecasts", label: "Forecasts" },
      { href: "/scenarios", label: "Scenario Planning" },
      { href: "/kpis", label: "Financial KPIs" },
      { href: "/working-capital", label: "Working Capital" },
      { href: "/categories", label: "Expense Categories" },
      { href: "/anomalies", label: "Anomalies" },
      { href: "/financial-overview", label: "Financial Overview" },
    ],
  },
  {
    label: "Administration",
    items: [
      { href: "/calendar", label: "Tax Calendar" },
      { href: "/reports", label: "Reports" },
      { href: "/management-reports", label: "Management Reports" },
      { href: "/settings", label: "Settings" },
    ],
  },
];

function DotIcon({ active }: { active: boolean }) {
  return (
    <span
      className={`inline-block w-1.5 h-1.5 rounded-full flex-shrink-0 ${active ? "bg-white" : "bg-[#5b5770]"}`}
      aria-hidden
    />
  );
}

export default function Shell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="flex-1 flex app-shell-v2 min-h-screen">
      <aside className={`nav-rail-v2 flex flex-col flex-shrink-0 transition-all duration-150 ${collapsed ? "w-16" : "w-64"}`}>
        <div className="flex items-center gap-2 px-4 py-5">
          <div className="w-8 h-8 rounded-lg hero-gradient-v2 flex items-center justify-center text-sm font-bold flex-shrink-0">O</div>
          {!collapsed && <span className="font-semibold tracking-tight text-white">OnHolland</span>}
        </div>

        <nav className="flex-1 overflow-y-auto px-2 space-y-5 pb-4">
          {NAV_GROUPS.map((group) => (
            <div key={group.label}>
              {!collapsed && <p className="px-3 text-[10px] font-medium uppercase tracking-wider text-[#6b6880] mb-1.5">{group.label}</p>}
              <div className="space-y-0.5">
                {group.items.map((item) => {
                  const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      title={collapsed ? item.label : undefined}
                      className={`nav-item-v2 flex items-center gap-2.5 px-3 py-2 text-sm ${active ? "active" : ""}`}
                    >
                      <DotIcon active={active} />
                      {!collapsed && <span className="truncate">{item.label}</span>}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>

        <div className="px-2 pb-4 pt-2 border-t border-white/10 space-y-1">
          {user && (
            <div className={`flex items-center gap-2.5 px-3 py-2 ${collapsed ? "justify-center" : ""}`}>
              <div className="w-7 h-7 rounded-full bg-brand-purple-600 text-white text-xs font-semibold flex items-center justify-center flex-shrink-0">
                {user.full_name.slice(0, 1).toUpperCase()}
              </div>
              {!collapsed && (
                <div className="min-w-0">
                  <p className="text-sm text-white truncate">{user.full_name}</p>
                  <p className="text-xs text-[#8b87a0] truncate">{user.role}</p>
                </div>
              )}
            </div>
          )}
          <Link href="/settings" className="nav-item-v2 flex items-center gap-2.5 px-3 py-2 text-sm">
            <DotIcon active={pathname.startsWith("/settings")} />
            {!collapsed && <span>Settings</span>}
          </Link>
          <button onClick={logout} className="nav-item-v2 w-full flex items-center gap-2.5 px-3 py-2 text-sm text-left">
            <DotIcon active={false} />
            {!collapsed && <span>Log out</span>}
          </button>
          <button
            onClick={() => setCollapsed((c) => !c)}
            className="nav-item-v2 w-full flex items-center gap-2.5 px-3 py-2 text-sm text-left"
          >
            <DotIcon active={false} />
            {!collapsed && <span>Collapse</span>}
          </button>
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0">
        <header className="bg-white border-b border-border-subtle px-6 py-3 flex items-center justify-between flex-shrink-0">
          <div className="text-sm text-text-secondary">OnHolland Accounting</div>
          <div className="flex items-center gap-3">
            <Link href="/sales/upload" className="btn-primary-v2 px-4 py-2 text-sm">
              + Create invoice
            </Link>
          </div>
        </header>
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
