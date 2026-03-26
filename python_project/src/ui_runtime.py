from __future__ import annotations

import hashlib
import html
import re
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.io as pio
try:
    import streamlit as st
except ModuleNotFoundError:  # pragma: no cover - import smoke fallback
    class _SessionStateStub(dict):
        pass

    class _StreamlitStub:
        session_state: dict[str, Any] = _SessionStateStub()

        def __getattr__(self, name: str):
            raise AttributeError(name)

    st = _StreamlitStub()
from fpdf import FPDF, XPos, YPos


def configure_helpers(**helpers: Any) -> None:
    globals().update(helpers)


def _hash_dataframe_for_csv(df: pd.DataFrame) -> str:
    try:
        digest = hashlib.sha1()
        digest.update(repr(tuple(df.columns)).encode("utf-8"))
        digest.update(repr(tuple(str(dtype) for dtype in df.dtypes)).encode("utf-8"))
        row_hash = pd.util.hash_pandas_object(df, index=False, categorize=False)
        digest.update(row_hash.to_numpy(dtype="uint64", copy=False).tobytes())
        return digest.hexdigest()
    except Exception:
        try:
            return hashlib.sha1(df.to_csv(index=False).encode("utf-8")).hexdigest()
        except Exception:
            return f"csv-fallback:{id(df)}:{len(df)}:{len(df.columns)}"


@st.cache_data(
    show_spinner=False,
    ttl=3600,
    max_entries=256,
    hash_funcs={pd.DataFrame: _hash_dataframe_for_csv},
)
def _dataframe_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def fmt_usd(x: float, decimals: int = 0) -> str:
    try:
        return f"${x:,.{decimals}f}"
    except Exception:
        return "$0"

def _shorten_text(value: str, max_len: int = 36) -> str:
    s = str(value or "").strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 3].rstrip() + "..."

def render_pill_list(items: list[str], limit: int = 12, empty_label: str = "--") -> str:
    cleaned = [str(i).strip() for i in (items or []) if str(i).strip()]
    if not cleaned:
        return f'<div class="pill-list"><span class="pill pill-muted">{html.escape(empty_label)}</span></div>'
    seen = []
    for item in cleaned:
        if item not in seen:
            seen.append(item)
    shown = seen[:limit]
    pills = [f'<span class="pill">{html.escape(item)}</span>' for item in shown]
    if len(seen) > limit:
        pills.append(f'<span class="pill pill-muted">+{len(seen) - limit} more</span>')
    return '<div class="pill-list">' + "".join(pills) + "</div>"

def _current_filter_parts(extra: list[str] | None = None) -> list[str]:
    parts = []
    session_val = st.session_state.get("session", None)
    session_label = _session_label(session_val) if session_val is not None else ""
    if session_label:
        parts.append(f"Session: {session_label}")
    scope_label = st.session_state.get("scope", "")
    if scope_label:
        parts.append(f"Scope: {scope_label}")
    lobbyshort = st.session_state.get("lobbyshort", "").strip()
    query = st.session_state.get("search_query", "").strip()
    if lobbyshort:
        parts.append(f"Lobbyist: {_shorten_text(lobbyshort, 28)}")
    elif query:
        parts.append(f"Query: {_shorten_text(query, 28)}")
    if extra:
        parts.extend([p for p in extra if p])
    return parts

def _export_context_label(extra: list[str] | None = None, max_len: int = 72) -> str:
    parts = _current_filter_parts(extra)
    if not parts:
        return ""
    return _shorten_text(", ".join(parts), max_len)

def _export_filename(filename: str, extra: list[str] | None = None) -> str:
    parts = _current_filter_parts(extra)
    if not parts:
        return filename
    stem = Path(filename).stem or "export"
    suffix = Path(filename).suffix or ".csv"
    tokens = []
    for part in parts:
        token = re.sub(r"[^A-Za-z0-9]+", "-", part).strip("-").lower()
        if token:
            tokens.append(token)
    tokens = tokens[:4]
    if not tokens:
        return filename
    return f"{stem}__{'__'.join(tokens)}{suffix}"

def export_dataframe(df: pd.DataFrame, filename: str, label: str = "Download CSV", context: list[str] | str | None = None):
    extra = []
    if isinstance(context, str):
        extra = [context]
    elif isinstance(context, (list, tuple)):
        extra = [str(c) for c in context if c]
    context_label = _export_context_label(extra)
    export_label = f"{label} ({context_label})" if context_label else label
    export_name = _export_filename(filename, extra)
    csv_bytes = _dataframe_csv_bytes(df)
    _ = st.download_button(label=export_label, data=csv_bytes, file_name=export_name, mime="text/csv")
    if context_label:
        st.markdown(f'<div class="section-caption">CSV includes: {context_label}.</div>', unsafe_allow_html=True)
    return ""


def require_columns(df: pd.DataFrame, required: list[str], label: str, hint: str = "") -> bool:
    missing = [c for c in required if c not in df.columns]
    if not missing:
        return True
    st.warning(f"{label} is missing required columns: {', '.join(missing)}.")
    if hint:
        st.caption(hint)
    return False

def reset_filters(default_session: str) -> None:
    st.session_state.search_query = ""
    st.session_state.lobbyshort = ""
    st.session_state.lobby_filerid = None
    st.session_state.lobby_selected_key = ""
    st.session_state.lobby_all_matches = False
    st.session_state.lobby_merge_keys = []
    st.session_state.lobby_candidate_map = {}
    st.session_state.lobby_match_query = ""
    st.session_state.lobby_match_select = "No match"
    st.session_state.bill_search = ""
    st.session_state.activity_search = ""
    st.session_state.disclosure_search = ""
    st.session_state.lobby_policy_focus = {}
    st.session_state.filter_lobbyshort = ""
    st.session_state.scope = "This Session"
    st.session_state.session = default_session


def _remember_recent_search(query: str) -> None:
    """Track recent lobby lookups for quick reuse."""
    if not query or not query.strip():
        return
    history = st.session_state.get("recent_lobby_searches", [])
    q = query.strip()
    deduped = [h for h in history if h.strip().lower() != q.lower()]
    deduped.insert(0, q)
    st.session_state.recent_lobby_searches = deduped[:6]


def reset_client_filters(default_session: str) -> None:
    st.session_state.client_query = ""
    st.session_state.client_name = ""
    st.session_state.client_bill_search = ""
    st.session_state.client_bill_search_seed = ""
    st.session_state.client_activity_search = ""
    st.session_state.client_disclosure_search = ""
    st.session_state.client_policy_focus = {}
    st.session_state.client_filter = ""
    st.session_state.client_scope = "This Session"
    st.session_state.client_session = default_session
    st.session_state.client_scope_radio = "This Session"
    st.session_state.client_session_select = _session_label(default_session)
    st.session_state.client_suggestions_select = "Select a client..."
    st.session_state.client_query_input = ""
    st.session_state.client_bill_search_input = ""
    st.session_state.client_activity_search_input = ""
    st.session_state.client_disclosure_search_input = ""
    st.session_state.client_filter_input = ""


def reset_member_filters(default_session: str) -> None:
    st.session_state.member_query = ""
    st.session_state.member_name = ""
    st.session_state.member_bill_search = ""
    st.session_state.member_witness_search = ""
    st.session_state.member_activity_search = ""
    st.session_state.member_filter = ""
    st.session_state.member_session = default_session
    st.session_state.member_session_select = _session_label(default_session)
    st.session_state.member_suggestions_select = "Select a legislator..."
    st.session_state.member_query_input = ""
    st.session_state.member_bill_search_input = ""
    st.session_state.member_witness_search_input = ""
    st.session_state.member_activity_search_input = ""
    st.session_state.member_filter_input = ""


def _remember_recent_client_search(query: str) -> None:
    if not query or not query.strip():
        return
    history = st.session_state.get("recent_client_searches", [])
    q = query.strip()
    deduped = [h for h in history if h.strip().lower() != q.lower()]
    deduped.insert(0, q)
    st.session_state.recent_client_searches = deduped[:6]


def _remember_recent_member_search(query: str) -> None:
    if not query or not query.strip():
        return
    history = st.session_state.get("recent_member_searches", [])
    q = query.strip()
    deduped = [h for h in history if h.strip().lower() != q.lower()]
    deduped.insert(0, q)
    st.session_state.recent_member_searches = deduped[:6]


def _ordinal(n: int) -> str:
    if 10 <= (n % 100) <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"

def _session_label(session_val: str) -> str:
    s = str(session_val).strip()
    if not s or s.lower() in {"none", "nan", "null"}:
        return ""
    # Special sessions encoded like 891 -> "89R / 1st Special".
    if s.isdigit():
        if len(s) >= 3:
            base = s[:-1]
            special = s[-1]
            if base.isdigit() and special.isdigit():
                return f"{base}R / {_ordinal(int(special))} Special"
        return _ordinal(int(s))
    return s

def _session_long_label(session_val: str | None) -> str:
    s = str(session_val or "").strip()
    if not s or s.lower() in {"none", "nan", "null"}:
        return ""
    if s.isdigit() and len(s) >= 3:
        base = s[:-1]
        special = s[-1]
        if base.isdigit() and special.isdigit():
            return f"{_ordinal(int(base))} {_ordinal(int(special))} Special Session"
    m = re.match(r"^(\d+)\s*R$", s, flags=re.IGNORECASE)
    if m:
        return f"{_ordinal(int(m.group(1)))} Regular Session"
    if s.isdigit():
        return f"{_ordinal(int(s))} Regular Session"
    m = re.search(r"(\d+).*(\d+)(?:st|nd|rd|th)?\s*Special", s, flags=re.IGNORECASE)
    if m:
        return f"{_ordinal(int(m.group(1)))} {_ordinal(int(m.group(2)))} Special Session"
    return s

def _session_range_label(series: pd.Series) -> str:
    if series is None or series.empty:
        return "All Sessions"
    base_nums = _session_base_number_series(series)
    base_nums = base_nums.dropna().astype(int)
    if base_nums.empty:
        return "All Sessions"
    min_base = int(base_nums.min())
    max_base = int(base_nums.max())
    if min_base == max_base:
        return f"{_ordinal(min_base)} Regular Session"
    return f"{_ordinal(min_base)} to {_ordinal(max_base)} Sessions"

def _session_sort_key(session_val: str) -> tuple[int, int, int]:
    s = str(session_val).strip()
    if not s:
        return (0, 2, 0)
    if s.isdigit():
        base = int(s[:-1]) if len(s) >= 2 else int(s)
        special = int(s[-1]) if len(s) >= 2 else 0
        return (base, 1, special)
    m = re.match(r"^(\d+)\s*R$", s, flags=re.IGNORECASE)
    if m:
        return (int(m.group(1)), 0, 0)
    return (0, 2, 0)

def _default_session_from_list(sessions: list[str]) -> str:
    if not sessions:
        return ""
    if "89R" in sessions:
        return "89R"
    regular = [s for s in sessions if str(s).strip().upper().endswith("R") and str(s).strip()[:-1].isdigit()]
    if regular:
        return sorted(regular, key=_session_sort_key)[-1]
    return sorted(sessions, key=_session_sort_key)[-1]

def _slugify(value: str, default: str = "report") -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", str(value or "")).strip("-").lower()
    return s or default

def _clean_options(options: list[str]) -> list[str]:
    clean = []
    for opt in options:
        s = str(opt).strip()
        if not s or s.lower() in {"none", "nan", "null"}:
            continue
        clean.append(s)
    return clean

def _pdf_safe_text(text: str) -> str:
    if text is None:
        return ""
    return str(text).encode("latin-1", "replace").decode("latin-1")

PDF_CHART_ERROR_KEY = "pdf_chart_error"

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

def _record_pdf_chart_error(message: str) -> None:
    if not message:
        return
    if PDF_CHART_ERROR_KEY not in st.session_state:
        st.session_state[PDF_CHART_ERROR_KEY] = message

def _clear_pdf_chart_error() -> None:
    if PDF_CHART_ERROR_KEY in st.session_state:
        del st.session_state[PDF_CHART_ERROR_KEY]

def _configure_kaleido_scope() -> bool:
    try:
        scope = pio.kaleido.scope
    except Exception as exc:
        _record_pdf_chart_error(f"Kaleido unavailable: {exc}")
        return False
    if scope is None:
        _record_pdf_chart_error("Kaleido scope unavailable. Install the kaleido package.")
        return False
    try:
        scope.mathjax = None
        scope.default_format = "png"
    except Exception:
        pass
    return True

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

def _apply_pdf_chart_layout(fig):
    if fig is None:
        return fig
    fig.update_layout(
        font=dict(family=PDF_FONT_SANS, size=10.5, color="#1f2937"),
        title_font=dict(family=PDF_FONT_SANS, size=13, color="#102843"),
        paper_bgcolor="#f8fbff",
        plot_bgcolor="#ffffff",
        legend=dict(
            font=dict(family=PDF_FONT_SANS, size=9.5, color="#1f2937"),
            bgcolor="rgba(248,251,255,0.9)",
            bordercolor="#d5e0ee",
            borderwidth=1,
        ),
    )
    fig.update_xaxes(
        automargin=True,
        showgrid=True,
        gridcolor="#e3eaf4",
        linecolor="#ccd7e6",
        tickfont=dict(family=PDF_FONT_SANS, color="#3a4a5f", size=9.5),
        title_font=dict(family=PDF_FONT_SANS, color="#2d3f57", size=10),
    )
    fig.update_yaxes(
        automargin=True,
        showgrid=True,
        gridcolor="#e3eaf4",
        linecolor="#ccd7e6",
        tickfont=dict(family=PDF_FONT_SANS, color="#3a4a5f", size=9.5),
        title_font=dict(family=PDF_FONT_SANS, color="#2d3f57", size=10),
    )
    return fig

def _fig_to_png_bytes(fig, width: int = 900, height: int = 500, scale: int = 2) -> bytes | None:
    if fig is None:
        return None
    if not _configure_kaleido_scope():
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
    if last_exc is not None:
        _record_pdf_chart_error(str(last_exc))
    return None

def _coerce_pdf_bytes(data) -> bytes | None:
    if data is None:
        return None
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    if isinstance(data, str):
        return data.encode("latin-1", errors="replace")
    if hasattr(data, "getvalue"):
        try:
            return data.getvalue()
        except Exception:
            return None
    try:
        return bytes(data)
    except Exception:
        return None

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

def _pdf_clean_chart_caption(caption: str) -> str:
    txt = str(caption or "").strip()
    if not txt:
        return "Chart"
    txt = re.sub(r"^(chart|figure)\s*\d+\s*[:.\-]\s*", "", txt, flags=re.IGNORECASE)
    return txt.strip() or "Chart"

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

def _pdf_add_cover_page(pdf: FPDF, payload: dict) -> None:
    page_w = pdf.w
    page_h = pdf.h

    pdf.set_fill_color(*PDF_COLOR_PAGE_BG)
    pdf.rect(0, 0, page_w, page_h, "F")

    # Minimal page architecture.
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

def _build_focus_chart(chart: dict):
    kind = str(chart.get("kind", "")).strip().lower()
    if kind == "bar":
        df = pd.DataFrame(chart.get("data", []))
        if df.empty or "label" not in df.columns or "value" not in df.columns:
            return None
        orientation = str(chart.get("orientation", "h")).strip().lower()
        if orientation == "v":
            fig = px.bar(
                df,
                x="label",
                y="value",
                text="value",
                color_discrete_sequence=["#4c78a8"],
            )
            fig.update_traces(textposition="outside", cliponaxis=False)
            fig.update_layout(
                template="plotly_white",
                title=chart.get("title", ""),
                xaxis_title="",
                yaxis_title="",
                margin=dict(l=40, r=20, t=50, b=40),
            )
            fig.update_yaxes(tickformat="~s")
        else:
            fig = px.bar(
                df.sort_values("value"),
                x="value",
                y="label",
                orientation="h",
                text="value",
                color_discrete_sequence=["#4c78a8"],
            )
            fig.update_traces(textposition="outside", cliponaxis=False)
            fig.update_layout(
                template="plotly_white",
                title=chart.get("title", ""),
                xaxis_title="",
                yaxis_title="",
                margin=dict(l=40, r=20, t=50, b=30),
            )
            fig.update_xaxes(tickformat="~s")
        return fig

    if kind == "grouped_bar":
        df = pd.DataFrame(chart.get("data", []))
        if df.empty or not {"Position", "Funding", "Count"}.issubset(df.columns):
            return None
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
        fig.update_layout(
            template="plotly_white",
            title=chart.get("title", ""),
            xaxis_title="",
            yaxis_title="",
            margin=dict(l=40, r=20, t=50, b=30),
        )
        fig.update_yaxes(tickformat="~s")
        return fig

    return None

def _calc_share_range(tfl_low: float, tfl_high: float, total_low: float, total_high: float) -> tuple[float, float]:
    if total_low <= 0 or total_high <= 0:
        return 0.0, 0.0
    low = tfl_low / total_high if total_high else 0.0
    high = tfl_high / total_low if total_low else 0.0
    low = min(max(low, 0.0), 1.0)
    high = min(max(high, 0.0), 1.0)
    return low * 100, high * 100

def _chart_lines(rows: list[tuple[str, str]]) -> str:
    return "\n".join([f"{label}: {value}" for label, value in rows if label])


def _hydrate_report_inputs(
    Bill_Sub_All: pd.DataFrame,
    focus_context: dict | None,
) -> tuple[pd.DataFrame, dict]:
    fc = dict(focus_context or {})
    loader = fc.get("table_loader")
    path = str(fc.get("table_loader_path", "")).strip()
    if not callable(loader) or not path:
        return Bill_Sub_All, fc

    raw_keys = fc.get("table_loader_keys", ())
    table_keys = tuple(str(key).strip() for key in raw_keys if str(key).strip())
    if not table_keys:
        return Bill_Sub_All, fc

    try:
        loaded = loader(path, table_keys)
    except Exception:
        return Bill_Sub_All, fc
    if not isinstance(loaded, dict):
        return Bill_Sub_All, fc

    tables = fc.get("tables", {})
    tables = dict(tables) if isinstance(tables, dict) else {}
    for key, value in loaded.items():
        if isinstance(value, pd.DataFrame):
            tables[str(key)] = value
    fc["tables"] = tables

    if (
        (not isinstance(Bill_Sub_All, pd.DataFrame) or Bill_Sub_All.empty)
        and isinstance(tables.get("Bill_Sub_All"), pd.DataFrame)
    ):
        Bill_Sub_All = tables["Bill_Sub_All"]

    return Bill_Sub_All, fc

