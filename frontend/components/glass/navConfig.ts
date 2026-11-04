import {
  IconDashboard,
  IconLedger,
  IconInvoice,
  IconBank,
  IconPayroll,
  IconTax,
  IconPlanning,
  IconDocuments,
  IconSettings,
} from "./icons";
import type { ComponentType, SVGProps } from "react";

export interface NavLeaf {
  label: string;
  href?: string;
  /** Set when the proposed IA names a feature this backend doesn't expose
   * yet -- rendered disabled with an explanatory tooltip instead of a
   * fake working link (explicit instruction: never invent a page). */
  unavailable?: string;
  /** Only shown to this role, if set. */
  onlyRole?: string;
}

export interface NavGroup {
  label: string;
  icon: ComponentType<SVGProps<SVGSVGElement> & { size?: number }>;
  items: NavLeaf[];
}

/** Every entry is either a real existing route, a new route built this
 * phase against the real backend (loonheffingen, annual statements,
 * employee self-service -- all shipped in Phase 10, previously without a
 * frontend), or explicitly marked unavailable. Nothing here is a mockup. */
export const NAV_GROUPS: NavGroup[] = [
  {
    label: "Dashboard",
    icon: IconDashboard,
    items: [
      { label: "Overview", href: "/" },
      { label: "Financial Overview", href: "/financial-overview" },
      { label: "AI Intelligence Dashboard", href: "/ai-intelligence" },
      { label: "AI Assistant", href: "/assistant" },
      { label: "Review & Approval Centre", href: "/review-centre" },
    ],
  },
  {
    label: "Accounting",
    icon: IconLedger,
    items: [
      { label: "General Ledger", href: "/ledger" },
      { label: "Trial Balance", href: "/trial-balance" },
      { label: "Profit & Loss", href: "/profit-and-loss" },
      { label: "Balance Sheet", href: "/balance-sheet" },
      { label: "VAT Returns", href: "/vat" },
      { label: "Chart of Accounts", unavailable: "Not yet implemented -- this app uses VAT-box/category classification rather than a traditional chart of accounts." },
    ],
  },
  {
    label: "Sales & Purchases",
    icon: IconInvoice,
    items: [
      { label: "Sales Invoices", href: "/sales/upload" },
      { label: "Purchase Invoices", href: "/purchases/upload" },
      { label: "Upload Batches", href: "/batches" },
      { label: "Expense Categories", href: "/categories" },
      { label: "Customers", unavailable: "No dedicated customer record management yet -- customer names are captured per-invoice." },
      { label: "Suppliers", unavailable: "No dedicated supplier record management yet -- supplier names are captured per-invoice." },
    ],
  },
  {
    label: "Banking",
    icon: IconBank,
    items: [
      { label: "Bank Accounts", href: "/banking" },
      { label: "Bank Transactions", href: "/bank-transactions" },
      { label: "Reconciliation", href: "/reconciliation" },
      { label: "Automation Centre", href: "/automation" },
      { label: "Anomalies", href: "/anomalies" },
    ],
  },
  {
    label: "Payroll & HR",
    icon: IconPayroll,
    items: [
      { label: "Employees", href: "/employees" },
      { label: "Payroll Runs & Payslips", href: "/payroll" },
      { label: "Payroll Tax (Loonheffingen)", href: "/loonheffingen" },
      { label: "Annual Statements (Jaaropgaaf)", href: "/annual-statements" },
      { label: "Working Hours", href: "/working-hours" },
      { label: "Entrepreneur Hours", href: "/entrepreneur-hours" },
      { label: "Employee Portal", href: "/employee-portal" },
      { label: "Leave & Absence", unavailable: "Not a separate module yet -- holiday/sick/absence are entry types within Working Hours." },
    ],
  },
  {
    label: "Tax & Compliance",
    icon: IconTax,
    items: [
      { label: "Tax Centre", href: "/tax-centre" },
      { label: "Tax Optimisation", href: "/tax-optimization" },
      { label: "Legal Structure", href: "/legal-structure" },
      { label: "Compliance Calendar", href: "/calendar" },
      { label: "Government Integration Centre", href: "/government" },
    ],
  },
  {
    label: "Planning & Analytics",
    icon: IconPlanning,
    items: [
      { label: "Cash Flow", href: "/cash-flow" },
      { label: "Forecasts", href: "/forecasts" },
      { label: "Scenarios", href: "/scenarios" },
      { label: "Budgets", href: "/budgets" },
      { label: "KPIs & Insights", href: "/kpis" },
      { label: "Working Capital", href: "/working-capital" },
    ],
  },
  {
    label: "Documents",
    icon: IconDocuments,
    items: [{ label: "All Documents", href: "/documents" }],
  },
  {
    label: "Company & Settings",
    icon: IconSettings,
    items: [
      { label: "Companies", href: "/companies" },
      { label: "Management Reports", href: "/management-reports" },
      { label: "Reports", href: "/reports" },
      { label: "Billing & Subscription", href: "/billing" },
      { label: "Settings", href: "/settings" },
      { label: "Users & Permissions", href: "/users" },
      { label: "Audit Log", href: "/audit-log" },
    ],
  },
];

/** Only rendered for user.is_platform_admin (a tier above tenant admin --
 * see app.models.user.User.is_platform_admin) -- GlassSidebar appends
 * this itself rather than every tenant seeing an empty/403 group. */
export const PLATFORM_ADMIN_NAV_GROUP: NavGroup = {
  label: "Administration",
  icon: IconSettings,
  items: [{ label: "Platform Overview", href: "/admin" }],
};

/** An employee-role account (app.core.deps.get_current_employee on the
 * backend) is never added to user_companies -- every item above would
 * 403. Show only what actually works for that role. */
export const EMPLOYEE_ROLE_NAV_GROUPS: NavGroup[] = [
  {
    label: "My Workspace",
    icon: IconPayroll,
    items: [{ label: "Employee Portal", href: "/employee-portal" }],
  },
];
