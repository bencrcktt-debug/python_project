from dataclasses import dataclass
from io import BytesIO
from typing import Callable, Dict, List

import pandas as pd
import plotly.express as px
import plotly.io as pio
from fpdf import FPDF


# ---- PDF utilities (trimmed copy from main.py for reuse)
def _pdf_safe_text(text: str) -> str:
    if text is None:
        return ""
    return str(text).encode("latin-1", "replace").decode("latin-1")

PALETTE = {
    "primary": (30, 144, 255),  # Dodger blue
    "accent": (0, 224, 184),  # teal
    "ink": (16, 35, 58),
    "muted": (100, 110, 125),
    "panel": (245, 246, 248),
}


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


def _pdf_add_paragraph(pdf: FPDF, text: str, size: int = 11, line_h: int = 6) -> None:
    pdf.set_font("Helvetica", "", size)
    max_w = max(20, pdf.w - pdf.l_margin - pdf.r_margin)
    for line in _wrap_pdf_line(pdf, text, max_w):
        pdf.cell(0, line_h, line, ln=1)
    pdf.ln(2)


def _pdf_add_heading(pdf: FPDF, text: str, size: int = 14) -> None:
    pdf.set_font("Helvetica", "B", size)
    max_w = max(20, pdf.w - pdf.l_margin - pdf.r_margin)
    for line in _wrap_pdf_line(pdf, text, max_w):
        pdf.cell(0, 8, line, ln=1)
    pdf.ln(1)


def _pdf_add_rule(pdf: FPDF) -> None:
    y = pdf.get_y()
    pdf.set_draw_color(180, 180, 180)
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.ln(4)


def _pdf_section_heading(pdf: FPDF, text: str) -> None:
    """A filled ribbon-style heading for better visual hierarchy."""
    pdf.set_fill_color(*PALETTE["primary"])
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, _pdf_safe_text(text), ln=1, fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(1)


def _pdf_add_kpi_rows(pdf: FPDF, rows: list[tuple[str, str]]) -> None:
    if not rows:
        return
    avail = max(20, pdf.w - pdf.l_margin - pdf.r_margin)
    label_w = min(70, max(30, avail * 0.4))
    value_w = max(30, avail - label_w)
    fill = False
    for label, value in rows:
        pdf.set_fill_color(245, 246, 248) if fill else pdf.set_fill_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(label_w, 6, _pdf_safe_text(label), ln=0, fill=fill)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(value_w, 6, _pdf_safe_text(value), ln=1, fill=fill)
        fill = not fill
    pdf.ln(2)


def _apply_pdf_chart_layout(fig):
    if fig is None:
        return fig
    fig.update_layout(
        font=dict(family="Helvetica", size=11, color="#1f2933"),
        paper_bgcolor="white",
        plot_bgcolor="white",
    )
    fig.update_xaxes(automargin=True)
    fig.update_yaxes(automargin=True)
    return fig


def _fig_to_png_bytes(fig, width: int = 900, height: int = 500, scale: int = 2) -> bytes | None:
    if fig is None:
        return None
    try:
        scope = pio.kaleido.scope
        if scope:
            scope.mathjax = None
            scope.default_format = "png"
    except Exception:
        return None

    _apply_pdf_chart_layout(fig)
    last_exc = None
    scales = [scale] if scale == 1 else [scale, 1]
    for attempt_scale in scales:
        try:
            return pio.to_image(
                fig,
                format="png",
                width=width,
                height=height,
                scale=attempt_scale,
                engine="kaleido",
            )
        except Exception as exc:
            last_exc = exc
    if last_exc:
        return None
    return None


def _pdf_add_chart(pdf: FPDF, fig, caption: str, width_px: int = 900, height_px: int = 500) -> bool:
    png = _fig_to_png_bytes(fig, width=width_px, height=height_px, scale=2)
    if not png:
        pdf.set_font("Helvetica", "I", 9)
        pdf.cell(0, 5, _pdf_safe_text(f"{caption} (chart unavailable)"), ln=1)
        pdf.ln(2)
        return False
    img_w = pdf.w - pdf.l_margin - pdf.r_margin
    img_h = img_w * (height_px / width_px)
    if pdf.get_y() + img_h + 10 > pdf.h - pdf.b_margin:
        pdf.add_page()
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(0, 5, _pdf_safe_text(caption), ln=1)
    pdf.image(BytesIO(png), x=pdf.l_margin, w=img_w, h=img_h, type="PNG")
    pdf.ln(4)
    return True


