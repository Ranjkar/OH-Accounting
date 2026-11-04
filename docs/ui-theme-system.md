# Light / Dark / System theme system

No dark mode existed before this phase (confirmed by grep: zero
`prefers-color-scheme`/`data-theme` references anywhere in the
codebase prior). Built from nothing, independently designed per theme
(not a CSS filter/invert), per the brief's explicit instruction.

## Architecture

- **`<html data-theme="light"|"dark">`** is the single source of truth.
  `app/globals.css` defines the light palette on `:root` and overrides
  it wholesale under `:root[data-theme="dark"]` — every token, every
  shared class, every Tailwind utility updates automatically from one
  attribute.
- **`lib/theme-context.tsx`** (`ThemeProvider`/`useTheme`): holds the
  user's *preference* (`light`/`dark`/`system`, persisted to
  `localStorage` under `onholland-theme`) separately from the
  *resolved* theme actually applied. For `system`, it reads
  `window.matchMedia("(prefers-color-scheme: dark)")` and subscribes to
  its `change` event, so flipping the OS theme live-updates the app
  without a reload.
- **Anti-flash inline script** (`app/layout.tsx`, in `<head>`): plain
  JS, runs before React hydrates, reads `localStorage` (or falls back
  to the OS preference) and sets `data-theme` synchronously — the first
  painted frame is already correct. `<html>` carries
  `suppressHydrationWarning` since this script legitimately makes the
  server-rendered attribute differ from the client's; this is the
  standard, documented pattern for this exact situation (the same one
  `next-themes` uses), not a workaround for a real bug — verified a real
  hydration-mismatch warning existed before adding it and disappeared after.
- **`components/glass/ThemeToggle.tsx`**: a 3-way segmented control
  (Light/Dark/System always visible, not a cycling single button).
  Rendered in Settings (primary location) and compact (icon-only) in
  the topbar for quick access.

## Verification

Functionally tested by scripting a real click on the toggle and reading
back `document.documentElement.getAttribute("data-theme")` and
`localStorage.getItem("onholland-theme")` — both updated correctly,
live, with no page reload. Visually verified with real Playwright
screenshots in both themes across multiple routes (see
`docs/ui-visual-verification.md`).

## Known gaps

- No automated contrast regression test — the one real contrast bug
  found this phase (`--navy` vs `--navy-solid`, see
  `docs/mollie-design-system.md`) was caught by eye during manual
  screenshot review, not a scanner. `frontend/scripts/contrast-check.py`
  (Phase 11.1) checks the light-mode palette only; extending it to also
  check the dark-mode override block would catch this class of bug
  automatically in future and was not done this phase.
- PDF preview theming (mentioned in the brief) was not addressed —
  no PDF preview component exists in this codebase to theme.
