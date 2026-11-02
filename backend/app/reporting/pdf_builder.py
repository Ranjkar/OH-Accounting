"""Minimal branded PDF report builder on top of PyMuPDF (already a
dependency for PDF text extraction) -- no new PDF library needed."""

import fitz

NAVY = (0x0F / 255, 0x1B / 255, 0x3D / 255)
SLATE = (0.35, 0.39, 0.46)
BLACK = (0.1, 0.1, 0.1)
GREEN = (0.08, 0.5, 0.24)
RED = (0.73, 0.11, 0.11)

PAGE_WIDTH, PAGE_HEIGHT = 595, 842  # A4 in points
MARGIN = 48


class PdfReportBuilder:
    def __init__(self, title: str, company_name: str, subtitle: str, generated_at: str):
        self.doc = fitz.open()
        self.page = self.doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        self.y = MARGIN
        self._header(title, company_name, subtitle, generated_at)

    def _header(self, title: str, company_name: str, subtitle: str, generated_at: str) -> None:
        self.page.draw_rect(fitz.Rect(0, 0, PAGE_WIDTH, 90), color=NAVY, fill=NAVY)
        self.page.insert_text((MARGIN, 35), "OnHolland Accounting", fontsize=12, color=(1, 1, 1), fontname="helv")
        self.page.insert_text((MARGIN, 60), title, fontsize=18, color=(1, 1, 1), fontname="helv")
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
        self.page.insert_text((MARGIN, self.y), text, fontsize=13, color=NAVY, fontname="helv")
        self.y += 6
        self._hr()

    def text(self, text: str, size: float = 10, color=BLACK, bold: bool = False) -> None:
        self._ensure_space(size + 6)
        self.page.insert_text((MARGIN, self.y), text, fontsize=size, color=color, fontname="helv")
        self.y += size + 6

    def table(self, headers: list[str], rows: list[list[str]], col_widths: list[float] | None = None) -> None:
        available = PAGE_WIDTH - 2 * MARGIN
        col_widths = col_widths or [available / len(headers)] * len(headers)
        self._ensure_space(20)
        x = MARGIN
        for h, w in zip(headers, col_widths):
            self.page.insert_text((x, self.y), h, fontsize=9, color=SLATE, fontname="helv")
            x += w
        self.y += 6
        self._hr()
        for row in rows:
            self._ensure_space(16)
            x = MARGIN
            for cell, w in zip(row, col_widths):
                self.page.insert_text((x, self.y), str(cell), fontsize=9.5, color=BLACK, fontname="helv")
                x += w
            self.y += 16

    def key_value_row(self, label: str, value: str, highlight: bool = False) -> None:
        self._ensure_space(18)
        color = NAVY if highlight else BLACK
        self.page.insert_text((MARGIN, self.y), label, fontsize=10, color=SLATE, fontname="helv")
        self.page.insert_text((PAGE_WIDTH - MARGIN - 120, self.y), value, fontsize=10.5, color=color, fontname="helv")
        self.y += 18

    def to_bytes(self) -> bytes:
        return self.doc.tobytes()