def _pdf_add_bullets(pdf: FPDF, bullets: List[str], size: int = 10, line_h: int = 5) -> None:
    if not bullets:
        return
    pdf.set_font("Helvetica", "", size)
    max_w = max(20, pdf.w - pdf.l_margin - pdf.r_margin - 6)
    for bullet in bullets:
        pdf.cell(4, line_h, "-", ln=0)
        lines = _wrap_pdf_line(pdf, bullet, max_w)
        if lines:
            pdf.cell(0, line_h, lines[0], ln=1)
            for cont in lines[1:]:
                pdf.cell(4, line_h, "", ln=0)
                pdf.cell(0, line_h, cont, ln=1)
        else:
            pdf.ln(line_h)
    pdf.ln(2)


# ---- Section spec
@dataclass
class SectionSpec:
    id: str
    title: str
    renderer: Callable[[FPDF, Dict], None]


def _render_cover(pdf: FPDF, payload: Dict) -> None:
    pdf.set_fill_color(*PALETTE["ink"])
    pdf.rect(pdf.l_margin, pdf.get_y(), pdf.w - pdf.l_margin - pdf.r_margin, 2, "F")
    pdf.ln(6)
    title = payload.get("report_title") or "Taxpayer-Funded Lobbying Report"
    subtitle = f"{payload.get('session_label','')} | {payload.get('scope_session_label') or payload.get('scope_label','')}"
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 8, _pdf_safe_text(title), ln=1)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 6, _pdf_safe_text(subtitle), ln=1)
    pdf.cell(0, 6, _pdf_safe_text(f"Generated: {payload.get('generated_ts') or payload.get('generated_date','')}"), ln=1)
    pdf.cell(0, 6, _pdf_safe_text(f"Report ID: {payload.get('report_id','')}"), ln=1)
    if payload.get("scope_session_label") or payload.get("scope_label"):
        pdf.cell(0, 6, _pdf_safe_text(f"Scope: {payload.get('scope_session_label') or payload.get('scope_label')}"), ln=1)
    if payload.get("focus_label"):
        pdf.cell(0, 6, _pdf_safe_text(f"Focus: {payload.get('focus_label')}"), ln=1)
    if payload.get("filter_summary"):
        pdf.multi_cell(0, 6, _pdf_safe_text(f"Filters: {payload['filter_summary']}"))
    pdf.ln(4)

    kpis = [
        ("Taxpayer-funded range", f"{payload.get('tfl_low','')} - {payload.get('tfl_high','')}"),
        ("Private range", f"{payload.get('private_low','')} - {payload.get('private_high','')}"),
        ("Taxpayer share", f"{payload.get('tfl_share_low_pct','0')}% - {payload.get('tfl_share_high_pct','0')}%"),
    ]
    _pdf_add_kpi_rows(pdf, kpis)


def _render_contents(pdf: FPDF, payload: Dict) -> None:
    _pdf_section_heading(pdf, "Contents")
    order = payload.get("section_order") or []
    titles = payload.get("section_titles") or {}
    items = []
    for idx, sid in enumerate(order, start=1):
        title = titles.get(sid)
        if not title or sid in {"cover", "contents"}:
            continue
        items.append(f"{idx}. {title}")
    if not items:
        _pdf_add_paragraph(pdf, "Contents unavailable.", size=9)
        return
    _pdf_add_bullets(pdf, items, size=10, line_h=5)


