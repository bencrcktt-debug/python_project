from __future__ import annotations

import html

import pandas as pd
import streamlit as st


def render_kpi_card(title: str, value: str, sub: str = "", help_text: str = "") -> None:
    tooltip_attr = f' title="{html.escape(help_text, quote=True)}"' if help_text else ""
    st.markdown(
        f"""
        <div class="card"{tooltip_attr}>
          <div class="kpi-title">{title}</div>
          <div class="kpi-value">{value}</div>
          <div class="kpi-sub">{sub}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def format_usd_series(series: pd.Series, fmt_usd) -> pd.Series:
    cleaned = series.fillna("").astype(str).str.strip()
    cleaned = cleaned.str.replace(r"^\((.*)\)$", r"-\1", regex=True)
    cleaned = cleaned.str.replace("$", "", regex=False).str.replace(",", "", regex=False)
    cleaned = cleaned.where(~cleaned.str.lower().isin({"", "nan", "none"}), "")
    numeric = pd.to_numeric(cleaned, errors="coerce").fillna(0.0)
    return numeric.map(fmt_usd)
