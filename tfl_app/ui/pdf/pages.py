from __future__ import annotations

from fpdf import FPDF, XPos, YPos

from tfl_app.ui.pdf.layout import (
    PDF_BODY_SIZE,
    PDF_COLOR_ACCENT,
    PDF_COLOR_BORDER,
    PDF_COLOR_MUTED,
    PDF_COLOR_NAVY_DARK,
    PDF_COLOR_PAGE_BG,
    PDF_COLOR_TEXT,
    PDF_FOOTNOTE_SIZE,
    PDF_FONT_SANS,
    PDF_FONT_SERIF,
    PDF_H1_SIZE,
    _pdf_add_heading,
    _pdf_add_paragraph,
    _pdf_add_subheading,
    _pdf_ensure_space,
    _pdf_safe_text,
)


def _pdf_add_cover_page(pdf: FPDF, payload: dict) -> None:
    page_w = pdf.w
    page_h = pdf.h

    pdf.set_fill_color(*PDF_COLOR_PAGE_BG)
    pdf.rect(0, 0, page_w, page_h, "F")

    pdf.set_fill_color(244, 249, 255)
    pdf.rect(page_w * 0.86, 0, page_w * 0.14, page_h, "F")
    pdf.set_fill_color(*PDF_COLOR_NAVY_DARK)
    pdf.rect(0, 0, page_w, 27, "F")
    pdf.set_fill_color(*PDF_COLOR_ACCENT)
    pdf.rect(0, 27, page_w, 1.6, "F")

    logo_w = 30
    logo_h = 10
    logo_x = page_w - pdf.r_margin - logo_w
    logo_y = 8.8
    pdf.set_draw_color(187, 205, 226)
    pdf.set_fill_color(23, 55, 90)
    pdf.rect(logo_x, logo_y, logo_w, logo_h, "DF")
    pdf.set_font(PDF_FONT_SANS, "B", 8)
    pdf.set_text_color(236, 243, 250)
    pdf.set_xy(logo_x, logo_y + 2.6)
    pdf.cell(logo_w, 4, "LOGO", align="C")

    header_title = payload.get("report_title", "Lobby Look-Up Report")
    scope_sub = payload.get("scope_session_label") or payload.get("scope_label", "")
    focus_label = payload.get("focus_label", "")

    pdf.set_text_color(236, 243, 250)
    pdf.set_font(PDF_FONT_SANS, "B", 8.5)
    pdf.set_xy(pdf.l_margin, 7.4)
    pdf.cell(page_w - pdf.l_margin - pdf.r_margin - logo_w - 8, 4.8, _pdf_safe_text(header_title))
    pdf.set_font(PDF_FONT_SANS, "", 7)
    pdf.set_xy(pdf.l_margin, 12.5)
    top_sub = f"{scope_sub} | {focus_label}".strip(" |")
    if len(top_sub) > 88:
        top_sub = top_sub[:85].rstrip() + "..."
    pdf.cell(page_w - pdf.l_margin - pdf.r_margin - logo_w - 8, 4.2, _pdf_safe_text(top_sub))

    pdf.set_text_color(*PDF_COLOR_NAVY_DARK)
    pdf.set_y(48)
    _pdf_add_heading(pdf, "TAXPAYER-FUNDED LOBBYING IN TEXAS", size=PDF_H1_SIZE)
    _pdf_add_subheading(pdf, f"Analysis of the {payload['session_label']} Legislative Session", size=12)

    box_x = pdf.l_margin
    box_y = 85
    box_w = page_w - pdf.l_margin - pdf.r_margin - 20
    box_h = 52
    pdf.set_fill_color(255, 255, 255)
    pdf.set_draw_color(*PDF_COLOR_BORDER)
    pdf.rect(box_x, box_y, box_w, box_h, "DF")
    pdf.set_fill_color(*PDF_COLOR_ACCENT)
    pdf.rect(box_x, box_y, 1.8, box_h, "F")

    pdf.set_font(PDF_FONT_SANS, "B", 10)
    pdf.set_text_color(*PDF_COLOR_NAVY_DARK)
    pdf.set_xy(box_x + 5.0, box_y + 3.0)
    pdf.cell(0, 5, "Report Scope")

    pdf.set_text_color(*PDF_COLOR_TEXT)
    pdf.set_font(PDF_FONT_SERIF, "", PDF_BODY_SIZE)
    pdf.set_xy(box_x + 5.0, box_y + 11.0)
    pdf.cell(0, 5.2, _pdf_safe_text(f"Session: {payload['session_label']}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(box_x + 5.0)
    pdf.cell(0, 5.2, _pdf_safe_text(f"Scope: {payload['scope_session_label']}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(box_x + 5.0)
    pdf.cell(0, 5.2, _pdf_safe_text(f"Focus: {payload['focus_label']}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(box_x + 5.0)
    pdf.cell(0, 5.2, _pdf_safe_text(f"Generated: {payload['generated_date']}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_draw_color(205, 218, 234)
    pdf.line(pdf.l_margin, page_h - 25, page_w - pdf.r_margin, page_h - 25)
    pdf.set_y(page_h - 23)
    pdf.set_font(PDF_FONT_SANS, "I", PDF_FOOTNOTE_SIZE)
    pdf.set_text_color(*PDF_COLOR_MUTED)
    pdf.cell(
        0,
        4.5,
        _pdf_safe_text("Prepared by Texas Taxpayer Lobbying Transparency Center"),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.cell(0, 4.5, _pdf_safe_text(payload.get("disclaimer_note", "")), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(*PDF_COLOR_TEXT)


def _pdf_add_contents_page(pdf: FPDF, payload: dict, *, include_focus_snapshot: bool) -> None:
    pdf.add_page()
    page_w = pdf.w
    page_h = pdf.h
    content_top = 20
    pdf.set_fill_color(*PDF_COLOR_PAGE_BG)
    pdf.rect(0, content_top, page_w, page_h - content_top, "F")

    pdf.set_text_color(*PDF_COLOR_NAVY_DARK)
    pdf.set_y(26)
    _pdf_add_heading(pdf, "Contents", size=14)
    _pdf_add_paragraph(
        pdf,
        "Legislative briefing sections included in this report.",
        size=10.5,
        line_h=5.2,
    )

    entries = [
        "Executive Summary",
    ]
    if include_focus_snapshot:
        entries.append("Focus Snapshot")
    entries.extend(
        [
            "I. The Scale of Lobbying",
            "II. What Taxpayer-Funded Lobbying Is - And Why It Matters",
            "III. Legislative Activity Patterns",
            "IV. Bills Most Opposed by Taxpayer-Funded Lobbyists",
            "V. Policy Areas Most Opposed by Taxpayer-Funded Lobbyists",
            "VI. Structural Incentives and the Compulsion Problem",
            "VII. Legal Parity and Statutory Inconsistency",
            "VIII. Policy Solution: A Comprehensive Ban on Taxpayer-Funded Lobbying",
            "IX. Data Sources and Methodology",
            "X. Conclusion",
        ]
    )

    index_w = 11
    text_w = page_w - pdf.l_margin - pdf.r_margin - index_w
    row_h = 5.8
    for idx, label in enumerate(entries, start=1):
        _pdf_ensure_space(pdf, row_h + 1.1)
        y = pdf.get_y()
        number_label = f"{idx:02d}"

        pdf.set_fill_color(250, 252, 255) if idx % 2 else pdf.set_fill_color(245, 249, 254)
        pdf.set_draw_color(*PDF_COLOR_BORDER)
        pdf.rect(pdf.l_margin, y, page_w - pdf.l_margin - pdf.r_margin, row_h, "DF")
        pdf.set_font(PDF_FONT_SANS, "B", 7.8)
        pdf.set_text_color(*PDF_COLOR_NAVY_DARK)
        pdf.set_xy(pdf.l_margin + 2.0, y + 1.1)
        pdf.cell(index_w - 2.0, 3.8, number_label, align="L")

        pdf.set_font(PDF_FONT_SERIF, "", 10)
        pdf.set_text_color(*PDF_COLOR_TEXT)
        pdf.set_xy(pdf.l_margin + index_w, y + 1.0)
        pdf.cell(text_w - 1.0, 4.2, _pdf_safe_text(label), align="L")
        pdf.set_y(y + row_h + 0.5)

    pdf.set_font(PDF_FONT_SANS, "I", PDF_FOOTNOTE_SIZE)
    pdf.set_text_color(*PDF_COLOR_MUTED)
    pdf.set_y(page_h - 18)
    pdf.cell(
        0,
        4.2,
        _pdf_safe_text(f"Generated {payload.get('generated_date', '')}"),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
        align="R",
    )
    pdf.set_text_color(*PDF_COLOR_TEXT)


__all__ = [
    "_pdf_add_contents_page",
    "_pdf_add_cover_page",
]