def _render_exec_summary(pdf: FPDF, payload: Dict) -> None:
    _pdf_section_heading(pdf, "Executive Summary")
    bullets = [
        f"Taxpayer-funded range: {payload.get('tfl_low')} to {payload.get('tfl_high')} ({payload.get('tfl_share_low_pct','0')}%-{payload.get('tfl_share_high_pct','0')}% of reported comp).",
        f"Private range: {payload.get('private_low')} to {payload.get('private_high')}.",
        f"Entity mix: {payload.get('unique_clients_tfl','0')} taxpayer-funded clients; {payload.get('unique_lobbyists_tfl','0')} lobbyists tied to TFL.",
        f"Opposition focus: top bills {', '.join([b.get('id','') for b in (payload.get('top_bills') or [])][:3]) or 'n/a'}, top policy areas {', '.join([s.get('Subject','') for s in (payload.get('top_subjects') or [])][:3]) or 'n/a'}.",
        "Use this briefing to surface dependency, opposition clusters, and priority policy areas for follow-up.",
    ]
    _pdf_add_bullets(pdf, [b for b in bullets if b.strip()], size=10, line_h=5)
    if payload.get("focus_label"):
        _pdf_add_paragraph(
            pdf,
            f"Focus: {payload.get('focus_label')} — tailor next actions to this entity's exposure, stance patterns, and policy concentration.",
            size=10,
            line_h=5,
        )


def _render_funding(pdf: FPDF, payload: Dict) -> None:
    _pdf_section_heading(pdf, "Funding Structure")
    _pdf_add_paragraph(
        pdf,
        "How much lobbying is financed by taxpayers versus private entities, using midpoints of reported ranges.",
        size=10,
    )
    rows = [
        ("Total range", f"{payload.get('total_low','')} - {payload.get('total_high','')}"),
        ("Taxpayer-funded", f"{payload.get('tfl_low','')} - {payload.get('tfl_high','')}"),
        ("Private", f"{payload.get('private_low','')} - {payload.get('private_high','')}"),
    ]
    _pdf_add_kpi_rows(pdf, rows)

    funding = payload.get("funding_mix") or {}
    if funding:
        df = pd.DataFrame(
            [{"Funding": k, "Midpoint": v} for k, v in funding.items() if k and v is not None]
        )
        if not df.empty:
            fig = px.bar(
                df,
                x="Funding",
                y="Midpoint",
                text="Midpoint",
                color="Funding",
                color_discrete_map={"Taxpayer Funded": "#d14b4b", "Private": "#4c78a8"},
            )
            fig.update_traces(texttemplate="$%{text:,.0f}", textposition="outside", cliponaxis=False)
            _pdf_add_chart(pdf, fig, "Chart: Funding mix (midpoint of ranges)", width_px=900, height_px=420)
    _pdf_add_paragraph(
        pdf,
        f"Taxpayer share signals dependency on public funds. Reported range: {payload.get('tfl_low','?')} to {payload.get('tfl_high','?')} "
        f"({payload.get('tfl_share_low_pct','?')}%-{payload.get('tfl_share_high_pct','?')}%).",
        size=9,
    )


def _render_witness(pdf: FPDF, payload: Dict) -> None:
    _pdf_section_heading(pdf, "Witness Positions")
    _pdf_add_paragraph(
        pdf,
        "Positions taken on bills signal posture. Compare taxpayer-funded versus private stance counts to see where compulsory dollars are deployed.",
        size=10,
    )
    counts = payload.get("witness_counts") or {}
    if counts:
        rows = []
        for position in ["Against", "For", "On"]:
            rows.append(
                (
                    f"{position} (TFL)",
                    f"{int(counts.get('tfl', {}).get(position, 0)):,}",
                )
            )
            rows.append(
                (
                    f"{position} (Private)",
                    f"{int(counts.get('private', {}).get(position, 0)):,}",
                )
            )
        _pdf_add_kpi_rows(pdf, rows)
        data = []
        for position in ["Against", "For", "On"]:
            data.append(
                {
                    "Position": position,
                    "Funding": "Taxpayer Funded",
                    "Count": int(counts.get("tfl", {}).get(position, 0)),
                }
            )
            data.append(
                {
                    "Position": position,
                    "Funding": "Private",
                    "Count": int(counts.get("private", {}).get(position, 0)),
                }
            )
        fig = px.bar(
            pd.DataFrame(data),
            x="Position",
            y="Count",
            color="Funding",
            barmode="group",
            text="Count",
            color_discrete_map={"Taxpayer Funded": "#d14b4b", "Private": "#4c78a8"},
        )
        fig.update_traces(textposition="outside", cliponaxis=False)
        _pdf_add_chart(pdf, fig, "Chart: Witness positions by funding type", width_px=900, height_px=420)
    else:
        _pdf_add_paragraph(pdf, "No witness counts available for the selected scope.", size=10)
    _pdf_add_paragraph(
        pdf,
        "Next step: join stances to bill outcomes to quantify efficacy and influence by funding type.",
        size=9,
    )


