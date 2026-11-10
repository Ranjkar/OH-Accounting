# UI/UX transformation (Phase 14)

## Starting point

Phase 11 built the glassmorphism design system and applied it across
every route (via Glass* React components on new/rebuilt pages, and by
re-theming the shared `.card-v2`/`.btn-primary-v2`/`.input-v2` CSS
classes so every page using them inherited the look without a rewrite).
Phase 11.1 then fixed concrete quality/accessibility defects (contrast,
focus traps, keyboard nav, a semantic colour token system). Phase 12/13
individually audited and fixed the ~29 pages Phase 11.1 hadn't reached.
Phase 14's real job was therefore a genuine **audit** of what remained
inconsistent, not a from-scratch redesign of an unstyled app.

## What the audit found and fixed

- **27 of 52 routes rendered a plain `<table>`** (pre-dating the
  `GlassTable` component, which has its own built-in mobile stacked-card
  view) **with no horizontal-scroll container** -- a wide financial
  table on a narrow viewport would force the whole page to scroll
  sideways, not just the table, breaking the sidebar/layout. Fixed by
  wrapping every one in `<div className="overflow-x-auto">` (verified
  first that every `<table>`/`</table>` tag was single-line with no
  nesting, scripted the wrap, spot-checked the diff). A full migration
  to `GlassTable` across 27 pages with differing column structures was
  judged too large a rewrite for the time available and was not
  attempted as a half-measure.
- **No global company switcher existed** -- every page managed its own
  independent company selector. Built `CompanyProvider`
  (`lib/company-context.tsx`) + `CompanySwitcher` in the topbar,
  persisted to `localStorage`. Wired into the 2 cross-cutting Phase 13
  screens (`/ai-intelligence`, `/review-centre`) as a drop-in
  replacement for their own per-page fetch+state. **Not** retrofitted
  into the other ~40 pages' own selectors -- too large and risky a
  refactor for this phase; stated as a known inconsistency, not
  silently claimed solved everywhere.
- **Two more missing-`aria-label` gaps** found and fixed (the new
  `/ai-intelligence` and `/review-centre` pages' own company selectors,
  plus `/banking`, `/vat`, and `/anomalies` which had the same gap
  pre-existing from before those pages adopted `GlassSelect`) -- see
  `docs/ui-accessibility-audit.md` for the full running history across
  Phases 12-14.
- **New pages this phase** (`/billing`, `/admin`, `/invitations/accept`)
  built with the existing Glass component set from the start, not a new
  one-off style.

## What was NOT done, stated honestly

- **Not every one of the 52 routes was individually re-designed.** Given
  the scale of genuinely new functional work this phase also required
  (company invitations, subscriptions/billing, platform admin), a
  full per-page visual pass across all 52 routes was not attempted on
  top of the targeted fixes above. The existing Phase 11/11.1 visual
  language (colour tokens, typography, card/button/input styling) is
  already consistently applied everywhere via the shared CSS classes;
  what changed this phase were concrete, found defects, not a visual
  re-skin.
- **No real browser screenshots.** Claude in Chrome tools were listed as
  available this session; a real attempt was made (dev servers started,
  a throwaway test user created) but the browser extension was not
  actually connected when tested. Documented honestly rather than
  claiming a screenshot that was not taken -- same limitation as every
  prior phase.
- **No formal automated accessibility scan run this phase** (axe-core
  via the frontend's own vitest suite continues to pass, 71/71, but no
  new Lighthouse/Playwright pass was run specifically for Phase 14's
  changes) -- manual code review and the existing automated suite are
  the evidence, not a scanner report.

## Verification

`tsc --noEmit`, `npm run lint`, `npm run build` (all 52 routes,
including the 3 new ones), and `npm run test` (71/71 vitest+axe-core)
all clean after every change in this phase.
