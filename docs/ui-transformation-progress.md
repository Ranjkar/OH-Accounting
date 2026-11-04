# UI transformation progress tracker

Status of all routes against the Mollie-inspired design system, per
`docs/mollie-ui-transformation-audit.md`'s bucket classification.

**Updated this phase ("PHASE 14 CONTINUATION — MOLLIE UI COMPLETION"):**
the 27-page `table-v3` gap recorded in the previous version of this
document is now closed. Every financial list in the app uses the
compact Mollie table style. This update also closes two gaps the
earlier verification pass missed entirely (not just left incomplete):
a shared upload-flow component that was never re-themed at all, and
currency values rendered as raw Decimal strings or hand-built
`€${value}` interpolation instead of the shared Dutch `formatEUR`
helper, in 16 files across two verification rounds this phase.

## Bucket A — global re-theme (automatic, no page edit needed)

Pages using only `.card-v2`/`.btn-primary-v2`/`.input-v2`/typography
classes, re-themed centrally in `app/globals.css`. Visually consistent
with the palette automatically; verified via screenshot for a
representative sample in both themes (see
`docs/ui-visual-verification.md`).

## Bucket B — component re-theme

Pages using `Glass*` components directly, re-themed via those
components' own CSS: `/ai-intelligence`, `/assistant`, `/review-centre`,
`/government`, `/billing`, `/admin`, `/invitations/accept`, `/settings`.

## Bucket C — bespoke work (prior rounds)

- **`/` (dashboard)**: AI card rebuilt from a vivid gradient hero to a
  flat tinted surface with dark text; removed a decorative blurred
  background circle.
- **Global shell** (`Shell.tsx`, `GlassSidebar.tsx`,
  `GlassNavigationGroup.tsx`): slim flush topbar with back/forward nav,
  warm off-white sidebar, theme toggle. Affects all routes equally.
- **`/bank-transactions`** and **`/ledger`**: the original two
  reference implementations of the compact `table-v3` style, used as
  the template for every page listed below.

## `table-v3` compact-table migration — now complete

All financial-list pages use the compact Mollie table style
(`.table-v3`, `.col-amount`, `.status-pill-*`, `formatEUR` currency
formatting, right-aligned monetary columns, thin row separators, no
heavy card borders per row). Completed this phase across 7 commits
(`4af6100` and the six commits before it on
`phase-14-mollie-ui-completion`):

`balance-sheet`, `batches/[id]`, `batches`, `budgets`, `calendar`,
`cash-flow`, `categories`, `companies/[id]`, `companies/[id]/workspace`,
`documents/[id]`, `employee-portal`, `employees`,
`entrepreneur-hours`, `financial-overview`, `forecasts`, `ledger/[id]`,
`loonheffingen`, `page` (dashboard), `payroll`, `profit-and-loss`,
`reports`, `scenarios`, `vat/[id]`, `vat`, `working-capital`,
`working-hours` — plus the original `bank-transactions` and `ledger`.

Verified via `grep` that zero `table className="w-full text-sm"`
(the old plain-table pattern) instances remain anywhere in `app/`.

## Found and fixed this phase, beyond the table migration itself

Three classes of defect were found by actually using the app (tablet
screenshots, axe-core, re-reading pages flagged "done" by an earlier
pass) rather than assumed fixed because a page was in a "complete"
bucket:

1. **A shared component with zero Mollie styling.** `components/
   BulkUploadScreen.tsx` (powers both `/sales/upload` and
   `/purchases/upload` — two of the explicitly required final
   screenshots) still used the pre-Mollie hardcoded `bg-white`/
   `slate-*` palette and a purple heading. It was never touched by
   any earlier sweep because those swept `app/` page files, not
   `components/`. Would have rendered as a broken white box on a dark
   page. Converted to `card-v2`/`input-v2`/theme tokens; verified in
   both themes.