def _build_report_payload(
    *,
    session_val: str | None,
    scope_label: str,
    focus_label: str,
    Lobby_TFL_Client_All: pd.DataFrame,
    Wit_All: pd.DataFrame,
    Bill_Status_All: pd.DataFrame,
    Bill_Sub_All: pd.DataFrame,
    tfl_session_val: str | None,
    focus_context: dict | None = None,
) -> dict:
    session_label = _session_label(session_val) if session_val else "Selected Session"
    generated_dt = datetime.now()
    generated_date = generated_dt.strftime("%B %d, %Y")
    generated_ts = generated_dt.strftime("%Y-%m-%d %H:%M")
    scope_label = scope_label or "Selected Session"
    focus_label = focus_label or "All"

    scope_all = scope_label.strip().lower().startswith("all")
    tfl_session = str(tfl_session_val) if tfl_session_val is not None else str(session_val or "")

    base = ensure_cols(
        Lobby_TFL_Client_All,
        {"IsTFL": 0, "Low_num": 0.0, "High_num": 0.0, "Client": "", "LobbyShort": ""},
    ).copy()
    if "Session" in base.columns:
        base["Session"] = base["Session"].astype(str).str.strip()
        if not scope_all and tfl_session:
            base = base[base["Session"] == tfl_session]

    base["IsTFL"] = pd.to_numeric(base.get("IsTFL", 0), errors="coerce").fillna(0).astype(int)
    base["Low_num"] = pd.to_numeric(base.get("Low_num", 0), errors="coerce").fillna(0.0)
    base["High_num"] = pd.to_numeric(base.get("High_num", 0), errors="coerce").fillna(0.0)

    scope_session_label = ""
    if scope_all:
        if "Session" in base.columns:
            scope_session_label = _session_range_label(base["Session"])
        else:
            scope_session_label = "All Sessions"
    else:
        scope_session_label = _session_long_label(session_val)
    if not scope_session_label:
        scope_session_label = scope_label or "Selected Session"

    report_id = f"LL-{generated_dt.strftime('%Y%m%d-%H%M')}-{_slugify(focus_label, default='scope')[:10]}"
    filter_summary_parts = [f"Scope: {scope_session_label}"]
    if focus_label:
        filter_summary_parts.append(f"Focus: {focus_label}")
    if focus_context and isinstance(focus_context, dict):
        if focus_context.get("type") == "bill":
            bill_id = focus_context.get("bill") or focus_context.get("query", "")
            if bill_id:
                filter_summary_parts.append(f"Bill: {bill_id}")
        if focus_context.get("type") == "lobbyist":
            lobby_name = focus_context.get("display_name", "")
            if lobby_name:
                filter_summary_parts.append(f"Lobbyist: {lobby_name}")
    filter_summary = "; ".join(filter_summary_parts)
    selected_lobbyist = ""
    if focus_context and isinstance(focus_context, dict) and focus_context.get("type") == "lobbyist":
        selected_lobbyist = focus_context.get("display_name") or ""

    total_low = float(base["Low_num"].sum()) if not base.empty else 0.0
    total_high = float(base["High_num"].sum()) if not base.empty else 0.0
    tfl_low = float(base.loc[base["IsTFL"] == 1, "Low_num"].sum()) if not base.empty else 0.0
    tfl_high = float(base.loc[base["IsTFL"] == 1, "High_num"].sum()) if not base.empty else 0.0
    private_low = float(base.loc[base["IsTFL"] == 0, "Low_num"].sum()) if not base.empty else 0.0
    private_high = float(base.loc[base["IsTFL"] == 0, "High_num"].sum()) if not base.empty else 0.0

    tfl_share_low_pct, tfl_share_high_pct = _calc_share_range(tfl_low, tfl_high, total_low, total_high)
    private_share_low_pct, private_share_high_pct = _calc_share_range(
        private_low, private_high, total_low, total_high
    )

    funding_mix = {
        "Taxpayer Funded": (tfl_low + tfl_high) / 2,
        "Private": (private_low + private_high) / 2,
    }

    def _top_clients(df: pd.DataFrame, is_tfl: int, limit: int = 5) -> list[dict]:
        if df.empty or "Client" not in df.columns:
            return []
        subset = df[df["IsTFL"] == is_tfl]
        subset["Client"] = subset["Client"].fillna("").astype(str).str.strip()
        subset = subset[subset["Client"] != ""]
        if subset.empty:
            return []
        grouped = (
            subset.groupby("Client", as_index=False)
            .agg(Low=("Low_num", "sum"), High=("High_num", "sum"))
            .sort_values(["High", "Low"], ascending=False)
            .head(limit)
        )
        return [
            {"Client": row.Client, "Low": float(row.Low), "High": float(row.High)}
            for row in grouped.itertuples(index=False)
        ]

    top_clients_tfl = _top_clients(base, 1, limit=5)
    top_clients_private = _top_clients(base, 0, limit=5)

    def _series_from(df: pd.DataFrame, col: str) -> pd.Series:
        s = df.get(col, pd.Series(dtype=object))
        if isinstance(s, pd.DataFrame):
            s = s.iloc[:, 0]
        return s

    def _unique_count(s: pd.Series) -> int:
        if s is None or s.empty:
            return 0
        v = s.dropna().astype(str).str.strip()
        v = v[(v != "") & (~v.str.lower().isin(["nan", "none", "null"]))]
        return int(v.nunique())

    unique_lobbyists_total = _unique_count(_series_from(base, "LobbyShort"))
    unique_lobbyists_tfl = _unique_count(_series_from(base.loc[base["IsTFL"] == 1], "LobbyShort"))
    unique_clients_total = _unique_count(_series_from(base, "Client"))
    unique_clients_tfl = _unique_count(_series_from(base.loc[base["IsTFL"] == 1], "Client"))

    chart_compensation_bar = _chart_lines(
        [
            ("Taxpayer Funded", f"{fmt_usd(tfl_low)} - {fmt_usd(tfl_high)}"),
            ("Private", f"{fmt_usd(private_low)} - {fmt_usd(private_high)}"),
            ("Total", f"{fmt_usd(total_low)} - {fmt_usd(total_high)}"),
        ]
    )
    chart_share = _chart_lines(
        [
            ("Taxpayer Funded share", f"{tfl_share_low_pct:.1f}% - {tfl_share_high_pct:.1f}%"),
            ("Private share", f"{private_share_low_pct:.1f}% - {private_share_high_pct:.1f}%"),
        ]
    )

    chart_entity_types = "No taxpayer-funded clients found."
    entity_type_counts = []
    tfl_clients = base[base["IsTFL"] == 1]
    if not tfl_clients.empty:
        clients = _series_from(tfl_clients, "Client").dropna().astype(str).str.strip()
        clients = clients[(clients != "") & (~clients.str.lower().isin(["nan", "none", "null"]))].drop_duplicates()
        if not clients.empty:
            type_counts = clients.map(lambda x: match_entity_type(x)[0]).value_counts().head(5)
            chart_entity_types = "\n".join(
                [f"{name}: {count} clients" for name, count in type_counts.items()]
            )
            entity_type_counts = [
                {"type": name, "count": int(count)} for name, count in type_counts.items()
            ]

    tfl_flag = pd.DataFrame(columns=["LobbyShort", "IsTFL"])
    if not base.empty and "LobbyShort" in base.columns:
        tfl_flag = (
            base.groupby("LobbyShort", as_index=False)["IsTFL"]
            .max()
            .rename(columns={"IsTFL": "IsTFL"})
        )

    witness_summary = "No witness-list data available for this scope/session."
    chart_witness_positions = "No witness-list data available."
    witness_counts = {
        "tfl": {"Against": 0, "For": 0, "On": 0},
        "private": {"Against": 0, "For": 0, "On": 0},
    }
    against = pd.DataFrame()

    wit = Wit_All if isinstance(Wit_All, pd.DataFrame) else pd.DataFrame()
    if not wit.empty and "LobbyShort" in wit.columns:
        if session_val is not None and "Session" in wit.columns:
            wit = wit[wit["Session"].astype(str).str.strip() == str(session_val)]
        if not wit.empty:
            pos = bill_position_from_flags(wit)
            if not pos.empty:
                pos = pos.merge(tfl_flag, on="LobbyShort", how="left")
                pos["IsTFL"] = pd.to_numeric(pos.get("IsTFL", 0), errors="coerce").fillna(0).astype(int)

                def _pos_counts(df: pd.DataFrame) -> dict:
                    return {
                        "Against": int(df["Position"].astype(str).str.contains("Against", case=False, na=False).sum()),
                        "For": int(df["Position"].astype(str).str.contains(r"\bFor\b", case=False, na=False).sum()),
                        "On": int(df["Position"].astype(str).str.contains(r"\bOn\b", case=False, na=False).sum()),
                    }

                tfl_counts = _pos_counts(pos[pos["IsTFL"] == 1])
                pri_counts = _pos_counts(pos[pos["IsTFL"] != 1])
                witness_counts = {"tfl": tfl_counts, "private": pri_counts}

                witness_summary = (
                    "Taxpayer-funded lobbyists recorded "
                    f"{tfl_counts['Against']:,} against, {tfl_counts['For']:,} for, "
                    f"and {tfl_counts['On']:,} on positions; private lobbyists recorded "
                    f"{pri_counts['Against']:,} against, {pri_counts['For']:,} for, "
                    f"and {pri_counts['On']:,} on positions."
                )
                chart_witness_positions = _chart_lines(
                    [
                        (
                            "Taxpayer Funded",
                            f"Against {tfl_counts['Against']:,}, For {tfl_counts['For']:,}, On {tfl_counts['On']:,}",
                        ),
                        (
                            "Private",
                            f"Against {pri_counts['Against']:,}, For {pri_counts['For']:,}, On {pri_counts['On']:,}",
                        ),
                    ]
                )
                against = pos[pos["Position"].astype(str).str.contains("Against", case=False, na=False)]

    top_bills = []
    if not against.empty:
        counts = (
            against.groupby(["Bill", "IsTFL"])
            .size()
            .unstack(fill_value=0)
            .reset_index()
        )
        counts["tfl"] = counts.get(1, 0)
        counts["private"] = counts.get(0, 0)
        counts = counts.sort_values(["tfl", "private", "Bill"], ascending=[False, False, True]).head(5)

        bill_info = Bill_Status_All if isinstance(Bill_Status_All, pd.DataFrame) else pd.DataFrame()
        if not bill_info.empty and "Session" in bill_info.columns and session_val is not None:
            bill_info = bill_info[bill_info["Session"].astype(str).str.strip() == str(session_val)]
        keep_cols = [c for c in ["Bill", "Caption", "Status"] if c in bill_info.columns]
        if keep_cols:
            bill_info = bill_info[keep_cols].drop_duplicates(subset=["Bill"])
        counts = counts.merge(bill_info, on="Bill", how="left") if keep_cols else counts

        for row in counts.itertuples(index=False):
            bill_id = str(getattr(row, "Bill", "")).strip() or "-"
            caption = str(getattr(row, "Caption", "")).strip() or "-"
            status = str(getattr(row, "Status", "")).strip()
            summary = f"Status: {status}" if status else "Status: Unknown"
            top_bills.append(
                {
                    "id": bill_id,
                    "caption": caption,
                    "tfl": int(getattr(row, "tfl", 0) or 0),
                    "private": int(getattr(row, "private", 0) or 0),
                    "summary": summary,
                }
            )

    chart_top_bills = (
        "\n".join(
            [
                f"{i + 1}. {b['id']} - TFL {b['tfl']:,}, Private {b['private']:,}"
                for i, b in enumerate(top_bills)
            ]
        )
        if top_bills
        else "No bill-level opposition data available."
    )

    top_subjects = []
    bill_sub = Bill_Sub_All if isinstance(Bill_Sub_All, pd.DataFrame) else pd.DataFrame()
    if not against.empty and not bill_sub.empty and {"Bill", "Subject"}.issubset(bill_sub.columns):
        if "Session" in bill_sub.columns and session_val is not None:
            bill_sub = bill_sub[bill_sub["Session"].astype(str).str.strip() == str(session_val)]
        merged = against[["Bill"]].merge(bill_sub[["Bill", "Subject"]], on="Bill", how="left")
        merged["Subject"] = merged["Subject"].fillna("").astype(str).str.strip()
        merged = merged[merged["Subject"] != ""]
        if not merged.empty:
            subject_counts = (
                merged.groupby("Subject")
                .size()
                .reset_index(name="Oppositions")
                .sort_values("Oppositions", ascending=False)
                .head(5)
            )
            top_subjects = subject_counts.to_dict("records")

    chart_top_subjects = (
        "\n".join(
            [
                f"{i + 1}. {s['Subject']} - {int(s['Oppositions']):,} oppositions"
                for i, s in enumerate(top_subjects)
            ]
        )
        if top_subjects
        else "No subject-level opposition data available."
    )

    scope_note = ""
    if scope_all:
        scope_note = (
            f"Totals reflect all available sessions. Bill-level sections reflect {session_label}."
        )

    existing_law_gap_summary = (
        "Texas law restricts state agencies from hiring lobbyists with public funds, "
        "but political subdivisions are not uniformly covered, creating a parity gap."
    )
    recommended_fix_statute = (
        "Amend Texas Government Code Section 556.005 to include political subdivisions and "
        "prohibit direct or indirect use of public funds for lobbying."
    )
    implementation_notes = (
        "Define political subdivision and public funds clearly, cover dues and assessments, "
        "and provide enforceable remedies for violations."
    )
    data_sources_bullets = "\n".join(
        [
            "- Texas Ethics Commission: lobby registrations, compensation ranges, and activity reports.",
            "- Texas Legislature Online: bill status, witness lists, and subject classifications.",
            "- Lobby Look-Up compiled dataset.",
        ]
    )
    disclaimer_note = (
        "Disclaimer: Figures are based on reported ranges and should be read as conservative estimates."
    )

    focus_section = None
    fc = focus_context or {}
    focus_type = str(fc.get("type", "")).strip().lower()
    tables = fc.get("tables", {}) if isinstance(fc, dict) else {}
    lookups = fc.get("lookups", {}) if isinstance(fc, dict) else {}
    if not isinstance(tables, dict):
        tables = {}
    if not isinstance(lookups, dict):
        lookups = {}

    staff_all = tables.get("Staff_All", pd.DataFrame())
    lobby_sub_all = tables.get("Lobby_Sub_All", pd.DataFrame())
    la_food = tables.get("LaFood", pd.DataFrame())
    la_ent = tables.get("LaEnt", pd.DataFrame())
    la_tran = tables.get("LaTran", pd.DataFrame())
    la_gift = tables.get("LaGift", pd.DataFrame())
    la_evnt = tables.get("LaEvnt", pd.DataFrame())
    la_awrd = tables.get("LaAwrd", pd.DataFrame())
    la_cvr = tables.get("LaCvr", pd.DataFrame())
    la_dock = tables.get("LaDock", pd.DataFrame())
    la_i4e = tables.get("LaI4E", pd.DataFrame())
    la_sub = tables.get("LaSub", pd.DataFrame())

    name_to_short = lookups.get("name_to_short", {})
    short_to_names = lookups.get("short_to_names", {})
    filerid_to_short = lookups.get("filerid_to_short", {})
    if not isinstance(name_to_short, dict):
        name_to_short = {}
    if not isinstance(short_to_names, dict):
        short_to_names = {}
    if not isinstance(filerid_to_short, dict):
        filerid_to_short = {}

    report_title = str(fc.get("report_title", "")).strip()
    if not report_title:
        if focus_type == "client":
            report_title = "Client Report"
        elif focus_type == "legislator":
            report_title = "Legislator Report"
        elif focus_type == "lobbyist":
            report_title = "Lobbyist Report"
        elif focus_type == "bill":
            report_title = "Bill Report"
        else:
            report_title = "Lobby Look-Up Report"

    def _truncate_text(text: str, max_len: int = 80) -> str:
        s = str(text or "").strip()
        if len(s) <= max_len:
            return s
        return s[: max_len - 3].rstrip() + "..."

    def _join_top(items: list[str], fallback: str = "Not available") -> str:
        clean = [s for s in items if str(s).strip()]
        return ", ".join(clean) if clean else fallback

    def _amount_mid_sum(series: pd.Series) -> float:
        if series is None or series.empty:
            return 0.0
        s = series.fillna("").astype(str).str.strip()
        s_clean = s.str.replace("$", "", regex=False).str.replace(",", "", regex=False)
        rng = s_clean.str.extract(_MONEY_RANGE)
        rng_lo = pd.to_numeric(rng[0], errors="coerce")
        rng_hi = pd.to_numeric(rng[1], errors="coerce")
        mid = (rng_lo + rng_hi) / 2
        single = pd.to_numeric(s_clean.str.extract(r"(-?\d+(?:\.\d+)?)")[0], errors="coerce")
        val = mid.where(mid.notna(), single).fillna(0.0)
        return float(val.sum())

    def _top_counts(series: pd.Series, limit: int = 5) -> list[tuple[str, int]]:
        if series is None or series.empty:
            return []
        clean = series.dropna().astype(str).str.strip()
        clean = clean[clean != ""]
        if clean.empty:
            return []
        counts = clean.value_counts().head(limit)
        return [(idx, int(val)) for idx, val in counts.items()]

    lobbyshort_to_name = {}
    if isinstance(short_to_names, dict) and short_to_names:
        lobbyshort_to_name = {k: (v[0] if v else k) for k, v in short_to_names.items()}
    if not lobbyshort_to_name and isinstance(Lobby_TFL_Client_All, pd.DataFrame) and not Lobby_TFL_Client_All.empty:
        tmp = Lobby_TFL_Client_All[["LobbyShort", "Lobby Name"]].dropna()
        tmp["LobbyShort"] = tmp["LobbyShort"].astype(str).str.strip()
        tmp["Lobby Name"] = tmp["Lobby Name"].astype(str).str.strip()
        lobbyshort_to_name = (
            tmp.groupby("LobbyShort")["Lobby Name"]
            .first()
            .to_dict()
        )

    def _pos_counts_from_positions(df: pd.DataFrame) -> dict:
        if df.empty:
            return {"Against": 0, "For": 0, "On": 0}
        return {
            "Against": int(df["Position"].astype(str).str.contains("Against", case=False, na=False).sum()),
            "For": int(df["Position"].astype(str).str.contains(r"\bFor\b", case=False, na=False).sum()),
            "On": int(df["Position"].astype(str).str.contains(r"\bOn\b", case=False, na=False).sum()),
        }

    if focus_type == "client":
        client_name = str(fc.get("name", "")).strip()
        if client_name:
            client_rows = ensure_cols(
                base,
                {"Client": "", "LobbyShort": "", "Low_num": 0.0, "High_num": 0.0, "IsTFL": 0, "Lobby Name": ""},
            ).copy()
            _cr_norms = norm_name_series(client_rows["Client"])
            client_rows = client_rows[_cr_norms == norm_name(client_name)]

            focus_section = {"title": f"Client - {client_name}", "summary": "", "metrics": [], "bullets": [], "charts": []}
            if client_rows.empty:
                focus_section["summary"] = "No client rows were found for the selected scope."
            else:
                client_rows["Mid"] = (client_rows["Low_num"] + client_rows["High_num"]) / 2
                c_total_low = float(client_rows["Low_num"].sum())
                c_total_high = float(client_rows["High_num"].sum())
                c_tfl_low = float(client_rows.loc[client_rows["IsTFL"] == 1, "Low_num"].sum())
                c_tfl_high = float(client_rows.loc[client_rows["IsTFL"] == 1, "High_num"].sum())
                c_pri_low = float(client_rows.loc[client_rows["IsTFL"] == 0, "Low_num"].sum())
                c_pri_high = float(client_rows.loc[client_rows["IsTFL"] == 0, "High_num"].sum())
                lobbyist_count = _unique_count(_series_from(client_rows, "LobbyShort"))
                session_count = _unique_count(_series_from(client_rows, "Session")) if "Session" in client_rows.columns else 0
                is_tfl_client = "Yes" if (client_rows["IsTFL"] == 1).any() else "No"

                focus_section["summary"] = (
                    f"{client_name} is associated with {lobbyist_count:,} lobbyists in this scope "
                    f"and reported compensation ranging from {fmt_usd(c_total_low)} to {fmt_usd(c_total_high)}."
                )
                focus_section["metrics"] = [
                    ("Client", client_name),
                    ("Taxpayer funded", is_tfl_client),
                    ("Lobbyists", f"{lobbyist_count:,}"),
                    ("Total range", f"{fmt_usd(c_total_low)} - {fmt_usd(c_total_high)}"),
                    ("Taxpayer-funded range", f"{fmt_usd(c_tfl_low)} - {fmt_usd(c_tfl_high)}"),
                    ("Private range", f"{fmt_usd(c_pri_low)} - {fmt_usd(c_pri_high)}"),
                ]
                if scope_all and session_count:
                    focus_section["bullets"].append(f"Sessions observed: {session_count:,}")

                lobbyshorts = (
                    client_rows["LobbyShort"].dropna().astype(str).str.strip().unique().tolist()
                )
                lobbyshort_norms = {norm_name(s) for s in lobbyshorts if s}
                lobbyist_names = [
                    lobbyshort_to_name.get(s, s) for s in lobbyshorts
                ]
                lobbyist_norms = set()
                for name in lobbyist_names + lobbyshorts:
                    lobbyist_norms |= norm_person_variants(name)
                    init_key = _last_first_initial_key(name)
                    if init_key:
                        lobbyist_norms.add(init_key)
                lobbyist_norms_tuple = tuple(sorted(lobbyist_norms))

                wit = Wit_All if isinstance(Wit_All, pd.DataFrame) else pd.DataFrame()
                bill_count = 0
                policy_count = 0
                top_bill_lines = []
                top_subject_lines = []
                status_counts = []
                bill_list_all = []
                sub_counts = pd.DataFrame()
                if lobbyshorts and not wit.empty and "LobbyShort" in wit.columns:
                    wit = wit[wit["LobbyShort"].astype(str).str.strip().isin(lobbyshorts)]
                    if session_val is not None and "Session" in wit.columns:
                        wit = wit[wit["Session"].astype(str).str.strip() == str(session_val)]
                    if not wit.empty:
                        pos = bill_position_from_flags(wit)
                        bill_count = int(pos["Bill"].nunique()) if not pos.empty else 0
                        bill_list_all = pos["Bill"].dropna().astype(str).unique().tolist() if not pos.empty else []
                        pos_counts = _pos_counts_from_positions(pos)
                        focus_section["bullets"].append(
                            f"Bills with witness activity (selected session): {bill_count:,}"
                        )
                        focus_section["bullets"].append(
                            f"Witness positions - Against {pos_counts['Against']:,}, For {pos_counts['For']:,}, On {pos_counts['On']:,}."
                        )

                        bs = Bill_Status_All if isinstance(Bill_Status_All, pd.DataFrame) else pd.DataFrame()
                        if not bs.empty and "Session" in bs.columns and session_val is not None:
                            bs = bs[bs["Session"].astype(str).str.strip() == str(session_val)]
                        if bill_list_all and not bs.empty and "Bill" in bs.columns:
                            status_counts = _top_counts(
                                bs[bs["Bill"].astype(str).isin(bill_list_all)].get(
                                    "Status", pd.Series(dtype=object)
                                ),
                                4,
                            )

                        if "Bill" in wit.columns:
                            bill_counts = (
                                wit.groupby("Bill").size().reset_index(name="Witness Rows")
                                .sort_values("Witness Rows", ascending=False)
                                .head(5)
                            )
                            if not bill_counts.empty:
                                if not bs.empty and "Bill" in bs.columns:
                                    bs_short = bs.drop_duplicates(subset=["Bill"])
                                    bill_counts = bill_counts.merge(
                                        bs_short[["Bill", "Caption", "Status"]],
                                        on="Bill",
                                        how="left",
                                    )
                                for row in bill_counts.to_dict("records"):
                                    bill = str(row.get("Bill", "")).strip()
                                    count = int(row.get("Witness Rows", 0) or 0)
                                    caption = _truncate_text(row.get("Caption", ""), 70)
                                    status = str(row.get("Status", "")).strip()
                                    line = f"{bill} ({count:,} witness rows)"
                                    if status:
                                        line += f", {status}"
                                    if caption:
                                        line += f" - {caption}"
                                    top_bill_lines.append(line)

                        bill_sub = Bill_Sub_All if isinstance(Bill_Sub_All, pd.DataFrame) else pd.DataFrame()
                        if bill_list_all and not bill_sub.empty and {"Bill", "Subject"}.issubset(bill_sub.columns):
                            if session_val is not None and "Session" in bill_sub.columns:
                                bill_sub = bill_sub[bill_sub["Session"].astype(str).str.strip() == str(session_val)]
                            sub_counts = (
                                bill_sub[bill_sub["Bill"].astype(str).isin(bill_list_all)]
                                .groupby("Subject")
                                .size()
                                .reset_index(name="Mentions")
                                .sort_values("Mentions", ascending=False)
                                .head(5)
                            )
                            policy_count = int(sub_counts["Subject"].nunique()) if not sub_counts.empty else 0
                            for row in sub_counts.to_dict("records"):
                                subject = _truncate_text(row.get("Subject", ""), 60)
                                mentions = int(row.get("Mentions", 0) or 0)
                                if subject:
                                    top_subject_lines.append(f"{subject} ({mentions:,})")

                if bill_count:
                    focus_section["metrics"].append(("Bills w/ witness activity", f"{bill_count:,}"))
                if policy_count:
                    focus_section["metrics"].append(("Policy areas", f"{policy_count:,}"))
                if top_bill_lines:
                    focus_section["bullets"].append(
                        f"Top bills by witness activity: {_join_top(top_bill_lines)}"
                    )
                if top_subject_lines:
                    focus_section["bullets"].append(
                        f"Top policy areas: {_join_top(top_subject_lines)}"
                    )
                if not sub_counts.empty:
                    focus_section["charts"].append(
                        {
                            "kind": "bar",
                            "orientation": "h",
                            "title": "Top Policy Areas (Witness Bills)",
                            "caption": "Focus Chart. Policy areas tied to client-linked witness activity",
                            "data": [
                                {"label": str(r.Subject), "value": int(r.Mentions)}
                                for r in sub_counts.itertuples()
                            ],
                        }
                    )
                if status_counts:
                    status_summary = ", ".join([f"{k} ({v:,})" for k, v in status_counts])
                    focus_section["bullets"].append(f"Bill outcomes (selected session): {status_summary}")

                if not lobby_sub_all.empty:
                    lobby_sub = lobby_sub_all
                    if "Session" in lobby_sub.columns and session_val is not None:
                        lobby_sub = lobby_sub[lobby_sub["Session"].astype(str).str.strip() == str(session_val)]
                    if "LobbyShortNorm" in lobby_sub.columns:
                        lobby_sub = lobby_sub[lobby_sub["LobbyShortNorm"].isin(lobbyshort_norms)]
                    elif "LobbyShort" in lobby_sub.columns:
                        lobby_sub = lobby_sub[lobby_sub["LobbyShort"].astype(str).str.strip().isin(lobbyshorts)]
                    else:
                        lobby_sub = lobby_sub.iloc[0:0]
                    if not lobby_sub.empty:
                        lobby_sub = lobby_sub.assign(
                            Subject=lobby_sub.get("Subject Matter", "").fillna("").astype(str).str.strip(),
                            Other=lobby_sub.get("Other Subject Matter Description", "").fillna("").astype(str).str.strip(),
                        )
                        for col in ["Subject", "Other"]:
                            series = lobby_sub[col]
                            lobby_sub[col] = series.where(~series.str.lower().isin(["nan", "none"]), "")
                        unnamed0 = lobby_sub.get("Unnamed: 0", lobby_sub.get("Column1", "")).fillna("").astype(str).str.strip()
                        unnamed0 = unnamed0.where(~unnamed0.str.lower().isin(["nan", "none"]), "")
                        topic = lobby_sub["Subject"]
                        topic = topic.where(topic != "", lobby_sub["Other"])
                        topic = topic.where(topic != "", unnamed0)
                        topic = topic.where(topic != "", "Unspecified")
                        lobby_sub["Topic"] = topic
                        topic_counts = _top_counts(lobby_sub["Topic"], 5)
                        if topic_counts:
                            topics = ", ".join([f"{t} ({c:,})" for t, c in topic_counts])
                            focus_section["bullets"].append(f"Reported subject matters: {topics}")

                if not staff_all.empty and lobbyist_norms:
                    staff_df = staff_all
                    staff_session_mask = (
                        staff_df["Session"].astype(str).str.strip() == str(session_val)
                        if "Session" in staff_df.columns and session_val is not None
                        else pd.Series(False, index=staff_df.index)
                    )
                    last_names = {last_name_norm_from_text(n) for n in lobbyist_names if last_name_norm_from_text(n)}
                    init_map = {k: v for k, v in ((_last_first_initial_key(n), n) for n in lobbyist_names) if k}
                    full_map = {norm_name(n): n for n in lobbyist_names if n}
                    last_map = {k: v for k, v in ((last_name_norm_from_text(n), n) for n in lobbyist_names) if k}

                    match_mask = pd.Series(False, index=staff_df.index)
                    match_mask = match_mask | staff_df.get("StaffNameNorm", pd.Series(False, index=staff_df.index)).isin(lobbyist_norms)
                    match_mask = match_mask | staff_df.get("StaffLastInitialNorm", pd.Series(False, index=staff_df.index)).isin(lobbyist_norms)
                    if last_names:
                        match_mask = match_mask | staff_df.get("StaffLastNorm", pd.Series(False, index=staff_df.index)).isin(last_names)
                    if lobbyshort_norms:
                        match_mask = match_mask | staff_df.get("StaffLastInitialNorm", pd.Series(False, index=staff_df.index)).isin(lobbyshort_norms)

                    staff_pick = staff_df[match_mask]
                    staff_pick_session = staff_df[staff_session_mask & match_mask]
                    if not staff_pick.empty:
                        staff_rows = int(len(staff_pick))
                        staff_legs = int(staff_pick.get("Legislator", pd.Series(dtype=object)).nunique()) if "Legislator" in staff_pick.columns else 0
                        focus_section["metrics"].append(("Staff history rows", f"{staff_rows:,}"))
                        if staff_legs:
                            focus_section["metrics"].append(("Legislators w/ staff ties", f"{staff_legs:,}"))
                if lobbyshorts:
                    activities = build_activities_multi(
                        la_food,
                        la_ent,
                        la_tran,
                        la_gift,
                        la_evnt,
                        la_awrd,
                        lobbyshorts=lobbyshorts,
                        session=str(session_val) if session_val is not None else None,
                        name_to_short=name_to_short,
                        lobbyist_norms_tuple=lobbyist_norms_tuple,
                        filerid_to_short=filerid_to_short,
                        lobbyshort_to_name=lobbyshort_to_name,
                    )
                    if not activities.empty:
                        focus_section["metrics"].append(("Activity rows", f"{len(activities):,}"))
                        type_counts = _top_counts(activities.get("Type", pd.Series(dtype=object)), 4)
                        if type_counts:
                            types = ", ".join([f"{t} ({c:,})" for t, c in type_counts])
                            focus_section["bullets"].append(f"Top activity types: {types}")
                        amount_total = _amount_mid_sum(activities.get("Amount", pd.Series(dtype=object)))
                        if amount_total > 0:
                            focus_section["bullets"].append(f"Reported activity amount (midpoint): {fmt_usd(amount_total)}")
                        focus_section["charts"].append(
                            {
                                "kind": "bar",
                                "orientation": "h",
                                "title": "Activity Types (Rows)",
                                "caption": "Focus Chart. Activity types for client-linked lobbyists",
                                "data": [{"label": t, "value": c} for t, c in type_counts],
                            }
                        )

                    disclosures = build_disclosures_multi(
                        la_cvr,
                        la_dock,
                        la_i4e,
                        la_sub,
                        lobbyshorts=lobbyshorts,
                        session=str(session_val) if session_val is not None else None,
                        name_to_short=name_to_short,
                        lobbyist_norms_tuple=lobbyist_norms_tuple,
                        filerid_to_short=filerid_to_short,
                        lobbyshort_to_name=lobbyshort_to_name,
                    )
                    if not disclosures.empty:
                        focus_section["metrics"].append(("Disclosure rows", f"{len(disclosures):,}"))
                        d_counts = _top_counts(disclosures.get("Type", pd.Series(dtype=object)), 4)
                        if d_counts:
                            types = ", ".join([f"{t} ({c:,})" for t, c in d_counts])
                            focus_section["bullets"].append(f"Top disclosure types: {types}")
                        focus_section["charts"].append(
                            {
                                "kind": "bar",
                                "orientation": "h",
                                "title": "Disclosure Types (Rows)",
                                "caption": "Focus Chart. Disclosure types for client-linked lobbyists",
                                "data": [{"label": t, "value": c} for t, c in d_counts],
                            }
                        )
                lobby_group = (
                    client_rows.groupby("LobbyShort", as_index=False)
                    .agg(Mid=("Mid", "sum"), LobbyName=("Lobby Name", lambda s: s.dropna().astype(str).iloc[0] if len(s) else ""))
                )
                lobby_group["Lobbyist"] = lobby_group["LobbyName"].where(
                    lobby_group["LobbyName"].astype(str).str.strip().ne(""),
                    lobby_group["LobbyShort"],
                )
                top_lobby = lobby_group.sort_values("Mid", ascending=False).head(5)
                chart_data = [
                    {"label": str(r.Lobbyist), "value": float(r.Mid)}
                    for r in top_lobby.itertuples()
                    if float(r.Mid) > 0
                ]
                if chart_data:
                    focus_section["charts"].append(
                        {
                            "kind": "bar",
                            "orientation": "h",
                            "title": "Top Lobbyists by Midpoint Compensation",
                            "caption": "Focus Chart. Top lobbyists by midpoint compensation",
                            "data": chart_data,
                        }
                    )

    if focus_type == "lobbyist":
        lobbyshort = str(fc.get("lobbyshort", "")).strip()
        display_name = str(fc.get("display_name", "")).strip() or lobbyshort
        if lobbyshort:
            lobbyist_norms = set()
            for name in [display_name, lobbyshort]:
                if not name:
                    continue
                lobbyist_norms |= norm_person_variants(name)
                init_key = _last_first_initial_key(name)
                if init_key:
                    lobbyist_norms.add(init_key)
            if isinstance(short_to_names, dict) and lobbyshort in short_to_names:
                for name in short_to_names.get(lobbyshort, []):
                    lobbyist_norms |= norm_person_variants(name)
                    init_key = _last_first_initial_key(name)
                    if init_key:
                        lobbyist_norms.add(init_key)
            lobbyist_norms_tuple = tuple(sorted(lobbyist_norms))
            lobbyshort_norm = norm_name(lobbyshort)

            lobby_rows = ensure_cols(
                base,
                {"Client": "", "LobbyShort": "", "Low_num": 0.0, "High_num": 0.0, "IsTFL": 0},
            )
            lobby_rows = lobby_rows[lobby_rows["LobbyShort"].astype(str).str.strip() == lobbyshort]

            focus_section = {"title": f"Lobbyist - {display_name}", "summary": "", "metrics": [], "bullets": [], "charts": []}
            if lobby_rows.empty:
                focus_section["summary"] = "No lobbyist rows were found for the selected scope."
            else:
                lobby_rows["Mid"] = (lobby_rows["Low_num"] + lobby_rows["High_num"]) / 2
                l_tfl_low = float(lobby_rows.loc[lobby_rows["IsTFL"] == 1, "Low_num"].sum())
                l_tfl_high = float(lobby_rows.loc[lobby_rows["IsTFL"] == 1, "High_num"].sum())
                l_pri_low = float(lobby_rows.loc[lobby_rows["IsTFL"] == 0, "Low_num"].sum())
                l_pri_high = float(lobby_rows.loc[lobby_rows["IsTFL"] == 0, "High_num"].sum())
                tfl_clients_count = int(lobby_rows.loc[lobby_rows["IsTFL"] == 1, "Client"].nunique())
                pri_clients_count = int(lobby_rows.loc[lobby_rows["IsTFL"] == 0, "Client"].nunique())

                focus_section["summary"] = (
                    f"{display_name} is tied to {tfl_clients_count + pri_clients_count:,} clients in this scope "
                    f"and reported compensation ranging from {fmt_usd(l_tfl_low + l_pri_low)} to {fmt_usd(l_tfl_high + l_pri_high)}."
                )
                focus_section["metrics"] = [
                    ("Lobbyist", display_name),
                    ("Total clients", f"{tfl_clients_count + pri_clients_count:,}"),
                    ("Taxpayer-funded clients", f"{tfl_clients_count:,}"),
                    ("Private clients", f"{pri_clients_count:,}"),
                    ("Taxpayer-funded range", f"{fmt_usd(l_tfl_low)} - {fmt_usd(l_tfl_high)}"),
                    ("Private range", f"{fmt_usd(l_pri_low)} - {fmt_usd(l_pri_high)}"),
                ]

                bill_count = 0
                policy_count = 0
                top_bill_lines = []
                top_subject_lines = []
                status_counts = []
                bill_list_all = []
                sub_counts = pd.DataFrame()

                wit = Wit_All if isinstance(Wit_All, pd.DataFrame) else pd.DataFrame()
                if not wit.empty and "LobbyShort" in wit.columns:
                    wit = wit[wit["LobbyShort"].astype(str).str.strip() == lobbyshort]
                    if session_val is not None and "Session" in wit.columns:
                        wit = wit[wit["Session"].astype(str).str.strip() == str(session_val)]
                    if not wit.empty:
                        pos = bill_position_from_flags(wit)
                        bill_count = int(pos["Bill"].nunique()) if not pos.empty else 0
                        bill_list_all = pos["Bill"].dropna().astype(str).unique().tolist() if not pos.empty else []
                        pos_counts = _pos_counts_from_positions(pos)
                        focus_section["bullets"].append(
                            f"Bills with witness activity (selected session): {bill_count:,}"
                        )
                        focus_section["bullets"].append(
                            f"Witness positions - Against {pos_counts['Against']:,}, For {pos_counts['For']:,}, On {pos_counts['On']:,}."
                        )

                        bs = Bill_Status_All if isinstance(Bill_Status_All, pd.DataFrame) else pd.DataFrame()
                        if not bs.empty and "Session" in bs.columns and session_val is not None:
                            bs = bs[bs["Session"].astype(str).str.strip() == str(session_val)]
                        if bill_list_all and not bs.empty and "Bill" in bs.columns:
                            status_counts = _top_counts(
                                bs[bs["Bill"].astype(str).isin(bill_list_all)].get(
                                    "Status", pd.Series(dtype=object)
                                ),
                                4,
                            )

                        if "Bill" in wit.columns:
                            bill_counts = (
                                wit.groupby("Bill").size().reset_index(name="Witness Rows")
                                .sort_values("Witness Rows", ascending=False)
                                .head(5)
                            )
                            if not bill_counts.empty:
                                if not bs.empty and "Bill" in bs.columns:
                                    bs_short = bs.drop_duplicates(subset=["Bill"])
                                    bill_counts = bill_counts.merge(
                                        bs_short[["Bill", "Caption", "Status"]],
                                        on="Bill",
                                        how="left",
                                    )
                                for row in bill_counts.to_dict("records"):
                                    bill = str(row.get("Bill", "")).strip()
                                    count = int(row.get("Witness Rows", 0) or 0)
                                    caption = _truncate_text(row.get("Caption", ""), 70)
                                    status = str(row.get("Status", "")).strip()
                                    line = f"{bill} ({count:,} witness rows)"
                                    if status:
                                        line += f", {status}"
                                    if caption:
                                        line += f" - {caption}"
                                    top_bill_lines.append(line)

                        bill_sub = Bill_Sub_All if isinstance(Bill_Sub_All, pd.DataFrame) else pd.DataFrame()
                        if bill_list_all and not bill_sub.empty and {"Bill", "Subject"}.issubset(bill_sub.columns):
                            if session_val is not None and "Session" in bill_sub.columns:
                                bill_sub = bill_sub[bill_sub["Session"].astype(str).str.strip() == str(session_val)]
                            sub_counts = (
                                bill_sub[bill_sub["Bill"].astype(str).isin(bill_list_all)]
                                .groupby("Subject")
                                .size()
                                .reset_index(name="Mentions")
                                .sort_values("Mentions", ascending=False)
                                .head(5)
                            )
                            policy_count = int(sub_counts["Subject"].nunique()) if not sub_counts.empty else 0
                            for row in sub_counts.to_dict("records"):
                                subject = _truncate_text(row.get("Subject", ""), 60)
                                mentions = int(row.get("Mentions", 0) or 0)
                                if subject:
                                    top_subject_lines.append(f"{subject} ({mentions:,})")

                if bill_count:
                    focus_section["metrics"].append(("Bills w/ witness activity", f"{bill_count:,}"))
                if policy_count:
                    focus_section["metrics"].append(("Policy areas", f"{policy_count:,}"))

                client_mid = (
                    lobby_rows.groupby(["Client", "IsTFL"], as_index=False)
                    .agg(Mid=("Mid", "sum"))
                    .sort_values("Mid", ascending=False)
                )
                tfl_top = client_mid[client_mid["IsTFL"] == 1].head(5)
                pri_top = client_mid[client_mid["IsTFL"] == 0].head(5)
                if not tfl_top.empty:
                    top_tfl = [
                        f"{_truncate_text(r.Client, 50)} ({fmt_usd(r.Mid)})"
                        for r in tfl_top.itertuples()
                    ]
                    focus_section["bullets"].append(f"Top taxpayer-funded clients: {_join_top(top_tfl)}")
                if not pri_top.empty:
                    top_pri = [
                        f"{_truncate_text(r.Client, 50)} ({fmt_usd(r.Mid)})"
                        for r in pri_top.itertuples()
                    ]
                    focus_section["bullets"].append(f"Top private clients: {_join_top(top_pri)}")
                if top_bill_lines:
                    focus_section["bullets"].append(
                        f"Top bills by witness activity: {_join_top(top_bill_lines)}"
                    )
                if top_subject_lines:
                    focus_section["bullets"].append(
                        f"Top policy areas: {_join_top(top_subject_lines)}"
                    )
                if not sub_counts.empty:
                    focus_section["charts"].append(
                        {
                            "kind": "bar",
                            "orientation": "h",
                            "title": "Top Policy Areas (Witness Bills)",
                            "caption": "Focus Chart. Policy areas tied to lobbyist witness activity",
                            "data": [
                                {"label": str(r.Subject), "value": int(r.Mentions)}
                                for r in sub_counts.itertuples()
                            ],
                        }
                    )
                if status_counts:
                    status_summary = ", ".join([f"{k} ({v:,})" for k, v in status_counts])
                    focus_section["bullets"].append(f"Bill outcomes (selected session): {status_summary}")

                if not lobby_sub_all.empty:
                    lobby_sub = lobby_sub_all
                    if "Session" in lobby_sub.columns and session_val is not None:
                        lobby_sub = lobby_sub[lobby_sub["Session"].astype(str).str.strip() == str(session_val)]
                    if "LobbyShortNorm" in lobby_sub.columns:
                        lobby_sub = lobby_sub[lobby_sub["LobbyShortNorm"] == lobbyshort_norm]
                    elif "LobbyShort" in lobby_sub.columns:
                        lobby_sub = lobby_sub[lobby_sub["LobbyShort"].astype(str).str.strip() == lobbyshort]
                    else:
                        lobby_sub = lobby_sub.iloc[0:0]
                    if not lobby_sub.empty:
                        lobby_sub = lobby_sub.assign(
                            Subject=lobby_sub.get("Subject Matter", "").fillna("").astype(str).str.strip(),
                            Other=lobby_sub.get("Other Subject Matter Description", "").fillna("").astype(str).str.strip(),
                        )
                        for col in ["Subject", "Other"]:
                            series = lobby_sub[col]
                            lobby_sub[col] = series.where(~series.str.lower().isin(["nan", "none"]), "")
                        unnamed0 = lobby_sub.get("Unnamed: 0", lobby_sub.get("Column1", "")).fillna("").astype(str).str.strip()
                        unnamed0 = unnamed0.where(~unnamed0.str.lower().isin(["nan", "none"]), "")
                        topic = lobby_sub["Subject"]
                        topic = topic.where(topic != "", lobby_sub["Other"])
                        topic = topic.where(topic != "", unnamed0)
                        topic = topic.where(topic != "", "Unspecified")
                        lobby_sub["Topic"] = topic
                        topic_counts = _top_counts(lobby_sub["Topic"], 5)
                        if topic_counts:
                            topics = ", ".join([f"{t} ({c:,})" for t, c in topic_counts])
                            focus_section["bullets"].append(f"Reported subject matters: {topics}")

                if not staff_all.empty and lobbyist_norms:
                    staff_df = staff_all
                    staff_session_mask = (
                        staff_df["Session"].astype(str).str.strip() == str(session_val)
                        if "Session" in staff_df.columns and session_val is not None
                        else pd.Series(False, index=staff_df.index)
                    )
                    last_names = {last_name_norm_from_text(n) for n in [display_name, lobbyshort] if last_name_norm_from_text(n)}

                    match_mask = pd.Series(False, index=staff_df.index)
                    match_mask = match_mask | staff_df.get("StaffNameNorm", pd.Series(False, index=staff_df.index)).isin(lobbyist_norms)
                    match_mask = match_mask | staff_df.get("StaffLastInitialNorm", pd.Series(False, index=staff_df.index)).isin(lobbyist_norms)
                    if last_names:
                        match_mask = match_mask | staff_df.get("StaffLastNorm", pd.Series(False, index=staff_df.index)).isin(last_names)
                    if lobbyshort_norm:
                        match_mask = match_mask | (
                            staff_df.get("StaffLastInitialNorm", pd.Series(False, index=staff_df.index)) == lobbyshort_norm
                        )

                    staff_pick = staff_df[match_mask]
                    staff_pick_session = staff_df[staff_session_mask & match_mask]
                    if not staff_pick.empty:
                        staff_rows = int(len(staff_pick))
                        staff_legs = int(staff_pick.get("Legislator", pd.Series(dtype=object)).nunique()) if "Legislator" in staff_pick.columns else 0
                        focus_section["metrics"].append(("Staff history rows", f"{staff_rows:,}"))
                        if staff_legs:
                            focus_section["metrics"].append(("Legislators w/ staff ties", f"{staff_legs:,}"))
                activities = build_activities(
                    la_food,
                    la_ent,
                    la_tran,
                    la_gift,
                    la_evnt,
                    la_awrd,
                    lobbyshort=lobbyshort,
                    session=str(session_val) if session_val is not None else None,
                    name_to_short=name_to_short,
                    lobbyist_norms_tuple=lobbyist_norms_tuple,
                    filerid_to_short=filerid_to_short,
                )
                if not activities.empty:
                    focus_section["metrics"].append(("Activity rows", f"{len(activities):,}"))
                    type_counts = _top_counts(activities.get("Type", pd.Series(dtype=object)), 4)
                    if type_counts:
                        types = ", ".join([f"{t} ({c:,})" for t, c in type_counts])
                        focus_section["bullets"].append(f"Top activity types: {types}")
                    amount_total = _amount_mid_sum(activities.get("Amount", pd.Series(dtype=object)))
                    if amount_total > 0:
                        focus_section["bullets"].append(f"Reported activity amount (midpoint): {fmt_usd(amount_total)}")
                    focus_section["charts"].append(
                        {
                            "kind": "bar",
                            "orientation": "h",
                            "title": "Activity Types (Rows)",
                            "caption": "Focus Chart. Activity types for the selected lobbyist",
                            "data": [{"label": t, "value": c} for t, c in type_counts],
                        }
                    )

                disclosures = build_disclosures(
                    la_cvr,
                    la_dock,
                    la_i4e,
                    la_sub,
                    lobbyshort=lobbyshort,
                    session=str(session_val) if session_val is not None else None,
                    name_to_short=name_to_short,
                    lobbyist_norms_tuple=lobbyist_norms_tuple,
                    filerid_to_short=filerid_to_short,
                )
                if not disclosures.empty:
                    focus_section["metrics"].append(("Disclosure rows", f"{len(disclosures):,}"))
                    d_counts = _top_counts(disclosures.get("Type", pd.Series(dtype=object)), 4)
                    if d_counts:
                        types = ", ".join([f"{t} ({c:,})" for t, c in d_counts])
                        focus_section["bullets"].append(f"Top disclosure types: {types}")
                    focus_section["charts"].append(
                        {
                            "kind": "bar",
                            "orientation": "h",
                            "title": "Disclosure Types (Rows)",
                            "caption": "Focus Chart. Disclosure types for the selected lobbyist",
                            "data": [{"label": t, "value": c} for t, c in d_counts],
                        }
                    )

                client_group = (
                    lobby_rows.groupby("Client", as_index=False)
                    .agg(Mid=("Mid", "sum"))
                    .sort_values("Mid", ascending=False)
                    .head(5)
                )
                chart_data = [
                    {"label": str(r.Client), "value": float(r.Mid)}
                    for r in client_group.itertuples()
                    if float(r.Mid) > 0
                ]
                if chart_data:
                    focus_section["charts"].append(
                        {
                            "kind": "bar",
                            "orientation": "h",
                            "title": "Top Clients by Midpoint Compensation",
                            "caption": "Focus Chart. Top clients by midpoint compensation",
                            "data": chart_data,
                        }
                    )

    if focus_type == "legislator":
        member_name = str(fc.get("name", "")).strip()
        if member_name:
            focus_section = {"title": f"Legislator - {member_name}", "summary": "", "metrics": [], "bullets": [], "charts": []}
            member_info = parse_member_name(member_name)
            authored_all = build_author_bill_index(Bill_Status_All) if isinstance(Bill_Status_All, pd.DataFrame) else pd.DataFrame()
            if authored_all.empty:
                focus_section["summary"] = "No authored bill data was available for the selected session."
            else:
                authored = authored_all
                authored = authored[authored["AuthorNorm"] == norm_name(member_name)]
                if session_val is not None and "Session" in authored.columns:
                    authored = authored[authored["Session"].astype(str).str.strip() == str(session_val)]

                bill_count = int(authored["Bill"].nunique()) if not authored.empty else 0
                passed = int((authored.get("Status", pd.Series(dtype=object)) == "Passed").sum()) if not authored.empty else 0
                failed = int((authored.get("Status", pd.Series(dtype=object)) == "Failed").sum()) if not authored.empty else 0
                bill_list = authored["Bill"].dropna().astype(str).unique().tolist() if not authored.empty else []

                wit = Wit_All if isinstance(Wit_All, pd.DataFrame) else pd.DataFrame()
                witness = pd.DataFrame()
                if bill_list and not wit.empty:
                    if session_val is not None and "Session" in wit.columns:
                        wit = wit[wit["Session"].astype(str).str.strip() == str(session_val)]
                    wit = wit[wit["Bill"].astype(str).isin(bill_list)] if "Bill" in wit.columns else wit.iloc[0:0]
                    witness = bill_position_from_flags(wit) if not wit.empty else pd.DataFrame()
                    if not witness.empty:
                        witness = witness.merge(tfl_flag, on="LobbyShort", how="left")
                        witness["IsTFL"] = pd.to_numeric(witness.get("IsTFL", 0), errors="coerce").fillna(0).astype(int)

                any_witness = int(witness["Bill"].nunique()) if not witness.empty else 0
                tfl_opposed = 0
                lobbyist_count = int(witness["LobbyShort"].nunique()) if not witness.empty and "LobbyShort" in witness.columns else 0
                tfl_lobbyist_count = int(witness.loc[witness["IsTFL"] == 1, "LobbyShort"].nunique()) if not witness.empty and "LobbyShort" in witness.columns else 0
                if not witness.empty:
                    against_mask = witness["Position"].astype(str).str.contains("Against", case=False, na=False)
                    tfl_mask = witness["IsTFL"] == 1
                    tfl_opposed = int(witness.loc[against_mask & tfl_mask, "Bill"].nunique())

                focus_section["summary"] = (
                    f"{member_name} authored {bill_count:,} bills in the selected session, with "
                    f"{passed:,} passed and {failed:,} failed."
                )
                focus_section["metrics"] = [
                    ("Bills authored", f"{bill_count:,}"),
                    ("Passed / Failed", f"{passed:,} / {failed:,}"),
                    ("Bills with witness activity", f"{any_witness:,}"),
                    ("Bills opposed by TFL lobbyists", f"{tfl_opposed:,}"),
                    ("Unique lobbyists", f"{lobbyist_count:,}"),
                    ("Lobbyists w/ TFL clients", f"{tfl_lobbyist_count:,}"),
                ]

                top_bills_lines = []
                if not authored.empty:
                    authored_unique = authored.drop_duplicates(subset=["Bill"])
                    status_rank = authored_unique.get("Status", pd.Series(dtype=object)).map(
                        {"Passed": 0, "Failed": 1}
                    ).fillna(2)
                    authored_unique = authored_unique.assign(_rank=status_rank)
                    top_authored = authored_unique.sort_values(["_rank", "Bill"]).head(5)
                    for row in top_authored.to_dict("records"):
                        bill = str(row.get("Bill", "")).strip()
                        status = str(row.get("Status", "")).strip()
                        caption = _truncate_text(row.get("Caption", ""), 70)
                        line = bill
                        if status:
                            line += f" ({status})"
                        if caption:
                            line += f" - {caption}"
                        if line.strip():
                            top_bills_lines.append(line)

                policy_count = 0
                top_subject_lines = []
                bill_sub = Bill_Sub_All if isinstance(Bill_Sub_All, pd.DataFrame) else pd.DataFrame()
                if bill_list and not bill_sub.empty and {"Bill", "Subject"}.issubset(bill_sub.columns):
                    if session_val is not None and "Session" in bill_sub.columns:
                        bill_sub = bill_sub[bill_sub["Session"].astype(str).str.strip() == str(session_val)]
                    sub_counts = (
                        bill_sub[bill_sub["Bill"].astype(str).isin(bill_list)]
                        .groupby("Subject")
                        .size()
                        .reset_index(name="Mentions")
                        .sort_values("Mentions", ascending=False)
                        .head(5)
                    )
                    policy_count = int(sub_counts["Subject"].nunique()) if not sub_counts.empty else 0
                    for row in sub_counts.to_dict("records"):
                        subject = _truncate_text(row.get("Subject", ""), 60)
                        mentions = int(row.get("Mentions", 0) or 0)
                        if subject:
                            top_subject_lines.append(f"{subject} ({mentions:,})")

                if top_bills_lines:
                    focus_section["bullets"].append(f"Top authored bills: {_join_top(top_bills_lines)}")
                if top_subject_lines:
                    focus_section["bullets"].append(f"Top policy areas: {_join_top(top_subject_lines)}")
                if policy_count:
                    focus_section["metrics"].append(("Policy areas", f"{policy_count:,}"))

                if not witness.empty:
                    pos_counts = _pos_counts_from_positions(witness)
                    focus_section["bullets"].append(
                        f"Witness positions - Against {pos_counts['Against']:,}, For {pos_counts['For']:,}, On {pos_counts['On']:,}."
                    )
                    if "LobbyShort" in witness.columns:
                        top_lobby = (
                            witness.groupby("LobbyShort")
                            .size()
                            .reset_index(name="Rows")
                            .sort_values("Rows", ascending=False)
                            .head(5)
                        )
                        top_lobby_lines = []
                        top_lobby_chart = []
                        for row in top_lobby.to_dict("records"):
                            short = str(row.get("LobbyShort", "")).strip()
                            rows = int(row.get("Rows", 0) or 0)
                            label = lobbyshort_to_name.get(short, short)
                            if label:
                                top_lobby_lines.append(f"{label} ({rows:,} rows)")
                                top_lobby_chart.append({"label": label, "value": rows})
                        if top_lobby_lines:
                            focus_section["bullets"].append(
                                f"Top lobbyists on witness lists: {_join_top(top_lobby_lines)}"
                            )
                        if top_lobby_chart:
                            focus_section["charts"].append(
                                {
                                    "kind": "bar",
                                    "orientation": "h",
                                    "title": "Top Lobbyists on Witness Lists",
                                    "caption": "Focus Chart. Lobbyists with the most witness-list rows",
                                    "data": top_lobby_chart,
                                }
                            )

                    if "IsTFL" in witness.columns:
                        counts = []
                        for funding_label, mask in [
                            ("Taxpayer Funded", witness["IsTFL"] == 1),
                            ("Private", witness["IsTFL"] != 1),
                        ]:
                            subset = witness[mask]
                            pos_counts = _pos_counts_from_positions(subset)
                            for position in ["Against", "For", "On"]:
                                counts.append(
                                    {
                                        "Position": position,
                                        "Funding": funding_label,
                                        "Count": int(pos_counts.get(position, 0)),
                                    }
                                )
                        if counts:
                            focus_section["charts"].append(
                                {
                                    "kind": "grouped_bar",
                                    "title": "Witness Positions by Funding Type",
                                    "caption": "Focus Chart. Witness positions by funding type",
                                    "data": counts,
                                }
                            )

                activities = build_member_activities(
                    la_food,
                    la_ent,
                    la_tran,
                    la_gift,
                    la_evnt,
                    la_awrd,
                    member_name=member_name,
                    session=str(session_val) if session_val is not None else None,
                    name_to_short=name_to_short,
                    filerid_to_short=filerid_to_short,
                    lobbyshort_to_name=lobbyshort_to_name,
                )
                if not activities.empty:
                    focus_section["metrics"].append(("Activity rows", f"{len(activities):,}"))
                    type_counts = _top_counts(activities.get("Type", pd.Series(dtype=object)), 4)
                    if type_counts:
                        types = ", ".join([f"{t} ({c:,})" for t, c in type_counts])
                        focus_section["bullets"].append(f"Top activity types: {types}")
                    amount_total = _amount_mid_sum(activities.get("Amount", pd.Series(dtype=object)))
                    if amount_total > 0:
                        focus_section["bullets"].append(f"Reported activity amount (midpoint): {fmt_usd(amount_total)}")
                    focus_section["charts"].append(
                        {
                            "kind": "bar",
                            "orientation": "h",
                            "title": "Activity Types (Rows)",
                            "caption": "Focus Chart. Activity types linked to the legislator",
                            "data": [{"label": t, "value": c} for t, c in type_counts],
                        }
                    )

                staff_matches = pd.DataFrame()
                if not staff_all.empty and "Legislator" in staff_all.columns:
                    staff_df = staff_all
                    leg_norm = norm_name_series(staff_df["Legislator"])
                    leg_last_norm = last_name_norm_series(staff_df["Legislator"])
                    leg_init_key = staff_df["Legislator"].fillna("").astype(str).map(_last_first_initial_key)

                    match = pd.Series(False, index=staff_df.index)
                    last_norm = member_info.get("last_norm", "")
                    if last_norm:
                        match = leg_last_norm == last_norm
                        if member_info.get("initial_key"):
                            match = match & (leg_init_key == member_info["initial_key"])

                    full_norm = member_info.get("full_norm", "")
                    if full_norm:
                        match = match | leg_norm.str.contains(full_norm, na=False)

                    staff_matches = staff_df[match]

                if not staff_matches.empty:
                    focus_section["metrics"].append(("Staff history rows", f"{len(staff_matches):,}"))
                    staffer_count = int(staff_matches.get("Staffer", pd.Series(dtype=object)).nunique()) if "Staffer" in staff_matches.columns else 0
                    if staffer_count:
                        focus_section["metrics"].append(("Staffers", f"{staffer_count:,}"))
                    top_staffers = _top_counts(staff_matches.get("Staffer", pd.Series(dtype=object)), 5)
                    if top_staffers:
                        staffer_list = ", ".join([f"{s} ({c:,})" for s, c in top_staffers])
                        focus_section["bullets"].append(f"Top staffers in history: {staffer_list}")

                staff_lobbyists = pd.DataFrame()
                if not staff_matches.empty and "Staffer" in staff_matches.columns:
                    tmp_short = Lobby_TFL_Client_All[["LobbyShort"]].dropna()
                    tmp_short["InitialKey"] = tmp_short["LobbyShort"].map(_last_first_initial_key)
                    init_counts = (
                        tmp_short.groupby(["InitialKey", "LobbyShort"])
                        .size()
                        .reset_index(name="n")
                        .sort_values(["InitialKey", "n"], ascending=[True, False])
                        .drop_duplicates("InitialKey")
                    )
                    initial_to_short = dict(zip(init_counts["InitialKey"], init_counts["LobbyShort"]))

                    def map_staffer(name: str) -> str:
                        if not name:
                            return ""
                        for v in norm_person_variants(name):
                            if v in name_to_short:
                                return str(name_to_short[v])
                        init_key = _last_first_initial_key(name)
                        if init_key and init_key in initial_to_short:
                            return str(initial_to_short[init_key])
                        return ""

                    staff_lobbyists = staff_matches
                    staff_lobbyists["LobbyShort"] = staff_lobbyists["Staffer"].fillna("").astype(str).map(map_staffer)
                    staff_lobbyists = staff_lobbyists[staff_lobbyists["LobbyShort"].astype(str).str.strip() != ""]
                    if not staff_lobbyists.empty:
                        focus_section["metrics"].append(
                            ("Staffers who became lobbyists", f"{staff_lobbyists['Staffer'].nunique():,}")
                        )
                        staff_lobbyists["Lobbyist"] = staff_lobbyists["LobbyShort"].map(lobbyshort_to_name).fillna(staff_lobbyists["LobbyShort"])
                        top_lobbyists = _top_counts(staff_lobbyists.get("Lobbyist", pd.Series(dtype=object)), 5)
                        if top_lobbyists:
                            lobbyist_list = ", ".join([f"{l} ({c:,})" for l, c in top_lobbyists])
                            focus_section["bullets"].append(f"Staff-to-lobbyist matches: {lobbyist_list}")

                chart_data = [
                    {"label": "Bills authored", "value": bill_count},
                    {"label": "Bills with witness activity", "value": any_witness},
                    {"label": "Bills opposed by TFL lobbyists", "value": tfl_opposed},
                ]
                focus_section["charts"].append(
                    {
                        "kind": "bar",
                        "orientation": "v",
                        "title": "Legislator Focus Metrics",
                        "caption": "Focus Chart. Legislator summary metrics",
                        "data": chart_data,
                    }
                )

    if focus_type == "bill":
        bill_id = str(fc.get("bill", "")).strip()
        if bill_id:
            bill_norm = bill_id
            try:
                bill_norm = normalize_bill(bill_id) or bill_id
            except Exception:
                bill_norm = bill_id
            bill_id = bill_norm
            focus_section = {"title": f"Bill - {bill_id}", "summary": "", "metrics": [], "bullets": [], "charts": []}
            bs = Bill_Status_All if isinstance(Bill_Status_All, pd.DataFrame) else pd.DataFrame()
            caption = ""
            status = ""
            author = ""
            if not bs.empty and "Bill" in bs.columns:
                bs = bs.copy()
                if session_val is not None and "Session" in bs.columns:
                    bs = bs[bs["Session"].astype(str).str.strip() == str(session_val)]
                try:
                    bs["BillNorm"] = bs["Bill"].astype(str).map(normalize_bill)
                except Exception:
                    bs["BillNorm"] = bs["Bill"].astype(str).str.strip()
                bs_match = bs[bs["BillNorm"] == bill_id]
                if not bs_match.empty:
                    caption = str(bs_match.get("Caption", pd.Series([""])).iloc[0]).strip()
                    status = str(bs_match.get("Status", pd.Series([""])).iloc[0]).strip()
                    for col in ["Author", "Authors"]:
                        if col in bs_match.columns:
                            author = str(bs_match.get(col, pd.Series([""])).iloc[0]).strip()
                            if author:
                                break

            wit = Wit_All if isinstance(Wit_All, pd.DataFrame) else pd.DataFrame()
            pos = pd.DataFrame()
            if not wit.empty and "Bill" in wit.columns:
                wit = wit.copy()
                if session_val is not None and "Session" in wit.columns:
                    wit = wit[wit["Session"].astype(str).str.strip() == str(session_val)]
                try:
                    wit["Bill"] = wit["Bill"].astype(str).map(normalize_bill)
                except Exception:
                    wit["Bill"] = wit["Bill"].astype(str).str.strip()
                wit = wit[wit["Bill"] == bill_id]
                if not wit.empty:
                    pos = bill_position_from_flags(wit)
                    if not pos.empty:
                        pos = pos.merge(tfl_flag, on="LobbyShort", how="left")
                        pos["IsTFL"] = pd.to_numeric(pos.get("IsTFL", 0), errors="coerce").fillna(0).astype(int)

            unique_lobbyists = int(pos["LobbyShort"].nunique()) if not pos.empty else 0
            org_series = wit.get("org", pd.Series(dtype=object)) if isinstance(wit, pd.DataFrame) else pd.Series(dtype=object)
            org_counts = _top_counts(org_series, 5)
            unique_orgs = int(org_series.dropna().astype(str).str.strip().nunique()) if not org_series.empty else 0

            witness_rows = int(len(wit)) if isinstance(wit, pd.DataFrame) else 0
            tfl_opposed = 0
            top_lobbyist_lines = []
            subject_lines = []
            tfl_witness_rows = 0
            private_witness_rows = 0
            if not pos.empty:
                against_mask = pos["Position"].astype(str).str.contains("Against", case=False, na=False)
                tfl_mask = pos["IsTFL"] == 1
                tfl_opposed = int(pos.loc[against_mask & tfl_mask, "LobbyShort"].nunique())
                tfl_witness_rows = int(pos.loc[tfl_mask, "LobbyShort"].nunique())
                private_witness_rows = int(pos.loc[~tfl_mask, "LobbyShort"].nunique())

                if "LobbyShort" in pos.columns:
                    name_map = {}
                    lt = Lobby_TFL_Client_All if isinstance(Lobby_TFL_Client_All, pd.DataFrame) else pd.DataFrame()
                    if not lt.empty and {"LobbyShort", "Lobby Name"}.issubset(lt.columns):
                        tmp = lt[["LobbyShort", "Lobby Name"]].dropna()
                        tmp["LobbyShort"] = tmp["LobbyShort"].astype(str).str.strip()
                        tmp["Lobby Name"] = tmp["Lobby Name"].astype(str).str.strip()
                        name_map = (
                            tmp.groupby("LobbyShort")["Lobby Name"]
                            .first()
                            .to_dict()
                        )

                    counts = (
                        pos.groupby("LobbyShort")
                        .size()
                        .reset_index(name="Rows")
                        .sort_values("Rows", ascending=False)
                        .head(5)
                    )
                    for row in counts.to_dict("records"):
                        short = str(row.get("LobbyShort", "")).strip()
                        rows = int(row.get("Rows", 0) or 0)
                        name = name_map.get(short, "")
                        label = f"{short}"
                        if name:
                            label = f"{name} ({short})"
                        top_lobbyist_lines.append(f"{label} ({rows:,} rows)")

            focus_section["summary"] = (
                f"{bill_id} has {witness_rows:,} witness-list rows in the selected session."
            )
            focus_section["metrics"] = [
                ("Bill", bill_id),
                ("Status", status or "Unknown"),
                ("Witness rows", f"{witness_rows:,}"),
                ("Unique lobbyists", f"{unique_lobbyists:,}"),
                ("TFL lobbyists opposed", f"{tfl_opposed:,}"),
                ("TFL lobbyists (any position)", f"{tfl_witness_rows:,}"),
                ("Private lobbyists (any position)", f"{private_witness_rows:,}"),
            ]
            if unique_orgs:
                focus_section["metrics"].append(("Organizations", f"{unique_orgs:,}"))
            if caption:
                focus_section["bullets"].append(f"Caption: {caption}")
            if author:
                focus_section["bullets"].append(f"Author: {author}")

            if top_lobbyist_lines:
                focus_section["bullets"].append(
                    f"Top lobbyists by witness rows: {_join_top(top_lobbyist_lines)}"
                )
            if org_counts:
                org_lines = [f"{_truncate_text(n, 60)} ({c:,})" for n, c in org_counts]
                focus_section["bullets"].append(
                    f"Top organizations on witness lists: {_join_top(org_lines)}"
                )
                focus_section["charts"].append(
                    {
                        "kind": "bar",
                        "orientation": "h",
                        "title": "Top Witness Organizations",
                        "caption": "Focus Chart. Organizations with the most witness-list rows",
                        "data": [{"label": n, "value": c} for n, c in org_counts],
                    }
                )

            bill_sub = Bill_Sub_All if isinstance(Bill_Sub_All, pd.DataFrame) else pd.DataFrame()
            if not bill_sub.empty and {"Bill", "Subject"}.issubset(bill_sub.columns):
                if session_val is not None and "Session" in bill_sub.columns:
                    bill_sub = bill_sub[bill_sub["Session"].astype(str).str.strip() == str(session_val)]
                bill_sub = bill_sub.copy()
                bill_sub["BillNorm"] = bill_sub["Bill"].astype(str).map(normalize_bill)
                sub_rows = bill_sub[bill_sub["BillNorm"] == bill_id]
                if not sub_rows.empty:
                    subjects = sub_rows["Subject"].dropna().astype(str).str.strip().unique().tolist()
                    for subject in subjects[:6]:
                        subject_lines.append(_truncate_text(subject, 70))
            if subject_lines:
                focus_section["bullets"].append(f"Subjects: {_join_top(subject_lines)}")

            if not pos.empty:
                counts = []
                for funding_label, mask in [
                    ("Taxpayer Funded", pos["IsTFL"] == 1),
                    ("Private", pos["IsTFL"] != 1),
                ]:
                    subset = pos[mask]
                    pos_counts = _pos_counts_from_positions(subset)
                    for position in ["Against", "For", "On"]:
                        counts.append(
                            {
                                "Position": position,
                                "Funding": funding_label,
                                "Count": int(pos_counts.get(position, 0)),
                            }
                        )
                focus_section["charts"].append(
                    {
                        "kind": "grouped_bar",
                        "title": "Witness Positions by Funding Type",
                        "caption": "Focus Chart. Witness positions by funding type",
                        "data": counts,
                    }
                )

    tfl_mid = (tfl_low + tfl_high) / 2
    private_mid = (private_low + private_high) / 2
    total_mid = tfl_mid + private_mid
    tfl_mid_share_pct = (tfl_mid / total_mid * 100) if total_mid > 0 else 0.0

    if total_mid <= 0:
        conditional_share_sentence = (
            "No reportable lobbying compensation was identified for the selected scope."
        )
        conditional_balance_sentence = ""
    else:
        if tfl_mid_share_pct >= 50:
            conditional_share_sentence = (
                "Midpoint estimates indicate taxpayer-funded entities represent a majority share "
                "of reported lobbying compensation in this scope."
            )
        elif tfl_mid_share_pct >= 35:
            conditional_share_sentence = (
                "Midpoint estimates indicate taxpayer-funded entities represent a substantial "
                "share of reported lobbying compensation in this scope."
            )
        elif tfl_mid_share_pct >= 15:
            conditional_share_sentence = (
                "Midpoint estimates indicate taxpayer-funded entities represent a material, "
                "non-trivial share of reported lobbying compensation in this scope."
            )
        else:
            conditional_share_sentence = (
                "Midpoint estimates indicate taxpayer-funded entities represent a smaller share "
                "of reported lobbying compensation in this scope."
            )

        mix_delta = tfl_mid - private_mid
        if abs(mix_delta) <= (0.10 * total_mid):
            conditional_balance_sentence = (
                "The midpoint funding mix is near parity between taxpayer-funded and private activity."
            )
        elif mix_delta > 0:
            conditional_balance_sentence = (
                "The midpoint funding mix shows taxpayer-funded activity outweighing private activity."
            )
        else:
            conditional_balance_sentence = (
                "The midpoint funding mix shows private activity outweighing taxpayer-funded activity."
            )

    tfl_w = witness_counts.get("tfl", {}) if isinstance(witness_counts, dict) else {}
    pri_w = witness_counts.get("private", {}) if isinstance(witness_counts, dict) else {}
    tfl_against = int(tfl_w.get("Against", 0) or 0)
    tfl_for = int(tfl_w.get("For", 0) or 0)
    tfl_on = int(tfl_w.get("On", 0) or 0)
    pri_against = int(pri_w.get("Against", 0) or 0)
    pri_for = int(pri_w.get("For", 0) or 0)
    pri_on = int(pri_w.get("On", 0) or 0)
    witness_total = tfl_against + tfl_for + tfl_on + pri_against + pri_for + pri_on
    if witness_total <= 0:
        conditional_witness_sentence = (
            "No witness-position activity was available in the selected scope/session."
        )
    else:
        if tfl_against >= max(tfl_for, tfl_on):
            stance_text = "taxpayer-funded testimony skews toward opposition"
        elif tfl_for >= max(tfl_against, tfl_on):
            stance_text = "taxpayer-funded testimony skews toward support"
        else:
            stance_text = "taxpayer-funded testimony is mixed across positions"
        conditional_witness_sentence = (
            f"In witness data, {stance_text} "
            f"({tfl_against:,} Against, {tfl_for:,} For, {tfl_on:,} On)."
        )

    if focus_type == "client":
        conditional_focus_sentence = (
            "Focus findings are client-centered and update as the selected client changes."
        )
        focus_highlights_intro = (
            "Key client-specific findings generated from the current scope and linked lobbyist activity."
        )
    elif focus_type == "lobbyist":
        conditional_focus_sentence = (
            "Focus findings are lobbyist-centered and update as the selected lobbyist changes."
        )
        focus_highlights_intro = (
            "Key lobbyist-specific findings generated from the current scope and linked client activity."
        )
    elif focus_type == "legislator":
        conditional_focus_sentence = (
            "Focus findings are legislator-centered and update as the selected legislator changes."
        )
        focus_highlights_intro = (
            "Key legislator-specific findings generated from authored-bill, witness, and activity data."
        )
    elif focus_type == "bill":
        conditional_focus_sentence = (
            "Focus findings are bill-centered and update as the selected bill changes."
        )
        focus_highlights_intro = (
            "Key bill-specific findings generated from witness, status, and subject-matter records."
        )
    else:
        conditional_focus_sentence = (
            "Focus findings are generated from the current filters and update as inputs change."
        )
        focus_highlights_intro = "Most relevant findings for the selected focus."

    conditional_exec_sentences = [
        s
        for s in [
            conditional_share_sentence,
            conditional_balance_sentence,
            conditional_witness_sentence,
        ]
        if str(s).strip()
    ]

    payload = {
        "session_label": session_label,
        "generated_date": generated_date,
        "generated_ts": generated_ts,
        "report_id": report_id,
        "scope_label": scope_label,
        "focus_label": focus_label,
        "filter_summary": filter_summary,
        "selected_lobbyist": selected_lobbyist,
        "total_low_value": total_low,
        "total_high_value": total_high,
        "tfl_low_value": tfl_low,
        "tfl_high_value": tfl_high,
        "private_low_value": private_low,
        "private_high_value": private_high,
        "total_low": fmt_usd(total_low),
        "total_high": fmt_usd(total_high),
        "tfl_low": fmt_usd(tfl_low),
        "tfl_high": fmt_usd(tfl_high),
        "private_low": fmt_usd(private_low),
        "private_high": fmt_usd(private_high),
        "tfl_share_low_pct": f"{tfl_share_low_pct:.1f}",
        "tfl_share_high_pct": f"{tfl_share_high_pct:.1f}",
        "tfl_share_low_pct_value": tfl_share_low_pct,
        "tfl_share_high_pct_value": tfl_share_high_pct,
        "private_share_low_pct_value": private_share_low_pct,
        "private_share_high_pct_value": private_share_high_pct,
        "funding_mix": funding_mix,
        "unique_lobbyists_total": f"{unique_lobbyists_total:,}",
        "unique_lobbyists_tfl": f"{unique_lobbyists_tfl:,}",
        "unique_clients_total": f"{unique_clients_total:,}",
        "unique_clients_tfl": f"{unique_clients_tfl:,}",
        "top_clients_tfl": top_clients_tfl,
        "top_clients_private": top_clients_private,
        "chart_compensation_bar": chart_compensation_bar,
        "chart_share": chart_share,
        "chart_entity_types": chart_entity_types,
        "chart_entity_types_data": entity_type_counts,
        "witness_activity_summary": witness_summary,
        "chart_witness_positions": chart_witness_positions,
        "witness_counts": witness_counts,
        "chart_top_bills": chart_top_bills,
        "chart_top_subjects": chart_top_subjects,
        "existing_law_gap_summary": existing_law_gap_summary,
        "recommended_fix_statute": recommended_fix_statute,
        "implementation_notes": implementation_notes,
        "data_sources_bullets": data_sources_bullets,
        "disclaimer_note": disclaimer_note,
        "report_title": report_title,
        "scope_session_label": scope_session_label,
        "scope_note": scope_note,
        "has_top_bills": bool(top_bills),
        "has_top_subjects": bool(top_subjects),
        "top_bills": top_bills,
        "top_subjects": top_subjects,
        "focus_section": focus_section,
        "conditional_exec_sentences": conditional_exec_sentences,
        "conditional_focus_sentence": conditional_focus_sentence,
        "focus_highlights_intro": focus_highlights_intro,
        "tfl_mid_share_pct_value": tfl_mid_share_pct,
    }

    for i in range(5):
        if i < len(top_bills):
            b = top_bills[i]
            payload[f"bill_{i + 1}_id"] = b["id"]
            payload[f"bill_{i + 1}_caption"] = b["caption"]
            payload[f"bill_{i + 1}_opp_count"] = f"{b['tfl']:,}"
            payload[f"bill_{i + 1}_private_opp"] = f"{b['private']:,}"
            payload[f"bill_{i + 1}_summary"] = b["summary"]
        else:
            payload[f"bill_{i + 1}_id"] = "-"
            payload[f"bill_{i + 1}_caption"] = "-"
            payload[f"bill_{i + 1}_opp_count"] = "0"
            payload[f"bill_{i + 1}_private_opp"] = "0"
            payload[f"bill_{i + 1}_summary"] = "No summary available."

    for i in range(5):
        if i < len(top_subjects):
            s = top_subjects[i]
            payload[f"subject_{i + 1}"] = s["Subject"]
            payload[f"subject_{i + 1}_opp_count"] = f"{int(s['Oppositions']):,}"
        else:
            payload[f"subject_{i + 1}"] = "-"
            payload[f"subject_{i + 1}_opp_count"] = "0"

    return payload

