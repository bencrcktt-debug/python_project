from __future__ import annotations

import hashlib
import html
import re
from pathlib import Path
from typing import Any

import pandas as pd

from tfl_app.ui.pdf.session_state import _session_label

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


__all__ = [
    "_current_filter_parts",
    "_dataframe_csv_bytes",
    "_export_context_label",
    "_export_filename",
    "_hash_dataframe_for_csv",
    "_shorten_text",
    "export_dataframe",
    "fmt_usd",
    "render_pill_list",
    "require_columns",
]
