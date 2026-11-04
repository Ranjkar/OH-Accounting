"""Minimal branded PDF report builder on top of PyMuPDF (already a
dependency for PDF text extraction) -- no new PDF library needed for
Latin-script output.

Persian/Arabic output needs two things base-14 PDF fonts and PyMuPDF's
insert_text() do not provide on their own:
  1. Actual Arabic-script glyphs -- the base-14 "helv" (Helvetica) font
     only covers WinAnsi/Latin-1, so Arabic/Persian text in it renders as
     empty/undefined-glyph boxes (verified empirically, not assumed: see
     the Phase 16.1 report). Fixed by embedding real fonts with Arabic
     GSUB/GPOS tables (see fonts/).
  2. Shaping -- insert_text() places one glyph per character in logical
     (reading) order; it does not apply Arabic contextual-form
     substitution or bidi reordering itself. Fixed by pre-processing text
     with arabic_reshaper (logical text -> correct initial/medial/final/
     isolated presentation-form glyphs) and python-bidi (logical order ->
     visual left-to-right glyph order), then inserting the result as a
     plain string -- the standard technique for PDF toolkits without a
     built-in complex-script shaping engine.
"""

from pathlib import Path

import arabic_reshaper
import fitz
from bidi.algorithm import get_display

NAVY = (0x0F / 255, 0x1B / 255, 0x3D / 255)
SLATE = (0.35, 0.39, 0.46)
BLACK = (0.1, 0.1, 0.1)
GREEN = (0.08, 0.5, 0.24)
RED = (0.73, 0.11, 0.11)

PAGE_WIDTH, PAGE_HEIGHT = 595, 842  # A4 in points
MARGIN = 48

FONTS_DIR = Path(__file__).parent / "fonts"

# Static instances (weight 400) cut from Google's variable Noto Sans
# Arabic / Vazirmatn woff2 files via fontTools, see the Phase 16.1 report
# for provenance -- both retain their GSUB/GPOS tables (contextual
# substitution + mark positioning), which is what makes the shaped
# presentation-form text below actually join up instead of rendering as
# disconnected isolated letterforms.
RTL_FONT_FILES = {
    "ar": FONTS_DIR / "NotoSansArabic-Regular.ttf",
    "fa": FONTS_DIR / "Vazirmatn-Regular.ttf",
}
RTL_LOCALES = set(RTL_FONT_FILES)


def is_rtl(locale: str) -> bool:
    return locale in RTL_LOCALES


def shape_rtl(text: str) -> str:
    """Logical-order text -> visual-order, presentation-form text ready
    for insert_text(). A no-op for any run with no Arabic-range
    characters, so it's safe to call on mixed Arabic/Latin/digit strings
    (IBANs, invoice refs, amounts) -- arabic_reshaper only rewrites
    Arabic-script codepoints and bidi.get_display() only reorders runs
    that actually need it per the Unicode Bidi Algorithm."""
    return get_display(arabic_reshaper.reshape(text))


