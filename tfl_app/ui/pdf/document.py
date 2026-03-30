from __future__ import annotations

from fpdf import FPDF, XPos, YPos

from tfl_app.ui.pdf.layout import (
    PDF_COLOR_BORDER,
    PDF_COLOR_MUTED,
    PDF_COLOR_NAVY,
    PDF_COLOR_NAVY_DARK,
    PDF_COLOR_TEXT,
    PDF_FOOTNOTE_SIZE,
    PDF_FONT_SANS,
    _pdf_safe_text,
)
from tfl_app.ui.pdf.pages import _pdf_add_contents_page, _pdf_add_cover_page


class ReportPDF(FPDF):
    def __init__(self, header_title: str, header_subtitle: str, generated_date: str):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.header_title = header_title
        self.header_subtitle = header_subtitle
        self.generated_date = generated_date

    def header(self):
        if self.page_no() == 1:
            return
        self.set_y(7.2)
        self.set_text_color(*PDF_COLOR_NAVY_DARK)
        self.set_font(PDF_FONT_SANS, "B", 7.6)
        width = self.w - self.l_margin - self.r_margin
        left_w = width * 0.78
        right_w = width - left_w
        self.cell(left_w, 4.3, _pdf_safe_text(self.header_title), new_x=XPos.RIGHT, new_y=YPos.TOP, align="L")
        self.set_font(PDF_FONT_SANS, "", 6.8)
        self.set_text_color(*PDF_COLOR_MUTED)
        self.cell(right_w, 4.3, _pdf_safe_text("Policy Brief"), new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="R")
        self.set_x(self.l_margin)
        subtitle = str(self.header_subtitle or "")
        if len(subtitle) > 90:
            subtitle = subtitle[:87].rstrip() + "..."
        self.set_font(PDF_FONT_SANS, "", 6.5)
        self.set_text_color(*PDF_COLOR_MUTED)
        self.cell(0, 3.2, _pdf_safe_text(subtitle), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*PDF_COLOR_BORDER)
        self.line(self.l_margin, self.get_y() + 0.4, self.w - self.r_margin, self.get_y() + 0.4)
        self.ln(1.8)
        self.set_text_color(*PDF_COLOR_TEXT)

    def footer(self):
        self.set_y(-12)
        self.set_text_color(*PDF_COLOR_MUTED)
        self.set_font(PDF_FONT_SANS, "", PDF_FOOTNOTE_SIZE)
        w = self.w - self.l_margin - self.r_margin
        self.set_draw_color(*PDF_COLOR_BORDER)
        self.line(self.l_margin, self.get_y() - 1.2, self.w - self.r_margin, self.get_y() - 1.2)
        left_w = w * 0.68
        right_w = w - left_w
        self.cell(left_w, 4, _pdf_safe_text(f"Generated {self.generated_date}"), new_x=XPos.RIGHT, new_y=YPos.TOP, align="L")
        self.set_font(PDF_FONT_SANS, "B", PDF_FOOTNOTE_SIZE)
        self.set_text_color(*PDF_COLOR_NAVY)
        self.cell(right_w, 4, _pdf_safe_text(f"Page {self.page_no()}"), new_x=XPos.RIGHT, new_y=YPos.TOP, align="R")
        self.set_text_color(*PDF_COLOR_TEXT)


def _create_report_pdf_shell(payload: dict) -> ReportPDF:
    header_title = payload.get("report_title", "Lobby Look-Up Report")
    scope_sub = payload.get("scope_session_label") or payload.get("scope_label", "")
    header_subtitle = f"{scope_sub} | {payload['focus_label']}".strip(" |")
    pdf = ReportPDF(header_title, header_subtitle, payload["generated_date"])
    pdf.set_margins(12, 20, 12)
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.set_title(_pdf_safe_text(header_title))
    pdf.set_author(_pdf_safe_text("Lobby Look-Up"))
    pdf.add_page()
    _pdf_add_cover_page(pdf, payload)
    _pdf_add_contents_page(
        pdf,
        payload,
        include_focus_snapshot=bool(payload.get("focus_section") and isinstance(payload.get("focus_section"), dict)),
    )
    pdf.add_page()
    setattr(pdf, "_figure_counter", 0)
    return pdf


__all__ = [
    "ReportPDF",
    "_create_report_pdf_shell",
]
