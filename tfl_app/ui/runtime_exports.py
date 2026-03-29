from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import pandas as pd

try:
    import streamlit as st
except ModuleNotFoundError:  # pragma: no cover - import smoke fallback
    class _CacheStub:
        def __call__(self, *decorator_args, **decorator_kwargs):
            if decorator_args and callable(decorator_args[0]) and len(decorator_args) == 1 and not decorator_kwargs:
                func = decorator_args[0]
                func.clear = lambda: None
                return func

            def decorator(func):
                func.clear = lambda: None
                return func

            return decorator

    class _StreamlitStub:
        cache_data = _CacheStub()
        session_state: dict[str, Any] = {}

        @staticmethod
        def download_button(*args, **kwargs):
            return None

        @staticmethod
        def markdown(*args, **kwargs):
            return None

        @staticmethod
        def warning(*args, **kwargs):
            return None

        @staticmethod
        def caption(*args, **kwargs):
            return None

    st = _StreamlitStub()

from tfl_app.ui.runtime_filters import _current_filter_parts
from tfl_app.ui.runtime_labels import _shorten_text


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
        extra = [str(item) for item in context if item]
    context_label = _export_context_label(extra)
    export_label = f"{label} ({context_label})" if context_label else label
    export_name = _export_filename(filename, extra)
    csv_bytes = _dataframe_csv_bytes(df)
    _ = st.download_button(label=export_label, data=csv_bytes, file_name=export_name, mime="text/csv")
    if context_label:
        st.markdown(f'<div class="section-caption">CSV includes: {context_label}.</div>', unsafe_allow_html=True)
    return ""


def require_columns(df: pd.DataFrame, required: list[str], label: str, hint: str = "") -> bool:
    missing = [column for column in required if column not in df.columns]
    if not missing:
        return True
    st.warning(f"{label} is missing required columns: {', '.join(missing)}.")
    if hint:
        st.caption(hint)
    return False

__all__ = [
    "_dataframe_csv_bytes",
    "_export_context_label",
    "_export_filename",
    "export_dataframe",
    "require_columns",
]