def _build_report_pdf_bytes(payload: dict) -> bytes:
    payload = dict(payload) if isinstance(payload, dict) else {}

    def _safe_str(value, default: str = "") -> str:
        if value is None:
            return default
        try:
            return str(value)
        except Exception:
            return default

    def _safe_float(value, default: float = 0.0) -> float:
        if value is None:
            return default
        try:
            if isinstance(value, str):
                txt = value.strip().replace(",", "")
                if txt == "":
                    return default
                return float(txt)
            return float(value)
        except Exception:
            return default

    def _safe_bool(value, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return bool(value)
        txt = _safe_str(value).strip().lower()
        if txt in {"true", "1", "yes", "y"}:
            return True
        if txt in {"false", "0", "no", "n"}:
            return False
        return default

    def _safe_list(value) -> list:
        return value if isinstance(value, list) else []

    def _safe_dict(value) -> dict:
        return value if isinstance(value, dict) else {}

    default_payload = {
        "report_title": "Lobby Look-Up Report",
        "session_label": "Selected Session",
        "scope_label": "Selected Session",
        "scope_session_label": "Selected Session",
        "focus_label": "All",
        "generated_date": datetime.now().strftime("%B %d, %Y"),
        "generated_ts": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_low": "$0",
        "total_high": "$0",
        "tfl_low": "$0",
        "tfl_high": "$0",
        "private_low": "$0",
        "private_high": "$0",
        "tfl_share_low_pct": "0.0",
        "tfl_share_high_pct": "0.0",
        "unique_lobbyists_total": "0",
        "unique_lobbyists_tfl": "0",
        "unique_clients_total": "0",
        "unique_clients_tfl": "0",
        "witness_activity_summary": "No witness-list data available for this scope/session.",
        "existing_law_gap_summary": "",
        "recommended_fix_statute": "",
        "implementation_notes": "",
        "data_sources_bullets": "",
        "disclaimer_note": "",
        "scope_note": "",
        "focus_section": {},
        "witness_counts": {},
        "top_bills": [],
        "top_subjects": [],
        "chart_entity_types_data": [],
        "conditional_exec_sentences": [],
        "conditional_focus_sentence": "",
        "focus_highlights_intro": "",
        "focus_snapshot_paragraph": "",
        "has_top_bills": False,
        "has_top_subjects": False,
    }
    for key, value in default_payload.items():
        payload.setdefault(key, value)

    numeric_defaults = {
        "total_low_value": 0.0,
        "total_high_value": 0.0,
        "tfl_low_value": 0.0,
        "tfl_high_value": 0.0,
        "private_low_value": 0.0,
        "private_high_value": 0.0,
        "tfl_share_low_pct_value": 0.0,
        "tfl_share_high_pct_value": 0.0,
        "private_share_low_pct_value": 0.0,
        "private_share_high_pct_value": 0.0,
        "tfl_mid_share_pct_value": 0.0,
    }
    for key, fallback in numeric_defaults.items():
        payload[key] = _safe_float(payload.get(key), fallback)

    string_keys = [
        "report_title",
        "session_label",
        "scope_label",
        "scope_session_label",
        "focus_label",
        "generated_date",
        "generated_ts",
        "total_low",
        "total_high",
        "tfl_low",
        "tfl_high",
        "private_low",
        "private_high",
        "tfl_share_low_pct",
        "tfl_share_high_pct",
        "unique_lobbyists_total",
        "unique_lobbyists_tfl",
        "unique_clients_total",
        "unique_clients_tfl",
        "witness_activity_summary",
        "existing_law_gap_summary",
        "recommended_fix_statute",
        "implementation_notes",
        "data_sources_bullets",
        "disclaimer_note",
        "scope_note",
        "conditional_focus_sentence",
        "focus_highlights_intro",
        "focus_snapshot_paragraph",
    ]
    for key in string_keys:
        payload[key] = _safe_str(payload.get(key), _safe_str(default_payload.get(key, "")))

    payload["focus_section"] = _safe_dict(payload.get("focus_section"))
    payload["witness_counts"] = _safe_dict(payload.get("witness_counts"))
    payload["top_bills"] = [b for b in _safe_list(payload.get("top_bills")) if isinstance(b, dict)]
    payload["top_subjects"] = [s for s in _safe_list(payload.get("top_subjects")) if isinstance(s, dict)]
    payload["chart_entity_types_data"] = [
        r for r in _safe_list(payload.get("chart_entity_types_data")) if isinstance(r, dict)
    ]
    payload["conditional_exec_sentences"] = [
        _safe_str(s).strip()
        for s in _safe_list(payload.get("conditional_exec_sentences"))
        if _safe_str(s).strip()
    ]
    payload["has_top_bills"] = _safe_bool(payload.get("has_top_bills"), False) or bool(payload["top_bills"])
    payload["has_top_subjects"] = _safe_bool(payload.get("has_top_subjects"), False) or bool(payload["top_subjects"])

    if payload["focus_section"]:
        fs = payload["focus_section"]
        fs["title"] = _safe_str(fs.get("title", ""))
        fs["summary"] = _safe_str(fs.get("summary", ""))

        metrics_safe = []
        for item in _safe_list(fs.get("metrics")):
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                metrics_safe.append((_safe_str(item[0]), _safe_str(item[1])))
        fs["metrics"] = metrics_safe

        fs["bullets"] = [
            _safe_str(item).strip()
            for item in _safe_list(fs.get("bullets"))
            if _safe_str(item).strip()
        ]
        fs["charts"] = _safe_list(fs.get("charts"))
        payload["focus_section"] = fs

    if not _safe_str(payload.get("total_low")).strip():
        payload["total_low"] = fmt_usd(payload["total_low_value"])
    if not _safe_str(payload.get("total_high")).strip():
        payload["total_high"] = fmt_usd(payload["total_high_value"])
    if not _safe_str(payload.get("tfl_low")).strip():
        payload["tfl_low"] = fmt_usd(payload["tfl_low_value"])
    if not _safe_str(payload.get("tfl_high")).strip():
        payload["tfl_high"] = fmt_usd(payload["tfl_high_value"])
    if not _safe_str(payload.get("private_low")).strip():
        payload["private_low"] = fmt_usd(payload["private_low_value"])
    if not _safe_str(payload.get("private_high")).strip():
        payload["private_high"] = fmt_usd(payload["private_high_value"])

    if payload["tfl_share_low_pct_value"] == 0.0 and payload["tfl_share_high_pct_value"] == 0.0:
        share_low, share_high = _calc_share_range(
            payload["tfl_low_value"],
            payload["tfl_high_value"],
            payload["total_low_value"],
            payload["total_high_value"],
        )
        payload["tfl_share_low_pct_value"] = share_low
        payload["tfl_share_high_pct_value"] = share_high
    if not _safe_str(payload.get("tfl_share_low_pct")).strip():
        payload["tfl_share_low_pct"] = f"{payload['tfl_share_low_pct_value']:.1f}"
    if not _safe_str(payload.get("tfl_share_high_pct")).strip():
        payload["tfl_share_high_pct"] = f"{payload['tfl_share_high_pct_value']:.1f}"

    top_bills_safe = []
    for bill in payload["top_bills"]:
        top_bills_safe.append(
            {
                "id": _safe_str(bill.get("id"), "-").strip() or "-",
                "tfl": int(_safe_float(bill.get("tfl"), 0.0)),
                "private": int(_safe_float(bill.get("private"), 0.0)),
                "caption": _safe_str(bill.get("caption"), "").strip(),
                "summary": _safe_str(bill.get("summary"), "").strip(),
            }
        )
    payload["top_bills"] = top_bills_safe

    top_subjects_safe = []
    for subject in payload["top_subjects"]:
        top_subjects_safe.append(
            {
                "Subject": _safe_str(subject.get("Subject"), "").strip(),
                "Oppositions": int(_safe_float(subject.get("Oppositions"), 0.0)),
            }
        )
    payload["top_subjects"] = top_subjects_safe

    entity_rows_safe = []
    for row in payload["chart_entity_types_data"]:
        label = _safe_str(row.get("type"), "").strip()
        if not label:
            continue
        entity_rows_safe.append({"type": label, "count": int(_safe_float(row.get("count"), 0.0))})
    payload["chart_entity_types_data"] = entity_rows_safe

    witness_counts_safe = _safe_dict(payload.get("witness_counts"))
    witness_counts_safe["tfl"] = _safe_dict(witness_counts_safe.get("tfl"))
    witness_counts_safe["private"] = _safe_dict(witness_counts_safe.get("private"))
    for bucket in ("tfl", "private"):
        for position in ("Against", "For", "On"):
            witness_counts_safe[bucket][position] = int(
                _safe_float(witness_counts_safe[bucket].get(position), 0.0)
            )
    payload["witness_counts"] = witness_counts_safe

    def _derive_exec_conditionals() -> list[str]:
        total_mid = (payload["total_low_value"] + payload["total_high_value"]) / 2.0
        tfl_mid = (payload["tfl_low_value"] + payload["tfl_high_value"]) / 2.0
        private_mid = (payload["private_low_value"] + payload["private_high_value"]) / 2.0
        out = []

        if total_mid <= 0:
            out.append("No reportable lobbying compensation was identified for the selected scope.")
        else:
            tfl_mid_pct = (tfl_mid / total_mid) * 100.0
            if tfl_mid_pct >= 50:
                out.append(
                    "Midpoint estimates indicate taxpayer-funded entities represent a majority share of reported lobbying compensation in this scope."
                )
            elif tfl_mid_pct >= 35:
                out.append(
                    "Midpoint estimates indicate taxpayer-funded entities represent a substantial share of reported lobbying compensation in this scope."
                )
            elif tfl_mid_pct >= 15:
                out.append(
                    "Midpoint estimates indicate taxpayer-funded entities represent a material, non-trivial share of reported lobbying compensation in this scope."
                )
            else:
                out.append(
                    "Midpoint estimates indicate taxpayer-funded entities represent a smaller share of reported lobbying compensation in this scope."
                )

            delta = tfl_mid - private_mid
            if abs(delta) <= (0.10 * total_mid):
                out.append("The midpoint funding mix is near parity between taxpayer-funded and private activity.")
            elif delta > 0:
                out.append("The midpoint funding mix shows taxpayer-funded activity outweighing private activity.")
            else:
                out.append("The midpoint funding mix shows private activity outweighing taxpayer-funded activity.")

        tfl_counts = payload["witness_counts"].get("tfl", {})
        tfl_against = int(tfl_counts.get("Against", 0))
        tfl_for = int(tfl_counts.get("For", 0))
        tfl_on = int(tfl_counts.get("On", 0))
        if (tfl_against + tfl_for + tfl_on) <= 0:
            out.append("No witness-position activity was available in the selected scope/session.")
        else:
            if tfl_against >= max(tfl_for, tfl_on):
                stance = "taxpayer-funded testimony skews toward opposition"
            elif tfl_for >= max(tfl_against, tfl_on):
                stance = "taxpayer-funded testimony skews toward support"
            else:
                stance = "taxpayer-funded testimony is mixed across positions"
            out.append(
                f"In witness data, {stance} ({tfl_against:,} Against, {tfl_for:,} For, {tfl_on:,} On)."
            )
        return [s for s in out if _safe_str(s).strip()]

    def _derive_focus_context_sentence() -> tuple[str, str]:
        focus_label_txt = _safe_str(payload.get("focus_label")).strip().lower()
        focus_title_txt = _safe_str(payload.get("focus_section", {}).get("title", "")).strip().lower()
        focus_hint = f"{focus_label_txt} {focus_title_txt}".strip()

        if "client" in focus_hint:
            return (
                "This snapshot is client-centered and updates with the selected client and filters.",
                "Client-specific indicators drawn from linked lobbying activity and session-scoped records.",
            )
        if "lobbyist" in focus_hint:
            return (
                "This snapshot is lobbyist-centered and updates with the selected lobbyist and filters.",
                "Lobbyist-specific indicators drawn from linked client relationships and session activity.",
            )
        if "legislator" in focus_hint:
            return (
                "This snapshot is legislator-centered and updates with the selected legislator and filters.",
                "Legislator-specific indicators drawn from authored bills, witness behavior, and related activity.",
            )
        if "bill" in focus_hint:
            return (
                "This snapshot is bill-centered and updates with the selected bill and filters.",
                "Bill-specific indicators drawn from witness records, status history, and subject patterns.",
            )
        return (
            "This snapshot updates from the current filters and focus selection.",
            "Most relevant findings generated for the selected focus.",
        )

    computed_exec_conditionals = _derive_exec_conditionals()
    combined_exec_conditionals = []
    for sentence in payload["conditional_exec_sentences"] + computed_exec_conditionals:
        clean_sentence = _safe_str(sentence).strip()
        if clean_sentence and clean_sentence not in combined_exec_conditionals:
            combined_exec_conditionals.append(clean_sentence)
    payload["conditional_exec_sentences"] = combined_exec_conditionals

    default_focus_sentence, default_focus_intro = _derive_focus_context_sentence()
    if not _safe_str(payload.get("conditional_focus_sentence")).strip():
        payload["conditional_focus_sentence"] = default_focus_sentence
    if not _safe_str(payload.get("focus_highlights_intro")).strip():
        payload["focus_highlights_intro"] = default_focus_intro

    def _derive_focus_snapshot_paragraph() -> str:
        focus_section_local = _safe_dict(payload.get("focus_section"))
        focus_title = _safe_str(focus_section_local.get("title", "")).strip()
        focus_label = _safe_str(payload.get("focus_label"), "This focus").strip() or "This focus"
        focus_subject = focus_title or focus_label
        focus_hint = f"{focus_label.lower()} {focus_title.lower()}".strip()

        if "client" in focus_hint:
            focus_type = "client"
        elif "lobbyist" in focus_hint:
            focus_type = "lobbyist"
        elif "legislator" in focus_hint:
            focus_type = "legislator"
        elif "bill" in focus_hint:
            focus_type = "bill"
        else:
            focus_type = "general"

        metric_map = {}
        for metric in _safe_list(focus_section_local.get("metrics")):
            if not isinstance(metric, (list, tuple)) or len(metric) < 2:
                continue
            label = " ".join(_safe_str(metric[0]).strip().lower().split())
            if label:
                metric_map[label] = _safe_str(metric[1]).strip()

        def _extract_numbers(value) -> list[float]:
            txt = _safe_str(value).replace(",", "").strip()
            if not txt:
                return []
            cleaned = "".join(ch if (ch.isdigit() or ch in ".-") else " " for ch in txt)
            out = []
            for token in cleaned.split():
                try:
                    out.append(float(token))
                except Exception:
                    continue
            return out

        def _first_number(value) -> float:
            nums = _extract_numbers(value)
            return nums[0] if nums else 0.0

        def _range_midpoint(value) -> float:
            nums = _extract_numbers(value)
            if not nums:
                return 0.0
            if len(nums) == 1:
                return nums[0]
            return (nums[0] + nums[1]) / 2.0

        def _metric_value(*labels: str) -> str:
            for label in labels:
                key = " ".join(_safe_str(label).strip().lower().split())
                if key and key in metric_map:
                    val = _safe_str(metric_map.get(key, "")).strip()
                    if val:
                        return val
            return ""

        def _metric_int(*labels: str) -> int:
            val = _metric_value(*labels)
            if not val:
                return 0
            return int(_first_number(val))

        def _first_int_after_keyword(text: str, keyword: str) -> int | None:
            text_norm = _safe_str(text)
            key_norm = _safe_str(keyword).strip().lower()
            idx = text_norm.lower().find(key_norm)
            if idx < 0:
                return None
            tail = text_norm[idx + len(key_norm):]
            cleaned = "".join(ch if ch.isdigit() else " " for ch in tail)
            tokens = [tok for tok in cleaned.split() if tok]
            if not tokens:
                return None
            try:
                return int(tokens[0])
            except Exception:
                return None

        def _sentence_case(text: str) -> str:
            t = _safe_str(text).strip()
            if not t:
                return ""
            return t[0].upper() + t[1:]

        parts = []
        signals_used = 0
        focus_specific_signals = 0

        if focus_type == "client":
            parts.append(f"{focus_subject} functions as a client-centered hub in the advocacy network for this scope.")
        elif focus_type == "lobbyist":
            parts.append(f"{focus_subject} functions as a lobbyist-centered conduit between client portfolios and legislative influence.")
        elif focus_type == "legislator":
            parts.append(f"{focus_subject} is evaluated through authored-bill outcomes and observed witness pressure patterns.")
        elif focus_type == "bill":
            parts.append(f"{focus_subject} functions as a bill-level pressure point where support and opposition activity converge.")
        else:
            parts.append(f"{focus_subject} reflects a concentrated set of relationships in the selected scope.")

        focus_clients_total = 0
        focus_clients_tfl = 0
        client_scope = "none"
        if focus_type == "client":
            # Client focus represents a single selected client; infer TFL status from client metrics.
            focus_clients_total = 1
            client_tfl_flag = _metric_value("taxpayer funded")
            normalized_flag = client_tfl_flag.strip().lower() if client_tfl_flag else ""
            if normalized_flag in {"yes", "true", "1"}:
                focus_clients_tfl = 1
                client_scope = "focus"
            elif normalized_flag in {"no", "false", "0"}:
                focus_clients_tfl = 0
                client_scope = "focus"
            else:
                # If classification is unavailable, suppress this ratio sentence for client focus.
                focus_clients_total = 0
                focus_clients_tfl = 0
        elif focus_type == "lobbyist":
            focus_clients_total = _metric_int("total clients")
            focus_clients_tfl = _metric_int("taxpayer-funded clients", "taxpayer funded clients")
            private_clients = _metric_int("private clients")
            if focus_clients_total <= 0 and (focus_clients_tfl + private_clients) > 0:
                focus_clients_total = focus_clients_tfl + private_clients
            if focus_clients_total <= 0:
                focus_clients_total = int(_safe_float(payload.get("focus_clients_total"), 0.0))
            if focus_clients_tfl <= 0:
                focus_clients_tfl = int(_safe_float(payload.get("focus_clients_tfl"), 0.0))
            if focus_clients_total > 0:
                client_scope = "focus"
        elif focus_type == "general":
            focus_clients_total = int(_safe_float(payload.get("focus_clients_total"), 0.0))
            focus_clients_tfl = int(_safe_float(payload.get("focus_clients_tfl"), 0.0))
            if focus_clients_total > 0:
                client_scope = "focus"
            else:
                focus_clients_total = int(_safe_float(payload.get("unique_clients_total"), 0.0))
                focus_clients_tfl = int(_safe_float(payload.get("unique_clients_tfl"), 0.0))
                if focus_clients_total > 0:
                    client_scope = "scope"

        if focus_clients_total > 0 and focus_clients_tfl > focus_clients_total:
            focus_clients_tfl = focus_clients_total
        if focus_clients_total > 0 and client_scope == "focus":
            focus_specific_signals += 1

        add_client_mix = focus_type in {"lobbyist", "general"}
        if add_client_mix and focus_clients_total > 0:
            signals_used += 1
            client_share_tfl = focus_clients_tfl / focus_clients_total
            prefix = "Across the selected scope, " if client_scope == "scope" else ""
            client_base_noun = "clients in the selected scope" if client_scope == "scope" else "associated clients"
            if client_share_tfl >= 0.60:
                parts.append(
                    f"{prefix}taxpayer-funded entities represent {focus_clients_tfl:,} of {focus_clients_total:,} {client_base_noun} "
                    f"({client_share_tfl:.0%}), indicating a strongly public-sector weighted client base."
                )
            elif client_share_tfl >= 0.30:
                parts.append(
                    f"{prefix}taxpayer-funded entities represent {focus_clients_tfl:,} of {focus_clients_total:,} {client_base_noun} "
                    f"({client_share_tfl:.0%}), indicating mixed but meaningful institutional exposure."
                )
            elif client_share_tfl > 0:
                parts.append(
                    f"{prefix}taxpayer-funded clients are present ({focus_clients_tfl:,} of {focus_clients_total:,} {client_base_noun}) but remain a minority share."
                )
            else:
                parts.append(f"{prefix}no taxpayer-funded clients are visible in the current client set.")

        if focus_type == "client":
            lobbyists_count = _metric_int("lobbyists")
            if lobbyists_count > 0:
                signals_used += 1
                focus_specific_signals += 1
                if lobbyists_count >= 10:
                    parts.append(f"This client is connected to {lobbyists_count:,} lobbyists, indicating broad representation capacity.")
                elif lobbyists_count >= 4:
                    parts.append(f"This client is connected to {lobbyists_count:,} lobbyists, suggesting meaningful representation depth.")
                else:
                    parts.append(f"This client is connected to {lobbyists_count:,} lobbyists in the current scope.")
            tfl_flag = _metric_value("taxpayer funded")
            if tfl_flag:
                signals_used += 1
                focus_specific_signals += 1
                normalized_flag = tfl_flag.strip().lower()
                if normalized_flag in {"yes", "true", "1"}:
                    parts.append("The client is classified as taxpayer-funded in the underlying records.")
                elif normalized_flag in {"no", "false", "0"}:
                    parts.append("The client is not classified as taxpayer-funded in the underlying records.")

        if focus_type == "lobbyist":
            lobby_total_clients = _metric_int("total clients")
            lobby_tfl_clients = _metric_int("taxpayer-funded clients", "taxpayer funded clients")
            if lobby_total_clients > 0:
                signals_used += 1
                focus_specific_signals += 1
                if lobby_tfl_clients > lobby_total_clients:
                    lobby_tfl_clients = lobby_total_clients
                share = (lobby_tfl_clients / lobby_total_clients) if lobby_total_clients > 0 else 0.0
                if share >= 0.60:
                    parts.append(
                        f"At the focus level, this lobbyist's client book is majority taxpayer-funded ({lobby_tfl_clients:,} of {lobby_total_clients:,})."
                    )
                elif share >= 0.30:
                    parts.append(
                        f"At the focus level, taxpayer-funded clients account for {lobby_tfl_clients:,} of {lobby_total_clients:,}, indicating a mixed portfolio."
                    )
                else:
                    parts.append(
                        f"At the focus level, taxpayer-funded clients account for {lobby_tfl_clients:,} of {lobby_total_clients:,}, with private clients dominant."
                    )

        if focus_type == "legislator":
            bills_authored = _metric_int("bills authored")
            bills_opposed_tfl = _metric_int("bills opposed by tfl lobbyists", "tfl lobbyists opposed")
            if bills_authored > 0:
                signals_used += 1
                focus_specific_signals += 1
                if bills_opposed_tfl > bills_authored:
                    bills_opposed_tfl = bills_authored
                if bills_opposed_tfl > 0:
                    oppose_share = bills_opposed_tfl / bills_authored
                    if oppose_share >= 0.50:
                        parts.append(
                            f"A substantial share of authored bills ({bills_opposed_tfl:,} of {bills_authored:,}) drew taxpayer-funded opposition."
                        )
                    elif oppose_share >= 0.25:
                        parts.append(
                            f"A meaningful share of authored bills ({bills_opposed_tfl:,} of {bills_authored:,}) drew taxpayer-funded opposition."
                        )
                    else:
                        parts.append(
                            f"Only a smaller share of authored bills ({bills_opposed_tfl:,} of {bills_authored:,}) drew taxpayer-funded opposition."
                        )
                else:
                    parts.append(f"No authored bills are shown as opposed by taxpayer-funded lobbyists out of {bills_authored:,} authored bills.")

        if focus_type == "bill":
            witness_rows = _metric_int("witness rows")
            tfl_witness = _metric_int("tfl lobbyists (any position)")
            private_witness = _metric_int("private lobbyists (any position)")
            if witness_rows > 0:
                signals_used += 1
                focus_specific_signals += 1
                if witness_rows >= 50:
                    parts.append(f"Witness-list volume is high for this bill ({witness_rows:,} rows), indicating elevated engagement intensity.")
                elif witness_rows >= 20:
                    parts.append(f"Witness-list volume is moderate for this bill ({witness_rows:,} rows).")
                else:
                    parts.append(f"Witness-list volume is limited for this bill ({witness_rows:,} rows).")
            if (tfl_witness + private_witness) > 0:
                signals_used += 1
                focus_specific_signals += 1
                total_w = tfl_witness + private_witness
                tfl_share = tfl_witness / total_w if total_w > 0 else 0.0
                if tfl_share >= 0.60:
                    parts.append(
                        f"Taxpayer-funded participation dominates witness representation ({tfl_witness:,} of {total_w:,} lobbyists recorded by funding class)."
                    )
                elif tfl_share >= 0.40:
                    parts.append(
                        f"Taxpayer-funded and private witness representation are comparatively balanced ({tfl_witness:,} vs {private_witness:,})."
                    )
                else:
                    parts.append(
                        f"Private witness representation exceeds taxpayer-funded participation ({private_witness:,} vs {tfl_witness:,})."
                    )

        focus_tfl_range_value = _metric_value("taxpayer-funded range", "taxpayer funded range")
        focus_private_range_value = _metric_value("private range")
        has_focus_comp_ranges = bool(focus_tfl_range_value or focus_private_range_value)
        tfl_mid = _range_midpoint(focus_tfl_range_value)
        pri_mid = _range_midpoint(focus_private_range_value)
        if has_focus_comp_ranges:
            focus_specific_signals += 1
        if (tfl_mid + pri_mid) <= 0:
            tfl_low = max(_safe_float(payload.get("tfl_low_value"), 0.0), 0.0)
            tfl_high = max(_safe_float(payload.get("tfl_high_value"), 0.0), 0.0)
            pri_low = max(_safe_float(payload.get("private_low_value"), 0.0), 0.0)
            pri_high = max(_safe_float(payload.get("private_high_value"), 0.0), 0.0)
            tfl_mid = (tfl_low + tfl_high) / 2.0 if (tfl_low > 0 or tfl_high > 0) else 0.0
            pri_mid = (pri_low + pri_high) / 2.0 if (pri_low > 0 or pri_high > 0) else 0.0

        funding_mid_total = tfl_mid + pri_mid
        if funding_mid_total > 0:
            signals_used += 1
            funding_delta = tfl_mid - pri_mid
            comp_scope = "within this focus" if has_focus_comp_ranges else "across the selected scope"
            if abs(funding_delta) <= (0.10 * funding_mid_total):
                parts.append(
                    f"Midpoint compensation estimates indicate near parity between taxpayer-funded and private financing {comp_scope}."
                )
            elif funding_delta > 0:
                parts.append(
                    f"Midpoint compensation estimates indicate taxpayer-funded financing exceeds private financing {comp_scope}."
                )
            else:
                parts.append(
                    f"Midpoint compensation estimates indicate private financing exceeds taxpayer-funded financing {comp_scope}."
                )

        tfl_against = 0
        tfl_for = 0
        tfl_on = 0
        witness_scope = "scope"
        for bullet in _safe_list(focus_section_local.get("bullets")):
            bullet_txt = _safe_str(bullet)
            if "witness positions" not in bullet_txt.lower():
                continue
            parsed_against = _first_int_after_keyword(bullet_txt, "Against")
            parsed_for = _first_int_after_keyword(bullet_txt, "For")
            parsed_on = _first_int_after_keyword(bullet_txt, "On")
            if parsed_against is not None:
                tfl_against = parsed_against
            if parsed_for is not None:
                tfl_for = parsed_for
            if parsed_on is not None:
                tfl_on = parsed_on
            witness_scope = "focus"
            focus_specific_signals += 1
            break
        if (tfl_against + tfl_for + tfl_on) <= 0:
            tfl_bucket = _safe_dict(_safe_dict(payload.get("witness_counts", {})).get("tfl", {}))
            tfl_against = int(_safe_float(tfl_bucket.get("Against"), 0.0))
            tfl_for = int(_safe_float(tfl_bucket.get("For"), 0.0))
            tfl_on = int(_safe_float(tfl_bucket.get("On"), 0.0))

        witness_total = tfl_against + tfl_for + tfl_on
        if witness_total > 0:
            signals_used += 1
            witness_prefix = "Across the selected scope, " if witness_scope == "scope" else "At the focus level, "
            if tfl_against > max(tfl_for, tfl_on):
                parts.append(
                    f"{witness_prefix}witness posture skews toward opposition ({tfl_against:,} Against vs {tfl_for:,} For)."
                )
            elif tfl_for > max(tfl_against, tfl_on):
                parts.append(
                    f"{witness_prefix}witness posture skews toward support ({tfl_for:,} For vs {tfl_against:,} Against)."
                )
            else:
                parts.append(
                    f"{witness_prefix}witness posture is mixed ({tfl_against:,} Against, {tfl_for:,} For, {tfl_on:,} On)."
                )

        bill_signal_count = _metric_int("bills opposed by tfl lobbyists", "tfl lobbyists opposed")
        if bill_signal_count > 0 and focus_type != "legislator":
            signals_used += 1
            focus_specific_signals += 1
            if bill_signal_count >= 10:
                parts.append(
                    "Focus-level opposition intensity is high, with double-digit taxpayer-funded opposition tied to at least one measure."
                )
            elif bill_signal_count >= 5:
                parts.append("Focus-level opposition intensity is moderate across selected measures.")
            else:
                parts.append("Focus-level opposition is present but not concentrated at high volume.")
        elif bill_signal_count <= 0:
            top_bill_counts = [
                int(_safe_float(_safe_dict(bill).get("tfl"), 0.0))
                for bill in _safe_list(payload.get("top_bills"))
                if int(_safe_float(_safe_dict(bill).get("tfl"), 0.0)) > 0
            ]
            total_top_bill = sum(top_bill_counts)
            top_bill_opp = max(top_bill_counts) if top_bill_counts else 0
            top_bill_share = (top_bill_opp / total_top_bill) if total_top_bill > 0 else 0.0
            if top_bill_opp > 0:
                signals_used += 1
                if top_bill_opp >= 10 or top_bill_share >= 0.45:
                    parts.append("Scope-level bill data indicates concentrated opposition around a narrow set of proposals.")
                elif top_bill_opp >= 5 or top_bill_share >= 0.30:
                    parts.append("Scope-level bill data indicates moderate concentration in opposition activity.")
                else:
                    parts.append("Scope-level bill data indicates opposition activity is relatively diffuse.")

        if focus_specific_signals >= 3:
            parts.append(
                "Taken together, focus-specific signals indicate a clear and internally consistent advocacy profile within the broader taxpayer-funded lobbying landscape."
            )
        elif signals_used >= 3:
            parts.append(
                "Taken together, the available indicators provide a coherent directional profile for this focus, though portions of the profile rely on scope-level context."
            )
        else:
            parts.append(
                "Available focus-specific indicators are limited, but the observable record still places this focus within the broader taxpayer-funded lobbying landscape."
            )

        clean_parts = [_sentence_case(p.rstrip(".")) + "." for p in parts if _safe_str(p).strip()]
        return " ".join(clean_parts)

    if not _safe_str(payload.get("focus_snapshot_paragraph")).strip():
        payload["focus_snapshot_paragraph"] = _derive_focus_snapshot_paragraph()

    def _derive_section_conditionals() -> dict[str, str]:
        out = {
            "scale": "",
            "activity": "",
            "bills": "",
            "subjects": "",
            "conclusion": "",
        }

        total_clients = int(_safe_float(payload.get("unique_clients_total"), 0.0))
        tfl_clients = int(_safe_float(payload.get("unique_clients_tfl"), 0.0))
        if total_clients > 0:
            tfl_client_share = (tfl_clients / total_clients) * 100.0
            if tfl_client_share >= 50:
                out["scale"] = (
                    "Taxpayer-funded entities make up a majority of unique clients in this scope, indicating broad institutional participation in lobbying activity."
                )
            elif tfl_client_share >= 30:
                out["scale"] = (
                    "Taxpayer-funded entities represent a substantial minority of unique clients in this scope, indicating durable institutional presence in lobbying activity."
                )
            elif tfl_client_share > 0:
                out["scale"] = (
                    "Taxpayer-funded entities represent a smaller but observable share of unique clients in this scope."
                )

        tfl_counts = _safe_dict(payload.get("witness_counts", {})).get("tfl", {})
        pri_counts = _safe_dict(payload.get("witness_counts", {})).get("private", {})
        tfl_against = int(_safe_float(_safe_dict(tfl_counts).get("Against"), 0.0))
        tfl_for = int(_safe_float(_safe_dict(tfl_counts).get("For"), 0.0))
        pri_against = int(_safe_float(_safe_dict(pri_counts).get("Against"), 0.0))
        pri_for = int(_safe_float(_safe_dict(pri_counts).get("For"), 0.0))
        if (tfl_against + tfl_for + pri_against + pri_for) > 0:
            if tfl_against > tfl_for and pri_against > pri_for:
                out["activity"] = (
                    "Both taxpayer-funded and private interests show a net-opposition profile in witness testimony for this scope."
                )
            elif tfl_against > tfl_for and not (pri_against > pri_for):
                out["activity"] = (
                    "Taxpayer-funded witness activity leans more opposition-oriented than private witness activity in this scope."
                )
            elif tfl_for > tfl_against:
                out["activity"] = (
                    "Taxpayer-funded witness activity includes a stronger support component than opposition in this scope."
                )

        top_bills = _safe_list(payload.get("top_bills"))
        if top_bills:
            bill_counts = [int(_safe_float(_safe_dict(row).get("tfl"), 0.0)) for row in top_bills]
            total_bill_opp = sum(bill_counts)
            top_bill_opp = max(bill_counts) if bill_counts else 0
            if total_bill_opp > 0 and top_bill_opp > 0:
                concentration = (top_bill_opp / total_bill_opp) * 100.0
                if concentration >= 40:
                    out["bills"] = (
                        "Opposition is relatively concentrated in the top-ranked bill, suggesting focused taxpayer-funded advocacy around a narrow set of proposals."
                    )
                else:
                    out["bills"] = (
                        "Opposition is distributed across multiple high-priority bills rather than concentrated in a single proposal."
                    )

        top_subjects = _safe_list(payload.get("top_subjects"))
        if top_subjects:
            subject_counts = [
                int(_safe_float(_safe_dict(row).get("Oppositions"), 0.0))
                for row in top_subjects
            ]
            total_subject_opp = sum(subject_counts)
            top_subject_opp = max(subject_counts) if subject_counts else 0
            if total_subject_opp > 0 and top_subject_opp > 0:
                concentration = (top_subject_opp / total_subject_opp) * 100.0
                if concentration >= 45:
                    out["subjects"] = (
                        "Policy-area opposition is concentrated in a leading subject, indicating a tighter taxpayer-funded advocacy focus."
                    )
                else:
                    out["subjects"] = (
                        "Policy-area opposition is spread across several subjects, indicating broader taxpayer-funded issue engagement."
                    )

        tfl_mid_share = _safe_float(payload.get("tfl_mid_share_pct_value"), 0.0)
        if tfl_mid_share >= 50:
            out["conclusion"] = (
                "At midpoint estimates, taxpayer-funded activity constitutes a majority share of reported lobbying compensation in this scope."
            )
        elif tfl_mid_share >= 35:
            out["conclusion"] = (
                "At midpoint estimates, taxpayer-funded activity constitutes a substantial share of reported lobbying compensation in this scope."
            )
        elif tfl_mid_share > 0:
            out["conclusion"] = (
                "At midpoint estimates, taxpayer-funded activity remains an identifiable share of reported lobbying compensation in this scope."
            )
        return out

    section_conditionals = _derive_section_conditionals()

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

    y0 = pdf.get_y()
    pdf.set_fill_color(*PDF_COLOR_NAVY_DARK)
    pdf.rect(pdf.l_margin, y0, pdf.w - pdf.l_margin - pdf.r_margin, 1.8, "F")
    pdf.ln(2.6)

    _pdf_add_heading(pdf, "TAXPAYER-FUNDED LOBBYING IN TEXAS", size=17)
    _pdf_add_subheading(
        pdf,
        f"Analysis of the {payload['session_label']} Legislative Session",
        size=12,
    )
    pdf.set_font(PDF_FONT_SANS, "", PDF_BODY_SIZE - 0.3)
    pdf.set_text_color(*PDF_COLOR_TEXT)
    pdf.cell(0, 4.8, _pdf_safe_text("Prepared by Texas Taxpayer Lobbying Transparency Center"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 4.8, _pdf_safe_text(f"Generated: {payload['generated_date']}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 4.8, _pdf_safe_text(f"Scope: {payload['scope_session_label']}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 4.8, _pdf_safe_text(f"Focus: {payload['focus_label']}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1.2)
    _pdf_add_rule(pdf)

    _pdf_add_section_title(pdf, "Executive Summary")
    exec_summary = (
        "Texas taxpayers should not be compelled to finance political advocacy through their own government. "
        f"During the {payload['session_label']} Legislative Session, registered lobbying activity reported "
        f"compensation ranges totaling between {payload['total_low']} and {payload['total_high']}. Within that total, "
        f"taxpayer-funded lobbying activity accounted for approximately {payload['tfl_low']} to {payload['tfl_high']}, "
        f"while privately funded lobbying accounted for approximately {payload['private_low']} to {payload['private_high']}. "
        f"Even under conservative assumptions, taxpayer-funded lobbying represented roughly {payload['tfl_share_low_pct']}% "
        f"to {payload['tfl_share_high_pct']}% of all reported lobbying compensation during this scope."
    )
    _pdf_add_paragraph(pdf, exec_summary, size=11)
    if payload.get("scope_note"):
        _pdf_add_paragraph(pdf, payload["scope_note"], size=10)
    exec_summary_2 = (
        "This report explains why taxpayer-funded lobbying is structurally inconsistent with transparent and "
        "accountable government, documents the scale of the practice in "
        f"{payload['session_label']}, and identifies the legislation and policy areas most frequently opposed by "
        "taxpayer-funded lobbyists. The conclusion is straightforward: Texas should abolish taxpayer-funded lobbying "
        "by political subdivisions and close both direct and indirect funding pathways so public money is used to provide "
        "public services, not to finance political advocacy."
    )
    _pdf_add_paragraph(pdf, exec_summary_2, size=11)
    exec_conditional = [
        str(s).strip() for s in payload.get("conditional_exec_sentences", []) if str(s).strip()
    ]
    if exec_conditional:
        _pdf_add_callout_box(pdf, "Data-Driven Context", exec_conditional[0])
        if len(exec_conditional) > 1:
            _pdf_add_bullets(pdf, exec_conditional[1:], size=9.8, line_h=4.8)

    _pdf_add_subheading(pdf, "Key Metrics", size=11)
    metrics = [
        ("Total lobbying range", f"{payload['total_low']} - {payload['total_high']}"),
        ("Taxpayer-funded range", f"{payload['tfl_low']} - {payload['tfl_high']}"),
        ("Private range", f"{payload['private_low']} - {payload['private_high']}"),
        ("Unique lobbyists", payload["unique_lobbyists_total"]),
        ("Lobbyists w/ TFL clients", payload["unique_lobbyists_tfl"]),
        ("Unique clients", payload["unique_clients_total"]),
        ("Taxpayer-funded clients", payload["unique_clients_tfl"]),
    ]
    _pdf_add_kpi_table(pdf, metrics, size=10)

    highlights = [
        f"Taxpayer-funded share: {payload['tfl_share_low_pct']}% - {payload['tfl_share_high_pct']}%",
        f"Taxpayer-funded range: {payload['tfl_low']} - {payload['tfl_high']}",
        f"Private range: {payload['private_low']} - {payload['private_high']}",
    ]
    _pdf_add_subheading(pdf, "Report Highlights", size=10)
    _pdf_add_bullets(pdf, highlights, size=10)
    _pdf_add_callout_box(
        pdf,
        "Key Claim: Taxpayer-Funded Share Range",
        (
            f"Even under conservative assumptions, taxpayer-funded lobbying represented "
            f"{payload['tfl_share_low_pct']}% to {payload['tfl_share_high_pct']}% of all reported "
            "lobbying compensation in this scope."
        ),
    )

    focus_section = payload.get("focus_section")
    if focus_section and isinstance(focus_section, dict):
        title = focus_section.get("title", "").strip()
        summary = focus_section.get("summary", "").strip()
        metrics = focus_section.get("metrics", [])
        bullets = focus_section.get("bullets", [])
        charts = focus_section.get("charts", [])

        if title or summary or metrics or bullets or charts:
            _pdf_add_section_title(pdf, "Focus Snapshot")
            if title:
                _pdf_add_subheading(pdf, title, size=11)
            if summary:
                _pdf_add_paragraph(pdf, summary, size=11)
            focus_dynamic_sentence = str(payload.get("conditional_focus_sentence", "")).strip()
            if focus_dynamic_sentence:
                _pdf_add_callout_box(
                    pdf,
                    "Focus Lens",
                    focus_dynamic_sentence,
                    accent=(34, 96, 74),
                )
            focus_snapshot_paragraph = _safe_str(payload.get("focus_snapshot_paragraph", "")).strip()
            if focus_snapshot_paragraph:
                _pdf_add_paragraph(pdf, focus_snapshot_paragraph, size=10.8, line_h=5.2)
            if bullets:
                _pdf_add_subheading(pdf, "Focus Highlights", size=10)
                _pdf_add_paragraph(
                    pdf,
                    str(payload.get("focus_highlights_intro", "Most relevant findings for the selected focus.")),
                    size=9.8,
                    line_h=5.0,
                )
                _pdf_add_focus_highlights(pdf, bullets, size=10)
            if charts:
                _pdf_add_subheading(pdf, "Focus Charts", size=10)
                for chart in charts:
                    fig = _build_focus_chart(chart if isinstance(chart, dict) else {})
                    if fig:
                        caption = str(chart.get("caption", "Focus Chart")).strip() if isinstance(chart, dict) else "Focus Chart"
                        _pdf_add_chart(pdf, fig, caption)
            _pdf_add_rule(pdf)

    _pdf_add_numbered_section_title(pdf, 1, f"THE SCALE OF LOBBYING IN {payload['session_label']}")
    scale_p1 = (
        "Lobbying in Texas is a major industry, and the compensation ranges reported to the state reflect the scale "
        "at which public policy is contested. For the "
        f"{payload['session_label']} session, the total reported lobbying compensation range across the selected scope "
        f"was {payload['total_low']} to {payload['total_high']}. Taxpayer-funded entities accounted for "
        f"{payload['tfl_low']} to {payload['tfl_high']} of that total, while privately funded entities accounted for "
        f"{payload['private_low']} to {payload['private_high']}. Because compensation is disclosed in ranges rather than "
        "precise amounts, these figures should be understood as conservative estimates of the activity captured in "
        "the underlying registrations and filings."
    )
    _pdf_add_paragraph(pdf, scale_p1, size=11)
    scale_p2 = (
        "The composition of the participating universe underscores why taxpayer-funded lobbying is not a marginal "
        "phenomenon. Across this scope, "
        f"{payload['unique_lobbyists_total']} unique lobbyists were observed, including {payload['unique_lobbyists_tfl']} "
        "who represented at least one taxpayer-funded client. Likewise, "
        f"{payload['unique_clients_total']} clients appeared in the data, including {payload['unique_clients_tfl']} that "
        "qualify as governmental or taxpayer-funded entities. The point is not merely that local governments participate "
        "in the process; it is that they do so at a scale capable of shaping agendas, crowding out citizen influence, "
        "and resisting reforms that would otherwise be evaluated on their merits."
    )
    _pdf_add_paragraph(pdf, scale_p2, size=11)
    if _safe_str(section_conditionals.get("scale")).strip():
        _pdf_add_paragraph(pdf, section_conditionals["scale"], size=10.5)

    comp_df = pd.DataFrame(
        [
            {"Funding": "Taxpayer Funded", "Low": payload["tfl_low_value"], "High": payload["tfl_high_value"]},
            {"Funding": "Private", "Low": payload["private_low_value"], "High": payload["private_high_value"]},
        ]
    )
    comp_long = comp_df.melt(id_vars="Funding", value_vars=["Low", "High"], var_name="Estimate", value_name="Total")
    if not comp_long.empty and comp_long["Total"].sum() > 0:
        fig_comp = px.bar(
            comp_long,
            x="Funding",
            y="Total",
            color="Estimate",
            barmode="group",
            text="Total",
            color_discrete_map={"Low": "#004c6d", "High": "#1f77b4"},
        )
        fig_comp.update_traces(texttemplate="$%{text:,.0f}", textposition="outside", cliponaxis=False)
        fig_comp.update_layout(
            template="plotly_white",
            title="Lobbying Compensation Range by Funding Type",
            yaxis_title="Reported compensation",
            xaxis_title="",
            legend_title="Estimate",
            margin=dict(l=40, r=20, t=50, b=30),
        )
        fig_comp.update_yaxes(tickprefix="$", tickformat="~s")
        _pdf_add_chart(pdf, fig_comp, "Chart 1. Lobbying Compensation Range by Funding Type")

    tfl_mid = (payload["tfl_low_value"] + payload["tfl_high_value"]) / 2
    pri_mid = (payload["private_low_value"] + payload["private_high_value"]) / 2
    if (tfl_mid + pri_mid) > 0:
        share_df = pd.DataFrame(
            {"Funding": ["Taxpayer Funded", "Private"], "Total": [tfl_mid, pri_mid]}
        )
        fig_share = px.pie(
            share_df,
            names="Funding",
            values="Total",
            hole=0.5,
            color="Funding",
            color_discrete_map={"Taxpayer Funded": "#0ea5a4", "Private": "#4c78a8"},
        )
        fig_share.update_layout(
            template="plotly_white",
            title="Share of Total Lobbying (Midpoint)",
            margin=dict(l=20, r=20, t=50, b=20),
        )
        _pdf_add_chart(pdf, fig_share, "Chart 2. Share of Total Lobbying - Taxpayer vs Private", width_px=700, height_px=420)

    _pdf_add_numbered_section_title(pdf, 2, "WHAT TAXPAYER-FUNDED LOBBYING IS - AND WHY IT MATTERS")
    def_p1 = (
        "Taxpayer-funded lobbying occurs when political subdivisions use public funds to employ registered lobbyists, "
        "contract with lobbying firms, or pay dues and assessments to associations that, in turn, employ lobbyists. "
        "In practice, the entities involved often include cities, counties, independent school districts, special "
        "districts, authorities, and intergovernmental associations funded by member governments. The distinctive "
        "feature is not the subject matter they address -- nearly any policy can be lobbied -- but the source of the "
        "money used to do it. When advocacy is financed with tax revenue or statutorily compelled fees, citizens are "
        "required to fund political activity as a condition of living, owning property, or receiving basic public services."
    )
    _pdf_add_paragraph(pdf, def_p1, size=11)
    def_p2 = (
        "That is why taxpayer-funded lobbying is a different category of problem than private-sector lobbying. "
        "Private entities spend their own money and must persuade contributors, shareholders, or members that the "
        "advocacy is worthwhile. Public entities spend money that was collected under compulsion and therefore operate "
        "without meaningful donor consent. This creates an unavoidable mismatch between who pays and who benefits. "
        "It also creates a confidence problem: citizens reasonably conclude that government is using their money to "
        "entrench itself, grow its authority, and resist reforms -- especially reforms aimed at fiscal restraint, "
        "regulatory limits, or transparency."
    )
    _pdf_add_paragraph(pdf, def_p2, size=11)

    entity_counts = payload.get("chart_entity_types_data", [])
    if entity_counts:
        entity_df = pd.DataFrame(entity_counts)
        fig_entities = px.bar(
            entity_df.sort_values("count"),
            x="count",
            y="type",
            orientation="h",
            text="count",
            color_discrete_sequence=["#4c78a8"],
        )
        fig_entities.update_traces(textposition="outside", cliponaxis=False)
        fig_entities.update_layout(
            template="plotly_white",
            title="Taxpayer-Funded Clients by Entity Type",
            xaxis_title="Clients",
            yaxis_title="",
            margin=dict(l=40, r=20, t=50, b=30),
        )
        _pdf_add_chart(pdf, fig_entities, "Chart 3. Taxpayer-Funded Clients by Entity Type")

    _pdf_add_numbered_section_title(pdf, 3, f"LEGISLATIVE ACTIVITY PATTERNS IN {payload['session_label']}")
    act_p1 = (
        "Compensation totals explain scale, but legislative activity signals show how that scale is used. "
        f"Across the {payload['session_label']} session, taxpayer-funded lobbyists appeared repeatedly in committee "
        "processes, filing and testifying in ways that illustrate institutional priorities. The witness-list record "
        "indicates that taxpayer-funded entities did not simply monitor legislation; they frequently intervened in it "
        "-- especially on proposals with direct implications for local discretion, budgets, and oversight."
    )
    _pdf_add_paragraph(pdf, act_p1, size=11)
    act_p2 = (
        "Within this scope, witness positions for taxpayer-funded and privately funded interests can be summarized as follows: "
        f"{payload['witness_activity_summary']} The distribution of positions matters because it is a proxy for the "
        "incentives embedded in taxpayer-funded lobbying."
    )
    _pdf_add_paragraph(pdf, act_p2, size=11)
    if _safe_str(section_conditionals.get("activity")).strip():
        _pdf_add_paragraph(pdf, section_conditionals["activity"], size=10.5)

    w_counts = payload.get("witness_counts", {})
    if w_counts:
        w_rows = []
        for position in ["Against", "For", "On"]:
            w_rows.append(
                {
                    "Position": position,
                    "Taxpayer Funded": int(w_counts.get("tfl", {}).get(position, 0)),
                    "Private": int(w_counts.get("private", {}).get(position, 0)),
                }
            )
        w_df = pd.DataFrame(w_rows)
        if not w_df.empty and w_df[["Taxpayer Funded", "Private"]].sum().sum() > 0:
            w_long = w_df.melt(id_vars="Position", var_name="Funding", value_name="Count")
            fig_wit = px.bar(
                w_long,
                x="Position",
                y="Count",
                color="Funding",
                barmode="group",
                text="Count",
                color_discrete_map={"Taxpayer Funded": "#ff6b6b", "Private": "#4c78a8"},
            )
            fig_wit.update_traces(textposition="outside", cliponaxis=False)
            fig_wit.update_layout(
                template="plotly_white",
                title="Witness Positions by Funding Type",
                yaxis_title="Positions",
                xaxis_title="",
                margin=dict(l=40, r=20, t=50, b=30),
            )
            _pdf_add_chart(pdf, fig_wit, "Chart 4. Witness Positions by Funding Type")

    _pdf_add_numbered_section_title(pdf, 4, "THE BILLS MOST OPPOSED BY TAXPAYER-FUNDED LOBBYISTS")
    if payload.get("has_top_bills"):
        bills_p = (
            "The most direct way to see taxpayer-funded lobbying in action is to identify the bills that generated "
            "concentrated opposition from taxpayer-funded entities. The bills below are ranked by the number of "
            "Against filings by taxpayer-funded lobbyists."
        )
        _pdf_add_paragraph(pdf, bills_p, size=11)
        if _safe_str(section_conditionals.get("bills")).strip():
            _pdf_add_paragraph(pdf, section_conditionals["bills"], size=10.5)
        top_bills = payload.get("top_bills", [])
        if top_bills:
            bill_df = pd.DataFrame(
                [{"Bill": b["id"], "Oppositions": b.get("tfl", 0)} for b in top_bills]
            )
            fig_bills = px.bar(
                bill_df.sort_values("Oppositions"),
                x="Oppositions",
                y="Bill",
                orientation="h",
                text="Oppositions",
                color_discrete_sequence=["#d14b4b"],
            )
            fig_bills.update_traces(textposition="outside", cliponaxis=False)
            fig_bills.update_layout(
                template="plotly_white",
                title="Top Bills Opposed by Taxpayer-Funded Lobbyists",
                xaxis_title="Oppositions",
                yaxis_title="",
                margin=dict(l=40, r=20, t=50, b=30),
            )
            _pdf_add_chart(pdf, fig_bills, "Chart 5. Top 5 Bills Opposed by Taxpayer-Funded Lobbyists")
    else:
        _pdf_add_paragraph(pdf, "No bill-level opposition data was available for the selected scope/session.", size=11)

    _pdf_add_numbered_section_title(pdf, 5, "THE POLICY AREAS MOST OPPOSED BY TAXPAYER-FUNDED LOBBYISTS")
    if payload.get("has_top_subjects"):
        subject_p = (
            "Bills are discrete, but policy areas reveal patterns. When opposition is aggregated by subject matter, "
            "taxpayer-funded lobbying tends to cluster in the places where the Legislature can most directly alter "
            "local fiscal and regulatory authority."
        )
        _pdf_add_paragraph(pdf, subject_p, size=11)
        if _safe_str(section_conditionals.get("subjects")).strip():
            _pdf_add_paragraph(pdf, section_conditionals["subjects"], size=10.5)
        top_subjects = payload.get("top_subjects", [])
        if top_subjects:
            subj_df = pd.DataFrame(
                [{"Subject": s["Subject"], "Oppositions": s.get("Oppositions", 0)} for s in top_subjects]
            )
            fig_subjects = px.bar(
                subj_df.sort_values("Oppositions"),
                x="Oppositions",
                y="Subject",
                orientation="h",
                text="Oppositions",
                color_discrete_sequence=["#7aa6c2"],
            )
            fig_subjects.update_traces(textposition="outside", cliponaxis=False)
            fig_subjects.update_layout(
                template="plotly_white",
                title="Top Policy Areas Opposed by Taxpayer-Funded Lobbyists",
                xaxis_title="Oppositions",
                yaxis_title="",
                margin=dict(l=40, r=20, t=50, b=30),
            )
            _pdf_add_chart(pdf, fig_subjects, "Chart 6. Top 5 Policy Areas Opposed by Taxpayer-Funded Lobbyists")
    else:
        _pdf_add_paragraph(pdf, "No subject-level opposition data was available for the selected scope/session.", size=11)

    _pdf_add_numbered_section_title(pdf, 6, "STRUCTURAL INCENTIVES AND THE COMPULSION PROBLEM")
    _pdf_add_paragraph(
        pdf,
        "Taxpayer-funded lobbying persists because it is rational for institutions. Political subdivisions face "
        "budget pressures, political pressures, and administrative demands, and they naturally seek to preserve the "
        "widest possible discretion to manage those pressures. But rationality for institutions is not the same as "
        "legitimacy for taxpayers. When the money used to lobby is collected under compulsion, the normal disciplining "
        "forces of voluntary association are absent. The cost of advocacy is dispersed across taxpayers, while the "
        "perceived benefits -- expanded authority, preserved revenues, reduced oversight -- accrue to the institution.",
        size=11,
    )
    _pdf_add_paragraph(
        pdf,
        "The result is a misalignment: the payer is not the decision-maker, and the decision-maker has an incentive "
        "to externalize the cost. That is why taxpayer-funded lobbying is not merely politics as usual. It is a "
        "financing structure that undermines accountability and encourages institutional self-protection. Over time, "
        "it becomes a form of self-reinforcing governance: public entities use public funds to defend and expand the "
        "very powers that allow them to collect and deploy public funds.",
        size=11,
    )

    _pdf_add_numbered_section_title(pdf, 7, "LEGAL PARITY AND STATUTORY INCONSISTENCY")
    _pdf_add_paragraph(
        pdf,
        "Texas has already recognized that using public money to hire lobbyists raises concerns. State agencies face "
        "statutory restrictions that prevent them from employing registered lobbyists with public funds. Yet political "
        "subdivisions are not subject to uniform prohibitions, and the result is a parity failure. "
        f"{payload['existing_law_gap_summary']}",
        size=11,
    )
    _pdf_add_paragraph(
        pdf,
        "If the state has concluded that state agencies should not use taxpayer dollars to hire registered lobbyists, "
        "the same logic applies -- often more urgently -- to political subdivisions. Local entities are numerous, "
        "collectively spend vast sums, and frequently coordinate through associations that amplify their influence. "
        "In that environment, the absence of a clear prohibition invites continual expansion of the practice and "
        "continued erosion of public trust.",
        size=11,
    )

    _pdf_add_numbered_section_title(pdf, 8, "POLICY SOLUTION: A COMPREHENSIVE BAN ON TAXPAYER-FUNDED LOBBYING")
    _pdf_add_paragraph(
        pdf,
        "The policy principle is simple: public money should not be used to lobby government. A workable statutory "
        "approach is equally straightforward: Texas should extend the existing state-agency prohibition framework to "
        "political subdivisions and close indirect funding pathways that allow local governments to outsource lobbying "
        "through membership associations.",
        size=11,
    )
    _pdf_add_callout_box(
        pdf,
        "Key Claim: Recommended Statutory Reform",
        f"Recommended statutory reform: {payload['recommended_fix_statute']}",
    )
    _pdf_add_paragraph(
        pdf,
        f"A recommended statutory reform is: {payload['recommended_fix_statute']}. Under this approach, the law should "
        "prohibit political subdivisions from using public funds to employ registered lobbyists directly, contract with "
        "registered lobbyists, or pay membership dues or assessments to organizations that employ registered lobbyists "
        "for the purpose of influencing legislation. The ban must be drafted to address both direct payments and indirect "
        "routing of funds. Otherwise, enforcement will become a game of accounting rather than a real protection for taxpayers.",
        size=11,
    )
    _pdf_add_paragraph(
        pdf,
        "Implementation should include clear definitions of political subdivision, public funds, and lobbying "
        "services, and should make explicit that the prohibition applies regardless of whether the money is labeled "
        "appropriated, fee-based, enterprise, or interlocal. The Legislature should also specify enforceable remedies. "
        f"{payload['implementation_notes']}",
        size=11,
    )

    _pdf_add_numbered_section_title(pdf, 9, "DATA SOURCES AND METHODOLOGY")
    _pdf_add_paragraph(pdf, "This report is based on public information drawn from:", size=11)
    bullets = [
        b.strip().lstrip("- ").strip()
        for b in payload.get("data_sources_bullets", "").splitlines()
        if b.strip()
    ]
    _pdf_add_bullets(pdf, bullets, size=10)
    _pdf_add_paragraph(
        pdf,
        "Compensation figures reflect statutory reporting ranges filed with the Texas Ethics Commission. Totals were "
        "calculated by aggregating minimum and maximum disclosed ranges within the selected scope. Witness list activity "
        "reflects publicly available committee records compiled into the Lobby Look-Up dataset. Because compensation is "
        "reported in ranges rather than exact amounts, the totals presented here should be interpreted as conservative "
        "estimates rather than precise expenditures.",
        size=11,
    )

    _pdf_add_numbered_section_title(pdf, 10, "CONCLUSION")
    _pdf_add_paragraph(
        pdf,
        f"During the {payload['session_label']} Legislative Session, taxpayers indirectly financed lobbying activity "
        f"totaling between {payload['tfl_low']} and {payload['tfl_high']} in reported compensation ranges. This practice "
        "compels political financing, entrenches institutional self-interest, and undermines public confidence that "
        "government is operating transparently and accountably.",
        size=11,
    )
    _pdf_add_paragraph(
        pdf,
        "Texas should abolish taxpayer-funded lobbying by political subdivisions and close both direct and indirect "
        "funding pathways. Public money should be used to provide public services -- not to finance political advocacy.",
        size=11,
    )
    if _safe_str(section_conditionals.get("conclusion")).strip():
        _pdf_add_paragraph(pdf, section_conditionals["conclusion"], size=10.5)
    pdf.ln(2)
    pdf.set_font("Helvetica", "I", PDF_CAPTION_SIZE)
    pdf.cell(0, 5, _pdf_safe_text("Prepared by Texas Taxpayer Lobbying Transparency Center"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "I", PDF_FOOTNOTE_SIZE)
    pdf.cell(0, 5, _pdf_safe_text(payload["disclaimer_note"]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    output = pdf.output()
    return output if isinstance(output, (bytes, bytearray)) else output.encode("latin-1")

def _render_pdf_report_section(
    *,
    key_prefix: str,
    session_val: str | None,
    scope_label: str,
    focus_label: str,
    Lobby_TFL_Client_All: pd.DataFrame,
    Wit_All: pd.DataFrame,
    Bill_Status_All: pd.DataFrame,
    Bill_Sub_All: pd.DataFrame,
    tfl_session_val: str | None,
    focus_context: dict | None = None,
) -> None:
    """Render PDF report generation section in an expander."""
    with st.expander("Custom PDF report", expanded=False):
        st.caption("Generate a PDF report using the current filters and selections.")

        sig_key = f"{key_prefix}_report_sig"
        pdf_key = f"{key_prefix}_report_pdf"
        name_key = f"{key_prefix}_report_name"
        signature = f"{session_val}|{scope_label}|{focus_label}"

        if st.session_state.get(sig_key) != signature:
            st.session_state[sig_key] = signature
            if pdf_key in st.session_state:
                del st.session_state[pdf_key]
            if name_key in st.session_state:
                del st.session_state[name_key]

        generate_clicked = st.button(
            "Generate report",
            key=f"{key_prefix}_report_build",
            width="stretch",
            help="Build a PDF using the current filters and selections.",
        )

        if generate_clicked:
            _clear_pdf_chart_error()
            try:
                with st.status("Generating PDF...", expanded=False):
                    report_bill_sub_all, report_focus_context = _hydrate_report_inputs(Bill_Sub_All, focus_context)
                    payload = _build_report_payload(
                        session_val=session_val,
                        scope_label=scope_label,
                        focus_label=focus_label,
                        Lobby_TFL_Client_All=Lobby_TFL_Client_All,
                        Wit_All=Wit_All,
                        Bill_Status_All=Bill_Status_All,
                        Bill_Sub_All=report_bill_sub_all,
                        tfl_session_val=tfl_session_val,
                        focus_context=report_focus_context,
                    )
                    pdf_bytes = _coerce_pdf_bytes(_build_report_pdf_bytes(payload))
                    if pdf_bytes and len(pdf_bytes) > 0:
                        st.session_state[pdf_key] = pdf_bytes
                        st.session_state[name_key] = f"tfl-report-{_slugify(focus_label)}.pdf"
                        st.success("Report generated")
            except Exception as e:
                st.error(f"Report generation failed: {str(e)}")

        if pdf_key in st.session_state and st.session_state.get(PDF_CHART_ERROR_KEY):
            st.warning(
                "PDF rendering encountered an issue (charts). "
                "Common cause: missing Kaleido for Plotly images."
            )
            st.caption(st.session_state[PDF_CHART_ERROR_KEY])

        if pdf_key in st.session_state and isinstance(st.session_state[pdf_key], bytes):
            st.download_button(
                "Download PDF",
                st.session_state[pdf_key],
                st.session_state.get(name_key, "report.pdf"),
                "application/pdf",
                key=f"{key_prefix}_dl",
                width="stretch",
            )

PLOTLY_CONFIG = {
    "displayModeBar": "hover",
    "responsive": True,
    "displaylogo": False,
    "modeBarButtonsToRemove": ["select2d", "lasso2d", "autoScale2d"],
    "modeBarButtonsToAdd": ["toggleSpikelines"],
    "toImageButtonOptions": {
        "format": "png",
        "filename": "tfl-chart-export",
        "height": 600,
        "width": 1000,
        "scale": 2,
    },
}
CHART_COLORS = [
    "#8caed3",
    "#6f92b9",
    "#5e7fa3",
    "#4f6f8e",
    "#4f8871",
    "#7d8fa6",
    "#8d7d96",
    "#7b6f86",
    "#a58a64",
    "#6d7682",
]
FUNDING_COLOR_MAP = {"Taxpayer Funded": "#8caed3", "Private": "#6d7682"}
OPPOSITION_COLOR_MAP = {"Opposed by TFL lobbyist": "#be7b7b", "Not opposed by TFL lobbyist": "#748bb0"}
TREND_COLOR_MAP = {"Low estimate": "#8d7d96", "High estimate": "#8caed3"}

def _session_base_number_series(s: pd.Series) -> pd.Series:
    base = s.fillna("").astype(str).str.strip().str.extract(r"^(\d+)", expand=False)
    base = base.where(base.str.len() <= 2, base.str[:-1])
    return pd.to_numeric(base, errors="coerce")

def _session_base_label(base_val: float | int) -> str:
    if pd.isna(base_val):
        return ""
    return _ordinal(int(base_val))

def _apply_plotly_layout(
    fig,
    *,
    height: int | None = None,
    showlegend: bool = False,
    legend_title: str | None = None,
    margin_top: int = 30,
):
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="IBM Plex Sans", color="rgba(235,245,255,0.92)", size=12),
        margin=dict(l=8, r=8, t=margin_top, b=8),
        showlegend=showlegend,
        legend_title_text=legend_title,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            font=dict(size=11, color="rgba(223,234,247,0.78)"),
        ),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor="rgba(16,27,41,0.96)",
            bordercolor="rgba(255,255,255,0.10)",
            font=dict(color="rgba(237,245,255,0.95)", size=12),
        ),
        transition=dict(duration=300, easing="cubic-in-out"),
    )
    if height:
        fig.update_layout(height=height)
    fig.update_xaxes(
        showgrid=False,
        zeroline=False,
        showline=False,
        ticks="outside",
        tickfont=dict(color="rgba(223,234,247,0.78)"),
        showspikes=True,
        spikecolor="rgba(134,167,198,0.3)",
        spikethickness=1,
        spikedash="dot",
        spikemode="across",
    )
    fig.update_yaxes(
        showgrid=False,
        zeroline=False,
        showline=False,
        ticks="outside",
        tickfont=dict(color="rgba(223,234,247,0.78)"),
        showspikes=True,
        spikecolor="rgba(134,167,198,0.3)",
        spikethickness=1,
        spikedash="dot",
        spikemode="across",
    )
    return fig
