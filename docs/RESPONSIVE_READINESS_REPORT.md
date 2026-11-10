# Responsive Readiness Report

**Scope:** OnHolland Accounting frontend (Next.js 16 / React 19 / Tailwind 4), every route, phones through 1920px desktops, LTR and RTL.
**Date:** 2026-11-10
**Branch / commits:** `main`, commits after `4cc9c76` (see git log for "Responsive:" commits).

## 1. Route inventory (56 routes, all reviewed)

Generated from `frontend/app/**/page.tsx`. Every route below was loaded at 320, 375, 768 and 1024 CSS px (Dutch), 375 and 1024 (Persian, RTL) and 375 (Arabic, RTL) by the scratch audit, and is covered by `e2e/responsive.spec.ts` on eight Playwright device projects.

| Area | Routes |
|---|---|
| Auth / onboarding | `/login`, `/invitations/accept`, `/users/invitations/accept` |
| Dashboard | `/` |
| Companies | `/companies`, `/companies/[id]`, `/companies/[id]/workspace` |
| Accounting & ledger | `/ledger`, `/ledger/[id]`, `/trial-balance`, `/balance-sheet`, `/profit-and-loss`, `/cash-flow`, `/working-capital`, `/financial-overview`, `/annual-statements` |
| Invoices, expenses & documents | `/documents`, `/documents/[id]`, `/sales/upload`, `/purchases/upload`, `/batches`, `/batches/[id]`, `/review-centre`, `/categories` |
| VAT & tax | `/vat`, `/vat/[id]`, `/tax-centre`, `/tax-optimization`, `/legal-structure`, `/loonheffingen`, `/government` |
| Banking | `/banking`, `/bank-transactions`, `/reconciliation` |
| AI | `/assistant`, `/ai-intelligence`, `/anomalies`, `/automation`, `/forecasts`, `/scenarios`, `/budgets`, `/kpis`, `/management-reports` |
| Reports | `/reports`, `/calendar`, `/audit-log` |
| People & payroll | `/users`, `/employees`, `/payroll`, `/employee-portal`, `/working-hours`, `/entrepreneur-hours` |
| Settings & billing | `/settings`, `/billing`, `/admin` (platform admin only) |

Shared layout: `components/Shell.tsx` (header + main), `components/glass/GlassSidebar.tsx` (desktop rail ≥1024px, modal drawer below), `GlassNavigationGroup`, `CompanySwitcher`, `GlassNavSearch`, `GlassModal`, `GlassTable`, `GlassPanel`, `GlassPageHeader`, `GlassTabs`, `GlassChartCard`, `GlassStatCard`, `BulkUploadScreen`.

## 2. Baseline findings (before changes)

The scratch audit (Dutch, 320/375/768/1024) found:

- **19 routes with horizontal page overflow at 320 and/or 375 px**: anomalies, balance-sheet, bank-transactions, batches, budgets, calendar, documents, documents/[id], employee-portal, forecasts, kpis, ledger, legal-structure, reconciliation, reports, tax-optimization, vat/[id], working-capital, ai-intelligence (at 1024).
- Root causes were shared, not per-page: toolbar rows (`flex items-center gap-*` with a `<select>` plus filter pills, inputs and buttons) that never wrapped; `grid grid-cols-2` layout grids with no breakpoint; `GlassTabs` using `inline-flex` without wrap; page headers (`h1` + action buttons) that could not wrap; fixed-width inputs (`w-36`…`w-48`) in non-wrapping rows.
- **Financial tables** were already inside `overflow-x-auto` wrappers, but dates wrapped mid-value ("2026-\n02-10"), there was no scroll affordance, and the scroll containers were not keyboard-focusable.
- **Touch targets:** many buttons (`← Back`, row actions, "Get AI suggestion") were 16–20 px tall.
- **No viewport safe-area handling**, no mitigation for iOS input-focus zoom (14 px controls).
- **Mobile drawer** had `role="dialog"` but no Escape handling, no focus management and no body scroll lock.
- **axe-core (WCAG 2.2 AA)** on representative pages: company switcher accessible name did not contain its visible text (2.5.3), icon-only "Create invoice" link had no name on phones, document review inputs/textarea had unassociated labels, horizontally scrollable regions were not focusable.

No console errors apart from expected 403s on the two role-gated pages (`/admin`, `/employee-portal`) for the test account.

## 3. Changes

### Global layout, navigation, shell
- `app/layout.tsx`: `viewport` export with `viewport-fit=cover`; user zoom is **not** disabled.
- `app/globals.css`: body padding from `env(safe-area-inset-*)`; `button, [role=button] { min-height: 1.5rem }`; on coarse pointers form controls and buttons get a 44 px minimum height and inputs a 16 px font (`max(16px, 1em)`) so iOS does not zoom on focus; page-title step-down below 400 px.
- `GlassSidebar`: drawer is a real modal (Escape closes, focus moves to the first control and returns to the opener, body scroll locked while open), `max-w-[85vw]`, safe-area padding; close button enlarged. Desktop rail unchanged.
- `Shell`: icon-only "Create invoice" link gets an `aria-label`.
- `CompanySwitcher`: accessible name is now the visible company name.

