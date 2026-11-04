# Visual verification

## Tooling

Claude in Chrome (used, unsuccessfully, in every prior phase) was
listed as available again but the extension was not actually connected
when tested. Per the brief's explicit instruction to investigate
alternatives: `npx playwright install chromium` was attempted and
**succeeded** — a real headless Chromium binary downloaded and launched
in this environment (confirmed first with a trivial `data:text/html`
page load before touching the real app). `playwright` was added as a
frontend devDependency. This is **genuine browser automation**, not a
simulation — every screenshot below is a real rendered page, reviewed
by actually looking at the image, not assumed from the markup.

## Method

A disposable admin user (`mollie-visual@example.com`) and a bank
account with 8 realistic transactions (varied amounts, counterparties,
reconciliation statuses, dates) were created directly in the dev
database for this purpose — left in place afterward as reusable dev
fixtures, not deleted, since they carry no PII/security sensitivity and
are clearly test data (`Visual Tester`, `visual-test.csv`). Local dev
servers (backend on :8010, frontend on :3000) were started and stopped
cleanly. A small scratch Playwright script (not committed — lived in
the frontend directory only transiently, deleted after each use) drove
real login, theme switching, and navigation.

## What was actually checked, and what was found

Every item below is something a screenshot caught that static code
reading would not have (or confirmed fixed afterward with a second
screenshot) — this list is the actual value of doing this, not a
formality:

1. **Sidebar nav-group labels unreadable** — `text-on-dark-secondary`
   (a pale grey meant for a dark sidebar) left over on a now-light
   sidebar background. Fixed, re-screenshotted, confirmed legible.
2. **Dashboard "OnHolland AI" card unreadable** — white text classes
   left over from when that card was a vivid gradient; now a flat tint
   with dark text. Fixed, confirmed.
3. **Native `<select>` elements looked like a different app** — OS
   default chrome next to custom-styled inputs. Fixed with a custom
   chevron, confirmed visually identical treatment to text inputs.
4. **A hydration-mismatch React warning** on every page load (caught in
   the dev server log while screenshotting, not from a screenshot
   itself) — fixed with `suppressHydrationWarning`, confirmed gone.