class PdfReportBuilder:
    def __init__(self, title: str, company_name: str, subtitle: str, generated_at: str, locale: str = "nl"):
        self.locale = locale
        self.rtl = is_rtl(locale)
        self.doc = fitz.open()
        self.page = self.doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        self.y = MARGIN
        if self.rtl:
            self.fontname = f"rtl-{locale}"
            self.fontfile = str(RTL_FONT_FILES[locale])
            self._font = fitz.Font(fontfile=self.fontfile)
        else:
            self.fontname = "helv"
            self.fontfile = None
            self._font = fitz.Font("helv")
        self._header(title, company_name, subtitle, generated_at)

    def _render(self, text: str) -> str:
        return shape_rtl(text) if self.rtl else text

    def _width(self, text: str, size: float) -> float:
        return self._font.text_length(text, fontsize=size)

    def _put(self, text: str, size: float, color, *, right_edge: float | None = None, x: float | None = None) -> None:
        """Insert text anchored either at a fixed left x, or with its
        right edge at `right_edge` (used for RTL paragraphs, which read
        from the page's right margin inward -- the logical-use-left-
        margin layout. For RTL this is not mere text-align: the whole
        text block's start position mirrors.)"""
        shaped = self._render(text)
        if right_edge is not None:
            x = right_edge - self._width(shaped, size)
        self.page.insert_text((x, self.y), shaped, fontsize=size, color=color, fontname=self.fontname, fontfile=self.fontfile)

    def _leading_edge(self) -> dict:
        """x= for LTR (text starts at the left margin), right_edge= for
        RTL (text starts at the right margin and grows leftward)."""
        return {"right_edge": PAGE_WIDTH - MARGIN} if self.rtl else {"x": MARGIN}

    def _header(self, title: str, company_name: str, subtitle: str, generated_at: str) -> None:
        self.page.draw_rect(fitz.Rect(0, 0, PAGE_WIDTH, 90), color=NAVY, fill=NAVY)
        self.y = 35
        self._put("OnHolland Accounting", 12, (1, 1, 1), **self._leading_edge())
        self.y = 60
        self._put(title, 18, (1, 1, 1), **self._leading_edge())
        self.y = 110
        self.text(company_name, size=13, bold=True)
        self.text(subtitle, size=10, color=SLATE)
        self.text(f"Generated {generated_at}", size=8, color=SLATE)
        self.y += 8
        self._hr()

    def _hr(self) -> None:
        self.page.draw_line((MARGIN, self.y), (PAGE_WIDTH - MARGIN, self.y), color=SLATE, width=0.5)
        self.y += 14

    def _ensure_space(self, needed: float = 20) -> None:
        if self.y + needed > PAGE_HEIGHT - MARGIN:
            self.page = self.doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
            self.y = MARGIN

    def heading(self, text: str) -> None:
        self._ensure_space(30)
        self.y += 8
        self._put(text, 13, NAVY, **self._leading_edge())
        self.y += 6
        self._hr()

    def text(self, text: str, size: float = 10, color=BLACK, bold: bool = False) -> None:
        self._ensure_space(size + 6)
        self._put(text, size, color, **self._leading_edge())
        self.y += size + 6

    def table(self, headers: list[str], rows: list[list[str]], col_widths: list[float] | None = None) -> None:
        """Columns flow from the page's leading edge: left-to-right for
        LTR locales, right-to-left for RTL ones (so the first header in
        `headers` is always the first column a reader of that language
        encounters), with each cell's text hugging its column's leading
        edge -- the PDF equivalent of text-align: start."""
        available = PAGE_WIDTH - 2 * MARGIN
        col_widths = col_widths or [available / len(headers)] * len(headers)
        self._ensure_space(20)

        def col_starts() -> list[float]:
            if not self.rtl:
                starts = []
                x = MARGIN
                for w in col_widths:
                    starts.append(x)
                    x += w
                return starts
            starts = []
            x = PAGE_WIDTH - MARGIN
            for w in col_widths:
                x -= w
                starts.append(x)
            return starts

        starts = col_starts()
        for h, x in zip(headers, starts):
            self._put(h, 9, SLATE, x=x)
        self.y += 6
        self._hr()
        for row in rows:
            self._ensure_space(16)
            for cell, x in zip(row, starts):
                self._put(str(cell), 9.5, BLACK, x=x)
            self.y += 16

    def key_value_row(self, label: str, value: str, highlight: bool = False) -> None:
        self._ensure_space(18)
        color = NAVY if highlight else BLACK
        if self.rtl:
            # Label hugs the right margin (leading edge for RTL), value
            # sits at the left margin -- mirrored from the LTR layout
            # below, not just re-aligned text.
            self._put(label, 10, SLATE, right_edge=PAGE_WIDTH - MARGIN)
            self._put(value, 10.5, color, x=MARGIN)
        else:
            self._put(label, 10, SLATE, x=MARGIN)
            self._put(value, 10.5, color, x=PAGE_WIDTH - MARGIN - 120)
        self.y += 18

    def to_bytes(self) -> bytes:
        return self.doc.tobytes()
