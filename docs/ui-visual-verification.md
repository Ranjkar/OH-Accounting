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

## What was NOT verified

- **Tablet breakpoint** (iPad-ish ~768–1024px) was not separately
  screenshotted — only desktop (1440px) and mobile (390px) were
  checked. The CSS uses the same Tailwind responsive utilities already
  present pre-Phase-14 (`sm:`/`md:`/`lg:` breakpoints), so tablet is
  very likely fine, but "likely fine" is not "verified," stated
  honestly.
- **All 52 routes individually** — the 12 screenshots above are a
  representative sample across the shared-layout mechanism (see
  `docs/ui-transformation-progress.md`), not an exhaustive per-route
  check. A defect specific to one of the ~40 un-screenshotted routes
  (as opposed to the shared Shell/Sidebar/token layer) could exist
  undetected.
- **axe-core / Lighthouse automated scan** was not re-run specifically
  for this phase's visual changes — the existing vitest+axe-core suite
  (71/71) continues to pass, but that suite covers component-level
  accessibility (focus traps, ARIA, keyboard nav), not a full-page
  colour-contrast or Lighthouse audit of the new theme.
