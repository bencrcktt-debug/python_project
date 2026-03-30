from __future__ import annotations

from io import BytesIO

from fpdf import FPDF, XPos, YPos

from tfl_app.ui.pdf.charts import _fig_to_png_bytes, _pdf_clean_chart_caption


PDF_H1_SIZE = 18
PDF_H2_SIZE = 13
PDF_BODY_SIZE = 11
PDF_CAPTION_SIZE = 9
PDF_FOOTNOTE_SIZE = 8
PDF_SECTION_BAR_H = 8
PDF_BODY_LINE_H = 5.2
PDF_FONT_SANS = "Helvetica"
PDF_FONT_SERIF = "Times"
PDF_COLOR_NAVY_DARK = (9, 28, 50)
PDF_COLOR_NAVY = (16, 42, 74)
PDF_COLOR_ACCENT = (34, 96, 146)
PDF_COLOR_TEXT = (33, 45, 60)
PDF_COLOR_MUTED = (92, 106, 124)
PDF_COLOR_PANEL = (244, 248, 253)
PDF_COLOR_PANEL_ALT = (237, 243, 250)
PDF_COLOR_BORDER = (206, 218, 232)
PDF_COLOR_PAGE_BG = (250, 252, 255)

_ROMAN_MAP = (
    (1000, "M"),
    (900, "CM"),
    (500, "D"),
    (400, "CD"),
    (100, "C"),
    (90, "XC"),
    (50, "L"),
    (40, "XL"),
    (10, "X"),
    (9, "IX"),
    (5, "V"),
    (4, "IV"),
    (1, "I"),
)


def _pdf_safe_text(text: str) -> str:
    if text is None:
        return ""
    return str(text).encode("latin-1", "replace").decode("latin-1")


def _wrap_pdf_line(pdf: FPDF, text: str, max_w: float) -> list[str]:
    if text is None:
        return [""]
    safe_text = _pdf_safe_text(text)
    if max_w <= 0:
        return [safe_text]
    words = safe_text.split(" ")
    if not words:
        return [""]

    lines = []
    current = ""
    for word in words:
        if word == "":
            continue
        candidate = word if not current else f"{current} {word}"
        if pdf.get_string_width(candidate) <= max_w:
            current = candidate
            continue

        if current:
            lines.append(current)
            current = ""

        if pdf.get_string_width(word) <= max_w:
            current = word
            continue

        chunk = ""
        for ch in word:
            if not chunk or pdf.get_string_width(chunk + ch) <= max_w:
                chunk += ch
            else:
                lines.append(chunk)
                chunk = ch
        current = chunk

    if current:
        lines.append(current)
    return lines if lines else [safe_text]


def _to_roman(value: int) -> str:
    if value <= 0:
        return str(value)
    out = []
    remaining = int(value)
    for numeral_value, numeral in _ROMAN_MAP:
        while remaining >= numeral_value:
            out.append(numeral)
            remaining -= numeral_value
    return "".join(out)


def _pdf_add_rule(
    pdf: FPDF,
    *,
    before: float = 0.0,
    after: float = 2.2,
    color: tuple[int, int, int] = PDF_COLOR_BORDER,
) -> None:
    if before > 0:
        pdf.ln(before)
    y = pdf.get_y()
    pdf.set_draw_color(*color)
    pdf.set_line_width(0.22)
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.set_line_width(0.2)
    if after > 0:
        pdf.ln(after)


