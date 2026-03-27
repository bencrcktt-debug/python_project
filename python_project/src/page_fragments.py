from __future__ import annotations

import hashlib
import importlib
import json
from typing import Any

import pandas as pd

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
_SELECTOR_KEYS = {
    "_client_workspace_ctx": ("PATH", "client_scope", "client_session", "client_name", "tfl_session_val"),
    "_member_workspace_ctx": ("PATH", "member_session", "member_name", "tfl_session_val"),
    "_lobby_workspace_ctx": (
        "PATH",
        "scope",
        "session",
        "tfl_session_val",
        "lobbyshort",
        "typed_norms_tuple",
        "selected_names",
        "selected_filer_ids",
    ),
}
_PREPARED_CONTEXT_CACHE: dict[tuple[str, str], dict[str, Any]] = {}


def configure_page_fragment_helpers(**helpers: Any) -> None:
    _HELPERS.update(helpers)


def _helper(name: str) -> Any:
    return _HELPERS.get(name)


def _merge_bundle_context(ctx: dict[str, Any], bundle: Any) -> dict[str, Any]:
    merged = dict(ctx)
    bundle_ctx = getattr(bundle, "context", None)
    if isinstance(bundle_ctx, dict):
        merged.update(bundle_ctx)
    return merged


def _clone_cache_value(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return value.copy()
    if isinstance(value, pd.Series):
        return value.copy()
    if isinstance(value, dict):
        return {key: _clone_cache_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clone_cache_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_clone_cache_value(item) for item in value)
    if isinstance(value, set):
        return {_clone_cache_value(item) for item in value}
    return value


def _session_selector_context(
    storage_key: str,
    ctx: dict[str, Any],
    *,
    selector_signature: str | None = None,
) -> dict[str, Any]:
    keys = _SELECTOR_KEYS.get(storage_key, ())
    if not keys:
        payload = dict(ctx)
    else:
        payload = {key: ctx.get(key) for key in keys if key in ctx}
    if selector_signature:
        payload["_prepared_signature"] = selector_signature
    elif "_prepared_signature" in ctx:
        payload["_prepared_signature"] = ctx["_prepared_signature"]
    return payload


def _remember_prepared_context(storage_key: str, selector_signature: str, ctx: dict[str, Any]) -> None:
    stale_keys = [key for key in _PREPARED_CONTEXT_CACHE.keys() if key[0] == storage_key and key[1] != selector_signature]
    for key in stale_keys:
        _PREPARED_CONTEXT_CACHE.pop(key, None)
    _PREPARED_CONTEXT_CACHE[(storage_key, selector_signature)] = _clone_cache_value(ctx)


def _prepared_context(storage_key: str, selector_signature: str) -> dict[str, Any] | None:
    cached = _PREPARED_CONTEXT_CACHE.get((storage_key, selector_signature))
    if cached is None:
        return None
    return _clone_cache_value(cached)


def merge_fragment_session_context(storage_key: str, selector_updates: dict[str, Any]) -> dict[str, Any]:
    current = {}
    if hasattr(st, "session_state"):
        raw = st.session_state.get(storage_key, {})
        if isinstance(raw, dict):
            current = dict(raw)
    current.update(dict(selector_updates or {}))
    if hasattr(st, "session_state"):
        current = _session_selector_context(storage_key, current)
        st.session_state[storage_key] = current
    return dict(current)


def _app_state_context(path: str) -> dict[str, Any]:
    get_app_state = _helper("get_app_state")
    if not path or not callable(get_app_state):
        return {}

    app_state = get_app_state(path)
    return {
        "name_to_short": getattr(app_state, "name_to_short", {}) or {},
        "short_to_names": getattr(app_state, "short_to_names", {}) or {},
        "filerid_to_short": getattr(app_state, "filerid_to_short", {}) or {},
    }


def _rehydrate_client_workspace_ctx(ctx: dict[str, Any]) -> dict[str, Any]:
    path = str(ctx.get("PATH", "")).strip()
    scope = ctx.get("client_scope")
    session = str(ctx.get("client_session", "")).strip()
    client_name = str(ctx.get("client_name", "")).strip()
    tfl_session_val = ctx.get("tfl_session_val")
    get_scope_bundle = _helper("get_client_scope_bundle")
    get_detail_bundle = _helper("get_client_workspace_detail_bundle")
    if not path or scope is None or not callable(get_scope_bundle) or not callable(get_detail_bundle):
        return ctx

    scope_bundle = get_scope_bundle(path, scope, tfl_session_val)
    detail_bundle = get_detail_bundle(path, session, tfl_session_val, client_name)
    merged = dict(ctx)
    merged.update(_app_state_context(path))
    merged = _merge_bundle_context(merged, detail_bundle)
    merged.update(
        {
            "client_scope_bundle": scope_bundle,
            "all_clients": scope_bundle.overview,
            "all_stats": scope_bundle.stats,
            "_prepared_client_workspace": True,
        }
    )
    return merged


def _rehydrate_member_workspace_ctx(ctx: dict[str, Any]) -> dict[str, Any]:
    path = str(ctx.get("PATH", "")).strip()
    session = str(ctx.get("member_session", "")).strip()
    member_name = str(ctx.get("member_name", "")).strip()
    tfl_session_val = ctx.get("tfl_session_val")
    get_session_bundle = _helper("get_member_session_bundle")
    get_detail_bundle = _helper("get_member_workspace_detail_bundle")
    if not path or not callable(get_session_bundle) or not callable(get_detail_bundle):
        return ctx

    session_bundle = get_session_bundle(path, session)
    detail_bundle = get_detail_bundle(path, session, tfl_session_val, member_name)
    merged = dict(ctx)
    merged.update(_app_state_context(path))
    merged = _merge_bundle_context(merged, detail_bundle)
    merged.update(
        {
            "all_legislators": session_bundle.all_legislators,
            "all_leg_stats": session_bundle.stats,
            "_prepared_member_workspace": True,
        }
    )
    return merged


def _rehydrate_lobby_workspace_ctx(ctx: dict[str, Any]) -> dict[str, Any]:
    path = str(ctx.get("PATH", "")).strip()
    scope = ctx.get("scope")
    session = str(ctx.get("session", "")).strip()
    tfl_session_val = ctx.get("tfl_session_val")
    lobbyshort = str(ctx.get("lobbyshort", "")).strip()
    typed_norms_tuple = tuple(ctx.get("typed_norms_tuple", ()) or ())
    selected_names = tuple(ctx.get("selected_names", ()) or ())
    selected_filer_ids = tuple(ctx.get("selected_filer_ids", ()) or ())
    get_scope_bundle = _helper("get_lobby_scope_bundle")
    get_detail_bundle = _helper("get_lobby_workspace_detail_bundle")
    if not path or scope is None or not callable(get_scope_bundle) or not callable(get_detail_bundle):
        return ctx

    scope_bundle = get_scope_bundle(path, scope, tfl_session_val)
    detail_bundle = get_detail_bundle(
        path,
        session,
        tfl_session_val,
        lobbyshort,
        typed_norms_tuple,
        selected_names,
        selected_filer_ids,
    )
    merged = dict(ctx)
    merged.update(_app_state_context(path))
    merged = _merge_bundle_context(merged, detail_bundle)
    merged.update(
        {
            "lobby_scope_bundle": scope_bundle,
            "all_pivot": scope_bundle.all_pivot,
            "all_stats": scope_bundle.all_stats,
            "_prepared_lobby_workspace": True,
        }
    )
    return merged


def _rehydrate_fragment_ctx(storage_key: str, ctx: dict[str, Any]) -> dict[str, Any]:
    if storage_key == "_client_workspace_ctx":
        return _rehydrate_client_workspace_ctx(ctx)
    if storage_key == "_member_workspace_ctx":
        return _rehydrate_member_workspace_ctx(ctx)
    if storage_key == "_lobby_workspace_ctx":
        return _rehydrate_lobby_workspace_ctx(ctx)
    return ctx


def _selector_signature(storage_key: str, ctx: dict[str, Any]) -> str:
    payload = {key: ctx.get(key) for key in _SELECTOR_KEYS.get(storage_key, ())}
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha1(encoded.encode("utf-8")).hexdigest()


def _run_fragment(storage_key: str) -> None:
    selector_ctx: dict[str, Any] = {}
    if hasattr(st, "session_state"):
        raw = st.session_state.get(storage_key, {})
        if isinstance(raw, dict):
            selector_ctx = dict(raw)
    selector_signature = _selector_signature(storage_key, selector_ctx)
    ctx = _prepared_context(storage_key, selector_signature)
    if ctx is None:
        ctx = _rehydrate_fragment_ctx(storage_key, selector_ctx)
        ctx["_prepared_signature"] = selector_signature
        _remember_prepared_context(storage_key, selector_signature, ctx)
    else:
        ctx["_prepared_signature"] = selector_signature
    if hasattr(st, "session_state"):
        st.session_state[storage_key] = _session_selector_context(
            storage_key,
            selector_ctx,
            selector_signature=selector_signature,
        )
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