def _render_top_bills(pdf: FPDF, payload: Dict) -> None:
    _pdf_section_heading(pdf, "Top Bills Opposed by Taxpayer-Funded Lobbyists")
    _pdf_add_paragraph(
        pdf,
        "Bills with concentrated taxpayer-funded opposition highlight where compulsory dollars are most defensive.",
        size=10,
    )
    top_bills = payload.get("top_bills") or []
    if not top_bills:
        _pdf_add_paragraph(pdf, "No bill-level opposition data available.", size=10)
        return
    df = pd.DataFrame(
        [{"Bill": b.get("id"), "Oppositions": b.get("tfl", 0)} for b in top_bills if b.get("id")]
    )
    if not df.empty:
        fig = px.bar(
            df.sort_values("Oppositions"),
            x="Oppositions",
            y="Bill",
            orientation="h",
            text="Oppositions",
            color_discrete_sequence=["#d14b4b"],
        )
        fig.update_traces(textposition="outside", cliponaxis=False)
        _pdf_add_chart(pdf, fig, "Chart: Top bills opposed", width_px=900, height_px=420)
    _pdf_add_paragraph(
        pdf,
        "Add bill statuses/captions alongside counts to brief decision-makers at a glance.",
        size=9,
    )


def _render_top_subjects(pdf: FPDF, payload: Dict) -> None:
    _pdf_section_heading(pdf, "Top Policy Areas")
    _pdf_add_paragraph(
        pdf,
        "Policy-area concentration shows strategic priorities. Persistent clusters suggest institutional goals.",
        size=10,
    )
    top_subjects = payload.get("top_subjects") or []
    if not top_subjects:
        _pdf_add_paragraph(pdf, "No subject-level data available.", size=10)
        return
    df = pd.DataFrame(
        [{"Subject": s.get("Subject"), "Oppositions": s.get("Oppositions", 0)} for s in top_subjects if s.get("Subject")]
    )
    if not df.empty:
        fig = px.bar(
            df.sort_values("Oppositions"),
            x="Oppositions",
            y="Subject",
            orientation="h",
            text="Oppositions",
            color_discrete_sequence=["#7aa6c2"],
        )
        fig.update_traces(textposition="outside", cliponaxis=False)
        _pdf_add_chart(pdf, fig, "Chart: Top policy areas opposed", width_px=900, height_px=420)
    _pdf_add_paragraph(
        pdf,
        "These subject clusters typically align with places where statewide reforms would constrain local discretion, budgets, or oversight.",
        size=9,
    )


def _render_focus(pdf: FPDF, payload: Dict) -> None:
    focus = payload.get("focus_section") or {}
    title = focus.get("title") or "Focus Snapshot"
    _pdf_section_heading(pdf, title)
    if focus.get("summary"):
        _pdf_add_paragraph(pdf, focus["summary"], size=11)
    metrics = focus.get("metrics") or []
    if metrics:
        _pdf_add_kpi_rows(pdf, metrics)
    bullets = focus.get("bullets") or []
    if bullets:
        pdf.set_font("Helvetica", "", 10)
        for b in bullets:
            pdf.cell(4, 5, "-", ln=0)
            pdf.multi_cell(0, 5, _pdf_safe_text(b))
        pdf.ln(2)
    charts = focus.get("charts") or []
    for chart in charts:
        kind = str(chart.get("kind", "")).lower()
        if kind == "bar":
            df = pd.DataFrame(chart.get("data", []))
            if not df.empty and {"label", "value"}.issubset(df.columns):
                fig = px.bar(
                    df.sort_values("value"),
                    x="value",
                    y="label",
                    orientation="h" if chart.get("orientation", "h") == "h" else "v",
                    text="value",
                    color_discrete_sequence=["#4c78a8"],
                )
                fig.update_traces(textposition="outside", cliponaxis=False)
                _pdf_add_chart(pdf, fig, chart.get("caption", chart.get("title", "Focus Chart")))
        elif kind == "grouped_bar":
            df = pd.DataFrame(chart.get("data", []))
            if not df.empty and {"Position", "Funding", "Count"}.issubset(df.columns):
                fig = px.bar(
                    df,
                    x="Position",
                    y="Count",
                    color="Funding",
                    barmode="group",
                    text="Count",
                    color_discrete_map={"Taxpayer Funded": "#d14b4b", "Private": "#4c78a8"},
                )
                fig.update_traces(textposition="outside", cliponaxis=False)
                _pdf_add_chart(pdf, fig, chart.get("caption", chart.get("title", "Focus Chart")))
    else:
        _pdf_add_paragraph(pdf, "No focus snapshot available for this selection.", size=10)


