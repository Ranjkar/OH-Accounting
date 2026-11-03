# UI accessibility audit

## Phase 11.1 (full remediation, not just an audit)

Phase 11.1 covered the dashboard, login, banking, VAT, loonheffingen,
annual-statements, employee-portal, trial-balance, ledger, payroll,
employees, tax-centre, and management-reports pages individually, plus
every shared Glass component. That work is documented in the Phase 11.1
final report (see git log) and is not repeated here. Summary of what it
fixed: colour-contrast failures (verified with
`frontend/scripts/contrast-check.py`, a hand-written WCAG 2.2 relative-
luminance checker, not an assumption), a real focus trap in `GlassModal`,
arrow-key navigation in `GlassDropdown`, keyboard-focusable chart points
with a `.sr-only` data table in `GlassChartCard`, a centralized semantic
colour token system, a typography scale, and `prefers-reduced-motion`
support.

## Phase 12 (Workstream A -- the remaining ~29 pages)

Phase 11.1 did not individually review every page. This phase swept the
remaining pages for the same defect class already fixed elsewhere:
interactive controls with no accessible name.

**Method:** grepped every `app/**/page.tsx` for `<select`/`<input`
elements, then manually inspected each hit's surrounding JSX (not just
counted matches) to separate three cases:

1. **No visible label, no placeholder, no `aria-label`** -- a screen
   reader announces these as an unnamed combobox/textbox. This is the
   real defect class fixed this phase.
2. **Visible `<label>` text present but not programmatically associated**
   (`htmlFor`/`id` missing) -- sighted users see a label; screen-reader
   users may not get it depending on DOM proximity/AT heuristics. Lower
   severity, **not fixed this phase** (see "Remaining gaps" below).
3. **Already adequately labelled** (placeholder, or `htmlFor`/`id` pair
   already wired) -- no action needed.

**Fixed (case 1), 24 files, ~40 controls:** `aria-label` added, inferred
from each field's own state-variable name (e.g. `financialYearId` ->
`"Financial Year"`) -- a mechanical, reviewed pass, not a guess at
unrelated copy. Files: `companies`, `balance-sheet`, `profit-and-loss`,
`reports`, `financial-overview`, `companies/[id]/workspace`, `assistant`,
`reconciliation`, `entrepreneur-hours`, `calendar`, `working-hours`,
`legal-structure`, `cash-flow`, `bank-transactions`, `budgets`,
`scenarios`, `automation`, `documents`, `forecasts`, `tax-optimization`,
`working-capital`, `batches`, `categories`, `batches/[id]` (one checkbox,
`aria-label="Select document {id}"`).

Verified with `tsc --noEmit` (clean), `npm run lint` (clean -- the two
pre-existing warnings are unrelated: an `<img>` LCP hint and one
`exhaustive-deps` hint), `npm run build` (clean, including the new
`/government` route), and `npm run test` (68/68 vitest + axe-core tests
passing).

**Also fixed in passing:** `lib/api.ts`'s `BankAccount` TypeScript
interface and `BankConsentStatus` type were stale -- missing
`provider_name`/`consent_granted_at`/`consent_expires_at`/
`last_synced_at`/`last_sync_error` (all real `BankAccountOut` fields since
Phase 12's Open Banking work) and listing a `FILE_IMPORT_ONLY` status
value that was never a backend enum member while missing the real
`PENDING`/`EXPIRED`/`ERROR`/`REVOKED` values. Not a visual defect, but a
real type-correctness gap that the new Banking Connections UI (see
`docs/open-banking.md`) would otherwise have silently mistyped.

## Remaining gaps (documented, not fixed)

- **Case 2 above** (visible label not programmatically associated) still
  exists in `app/companies/page.tsx`, `app/companies/[id]/page.tsx`,
  `app/documents/[id]/page.tsx`, and `app/ledger/[id]/page.tsx`. Sighted
  users are unaffected; screen-reader users relying on strict
  label-association (rather than DOM-proximity heuristics some AT/browser
  combinations apply) may not hear the label. Fix is mechanical
  (`htmlFor`/`id` pairs, same pattern Phase 11.1 already applied
  elsewhere) but was not done this phase to keep the change scoped and
  reviewable; flagging it explicitly rather than claiming full coverage.
- **No automated axe-core `color-contrast` checking** -- jsdom (used by
  the vitest suite) has no rendering engine, so that axe rule is
  disabled in tests by design; contrast is verified separately by the
  Python script, as already documented in Phase 11.1. This phase added
  no new colour usage, so no new contrast check was needed.
- **No browser automation / real screen-reader testing was performed**
  this phase (same limitation as Phases 11 and 11.1, documented there) --
  these are static-analysis and automated-test fixes, not manually
  verified with a screen reader or against rendered contrast. Do not
  read this document as a WCAG compliance claim.
