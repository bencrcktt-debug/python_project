from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import streamlit as st


_PAGE_TITLE = "Texas Taxpayer Lobbying Transparency Center"
_PAGE_LAYOUT = "wide"
_BOOTSTRAP_ASSET_DIR = Path(__file__).with_name("assets") / "bootstrap"
_GLOBAL_STYLE_ASSET_NAMES = (
    "global_style.html",
    "workspace_style.html",
)
_GLOBAL_UX_ASSET_NAME = "global_ux.html"


@lru_cache(maxsize=8)
def _load_bootstrap_asset(name: str) -> str:
    return (_BOOTSTRAP_ASSET_DIR / name).read_text(encoding="utf-8")


def configure_page() -> None:
    st.set_page_config(page_title=_PAGE_TITLE, layout=_PAGE_LAYOUT)


def render_global_styles() -> None:
    for asset_name in _GLOBAL_STYLE_ASSET_NAMES:
        st.markdown(_load_bootstrap_asset(asset_name), unsafe_allow_html=True)


def render_global_ux() -> None:
    st.markdown(_load_bootstrap_asset(_GLOBAL_UX_ASSET_NAME), unsafe_allow_html=True)

