# Mollie-inspired UI transformation — audit

Audit performed before any visual changes, per the brief's step 3.

## 1-2. Frontend architecture & existing design tokens

Next.js App Router, Tailwind v4 (`@theme inline` mapping CSS custom
properties to utility classes), no CSS-in-JS. All tokens live in
`app/globals.css` as `:root` custom properties:

- **Legacy tokens** (`--navy`, `--navy-light`, `--status-*`) — back
  `.btn-primary-v2`, `.card-v2`, `bg-navy`, etc. used across ~37 pages
  since Phase 1-8. Re-pointing these values re-skins every page using
  them with zero page-file edits (the mechanism Phase 11 used, and the
  one this transformation reuses).
- **Phase 11 glassmorphism primitives** (`--surface-page`,
  `--brand-purple-*`, `--glass-surface`, `--glass-blur`, `--app-gradient`,
  etc.) — purple/violet/cyan palette, frosted-glass surfaces, a fixed
  deep-navy gradient background. This is the layer being replaced.
- **Phase 11.1 semantic tokens** (`--color-token-*`, exposed via
  `@theme inline` as `--color-surface`, `--color-primary`, etc.) — a
  naming layer on top of the Phase 11 primitives. Kept, but repointed.
- **No dark mode exists today.** Confirmed by grep: zero occurrences of
  `prefers-color-scheme` or `data-theme` anywhere in the codebase. This
  is being built from nothing, not adjusted.

## 3. Existing glassmorphism components

`components/glass/`: `GlassButton`, `GlassCard`, `GlassChartCard`,
`GlassDropdown`, `GlassEmptyState`, `GlassInput` (+`GlassSelect`),
`GlassLoadingState` (+`GlassErrorState`), `GlassModal`,
`GlassNavigationGroup`, `GlassNavSearch`, `GlassPageHeader`,
`GlassPanel`, `GlassSidebar`, `GlassStatCard`, `GlassTable`, `GlassTabs`,
plus `icons.tsx` and `navConfig.ts`. Used directly by 13 of 52 routes;
the other 39 use the shared `.card-v2`/`.btn-primary-v2`/`.input-v2`
CSS classes instead (visually equivalent today since both draw from the
same tokens) or page-specific inline Tailwind.

**Decision on renaming:** kept the `Glass*` component/file names.
Renaming 19 files and every import site across 52 pages for a cosmetic
naming match was judged high mechanical risk for zero functional or
visual benefit this phase; the components' *output* changes completely,
their names do not. Flagged here as a legitimate future cleanup, not
done now.

## 4. Route inventory (52 routes) & redesign approach

Every route falls into one of three buckets for this transformation:

- **A — Global re-theme only** (new tokens + re-themed shared classes
  apply automatically, no page file edited): the 39 pages using
  `.card-v2`/`.btn-primary-v2`/`.input-v2` exclusively.