def _render_methodology(pdf: FPDF, payload: Dict) -> None:
    _pdf_section_heading(pdf, "Data Sources & Methodology")
    max_w = max(40, pdf.w - pdf.l_margin - pdf.r_margin)
    bullets = [
        b.strip().lstrip("- ").strip()
        for b in str(payload.get("data_sources_bullets", "")).splitlines()
        if b.strip()
    ]
    if bullets:
        pdf.set_font("Helvetica", "", 10)
        for b in bullets:
            pdf.cell(4, 5, "-", ln=0)
            pdf.multi_cell(max_w - 4, 5, _pdf_safe_text(b))
    if payload.get("disclaimer_note"):
        pdf.ln(2)
        pdf.set_font("Helvetica", "I", 9)
        pdf.multi_cell(max_w, 5, _pdf_safe_text(payload["disclaimer_note"]))
    if payload.get("filter_summary"):
        pdf.ln(1)
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(max_w, 5, _pdf_safe_text(f"Filter context: {payload['filter_summary']}"))


def _render_conclusion(pdf: FPDF, payload: Dict) -> None:
    _pdf_section_heading(pdf, "Conclusion")
    conclusion = (
        f"During the {payload.get('session_label','')} session, taxpayer-funded lobbying totaled "
        f"between {payload.get('tfl_low')} and {payload.get('tfl_high')} in reported ranges. "
        "Because the dollars are compulsory, the normal discipline of voluntary funding does not apply—creating a standing "
        "conflict between taxpayer interests and institutional self-protection. "
        "Closing both direct and indirect pathways for taxpayer-funded lobbying would align spending with public services, "
        "restore trust, and keep advocacy accountable to those who pay for it."
    )
    _pdf_add_paragraph(pdf, conclusion, size=11)
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(0, 5, _pdf_safe_text("Prepared by Texas Lobby Data Center"), ln=1)
    if payload.get("disclaimer_note"):
        pdf.cell(0, 5, _pdf_safe_text(payload["disclaimer_note"]), ln=1)


SECTION_REGISTRY: List[SectionSpec] = [
    SectionSpec("cover", "Cover", _render_cover),
    SectionSpec("contents", "Contents", _render_contents),
    SectionSpec("exec", "Executive Summary", _render_exec_summary),
    SectionSpec("funding", "Funding Structure", _render_funding),
    SectionSpec("witness", "Witness Positions", _render_witness),
    SectionSpec("bills", "Top Bills", _render_top_bills),
    SectionSpec("subjects", "Top Policy Areas", _render_top_subjects),
    SectionSpec("focus", "Focus Snapshot", _render_focus),
    # Narrative section is optional; included only when explicitly enabled.
    SectionSpec("narrative", "Narrative Argument", lambda pdf, payload: _render_narrative(pdf, payload)),
    SectionSpec("methodology", "Data Sources & Methodology", _render_methodology),
    SectionSpec("conclusion", "Conclusion", _render_conclusion),
]


