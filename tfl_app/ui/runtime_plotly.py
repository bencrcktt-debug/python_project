from __future__ import annotations

import pandas as pd

from tfl_app.ui.runtime_labels import _ordinal

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

__all__ = [
    "CHART_COLORS",
    "FUNDING_COLOR_MAP",
    "OPPOSITION_COLOR_MAP",
    "PLOTLY_CONFIG",
    "TREND_COLOR_MAP",
    "_apply_plotly_layout",
]