- **B — Component re-theme** (visual output changes via a shared
  component's own CSS, page files unedited): the 13 pages using
  `GlassCard`/`GlassTable`/etc. directly.
- **C — Bespoke layout work this phase**: dashboard (`/`), the global
  shell (`Shell.tsx`/`GlassSidebar.tsx`, affecting all 52 routes equally),
  and the banking/transaction-list visual treatment specifically
  (explicitly the most-detailed part of the brief).

| Route | Bucket |
|---|---|
| `/` (dashboard) | C |
| `/login` | A |
| `/banking`, `/bank-transactions`, `/reconciliation` | B/C (transaction-table treatment) |
| `/ledger`, `/ledger/[id]` | A (table style via C) |
| `/vat`, `/vat/[id]` | A |
| `/balance-sheet`, `/profit-and-loss`, `/trial-balance`, `/working-capital` | A |
| `/payroll`, `/employees`, `/employee-portal`, `/working-hours`, `/entrepreneur-hours` | A |
| `/loonheffingen`, `/annual-statements` | A |
| `/tax-centre`, `/tax-optimization`, `/legal-structure`, `/calendar` | A |
| `/cash-flow`, `/forecasts`, `/scenarios`, `/budgets`, `/kpis` | A |
| `/ai-intelligence`, `/assistant`, `/review-centre` | B |
| `/government` | B |
| `/companies`, `/companies/[id]`, `/companies/[id]/workspace` | A |
| `/documents`, `/documents/[id]`, `/batches`, `/batches/[id]`, `/categories` | A |
| `/sales/upload`, `/purchases/upload` | A |
| `/management-reports`, `/reports`, `/financial-overview` | A |
| `/billing`, `/admin`, `/invitations/accept`, `/settings` | B |
| `/automation`, `/anomalies` | A |

Tracked in detail in `docs/ui-transformation-progress.md`.

## 5. Shared layouts & navigation

`components/Shell.tsx` (topbar + content area) wraps every
authenticated route; `GlassSidebar.tsx` (desktop fixed sidebar + mobile
drawer, collapse/expand, localStorage-persisted open-group state,
role-based swap between `NAV_GROUPS`/`EMPLOYEE_ROLE_NAV_GROUPS`, plus
the Phase 14 `PLATFORM_ADMIN_NAV_GROUP` addition) provides navigation.
Both are rewritten visually this phase; all their existing *logic*
(collapse, mobile drawer, persistence, role filtering, company
switching) is reused untouched.

## 6. Tables, charts, forms, modals, dropdowns

- Tables: `GlassTable` (used by 13 pages) vs. a plain `<table>` in the
  other 27 (wrapped in `overflow-x-auto` last phase for mobile safety,
  but not yet visually unified). Both get the new compact,
  banking-style treatment this phase — `GlassTable`'s own CSS for its
  13 call sites, and new shared table utility classes
  (`.table-v3`/`.table-row-v3`/etc.) for the 27 plain-table pages, so
  neither requires a full per-page column rewrite.
- Forms: `GlassInput`/`GlassSelect` plus the legacy `.input-v2` class —
  both repointed to the new flat, bordered Mollie input style.
- Modals/dropdowns: `GlassModal`/`GlassDropdown` — visual-only changes;
  their focus-trap/keyboard-nav logic (built in Phase 11.1) is untouched.
- Charts: `GlassChartCard` — visual-only changes to its SVG styling
  (line weight, gridlines, colours); its accessibility features
  (`.sr-only` data table, keyboard-focusable points) are untouched.

## 7-8. Dark-mode readiness & hardcoded colours

Confirmed zero dark-mode infrastructure exists (see §2). 12 page files
use a hardcoded hex/`bg-white`/`bg-black` value outside the token
system, which would NOT respond to a theme change if left as-is:
`page.tsx`, `ledger/page.tsx`, `calendar/page.tsx`,
`loonheffingen/page.tsx`, `anomalies/page.tsx`, `vat/page.tsx`,
`annual-statements/page.tsx`, `cash-flow/page.tsx`,
`bank-transactions/page.tsx`, `documents/page.tsx`,
`working-capital/page.tsx`, `batches/page.tsx`. Each is checked and
fixed (replaced with a token-backed class) as part of this phase's
dark-mode work — tracked in `docs/ui-transformation-progress.md`.

## 9. Components that won't respond correctly to a theme change

Everything using a legacy/Phase-11 token *by value* responds correctly
once the token's *value* changes per theme (that's the whole point of
the token indirection). The 12 hardcoded-colour files above are the
actual risk list — fixed this phase. `GlassStatCard`'s `TONE_CLASS`/
`TONE_ICON` maps and `StatusBadge`/`TransactionBadges`/
`DocumentStatusBadge`/`CalendarStatusBadge` already encode colour +
icon/text together (never colour alone, per the Phase 11.1
accessibility work) — these need their literal Tailwind colour
utilities (`bg-green-100`, `text-red-700`, etc.) re-checked for
contrast in dark mode specifically, since Tailwind's default colour
scale wasn't tuned against the new dark palette.