2. **Non-Dutch / raw currency formatting**, found incrementally across
   two rounds (16 files total): some values were never passed through
   `formatEUR` at all (raw backend Decimal strings, e.g.
   `financial-overview`'s company-detail tiles showing `"3003.20"`);
   others used ad-hoc `` `€${value}` `` string interpolation instead
   of the shared formatter (dashboard stat cards, employee-portal,
   annual-statements, billing — showing `"€1000.00"` instead of the
   correct `"€ 1.000,00"`). Every call site now uses `formatEUR`.
3. **Two stray hardcoded-white hover states** in `CompanySwitcher.tsx`
   (`hover:bg-white/50`/`/60`, a glassmorphism leftover) and one
   `text-slate-500` loading label in `AuthGuard.tsx` — found via a
   repo-wide (not just `app/`) grep, since the earlier 23-file sweep
   was also scoped to `app/` only.

A repo-wide grep for `bg-slate-*`/`text-slate-*`/`border-slate-*`/
`divide-slate-*` now returns matches only in the three deliberately
undone self-contained badge components (`DocumentStatusBadge`,
`CalendarStatusBadge`, `TransactionBadges` — their own internal
contrast doesn't depend on page background, confirmed in
`docs/ui-visual-verification.md`'s prior round).

## Tablet responsiveness (768px / 1024px) — verified this phase

390px and 1440px were verified in the prior round. 768px and 1024px
were verified this phase across 15+ representative routes (dashboard,
banking, ledger, VAT, VAT detail, scenarios, working-capital,
cash-flow, sales/purchases upload, profit-and-loss, employees,
forecasts) in both themes where applicable. Zero page-level horizontal
overflow found anywhere (`document.documentElement.scrollWidth -
clientWidth === 0` on every route tested). The sidebar correctly
switches from a hamburger/slide-over (below the Tailwind `lg:` 1024px
breakpoint) to the full fixed rail (at/above 1024px) — this is the
exact boundary and it behaves correctly. Wide financial tables (8+
columns, e.g. the ledger list) use an inner `overflow-x-auto` wrapper
that scrolls within its own card rather than overflowing the page —
intentional, standard responsive-table behavior, not a defect.

## Accessibility — real-browser axe-core sweep (new this phase)

Earlier rounds used `test/axe.ts`, a jsdom-based axe-core run that
explicitly cannot check `color-contrast` (jsdom has no layout/paint
engine). This phase added a Playwright-driven axe-core run against the
live, rendered app — 12 representative routes × 2 themes (24
combinations), using the full `wcag2a`/`wcag2aa`/`wcag22aa` ruleset.
Found and fixed 5 genuine defects (not previously caught, because they
require real rendering): a dashboard `<select>` with no accessible
name, a marginal (~4.25:1, needs 4.5:1) contrast failure on
`.status-pill-success`/`-warning` tint backgrounds, an invalid `<dl>`
child in `ai-intelligence`, and an ARIA conflict (`role="img"` on an
SVG chart that also contains real focusable per-data-point hit
targets). Full writeup: `docs/ui-visual-verification.md`.

## Chart comparison series (Priority 4) — verified not applicable

The only chart in the app (`GlassChartCard`, used once, on the
dashboard's "Cash Flow" card) is driven by the cash-flow *forecast*
endpoint, which has no previous-period/comparison field in its
response shape (`monthly_projection: { month, expected_incoming,
expected_outgoing, net, is_estimate }[]` — forward-looking only).
Per the explicit instruction to never fabricate comparison data, no
chart changes were made. Real actual-vs-comparison data does exist
(the Profit & Loss page's "Previous period" / "% change" columns,
backed by the backend's real prior-period comparison), but it is
presented as a table, not a chart — there is no existing chart on that
page to add a series to, and adding a net-new chart component was
judged out of scope for a comparison-series task.

## What was explicitly NOT attempted

- A bespoke, hand-designed layout for every route individually (as
  opposed to the shared-class mechanism). The brief's acceptance
  criteria is about a consistent *visual language*, not a unique
  bespoke layout per page.
- Adding a net-new chart to Profit & Loss (or anywhere else) to carry
  the existing comparison data visually, since Priority 4 asked for
  comparison *series on charts*, not new charts.