def _pdf_add_heading(pdf: FPDF, text: str, size: int = PDF_H2_SIZE) -> None:
    pdf.set_font(PDF_FONT_SANS, "B", size)
    pdf.set_text_color(*PDF_COLOR_NAVY_DARK)
    max_w = pdf.w - pdf.l_margin - pdf.r_margin
    line_h = max(5.7, size * 0.41)
    for line in _wrap_pdf_line(pdf, text, max_w):
        pdf.cell(0, line_h, line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(*PDF_COLOR_TEXT)
    pdf.ln(0.9)


def _pdf_add_subheading(pdf: FPDF, text: str, size: int = PDF_H2_SIZE) -> None:
    pdf.set_font(PDF_FONT_SANS, "B", size)
    pdf.set_text_color(*PDF_COLOR_NAVY)
    max_w = pdf.w - pdf.l_margin - pdf.r_margin
    line_h = max(4.8, size * 0.4)
    for line in _wrap_pdf_line(pdf, text, max_w):
        pdf.cell(0, line_h, line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(*PDF_COLOR_TEXT)
    pdf.ln(0.7)


def _pdf_add_paragraph(pdf: FPDF, text: str, size: int = PDF_BODY_SIZE, line_h: float = PDF_BODY_LINE_H) -> None:
    pdf.set_font(PDF_FONT_SERIF, "", size)
    pdf.set_text_color(*PDF_COLOR_TEXT)
    max_w = pdf.w - pdf.l_margin - pdf.r_margin
    for line in _wrap_pdf_line(pdf, text, max_w):
        pdf.cell(0, line_h, line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1.1)


def _pdf_add_bullets(pdf: FPDF, bullets: list[str], size: int = 10, line_h: float = 4.9) -> None:
    if not bullets:
        return
    bullet_x = pdf.l_margin + 1.4
    bullet_size = 1.2
    text_x = bullet_x + bullet_size + 2.2
    max_w = pdf.w - pdf.r_margin - text_x
    for bullet in bullets:
        safe_bullet = _pdf_safe_text(bullet)
        lines = _wrap_pdf_line(pdf, safe_bullet, max_w) if safe_bullet else [""]
        row_h = max(line_h, len(lines) * line_h)
        _pdf_ensure_space(pdf, row_h + 0.9)

        row_y = pdf.get_y()
        pdf.set_fill_color(*PDF_COLOR_ACCENT)
        pdf.set_draw_color(*PDF_COLOR_ACCENT)
        dot_y = row_y + (line_h - bullet_size) * 0.58
        pdf.ellipse(bullet_x, dot_y, bullet_size, bullet_size, "F")

        pdf.set_font(PDF_FONT_SERIF, "", size)
        pdf.set_text_color(*PDF_COLOR_TEXT)
        for idx, line in enumerate(lines):
            if idx == 0:
                pdf.set_xy(text_x, row_y)
            else:
                pdf.set_xy(text_x, row_y + (line_h * idx))
            pdf.cell(0, line_h, line, new_x=XPos.LMARGIN, new_y=YPos.TOP)
        pdf.set_y(row_y + row_h + 0.6)
    pdf.ln(0.6)


def _pdf_add_kpi_table(pdf: FPDF, rows: list[tuple[str, str]], size: int = 10) -> None:
    if not rows:
        return
    table_w = pdf.w - pdf.l_margin - pdf.r_margin
    label_w = min(110.0, table_w * 0.56)
    value_w = table_w - label_w
    body_line_h = 4.5
    for idx, (label, value) in enumerate(rows):
        label_txt = _pdf_safe_text(label)
        value_txt = _pdf_safe_text(value)

        pdf.set_font(PDF_FONT_SANS, "", size)
        label_lines = _wrap_pdf_line(pdf, label_txt, label_w - 4)
        pdf.set_font(PDF_FONT_SANS, "B", size)
        value_lines = _wrap_pdf_line(pdf, value_txt, value_w - 4)

        lines = max(len(label_lines), len(value_lines))
        row_h = max(6.8, lines * body_line_h + 1.8)
        _pdf_ensure_space(pdf, row_h + 0.8)

        row_y = pdf.get_y()
        fill_color = (248, 251, 255) if (idx % 2 == 0) else (243, 248, 253)
        pdf.set_fill_color(*fill_color)
        pdf.set_draw_color(*PDF_COLOR_BORDER)
        pdf.rect(pdf.l_margin, row_y, table_w, row_h, "DF")
        pdf.line(pdf.l_margin + label_w, row_y, pdf.l_margin + label_w, row_y + row_h)

        label_start_y = row_y + max(0.9, (row_h - len(label_lines) * body_line_h) / 2)
        value_start_y = row_y + max(0.9, (row_h - len(value_lines) * body_line_h) / 2)

        pdf.set_text_color(*PDF_COLOR_TEXT)
        pdf.set_font(PDF_FONT_SANS, "", size)
        for line_idx, line in enumerate(label_lines):
            pdf.set_xy(pdf.l_margin + 2.2, label_start_y + line_idx * body_line_h)
            pdf.cell(label_w - 4, body_line_h, line, align="L")

        pdf.set_text_color(*PDF_COLOR_NAVY_DARK)
        pdf.set_font(PDF_FONT_SANS, "B", size)
        for line_idx, line in enumerate(value_lines):
            pdf.set_xy(pdf.l_margin + label_w + 2, value_start_y + line_idx * body_line_h)
            pdf.cell(value_w - 4, body_line_h, line, align="R")

        pdf.set_text_color(*PDF_COLOR_TEXT)
        pdf.set_y(row_y + row_h)
    pdf.ln(1.2)


def _pdf_ensure_space(pdf: FPDF, height_needed: float) -> None:
    if pdf.get_y() + height_needed > pdf.h - pdf.b_margin:
        pdf.add_page()


def _pdf_add_chart(pdf: FPDF, fig, caption: str, width_px: int = 900, height_px: int = 500) -> None:
    png = _fig_to_png_bytes(fig, width=width_px, height=height_px, scale=2)
    base_caption = _pdf_clean_chart_caption(caption)
    figure_no = int(getattr(pdf, "_figure_counter", 0)) + 1
    setattr(pdf, "_figure_counter", figure_no)
    figure_caption = f"Figure {figure_no}. {base_caption}"
    if not png:
        pdf.set_font(PDF_FONT_SANS, "I", PDF_CAPTION_SIZE)
        pdf.set_text_color(*PDF_COLOR_MUTED)
        pdf.cell(0, 5, _pdf_safe_text(f"{figure_caption} (chart unavailable)"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(*PDF_COLOR_TEXT)
        pdf.ln(2)
        return

    block_w = pdf.w - pdf.l_margin - pdf.r_margin
    pad = 2.0
    caption_line_h = 4.0
    caption_pad = 1.2
    img_w = block_w - (pad * 2)
    img_h = img_w * (height_px / width_px)
    pdf.set_font(PDF_FONT_SANS, "", PDF_CAPTION_SIZE)
    caption_lines = _wrap_pdf_line(pdf, figure_caption, img_w)
    caption_h = max(4.8, len(caption_lines) * caption_line_h + caption_pad)
    block_h = caption_h + img_h + (pad * 2)
    _pdf_ensure_space(pdf, block_h + 2.2)

    y = pdf.get_y()
    pdf.set_fill_color(252, 254, 255)
    pdf.set_draw_color(*PDF_COLOR_BORDER)
    pdf.rect(pdf.l_margin, y, block_w, block_h, "DF")
    caption_y = y + 1.0
    pdf.set_font(PDF_FONT_SANS, "", PDF_CAPTION_SIZE)
    pdf.set_text_color(*PDF_COLOR_NAVY)
    y_cursor = caption_y + 1.6
    for line in caption_lines:
        pdf.set_xy(pdf.l_margin + pad, y_cursor)
        pdf.cell(img_w, caption_line_h, _pdf_safe_text(line), align="L")
        y_cursor += caption_line_h

    pdf.set_draw_color(223, 231, 241)
    pdf.line(pdf.l_margin + pad, y + caption_h + 1.1, pdf.w - pdf.r_margin - pad, y + caption_h + 1.1)
    img_y = y + caption_h + pad
    pdf.image(BytesIO(png), x=pdf.l_margin + pad, y=img_y, w=img_w, h=img_h)
    pdf.set_text_color(*PDF_COLOR_TEXT)
    pdf.set_y(y + block_h + 1.6)


def _pdf_add_section_title(pdf: FPDF, text: str, number: str | None = None) -> None:
    if pdf.get_y() > (pdf.t_margin + 4):
        pdf.ln(1.5)
    bar_w = pdf.w - pdf.l_margin - pdf.r_margin
    title = f"{number} {text}".strip() if number else text
    title_w = bar_w
    pdf.set_font(PDF_FONT_SANS, "B", PDF_H2_SIZE - 0.2)
    title_lines = _wrap_pdf_line(pdf, _pdf_safe_text(title), title_w)
    title_line_h = 4.8
    title_h = max(6.0, len(title_lines) * title_line_h)
    _pdf_ensure_space(pdf, title_h + 3.2)
    y = pdf.get_y()
    pdf.set_font(PDF_FONT_SANS, "B", PDF_H2_SIZE - 0.2)
    pdf.set_text_color(*PDF_COLOR_NAVY_DARK)
    y_cursor = y + 0.2
    for line in title_lines:
        pdf.set_xy(pdf.l_margin, y_cursor)
        pdf.cell(title_w, title_line_h, _pdf_safe_text(line), align="L")
        y_cursor += title_line_h
    pdf.set_draw_color(*PDF_COLOR_BORDER)
    pdf.line(pdf.l_margin, y + title_h + 0.4, pdf.w - pdf.r_margin, y + title_h + 0.4)
    pdf.set_text_color(*PDF_COLOR_TEXT)
    pdf.set_y(y + title_h + 1.6)


def _pdf_add_numbered_section_title(pdf: FPDF, number: int, text: str) -> None:
    _pdf_add_section_title(pdf, text, number=f"{_to_roman(number)}.")


def _pdf_add_callout_box(
    pdf: FPDF,
    title: str,
    body: str,
    *,
    accent: tuple[int, int, int] = PDF_COLOR_ACCENT,
) -> None:
    title = _pdf_safe_text(title)
    body = _pdf_safe_text(body)
    if not title and not body:
        return

    inner_pad = 2.8
    title_size = 9.4
    body_size = PDF_BODY_SIZE
    line_h = 4.9
    left_accent_w = 1.6
    box_w = pdf.w - pdf.l_margin - pdf.r_margin
    text_w = box_w - left_accent_w - (inner_pad * 2)

    pdf.set_font(PDF_FONT_SANS, "B", title_size)
    title_lines = _wrap_pdf_line(pdf, title, text_w)
    pdf.set_font(PDF_FONT_SERIF, "", body_size)
    body_lines = _wrap_pdf_line(pdf, body, text_w)

    content_lines = len(title_lines) + len(body_lines)
    box_h = max(13.6, inner_pad * 2 + content_lines * line_h + 0.5)
    _pdf_ensure_space(pdf, box_h + 1.2)
    y = pdf.get_y()

    pdf.set_fill_color(247, 250, 254)
    pdf.set_draw_color(*PDF_COLOR_BORDER)
    pdf.rect(pdf.l_margin, y, box_w, box_h, "DF")
    pdf.set_fill_color(*accent)
    pdf.rect(pdf.l_margin, y, left_accent_w, box_h, "F")

    x_text = pdf.l_margin + left_accent_w + inner_pad
    y_cursor = y + inner_pad
    pdf.set_text_color(*PDF_COLOR_NAVY_DARK)
    pdf.set_font(PDF_FONT_SANS, "B", title_size)
    for line in title_lines:
        pdf.set_xy(x_text, y_cursor)
        pdf.cell(text_w, line_h, line, align="L")
        y_cursor += line_h

    pdf.set_font(PDF_FONT_SERIF, "", body_size)
    pdf.set_text_color(*PDF_COLOR_TEXT)
    for line in body_lines:
        pdf.set_xy(x_text, y_cursor)
        pdf.cell(text_w, line_h, line, align="L")
        y_cursor += line_h

    pdf.set_text_color(*PDF_COLOR_TEXT)
    pdf.set_y(y + box_h + 1.1)


def _pdf_add_focus_highlights(pdf: FPDF, highlights: list[str], *, size: int = 10) -> None:
    clean = [str(h).strip() for h in (highlights or []) if str(h).strip()]
    if not clean:
        return

    block_w = pdf.w - pdf.l_margin - pdf.r_margin
    badge_w = 5.2
    inner_pad = 2.1
    row_gap = 1.0
    line_h = 4.5

    for idx, raw in enumerate(clean, start=1):
        title = raw
        detail = ""
        lead, sep, tail = raw.partition(":")
        if sep and len(lead.strip()) <= 42:
            title = lead.strip()
            detail = tail.strip()

        text_x = pdf.l_margin + badge_w + 2.2
        text_w = block_w - badge_w - 6
        pdf.set_font(PDF_FONT_SANS, "B", size)
        title_lines = _wrap_pdf_line(pdf, title, text_w)
        pdf.set_font(PDF_FONT_SERIF, "", max(9.3, size - 0.2))
        detail_lines = _wrap_pdf_line(pdf, detail, text_w) if detail else []

        row_lines = len(title_lines) + len(detail_lines)
        row_h = max(10.8, (row_lines * line_h) + (inner_pad * 2))
        _pdf_ensure_space(pdf, row_h + row_gap + 1)
        y = pdf.get_y()

        fill = (248, 251, 255) if idx % 2 else (243, 248, 253)
        pdf.set_fill_color(*fill)
        pdf.set_draw_color(*PDF_COLOR_BORDER)
        pdf.rect(pdf.l_margin, y, block_w, row_h, "DF")

        pdf.set_fill_color(225, 236, 248)
        pdf.rect(pdf.l_margin, y, badge_w, row_h, "F")
        pdf.set_fill_color(*PDF_COLOR_NAVY)
        circle_d = 3.3
        circle_x = pdf.l_margin + (badge_w - circle_d) / 2
        circle_y = y + (row_h - circle_d) / 2
        pdf.ellipse(circle_x, circle_y, circle_d, circle_d, "F")
        pdf.set_text_color(236, 243, 250)
        pdf.set_font(PDF_FONT_SANS, "B", 6.7)
        pdf.set_xy(circle_x, circle_y + 0.25)
        pdf.cell(circle_d, 2.8, f"{idx}", align="C")

        pdf.set_text_color(*PDF_COLOR_NAVY_DARK)
        pdf.set_font(PDF_FONT_SANS, "B", size)
        y_cursor = y + inner_pad
        for line in title_lines:
            pdf.set_xy(text_x, y_cursor)
            pdf.cell(text_w, line_h, _pdf_safe_text(line), align="L")
            y_cursor += line_h

        if detail_lines:
            pdf.set_text_color(*PDF_COLOR_TEXT)
            pdf.set_font(PDF_FONT_SERIF, "", max(9.3, size - 0.2))
            for line in detail_lines:
                pdf.set_xy(text_x, y_cursor)
                pdf.cell(text_w, line_h, _pdf_safe_text(line), align="L")
                y_cursor += line_h

        pdf.set_text_color(*PDF_COLOR_TEXT)
        pdf.set_y(y + row_h + row_gap)


__all__ = [
    "PDF_BODY_LINE_H",
    "PDF_BODY_SIZE",
    "PDF_CAPTION_SIZE",
    "PDF_COLOR_ACCENT",
    "PDF_COLOR_BORDER",
    "PDF_COLOR_MUTED",
    "PDF_COLOR_NAVY",
    "PDF_COLOR_NAVY_DARK",
    "PDF_COLOR_PAGE_BG",
    "PDF_COLOR_PANEL",
    "PDF_COLOR_PANEL_ALT",
    "PDF_COLOR_TEXT",
    "PDF_FOOTNOTE_SIZE",
    "PDF_FONT_SANS",
    "PDF_FONT_SERIF",
    "PDF_H1_SIZE",
    "PDF_H2_SIZE",
    "PDF_SECTION_BAR_H",
    "_pdf_add_bullets",
    "_pdf_add_callout_box",
    "_pdf_add_chart",
    "_pdf_add_focus_highlights",
    "_pdf_add_heading",
    "_pdf_add_kpi_table",
    "_pdf_add_numbered_section_title",
    "_pdf_add_paragraph",
    "_pdf_add_rule",
    "_pdf_add_section_title",
    "_pdf_add_subheading",
    "_pdf_ensure_space",
    "_pdf_safe_text",
    "_to_roman",
    "_wrap_pdf_line",
]
