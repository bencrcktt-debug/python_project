from __future__ import annotations

import hashlib
import importlib
import json
from typing import Any

import pandas as pd
from .page_fragments import merge_fragment_session_context

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
_TRANSIENT_CONTEXTS: dict[str, dict[str, Any]] = {}
_PREPARED_MAP_CONTEXT_CACHE: dict[str, dict[str, Any]] = {}


def configure_map_fragment_helpers(**helpers: Any) -> None:
    _HELPERS.update(helpers)


def remember_map_workspace_transient_context(storage_key: str, ctx: dict[str, Any]) -> None:
    _TRANSIENT_CONTEXTS[storage_key] = dict(ctx or {})


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


def _remember_prepared_context(runtime_signature: str, ctx: dict[str, Any]) -> None:
    stale_keys = [key for key in _PREPARED_MAP_CONTEXT_CACHE.keys() if key != runtime_signature]
    for key in stale_keys:
        _PREPARED_MAP_CONTEXT_CACHE.pop(key, None)
    _PREPARED_MAP_CONTEXT_CACHE[runtime_signature] = _clone_cache_value(ctx)


def _prepared_context(runtime_signature: str) -> dict[str, Any] | None:
    cached = _PREPARED_MAP_CONTEXT_CACHE.get(runtime_signature)
    if cached is None:
        return None
    return _clone_cache_value(cached)