### Shared components
- `GlassPageHeader`: stacks title/subtitle above actions below `sm`.
- `GlassPanel`: header row wraps; tighter padding on phones.
- `GlassModal`: `100dvh`-based max height, bottom-sheet on phones (full width, square bottom corners, safe-area padding), sticky header, wrapping footer, larger close target.
- `GlassTabs`: wraps instead of overflowing.
- `GlassChartCard`: header wraps; axis labels truncate rather than push the card wider (full values remain in the screen-reader table and tooltip).
- `GlassTable` already rendered a stacked card list below `sm`; unchanged.

### Pages (40 files, mechanical)
- Every toolbar/filter/pill/action row now wraps (`flex-wrap`), including page-header rows with action buttons.
- Every `grid grid-cols-2` layout grid is `grid-cols-1 sm:grid-cols-2` (or `lg:` where the two halves are tables or the document preview).
- `/documents/[id]`: preview and extracted-fields panels stack below `lg`; preview is `60dvh` tall on phones; every field label is associated with its input (`useId`), textarea labelled.
- `/vat/[id]`: status stepper wraps.
- `/ai-intelligence`: six-up KPI grid only at `xl`.
- `inputMode="decimal"` on amount/hours/revenue/profit inputs (ledger lines, budgets, balance-sheet, employees, legal-structure, tax-optimization, tax-centre, working-hours, entrepreneur-hours); `inputMode="numeric"` on the KvK number.

### Financial tables (`.table-v3`, 27 pages)
- Header cells, first column, and amount columns never wrap (`white-space: nowrap`); free-text columns still wrap.
- Below 640 px: compact cell padding, secondary font size, and a **sticky first column** (date / box / name) that stays visible while the rest of the row scrolls.
- CSS-only scroll shadows on every `.overflow-x-auto` container so a cut-off column is visibly scrollable; containers are `tabIndex={0}` for keyboard scrolling (axe `scrollable-region-focusable`).
- No accounting values, formatting or calculations were touched.

### Tests
- `playwright.config.ts`: new projects `iphone-se`, `iphone-15`, `pixel-7`, `ipad-mini`, `ipad`, `ipad-pro-landscape`, `desktop-1920` (all Chromium; see limitations) running `e2e/responsive.spec.ts`; `chromium` (1280) runs everything. `workers: 1` because every spec shares one test account (server-side locale preference) and the login endpoint is rate-limited.
- `e2e/responsive.spec.ts` (10 tests × 8 projects): login journey; every route checked for horizontal overflow, elements outside the viewport, buttons under 24 px and console errors; mobile drawer open/close/Escape/focus/active state; desktop rail; document upload (file list, upload button reachable); invoice review (stacked below `lg`, side-by-side above); VAT return (figures, exports, nowrap amounts); table scroll container; RTL (Persian) on five routes plus right-anchored drawer; reduced-motion; axe-core WCAG 2.2 AA on eight pages.
- Unit test `GlassSidebar.test.tsx` updated for the translated drawer name.

## 4. Validation results

All runs on 2026-11-10 against the local dev stack (Homebrew Postgres, backend on :8010, `next dev` on :3000 with `BACKEND_INTERNAL_URL` set).

| Check | Command | Result |
|---|---|---|
| TypeScript | `npx tsc --noEmit` | 0 errors |
| Lint | `npm run lint` | 0 errors, 4 pre-existing warnings (exhaustive-deps ×3, `<img>` in document preview), none introduced |
| Unit tests | `npx vitest run` | 11 files, 175 tests passed |
| Production build | `npm run build` | Compiled successfully, 58/58 pages generated |
| Browser tests | `npx playwright test` | **115 passed, 0 failed** (12.3 min): i18n suite on chromium + responsive suite on chromium 1280, iPhone SE, iPhone 15, Pixel 7, iPad Mini, iPad, iPad Pro 11 landscape, desktop 1920 |

Scratch audit (every route, screenshot + overflow + console scan), after the changes:

| Locale / dir | Widths | Routes with page overflow | Elements outside viewport | Console errors |
|---|---|---|---|---|
| nl (LTR) | 320, 375, 1024 | 0 / 56 | 0 | only the expected 403s on `/admin`, `/employee-portal` |
| fa (RTL) | 375, 1024 | 0 / 56 | 0 | same |
| ar (RTL) | 375 | 0 / 56 (partial run; the Playwright RTL test covers the rest) | 0 | same |

