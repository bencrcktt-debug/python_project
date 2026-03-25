from __future__ import annotations

import importlib
from typing import Any

try:
    import streamlit as st
except ModuleNotFoundError:  # pragma: no cover - import smoke fallback
    class _FragmentStub:
        def __call__(self, *decorator_args, **decorator_kwargs):
            if decorator_args and callable(decorator_args[0]) and len(decorator_args) == 1 and not decorator_kwargs:
                return decorator_args[0]

            def decorator(func):
                return func

            return decorator

    class _StreamlitStub:
        fragment = _FragmentStub()
        session_state: dict[str, Any] = {}

    st = _StreamlitStub()


_HELPERS: dict[str, Any] = {}
_RENDERERS = {
    "_client_workspace_ctx": "render_client_workspace",
    "_member_workspace_ctx": "render_member_workspace",
    "_lobby_workspace_ctx": "render_lobby_workspace",
}


def configure_page_fragment_helpers(**helpers: Any) -> None:
    _HELPERS.update(helpers)


def _run_fragment(storage_key: str) -> None:
    ctx = {}
    if hasattr(st, "session_state"):
        raw = st.session_state.get(storage_key, {})
        if isinstance(raw, dict):
            ctx = raw
    renderer_name = _RENDERERS.get(storage_key)
    if not renderer_name:
        return
    module = importlib.import_module("src.page_workspace_renderers")
    module.configure_helpers(**_HELPERS)
    getattr(module, renderer_name)(ctx)


@st.fragment
def render_client_workspace_fragment(storage_key: str = "_client_workspace_ctx") -> None:
    _run_fragment(storage_key)


@st.fragment
def render_member_workspace_fragment(storage_key: str = "_member_workspace_ctx") -> None:
    _run_fragment(storage_key)


@st.fragment
def render_lobby_workspace_fragment(storage_key: str = "_lobby_workspace_ctx") -> None:
    _run_fragment(storage_key)