def _build_forensics_source_signature(atlas_bundle: Any) -> str:
    spend_lookup = getattr(atlas_bundle, "spend_lookup", {}) or {}
    normalized_spend = []
    if isinstance(spend_lookup, dict):
        for client, payload in sorted(spend_lookup.items(), key=lambda item: str(item[0]).strip().lower()):
            payload_dict = payload if isinstance(payload, dict) else {}
            normalized_spend.append(
                {
                    "client": str(client).strip(),
                    "entity_type": str(payload_dict.get("EntityType", "")).strip(),
                    "low": round(float(payload_dict.get("Low", 0.0) or 0.0), 2),
                    "high": round(float(payload_dict.get("High", 0.0) or 0.0), 2),
                    "lobbyists": int(payload_dict.get("Lobbyists", 0) or 0),
                }
            )
    payload = {
        "map_payload_signature": str(getattr(atlas_bundle, "map_payload_signature", "")).strip(),
        "spend_lookup": normalized_spend,
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(encoded.encode("utf-8")).hexdigest()


def _build_runtime_signature(path: str, selected_subdivision_signature: str) -> str:
    payload = {
        "path": str(path or "").strip(),
        "scope": str(st.session_state.get("map_scope", "")).strip(),
        "session": str(st.session_state.get("map_session", "")).strip(),
        "selected_subdivision_signature": str(selected_subdivision_signature or "").strip(),
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(encoded.encode("utf-8")).hexdigest()


def _refresh_map_runtime_context(ctx: dict[str, Any]) -> dict[str, Any]:
    required = (
        "PATH",
        "get_map_state",
        "_tfl_session_for_filter",
        "_map_runtime",
        "get_map_forensics_bundle",
        "get_map_atlas_bundle",
    )
    if any(name not in _HELPERS for name in required):
        return ctx

    try:
        path = str(_HELPERS["PATH"])
        map_state = _HELPERS["get_map_state"](path)
        tfl_sessions = set(getattr(map_state, "map_sessions", []) or [])
        session_for_filter = _HELPERS["_tfl_session_for_filter"](
            st.session_state.get("map_session"),
            tfl_sessions,
        )
        selected_subdivision_signature = _HELPERS["_map_runtime"].build_selected_subdivision_signature(
            st.session_state.get("map_selected_subdivision_context", {}),
        )
        runtime_signature = _build_runtime_signature(path, selected_subdivision_signature)
        cached = _prepared_context(runtime_signature)
        if cached is not None:
            refreshed = cached
            docket = st.session_state.get("map_watchlist", [])
            docket_count = len(docket) if isinstance(docket, list) else 0
            subdivision_matches = refreshed.get("subdivision_matches")
            atlas_count = len(subdivision_matches) if hasattr(subdivision_matches, "empty") and not subdivision_matches.empty else 0
            refreshed.update(
                {
                    "tfl_sessions": tfl_sessions,
                    "session_for_filter": session_for_filter,
                    "selected_subdivision_signature": selected_subdivision_signature,
                    "_map_runtime_signature": runtime_signature,
                    "_atlas_count": atlas_count,
                    "_docket_count": docket_count,
                    "_atlas_label": f"\U0001f5fa\ufe0f Coverage Atlas ({atlas_count:,})",
                    "_forensics_label": "\U0001f50d Address Forensics",
                    "_docket_label": (
                        f"\U0001f4cb Case Docket ({docket_count:,})"
                        if docket_count
                        else "\U0001f4cb Case Docket"
                    ),
                }
            )
            return refreshed
        map_forensics_bundle = _HELPERS["get_map_forensics_bundle"](
            path,
            str(st.session_state.get("map_scope", "")),
            session_for_filter,
            selected_subdivision_signature,
        )
        atlas_bundle = _HELPERS["get_map_atlas_bundle"](
            path,
            str(st.session_state.get("map_scope", "")),
            session_for_filter,
        )
    except Exception:
        return ctx

    subdivision_matches = map_forensics_bundle.subdivision_matches.copy()
    docket = st.session_state.get("map_watchlist", [])
    docket_count = len(docket) if isinstance(docket, list) else 0
    atlas_count = len(subdivision_matches) if not subdivision_matches.empty else 0
    forensics_source_signature = _build_forensics_source_signature(atlas_bundle)
    if str(ctx.get("_map_forensics_source_signature", "")).strip() != forensics_source_signature:
        st.session_state.pop("_mp5_forensics_bundle_v1", None)
        st.session_state.pop("_mp5_forensics_rows_v1", None)
        st.session_state.pop("_mp5_filtered_forensics_bundle_v1", None)

    refreshed = dict(ctx)
    refreshed.update(
        {
            "tfl_sessions": tfl_sessions,
            "session_for_filter": session_for_filter,
            "selected_subdivision_signature": selected_subdivision_signature,
            "map_forensics_bundle": map_forensics_bundle,
            "atlas_bundle": atlas_bundle,
            "totals": map_forensics_bundle.totals.copy(),
            "tfl_spend": map_forensics_bundle.tfl_spend.copy(),
            "subdivision_matches": subdivision_matches,
            "matched_clients": set(map_forensics_bundle.matched_clients),
            "total_tfl": int(map_forensics_bundle.total_tfl or 0),
            "total_high": float(map_forensics_bundle.total_high or 0.0),
            "mapped_high": float(map_forensics_bundle.mapped_high or 0.0),
            "mapped_rate": float(map_forensics_bundle.mapped_rate or 0.0),
            "unmapped_count": int(map_forensics_bundle.unmapped_count or 0),
            "hotspot_label": map_forensics_bundle.hotspot_label or "--",
            "hotspot_high": float(map_forensics_bundle.hotspot_high or 0.0),
            "_map_runtime_signature": runtime_signature,
            "_map_forensics_source_signature": forensics_source_signature,
            "_atlas_count": atlas_count,
            "_docket_count": docket_count,
            "_atlas_label": f"\U0001f5fa\ufe0f Coverage Atlas ({atlas_count:,})",
            "_forensics_label": "\U0001f50d Address Forensics",
            "_docket_label": (
                f"\U0001f4cb Case Docket ({docket_count:,})"
                if docket_count
                else "\U0001f4cb Case Docket"
            ),
        }
    )
    _remember_prepared_context(runtime_signature, refreshed)
    return refreshed


def _run_fragment(storage_key: str) -> None:
    persisted_ctx: dict[str, Any] = {}
    if hasattr(st, "session_state"):
        raw = st.session_state.get(storage_key, {})
        if isinstance(raw, dict):
            persisted_ctx = dict(raw)
    ctx = dict(persisted_ctx)
    ctx.update(_TRANSIENT_CONTEXTS.get(storage_key, {}))
    ctx = _refresh_map_runtime_context(ctx)
    ctx.update(_TRANSIENT_CONTEXTS.get(storage_key, {}))
    if hasattr(st, "session_state"):
        st.session_state[storage_key] = {
            "PATH": persisted_ctx.get("PATH", ctx.get("PATH", "")),
            "_map_runtime_signature": ctx.get("_map_runtime_signature", ""),
            "_map_forensics_source_signature": ctx.get("_map_forensics_source_signature", ""),
        }
    module = importlib.import_module("src.map_workspace_renderer")
    module.configure_helpers(**_HELPERS)
    module.render_map_workspace(ctx)


@st.fragment
def render_map_workspace_fragment(storage_key: str = "_map_workspace_ctx") -> None:
    _run_fragment(storage_key)
