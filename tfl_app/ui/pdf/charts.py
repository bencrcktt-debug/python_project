from __future__ import annotations

import re
from typing import Any

import pandas as pd
import plotly.express as px

from tfl_app.ui.pdf.runtime_helpers import _plotly_io

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


PDF_CHART_ERROR_KEY = "pdf_chart_error"
PDF_FONT_SANS = "Helvetica"


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
        scope = _plotly_io().kaleido.scope
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
            return _plotly_io().to_image(
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


def _pdf_clean_chart_caption(caption: str) -> str:
    txt = str(caption or "").strip()
    if not txt:
        return "Chart"
    txt = re.sub(r"^(chart|figure)\s*\d+\s*[:.\-]\s*", "", txt, flags=re.IGNORECASE)
    return txt.strip() or "Chart"


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


__all__ = [
    "PDF_CHART_ERROR_KEY",
    "_apply_pdf_chart_layout",
    "_build_focus_chart",
    "_calc_share_range",
    "_chart_lines",
    "_clear_pdf_chart_error",
    "_coerce_pdf_bytes",
    "_fig_to_png_bytes",
    "_pdf_clean_chart_caption",
]