5. **Dark mode genuinely did not work in my first test** — the test
   script set `localStorage` after the page had already hydrated,
   which doesn't retroactively change already-rendered state. Caught
   because the "dark" screenshot was pixel-identical to the "light"
   one. Fixed the test methodology (reload after setting storage, which
   mirrors how a real user's *next visit* behaves) before concluding
   dark mode itself was broken — it wasn't; the first test was.
6. **A white-on-purple contrast failure in dark mode** — `--navy`'s
   dark-mode value (lightened for text legibility) used as a solid
   button fill measured 2.72:1 for white text, visibly weak in the
   dark-mode Ledger screenshot. Measured precisely (not just "looks a
   bit off"), fixed with a separate `--navy-solid` token, re-measured
   at 5.7:1, re-screenshotted to confirm.
7. **An invalid hex colour** (`#ecease9`, 7 characters) shipped in
   `globals.css` for the active-nav-item background — found while
   rewriting the contrast-check script to parse the actual current
   tokens (it failed to parse), not from a screenshot. Fixed.
8. **Theme toggle verified functionally, not just visually**: scripted
   a real click on the "Dark" option and read back
   `document.documentElement.getAttribute("data-theme")` and
   `localStorage.getItem("onholland-theme")` immediately after — both
   updated correctly with no reload, confirming the toggle actually
   works end-to-end, not just that it renders.

## Screenshots taken and reviewed

| # | Page | Theme | Viewport | Result |
|---|---|---|---|---|
| 1 | Dashboard | Light | 1440×900 | Clean; AI card legible; nav legible |
| 2 | Dashboard | Dark | 1440×900 | Clean; all fixes above verified |
| 3 | Bank Transactions | Light | 1440×900 | Compact table, Dutch currency, status pills |
| 4 | Bank Transactions | Dark | 1440×900 | Status pills and amounts remain legible |
| 5 | Accounting Ledger | Light | 1440×900 | Same compact-table treatment, second example |
| 6 | Accounting Ledger | Dark | 1440×900 | Confirmed the white-on-button contrast fix |
| 7 | VAT Overview | Light | 1440×900 | Clean; near-black title; empty state styled correctly |
| 8 | Payroll (Salarisadministratie) | Light | 1440×900 | Clean; consistent card/table styling |
| 9 | Financial Overview (accountant portfolio) | Light | 1440×900 | Multi-company table, real revenue/VAT/reconciliation data |
| 10 | Dashboard | Light, mobile 390×844 | No horizontal overflow; cards stack; topbar icons fit |
| 11 | Mobile nav drawer (open) | Light, mobile 390×844 | Overlay, close button, all nav items, user footer all functional |
| 12 | Login | Light + Dark | 1440×900 | First page verified; confirmed the dark-mode testing methodology fix (#5 above) here first |

## Round 2 ("PHASE 14 CONTINUATION — MOLLIE UI COMPLETION")

Started from the Round 1 state above. First completed the remaining
27-page `table-v3` migration (see `docs/ui-transformation-progress.md`
for the full list), then ran the four verification passes Round 1
explicitly flagged as not done.

### Tablet responsiveness (768px, 1024px)

Captured real screenshots at both breakpoints across 15+ routes
(dashboard, banking, ledger, VAT list + detail, scenarios,
working-capital, cash-flow, sales/purchases upload, profit-and-loss,
employees, forecasts), in light and dark mode where applicable, plus
with a company actively selected (not just the empty "select a
company" state) so real data tables/forms render. Checked
`document.documentElement.scrollWidth - clientWidth` on every page —
**zero horizontal page overflow found anywhere**. Confirmed the
sidebar's hamburger-to-full-rail transition happens exactly at
Tailwind's `lg:` (1024px) breakpoint as intended, both with and
without the breakpoint-boundary pixel. Wide tables (8+ columns, e.g.
the ledger list showing Date/Type/Counterparty/Net/VAT/Gross/Payment/
Approval) scroll within their own card via `overflow-x-auto` rather
than overflowing the page — this is the existing, intentional
responsive-table pattern, confirmed working, not a gap.

### Real-browser axe-core sweep (light + dark, 12 routes)

Round 1 explicitly noted axe-core had not been re-run for the new
theme and that the existing suite (`test/axe.ts`) runs in jsdom, which
cannot evaluate `color-contrast` at all (no layout/paint engine —
axe-core itself skips the rule there). This round injected the real
`axe-core` package into live Playwright-rendered pages (`page.
addScriptTag` + `window.axe.run`), which *can* evaluate contrast
against actual computed/rendered colors. Ran the full `wcag2a`/
`wcag2aa`/`wcag22aa` ruleset against 12 representative routes × 2
themes = 24 combinations.

Found 5 genuine defects, all now fixed and re-verified at 0 violations
across all 24 combinations:

| Finding | Where | Fix |
|---|---|---|
| `<select>` with no accessible name (critical) | Dashboard company switcher | Added `aria-label="Company"` |
| `.status-pill-success`/`-warning` text-on-tint contrast measured 4.25–4.27:1 (needs 4.5:1) | Dashboard, Bank Transactions | Reduced pill background tint alpha 0.12→0.06 for all 4 status colors; re-measured 4.5–6.1:1 |
| Stray `<p>` as direct child of `<dl>` (invalid structure) | `ai-intelligence` | Moved disclaimer text outside the `<dl>` |
| `<svg role="img">` containing real focusable `role="button"` hit targets — `role="img"` forbids accessible descendants | `GlassChartCard` (dashboard Cash Flow chart) | Changed to `role="group"`, which permits the existing per-data-point keyboard navigation |
| `text-amber-600` (Tailwind raw, not a theme token) measured 3.19:1 on white — a clear pre-existing failure, not introduced this phase | 9 files, all plain disclaimer/status text | Swept to the existing theme-aware `text-pending` class, already passing in both themes |

One contrast fix took two attempts to verify correctly: the first
re-run after editing `globals.css` still reported the old `rgba(…,
0.12)` background via `getComputedStyle` — the Next.js dev server's
cache hadn't picked up the CSS change. Caught by checking the actual
computed style value, not just trusting the edited source file; fixed
by restarting the dev server (`rm -rf .next/cache` + restart), then
re-confirmed 0 violations.

Also re-ran `scripts/contrast-check.py` (the static token-pair
checker) to re-examine the two previously documented "expected
exception" cases, per this round's explicit instruction to
distinguish real exceptions from defects riding on that label. Both
remain legitimate (disabled/placeholder text, a decorative divider) —
but the re-check surfaced one usage that had been *incorrectly*
treated as covered by the "disabled/placeholder only" exception:
`kpis/page.tsx` rendered each KPI's formula as permanent, substantive
text in `text-muted`. Fixed to `text-secondary`.

### Currency formatting audit (found via tablet screenshots, not axe-core)

Not an accessibility check, but found during the same screenshot
review: `/cash-flow`'s "Actual — net bank movement to date" stat
rendered as a raw `"3003.20"` instead of `"€ 3.003,20"`. Grepping for
the same pattern (a currency-sounding field name rendered without
`formatEUR`) across every page that already imports `formatEUR`
(meaning it was partially converted, so likely to have missed a spot)
found 7 more files with the same gap; a second, broader grep for
literal `€${value}` string interpolation (a different wrong pattern —
produces `"€1000.00"`, not Dutch-formatted) found 4 more files,
including the dashboard's own top-level YTD stat cards. 16 files
fixed in total across both rounds. See
`docs/ui-transformation-progress.md` for the full list.

### Shared component gap (found via screenshotting a "done" page)

`/sales/upload` and `/purchases/upload` were listed as part of the
"automatic via shared CSS" bucket A, since the page files themselves
are trivial wrappers. A tablet screenshot of `/sales/upload` showed a
purple heading and plain-white OS-default form card — the actual
upload UI lives in `components/BulkUploadScreen.tsx`, which every
earlier sweep had missed because they searched `app/` only. Converted
it to the standard `card-v2`/`input-v2`/theme-token treatment;
re-screenshotted in both light and dark to confirm (dark mode before
the fix would have rendered as a solid white card on a dark page).

### Screenshots taken and reviewed (Round 2)

| # | Page | Theme | Viewport | Result |
|---|---|---|---|---|
| 13 | Dashboard | Light + Dark | 1440×900 | Chart renders with theme-correct colors; YTD stat cards now Dutch-formatted |
| 14 | Bank Transactions | Light + Dark | 1440×900 | Re-confirmed after status-pill contrast fix |
| 15 | Accounting Ledger | Light + Dark | 1440×900 | Re-confirmed |
| 16 | Sales Invoices (`/sales/upload`) | Light + Dark | 1440×900 / 768×1100 | Confirmed BulkUploadScreen fix in both themes |
| 17 | Purchase Invoices (`/purchases/upload`) | Light + Dark | 1440×900 | Confirmed BulkUploadScreen fix in both themes |
| 18 | VAT Overview + detail | Light + Dark | 1440×900 / 768×1100 | Clean |
| 19 | Payroll | Light | 1440×900 | Clean |
| 20 | Reports | Light | 1440×900 | Clean |
| 21 | AI Intelligence | Light + Dark | 1440×1100 | `<dl>` structure fix confirmed |
| 22 | Financial Overview (accountant workspace) | Light | 1440×900 | All 8 tiles now Dutch-formatted (previously raw decimals) |
| 23 | Scenarios, Working Capital, Cash Flow, Profit & Loss, Employees, Forecasts | Light | 768×~1100–1400 | Form/table reflow verified, no overflow |
| 24 | Dashboard, Bank Transactions | Light | Mobile 390×844 | Re-confirmed; wide tables scroll within their card as designed |
| 25 | Dashboard, Ledger | Light | Tablet 768×1024 / 1024×900 | Sidebar breakpoint transition confirmed correct |

## What was NOT verified

- **All routes individually** — the screenshots above (25 total across
  both rounds) are a representative sample across the shared-layout
  mechanism (see `docs/ui-transformation-progress.md`), not an
  exhaustive per-route check. A defect specific to one of the
  un-screenshotted routes could exist undetected, though the repo-wide
  greps this round (hardcoded colors, `€${}` interpolation, raw
  currency fields) substantially reduce that risk for the classes of
  bug actually found so far.
- **Real screen-reader testing** (VoiceOver/NVDA) — axe-core and the
  jsdom test suite catch structural/ARIA/contrast issues but are not a
  substitute for an actual screen-reader pass; none was done.
- **Lighthouse performance/SEO audit** — out of scope for this visual/
  accessibility-focused round.