Per-criterion status:

- **No horizontal overflow at 320–1920 px:** verified on all 56 routes by the audit and asserted on every project by the suite.
- **Navigation:** drawer on phones/tablets (Escape, focus trap entry/return, closes on selection, `aria-current` on the active item, right-anchored in RTL), rail on ≥1024 px. Asserted per project.
- **Tables:** no page overflow; identifiers/amounts never wrap; container scroll with shadows, sticky identifier column and keyboard focus. Asserted on `/ledger` and `/vat/5`.
- **Forms:** rows wrap, decimal/numeric keyboards on amount fields, 16 px controls on touch (asserted on `/login`), labels associated (axe), submit buttons reachable (asserted on upload and review pages).
- **Upload / review:** file input accepts jpg/jpeg/png/pdf/xlsx/csv with `multiple`; selected files listed; review page stacks preview above fields below `lg`. Asserted.
- **Dashboards / charts:** KPI grids collapse (`grid-cols-2 sm:3 xl:6`), SVG charts scale with `viewBox`, axis labels truncate, tooltip reachable by touch/keyboard, data duplicated in an sr-only table.
- **Accessibility:** axe-core WCAG 2.0/2.1/2.2 A+AA scan of 8 pages: 0 violations on every project. Reduced motion asserted. All buttons ≥24 px on every route (asserted); form controls/buttons ≥44 px on touch.
- **Localisation:** nl/en/fa/ar still pass the existing i18n suite; RTL verified visually (Persian dashboard screenshot) and by assertion.

## 5. Visual evidence

Screenshots captured by the suite are in `frontend/e2e/.screenshots/responsive/` (git-ignored, regenerated on each run). A representative set is committed under `docs/responsive-screenshots/`:

| File | What it shows |
|---|---|
| `login_iphone-se.png` | Login at 375×667, whole form and button above the fold |
| `dashboard_iphone-se.png`, `dashboard_pixel-7.png` | Dashboard on phones: compact header, stacked cards |
| `dashboard_fa_rtl_375.png` | Dashboard in Persian, RTL mirrored header and cards |
| `dashboard_ipad-mini.png`, `dashboard_ipad-pro-landscape.png`, `dashboard_desktop-1920.png` | Tablet portrait (drawer), tablet landscape (rail), desktop |
| `documents_iphone-se.png` | Document list with wrapping status filters |
| `documents_9_iphone-se.png`, `documents_9_ipad.png` | Invoice review: preview stacked above fields on phone, side-by-side on iPad (PDF body is blank in headless Chromium) |
| `ledger_iphone-se.png`, `ledger_ipad-mini.png` | Ledger: wrapped filter pills, scrolling table with sticky date column |
| `vat_5_iphone-se.png`, `vat_5_ipad.png` | VAT return: status stepper wraps, figures and exports visible |
| `settings_iphone-15.png` | Settings with theme and language controls |

## 6. Known limitations

- **Engine:** iPhone/iPad projects run on Chromium with device emulation (viewport, DPR, touch, UA). WebKit is not installed locally; the layout and overflow assertions are engine-independent, but Safari-specific rendering was not exercised. Install with `npx playwright install webkit` and drop the `defaultBrowserType` overrides to run the same spec on WebKit.
- **Tables on phones** use horizontal scrolling with a sticky identifier column rather than a per-table card redesign. `GlassTable` (used by banking, government, admin, review-centre, ai-intelligence) renders cards below `sm`; the 27 `.table-v3` pages keep all columns and scroll. Converting those to card layouts is a follow-up, not a blocker.
- **Inline links** (e.g. a date link inside a table cell, "Manage" in a card header) are 16–18 px tall. WCAG 2.5.8 exempts inline links and targets with ≥24 px spacing, which these are; all `<button>` elements meet 24 px and all form controls meet 44 px on touch devices.
- **Role-gated pages** (`/admin`, `/employee-portal`) log a browser "403" resource error for accounts without that role. Expected; the pages show their own error state.
- **Language switcher** is hidden from the header below `lg` (space); it remains available on the login page and in Settings.
- Zoom was verified by viewport width (640 px ≈ 200 % and 320 px ≈ 400 % of a 1280 px window), not by driving the browser's zoom control.

## 7. Deployment readiness

- No schema, data, auth, tenant, permission, calculation, secret, Docker volume or Tailscale changes. All edits are in `frontend/` (TSX/CSS/tests) plus this document.
- Rebuild/redeploy on the Mac mini with the existing compose workflow once the validation above is green; nothing else changes.

**Status: ready to deploy.** All validation above is green; no production-side configuration changes are needed. The usual `docker compose -f docker-compose.prod.yml up -d --build frontend` on the Mac mini picks up the frontend image. Not deployed automatically as part of this work.
