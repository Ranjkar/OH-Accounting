#!/usr/bin/env python3
"""WCAG 2.2 relative-luminance contrast checker for this app's actual
colour tokens (app/globals.css), not guesses. Run:
python3 scripts/contrast-check.py
No dependencies -- stdlib only.

Phase 14 rewrite: the previous version's cases were all tied to the
Phase 11 glassmorphism palette (translucent glass-surface blends over a
dark gradient background), which no longer exists -- every token below
is copied directly from the current app/globals.css light (:root) and
dark (:root[data-theme="dark"]) blocks. Covers both themes: the one
real contrast bug this phase (white text on --navy's dark-mode value,
2.72:1) was found by eye during screenshot review, not by this script,
precisely because the previous version never checked dark mode at all.
"""


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def srgb_to_linear(c):
    c = c / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb):
    r, g, b = (srgb_to_linear(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(hex1, hex2):
    l1 = relative_luminance(hex_to_rgb(hex1))
    l2 = relative_luminance(hex_to_rgb(hex2))
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def verdict(ratio, large=False):
    threshold = 3.0 if large else 4.5
    return "PASS" if ratio >= threshold else "FAIL"


LIGHT = {
    "background": "#ffffff", "sidebar-bg": "#faf8f7", "sidebar-active-bg": "#eceae9",
    "surface-card": "#ffffff", "border-subtle": "#eae7e5",
    "text-primary": "#171717", "text-secondary": "#666666", "text-muted": "#929292",
    "sidebar-text": "#171717", "sidebar-text-secondary": "#666666",
    "navy": "#7c3aed", "navy-solid": "#7c3aed",
    "semantic-success": "#15803d", "semantic-warning": "#b45309", "semantic-error": "#b91c1c", "semantic-info": "#1d4ed8",
}

DARK = {
    "background": "#171717", "sidebar-bg": "#1d1d1d", "sidebar-active-bg": "#303030",
    "surface-card": "#242424", "border-subtle": "#383838",
    "text-primary": "#f5f5f5", "text-secondary": "#a3a3a3", "text-muted": "#737373",
    "sidebar-text": "#f5f5f5", "sidebar-text-secondary": "#a3a3a3",
    "navy": "#a78bfa", "navy-solid": "#7c3aed",
    "semantic-success": "#4ade80", "semantic-warning": "#fbbf24", "semantic-error": "#f87171", "semantic-info": "#60a5fa",
}


def cases_for(theme_name, t):
    return [
        (f"[{theme_name}] text-primary on background", t["text-primary"], t["background"], False),
        (f"[{theme_name}] text-secondary on background", t["text-secondary"], t["background"], False),
        (f"[{theme_name}] text-primary on surface-card", t["text-primary"], t["surface-card"], False),
        (f"[{theme_name}] text-secondary on surface-card", t["text-secondary"], t["surface-card"], False),
        (f"[{theme_name}] sidebar-text on sidebar-bg", t["sidebar-text"], t["sidebar-bg"], False),
        (f"[{theme_name}] sidebar-text-secondary on sidebar-bg (nav section headings)", t["sidebar-text-secondary"], t["sidebar-bg"], False),
        (f"[{theme_name}] sidebar-text on sidebar-active-bg (active nav item)", t["sidebar-text"], t["sidebar-active-bg"], False),
        (f"[{theme_name}] navy (accent text/links) on background", t["navy"], t["background"], False),
        (f"[{theme_name}] white text on navy-solid (primary buttons/pills/badges)", "#ffffff", t["navy-solid"], False),
        (f"[{theme_name}] semantic-success on surface-card (value-positive)", t["semantic-success"], t["surface-card"], False),
        (f"[{theme_name}] semantic-warning on surface-card (value-warning)", t["semantic-warning"], t["surface-card"], False),
        (f"[{theme_name}] semantic-error on surface-card (value-negative)", t["semantic-error"], t["surface-card"], False),
        (f"[{theme_name}] semantic-info on surface-card", t["semantic-info"], t["surface-card"], False),
        (f"[{theme_name}] text-muted on surface-card -- EXPECTED EXCEPTION: only used for disabled/unavailable nav items and form placeholders, both exempt under WCAG's disabled-control guidance, never substantive content", t["text-muted"], t["surface-card"], False),
        (f"[{theme_name}] border-subtle on background -- EXPECTED EXCEPTION: a deliberately subtle divider, not a required-to-perceive UI boundary (no WCAG non-text-contrast obligation for a decorative separator)", t["border-subtle"], t["background"], True),
    ]


if __name__ == "__main__":
    cases = cases_for("light", LIGHT) + cases_for("dark", DARK)
    print(f"{'Verdict':<6} {'Ratio':>6}  Case")
    print("-" * 100)
    fails = []
    for desc, fg, bg, large in cases:
        ratio = contrast(fg, bg)
        v = verdict(ratio, large)
        if v == "FAIL":
            fails.append(desc)
        print(f"{v:<6} {ratio:>5.2f}  {desc}")
    print("-" * 100)
    print(f"{len(fails)} failing case(s) out of {len(cases)}")
    if fails:
        for f in fails:
            print(f"  FAIL: {f}")
