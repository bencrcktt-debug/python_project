import plotly.graph_objects as go

from .config import PLOTLY_CONFIG


def apply_layout(fig: go.Figure, height: int = 320, showlegend: bool = False) -> go.Figure:
    """Centralize layout tweaks for consistent styling across app and PDF."""
    fig.update_layout(
        height=height,
        margin=dict(l=24, r=24, t=24, b=24),
        showlegend=showlegend,
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="rgba(235,245,255,0.9)"),
        config=PLOTLY_CONFIG,
    )
    return fig


def sparkline(x, y, color: str = "#1e90ff") -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=y, mode="lines", line=dict(color=color, width=3)))
    fig.update_layout(
        height=120,
        margin=dict(l=8, r=8, t=4, b=4),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        showlegend=False,
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig
