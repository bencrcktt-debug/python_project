from __future__ import annotations

import hashlib
import importlib
import json
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


def configure_map_fragment_helpers(**helpers: Any) -> None:
    _HELPERS.update(helpers)


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
    return refreshed


def _run_fragment(storage_key: str) -> None:
    ctx = {}
    if hasattr(st, "session_state"):
        raw = st.session_state.get(storage_key, {})
        if isinstance(raw, dict):
            ctx = raw
        ctx = _refresh_map_runtime_context(ctx)
        st.session_state[storage_key] = ctx
    module = importlib.import_module("src.map_workspace_renderer")
    module.configure_helpers(**_HELPERS)
    module.render_map_workspace(ctx)


@st.fragment
def render_map_workspace_fragment(storage_key: str = "_map_workspace_ctx") -> None:
    _run_fragment(storage_key)