def _render_narrative(pdf: FPDF, payload: Dict) -> None:
    text = payload.get("long_narrative", "")
    if not text:
        _pdf_add_paragraph(pdf, "Narrative not available for this selection.", size=10)
        return
    _pdf_section_heading(pdf, "Narrative Argument")
    # Split the legacy narrative into paragraphs and render as flowing text.
    paras = [p.strip() for p in text.splitlines() if p.strip()]
    for p in paras:
        _pdf_add_paragraph(pdf, p, size=10, line_h=5)
    pdf.ln(1)

    # Integrate key charts inline to keep visuals close to the argument.
    charts = [
        ("Chart: Funding mix (midpoint of ranges)", payload.get("chart_compensation_bar")),
        ("Chart: Share of Total Lobbying - Taxpayer vs Private", payload.get("chart_share")),
        ("Chart: Top bills opposed", payload.get("chart_top_bills")),
        ("Chart: Top policy areas opposed", payload.get("chart_top_subjects")),
    ]
    used = 0
    for caption, fig in charts:
        if fig is None:
            continue
        if used >= 3:
            break
        _pdf_add_chart(pdf, fig, caption, width_px=900, height_px=420)
        used += 1


def build_pdf(payload: Dict, sections: List[str] | None = None) -> bytes:
    """
    Build a structured PDF using the legacy FPDF engine but with a section registry.
    """
    include_narrative = bool(payload.get("include_narrative"))
    default_sections = [s.id for s in SECTION_REGISTRY if s.id != "narrative"]
    if include_narrative:
        default_sections.append("narrative")
    chosen = sections or default_sections
    section_map = {s.id: s for s in SECTION_REGISTRY}
    payload = dict(payload)
    payload["section_order"] = chosen
    payload["section_titles"] = {s.id: s.title for s in SECTION_REGISTRY}

    class ReportPDF(FPDF):
        def __init__(self, header_title: str, header_subtitle: str, generated_ts: str, report_id: str):
            super().__init__(orientation="P", unit="mm", format="A4")
            self.header_title = header_title
            self.header_subtitle = header_subtitle
            self.generated_ts = generated_ts
            self.report_id = report_id

        def header(self):
            if self.page_no() == 1:
                return
            self.set_text_color(60, 60, 60)
            self.set_font("Helvetica", "B", 9)
            self.cell(0, 5, _pdf_safe_text(self.header_title), ln=1)
            self.set_font("Helvetica", "", 8)
            subtitle = str(self.header_subtitle or "")
            if len(subtitle) > 110:
                subtitle = subtitle[:107].rstrip() + "..."
            self.cell(0, 4, _pdf_safe_text(subtitle), ln=1)
            self.set_draw_color(200, 200, 200)
            self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
            self.ln(3)
            self.set_text_color(0, 0, 0)

        def footer(self):
            self.set_y(-12)
            self.set_text_color(120, 120, 120)
            self.set_font("Helvetica", "", 8)
            w = self.w - self.l_margin - self.r_margin
            self.cell(w, 4, _pdf_safe_text(self.report_id), 0, 0, "L")
            self.cell(0, 4, _pdf_safe_text(f"Page {self.page_no()}"), 0, 0, "R")

    header_title = payload.get("report_title") or "Taxpayer-Funded Lobbying Report"
    header_subtitle = f"{payload.get('session_label','')} | {payload.get('scope_session_label') or payload.get('scope_label','')}"
    pdf = ReportPDF(header_title, header_subtitle, payload.get("generated_ts", ""), payload.get("report_id", ""))
    pdf.set_left_margin(12)
    pdf.set_right_margin(12)
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()

    errors: List[str] = []
    for sid in chosen:
        spec = section_map.get(sid)
        if not spec:
            continue
        if sid != "cover":
            pdf.ln(2)
            _pdf_add_rule(pdf)
        try:
            spec.renderer(pdf, payload)
        except Exception as exc:  # pragma: no cover - robustness
            errors.append(f"{spec.title}: {exc}")
            continue

    if errors:
        _pdf_section_heading(pdf, "Rendering Notes")
        _pdf_add_paragraph(
            pdf,
            "Some sections failed to render. The report is still usable; see notes below.",
            size=10,
        )
        _pdf_add_bullets(pdf, errors, size=9, line_h=5)

    output = pdf.output(dest="S")
    return output if isinstance(output, (bytes, bytearray)) else output.encode("latin-1")
