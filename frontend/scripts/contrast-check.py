#!/usr/bin/env python3
"""WCAG 2.2 relative-luminance contrast checker for this app's actual color
tokens (from globals.css), not guesses. Run: python3 scripts/contrast-check.py
No dependencies -- stdlib only."""

def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def srgb_to_linear(c):
    c = c / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb):
    r, g, b = (srgb_to_linear(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _as_rgb(c):
    return hex_to_rgb(c) if isinstance(c, str) else c


def blend(fg_hex, bg_hex, alpha):
    """Composite a translucent fg color over an opaque bg color."""
    fr, fg_, fb = _as_rgb(fg_hex)
    br, bg_, bb = _as_rgb(bg_hex)
    return (
        round(fr * alpha + br * (1 - alpha)),
        round(fg_ * alpha + bg_ * (1 - alpha)),
        round(fb * alpha + bb * (1 - alpha)),
    )


def contrast(hex1, hex2):
    l1 = relative_luminance(hex_to_rgb(hex1))
    l2 = relative_luminance(hex_to_rgb(hex2))
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def verdict(ratio, large=False):
    threshold = 3.0 if large else 4.5
    return "PASS" if ratio >= threshold else "FAIL"


CASES = [
    # (description, fg_hex, effective_bg_hex, is_large_text)
    ("text-primary (#0f0e17) on glass-surface over app-gradient darkest stop (#0b0a1f, 0.86 alpha)", "#0f0e17", blend("#ffffff", "#0b0a1f", 0.86), False),
    ("text-secondary (#6b7280) on glass-surface over app-gradient darkest stop", "#6b7280", blend("#ffffff", "#0b0a1f", 0.86), False),
    ("text-on-dark (#f4f3f8) on nav-rail dark bg (#0b0a1f)", "#f4f3f8", "#0b0a1f", False),
    ("nav-item default text (#a6a3b8) on nav-rail dark bg (#0b0a1f)", "#a6a3b8", "#0b0a1f", False),
    ("text-on-dark-secondary (#c9c6dc) on nav-rail dark bg", "#c9c6dc", "#0b0a1f", False),
    ("white text on btn-primary-v2 gradient start (#7c3aed)", "#ffffff", "#7c3aed", False),
    ("white text on btn-primary-v2 gradient end (#4f46e5 indigo-600)", "#ffffff", "#4f46e5", False),
    ("white text on glass-hero cyan-heavy end stop blended onto dark nav (cyan #22d3ee @ 0.35 over #4f46e5)", "#ffffff", blend("#22d3ee", "#4f46e5", 0.35), False),
    ("value-negative/error (#b91c1c) on white card", "#b91c1c", "#ffffff", False),
    ("value-positive/success (#15803d) on white card", "#15803d", "#ffffff", False),
    ("value-warning (#b45309) on white card", "#b45309", "#ffffff", False),
    ("text-primary on input-v2 bg (white @ 0.7 over glass-surface white @0.86 over dark app bg)", "#0f0e17", blend("#ffffff", blend("#ffffff", "#0b0a1f", 0.86), 0.7), False),
    ("placeholder text-secondary (#6b7280) on input-v2 bg", "#6b7280", blend("#ffffff", blend("#ffffff", "#0b0a1f", 0.86), 0.7), False),
    ("focus ring purple-500 (#8b5cf6) on btn-primary-v2 gradient start (#7c3aed) -- outline visibility, not text contrast", "#8b5cf6", "#7c3aed", False),
    ("disabled btn-primary-v2 text (white @ full) on 50%-opacity purple over glass card", "#ffffff", blend("#7c3aed", "#ffffff", 0.5), False),
]

if __name__ == "__main__":
    print(f"{'Verdict':<6} {'Ratio':>6}  Case")
    print("-" * 100)
    fails = []
    for desc, fg, bg, large in CASES:
        bg_hex = bg if isinstance(bg, str) else "#%02x%02x%02x" % bg
        fg_hex = fg if isinstance(fg, str) else "#%02x%02x%02x" % fg
        ratio = contrast(fg_hex, bg_hex)
        v = verdict(ratio, large)
        if v == "FAIL":
            fails.append(desc)
        print(f"{v:<6} {ratio:>5.2f}  {desc}")
    print("-" * 100)
    print(f"{len(fails)} failing case(s) out of {len(CASES)}")
