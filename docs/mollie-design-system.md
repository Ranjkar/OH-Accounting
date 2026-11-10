# Mollie-inspired design system

Replaces the Phase 11 glassmorphism palette as the application's default
visual language. Design authority: a detailed written description the
user provided of the Mollie Business Banking screenshots (no image
files were actually attached to the request; the user confirmed this
and supplied the description instead — see
`docs/mollie-ui-transformation-audit.md` for how that was handled).

## Principles

Minimalist, premium, spacious, understated. White main content, warm
off-white sidebar, near-black primary text, thin borders, minimal/no
shadows, no blur, no gradients, no decorative backgrounds. A restrained
OnHolland purple accent reserved for interactive elements (buttons,
active nav state, links, focus rings) — never page titles, section
headings, or large surfaces.

## Tokens (`app/globals.css`)

All values are CSS custom properties on `:root`, overridden wholesale
under `:root[data-theme="dark"]` (see `docs/ui-theme-system.md`). Every
existing shared class (`.card-v2`, `.btn-primary-v2`, `.input-v2`,
`.nav-item-v2`, etc.) and Tailwind utility (`bg-surface-card`,
`text-text-primary`, ...) draws from these, so changing a value here
re-skins every page using it — the same high-leverage mechanism Phase
11 used, reused for the opposite visual direction.

| Token | Light | Dark | Use |
|---|---|---|---|
| `--background` / `--surface-page` | `#ffffff` | `#171717` | Main content background |
| `--sidebar-bg` | `#faf8f7` | `#1d1d1d` | Sidebar |
| `--sidebar-active-bg` | `#ecease9` | `#303030` | Active/hovered nav item |
| `--surface-card` | `#ffffff` | `#242424` | Cards |
| `--surface-elevated` | `#ffffff` | `#2a2a2a` | Modals/dropdowns |
| `--border-subtle` | `#eae7e5` | `#383838` | Default borders |
| `--text-primary` | `#171717` | `#f5f5f5` | Primary text |
| `--text-secondary` | `#666666` | `#a3a3a3` | Secondary text |
| `--text-muted` | `#929292` | `#737373` | Muted/placeholder text |
| `--navy` | `#7c3aed` | `#a78bfa` | Accent text/links/icons (lightens in dark mode for legibility) |
| `--navy-solid` | `#7c3aed` | `#7c3aed` | Accent **fills** (buttons, pills, badges) — deliberately theme-invariant, see below |

### Why `--navy` and `--navy-solid` are different tokens

`--navy` needs to get lighter in dark mode to stay legible as plain
text against a dark page (`#a78bfa` on `#171717`). But that same
lighter value, used as a solid *background* with white text on top
(every primary button, active pill, badge), measures 2.72:1 — fails
WCAG AA's 4.5:1. A solid purple fill doesn't have the "stay readable
against the dark page" problem, so `--navy-solid` stays at the original
saturated `#7c3aed` in both themes, giving white text 5.7:1 in both.
This was a real bug, found and measured (not assumed) during visual
verification — see `docs/ui-visual-verification.md`.

## Components

- **Cards**: `--radius-card: 0.75rem` (~12px), `--border-subtle`,
  `--shadow-card` (`0 1px 2px rgba(23,23,23,0.04)` — effectively flat).
  No backdrop-filter, no translucency.
- **Buttons**: flat fills (`--navy-solid` for primary,
  `--semantic-error`/`--semantic-success` for danger/success), no
  gradients, no glow shadows.
- **Status pills** (`.status-pill-success/-neutral/-info/-warning/-danger`):
  low-saturation tinted fills, matching the Mollie transaction-list
  description (green=paid/matched, grey=neutral/expired,
  blue=info/refunded, amber=pending, red=failed). Tint alpha is `0.06`
  (not `0.12` as first shipped) — a real-browser axe-core run found the
  original value measured ~4.25:1 text-on-tint contrast in light mode
  (needs 4.5:1 for 12px text); `0.06` re-measures at 4.5–6.1:1 across
  all four colors in both themes. See `docs/ui-visual-verification.md`.
- **Tables** (`.table-v3`): compact rows (~36px), thin horizontal
  separators only, right-aligned monetary columns (`.col-amount`), no
  vertical gridlines. Now applied to every financial-list page in the
  app (completed in the "MOLLIE UI COMPLETION" continuation round) —
  confirmed via `grep` that no plain `<table className="w-full
  text-sm">` markup remains anywhere in `app/`. Wide tables (8+
  columns) scroll within their own card (`overflow-x-auto`) rather than
  overflowing the page on narrow viewports — verified at 390/768/1024/
  1440px.
- **Native `<select>` elements**: `appearance: none` plus a custom
  theme-aware chevron (inline SVG data-URI) so a select matches
  `.input-v2`'s flat styling instead of the OS's own dropdown chrome.
- **Charts** (`GlassChartCard`): SVG `fill`/`stroke` reference CSS
  custom properties (`var(--navy)`, `var(--border-subtle)`, etc.)
  instead of hardcoded hex, so they theme correctly. The chart
  container's ARIA role is `role="group"` (not `role="img"`, which
  would forbid its real focusable per-data-point hit targets — an ARIA
  conflict axe-core caught; see `docs/ui-visual-verification.md`). The
  app has one chart (dashboard Cash Flow); it shows a single
  forward-looking forecast series only — its backend response has no
  comparison/prior-period field, so no second series was added
  (fabricating one was explicitly out of scope).

## Currency & number formatting

`lib/format.ts`'s `formatEUR()` — `Intl.NumberFormat("nl-NL", {style:
"currency", currency: "EUR"})`, giving `€ 1.250,00` / `€ -89,50`
exactly per the brief's Dutch-formatting requirement. Now applied
consistently everywhere a monetary value is displayed. This took two
cleanup rounds to actually reach "everywhere": the first round applied
it only to Bank Transactions and the Ledger as the reference
implementation and left every other page rendering the backend's raw
Decimal string unformatted; the completion round found and fixed 16
more files across two passes — some had never called `formatEUR` at
all (e.g. `financial-overview`'s company-detail tiles showing
`"3003.20"`), others used ad-hoc `` `€${value}` `` string
interpolation instead of the shared formatter (e.g. the dashboard's
own YTD stat cards showing `"€1000.00"` instead of `"€ 1.000,00"` —
correct-looking at a glance, wrong on close inspection, which is
exactly why this needed an actual visual pass rather than a code-only
review).
