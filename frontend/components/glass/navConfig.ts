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
  /** Key under the "nav.items" translation namespace -- resolved via
   * useTranslations("nav") at render time (navConfig.ts itself is a
   * plain module, not a component, so it can't call useTranslations
   * directly). English literal removed in Phase 16; see messages/*.json. */
  labelKey: string;
  href?: string;
  /** Set when the proposed IA names a feature this backend doesn't expose
   * yet -- rendered disabled with an explanatory tooltip instead of a
   * fake working link (explicit instruction: never invent a page). Key
   * under "nav.unavailable" or an existing domain namespace that already
   * had the right copy (customers.unavailable / suppliers.unavailable). */
  unavailableKey?: string;
  /** Only shown to this role, if set. */
  onlyRole?: string;
}

export interface NavGroup {
  /** Key under the "nav.groups" translation namespace. */
  labelKey: string;
  icon: ComponentType<SVGProps<SVGSVGElement> & { size?: number }>;
  items: NavLeaf[];
}

/** Every entry is either a real existing route, a new route built this
 * phase against the real backend (loonheffingen, annual statements,
 * employee self-service -- all shipped in Phase 10, previously without a
 * frontend), or explicitly marked unavailable. Nothing here is a mockup. */
export const NAV_GROUPS: NavGroup[] = [
  {
    labelKey: "dashboard",
    icon: IconDashboard,
    items: [
      { labelKey: "overview", href: "/" },
      { labelKey: "financialOverview", href: "/financial-overview" },
      { labelKey: "aiIntelligenceDashboard", href: "/ai-intelligence" },
      { labelKey: "aiAssistant", href: "/assistant" },
      { labelKey: "reviewApprovalCentre", href: "/review-centre" },
    ],
  },
  {
    labelKey: "accounting",
    icon: IconLedger,
    items: [
      { labelKey: "generalLedger", href: "/ledger" },
      { labelKey: "trialBalance", href: "/trial-balance" },
      { labelKey: "profitLoss", href: "/profit-and-loss" },
      { labelKey: "balanceSheet", href: "/balance-sheet" },
      { labelKey: "vatReturns", href: "/vat" },
      { labelKey: "chartOfAccounts", unavailableKey: "nav.unavailable.chartOfAccountsUnavailable" },
    ],
  },
  {
    labelKey: "salesPurchases",
    icon: IconInvoice,
    items: [
      { labelKey: "salesInvoices", href: "/sales/upload" },
      { labelKey: "purchaseInvoices", href: "/purchases/upload" },
      { labelKey: "uploadBatches", href: "/batches" },
      { labelKey: "expenseCategories", href: "/categories" },
      { labelKey: "customers", unavailableKey: "customers.unavailable" },
      { labelKey: "suppliers", unavailableKey: "suppliers.unavailable" },
    ],
  },
  {
    labelKey: "banking",
    icon: IconBank,
    items: [
      { labelKey: "bankAccounts", href: "/banking" },
      { labelKey: "bankTransactions", href: "/bank-transactions" },
      { labelKey: "reconciliation", href: "/reconciliation" },
      { labelKey: "automationCentre", href: "/automation" },
      { labelKey: "anomalies", href: "/anomalies" },
    ],
  },
  {
    labelKey: "payrollHr",
    icon: IconPayroll,
    items: [
      { labelKey: "employees", href: "/employees" },
      { labelKey: "payrollRunsPayslips", href: "/payroll" },
      { labelKey: "payrollTax", href: "/loonheffingen" },
      { labelKey: "annualStatements", href: "/annual-statements" },
      { labelKey: "workingHours", href: "/working-hours" },
      { labelKey: "entrepreneurHours", href: "/entrepreneur-hours" },
      { labelKey: "employeePortal", href: "/employee-portal" },
      { labelKey: "leaveAbsence", unavailableKey: "nav.unavailable.leaveAbsenceUnavailable" },
    ],
  },
  {
    labelKey: "taxCompliance",
    icon: IconTax,
    items: [
      { labelKey: "taxCentre", href: "/tax-centre" },
      { labelKey: "taxOptimisation", href: "/tax-optimization" },
      { labelKey: "legalStructure", href: "/legal-structure" },
      { labelKey: "complianceCalendar", href: "/calendar" },
      { labelKey: "governmentIntegrationCentre", href: "/government" },
    ],
  },
  {
    labelKey: "planningAnalytics",
    icon: IconPlanning,
    items: [
      { labelKey: "cashFlow", href: "/cash-flow" },
      { labelKey: "forecasts", href: "/forecasts" },
      { labelKey: "scenarios", href: "/scenarios" },
      { labelKey: "budgets", href: "/budgets" },
      { labelKey: "kpisInsights", href: "/kpis" },
      { labelKey: "workingCapital", href: "/working-capital" },
    ],
  },
  {
    labelKey: "documents",
    icon: IconDocuments,
    items: [{ labelKey: "allDocuments", href: "/documents" }],
  },
  {
    labelKey: "companySettings",
    icon: IconSettings,
    items: [
      { labelKey: "companies", href: "/companies" },
      { labelKey: "managementReports", href: "/management-reports" },
      { labelKey: "reports", href: "/reports" },
      { labelKey: "billingSubscription", href: "/billing" },
      { labelKey: "settings", href: "/settings" },
      { labelKey: "usersPermissions", href: "/users" },
      { labelKey: "auditLog", href: "/audit-log" },
    ],
  },
];

/** Only rendered for user.is_platform_admin (a tier above tenant admin --
 * see app.models.user.User.is_platform_admin) -- GlassSidebar appends
 * this itself rather than every tenant seeing an empty/403 group. */
export const PLATFORM_ADMIN_NAV_GROUP: NavGroup = {
  labelKey: "administration",
  icon: IconSettings,
  items: [{ labelKey: "platformOverview", href: "/admin" }],
};

/** An employee-role account (app.core.deps.get_current_employee on the
 * backend) is never added to user_companies -- every item above would
 * 403. Show only what actually works for that role. */
export const EMPLOYEE_ROLE_NAV_GROUPS: NavGroup[] = [
  {
    labelKey: "myWorkspace",
    icon: IconPayroll,
    items: [{ labelKey: "employeePortal", href: "/employee-portal" }],
  },
];
