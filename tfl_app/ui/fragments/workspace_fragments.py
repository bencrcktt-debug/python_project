from __future__ import annotations

import hashlib
import importlib
import json
from typing import Any

from tfl_app.services import WorkspaceServices
from tfl_app.ui.contexts import (
    AppLookupMaps,
    ClientWorkspacePreparedContext,
    ClientWorkspaceSelector,
    LobbyWorkspacePreparedContext,
    LobbyWorkspaceSelector,
    MemberWorkspacePreparedContext,
    MemberWorkspaceSelector,
)
from tfl_app.ui.fragments.prepared_cache import (
    get_scoped_prepared_context,
    remember_scoped_prepared_context,
)

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
_SELECTOR_TYPES = {
    "_client_workspace_ctx": ClientWorkspaceSelector,
    "_member_workspace_ctx": MemberWorkspaceSelector,
    "_lobby_workspace_ctx": LobbyWorkspaceSelector,
}
_PREPARED_CONTEXT_CACHE: dict[tuple[str, str], Any] = {}
_LEGACY_HELPER_SERVICES: WorkspaceServices | None = None


def configure_page_fragment_helpers(**helpers: Any) -> None:
    global _LEGACY_HELPER_SERVICES
    _LEGACY_HELPER_SERVICES = WorkspaceServices.build(**helpers)


def _resolve_legacy_services() -> WorkspaceServices:
    services = _LEGACY_HELPER_SERVICES
    if services is None:
        services = WorkspaceServices.build()
        configure_page_fragment_helpers(**dict(services.values))
    return services


def _merge_bundle_context(payload: dict[str, Any], bundle: Any) -> dict[str, Any]:
    merged = dict(payload)
    bundle_ctx = getattr(bundle, "context", None)
    if isinstance(bundle_ctx, dict):
        merged.update(bundle_ctx)
    return merged


def _selector_from_payload(storage_key: str, payload: dict[str, Any]) -> Any:
    selector_type = _SELECTOR_TYPES.get(storage_key)
    if selector_type is None:
        return payload
    return selector_type.from_payload(payload)


def _session_selector_context(
    storage_key: str,
    selector_or_payload: dict[str, Any] | Any,
    *,
    selector_signature: str | None = None,
) -> dict[str, Any]:
    selector = (
        selector_or_payload
        if hasattr(selector_or_payload, "to_payload")
        else _selector_from_payload(storage_key, dict(selector_or_payload or {}))
    )
    if hasattr(selector, "to_payload"):
        payload = selector.to_payload()
    else:
        keys = _SELECTOR_KEYS.get(storage_key, ())
        payload = {key: selector_or_payload.get(key) for key in keys if key in selector_or_payload}
    if selector_signature:
        payload["_prepared_signature"] = selector_signature
    return payload


def _remember_prepared_context(storage_key: str, selector_signature: str, value: Any) -> None:
    remember_scoped_prepared_context(_PREPARED_CONTEXT_CACHE, storage_key, selector_signature, value)


def _prepared_context(storage_key: str, selector_signature: str) -> Any | None:
    return get_scoped_prepared_context(_PREPARED_CONTEXT_CACHE, storage_key, selector_signature)


def merge_fragment_session_context(storage_key: str, selector_updates: dict[str, Any]) -> dict[str, Any]:
    current: dict[str, Any] = {}
    if hasattr(st, "session_state"):
        raw = st.session_state.get(storage_key, {})
        if isinstance(raw, dict):
            current = dict(raw)
    current.update(dict(selector_updates or {}))
    selector = _selector_from_payload(storage_key, current)
    payload = _session_selector_context(storage_key, selector)
    if hasattr(st, "session_state"):
        st.session_state[storage_key] = payload
    return dict(payload)


def _app_state_context(services: WorkspaceServices, path: str) -> dict[str, Any]:
    get_app_state = services.get("get_app_state")
    if not path or not callable(get_app_state):
        return {}

    app_state = get_app_state(path)
    return {
        "name_to_short": getattr(app_state, "name_to_short", {}) or {},
        "short_to_names": getattr(app_state, "short_to_names", {}) or {},
        "filerid_to_short": getattr(app_state, "filerid_to_short", {}) or {},
    }


def _rehydrate_client_workspace_ctx(
    services: WorkspaceServices,
    selector: ClientWorkspaceSelector,
) -> ClientWorkspacePreparedContext | ClientWorkspaceSelector:
    path = selector.path
    scope = selector.client_scope
    session = selector.client_session
    client_name = selector.client_name
    tfl_session_val = selector.tfl_session_val
    get_scope_bundle = services.get("get_client_scope_bundle")
    get_detail_bundle = services.get("get_client_workspace_detail_bundle")
    if not path or scope is None or not callable(get_scope_bundle) or not callable(get_detail_bundle):
        return selector

    scope_bundle = get_scope_bundle(path, scope, tfl_session_val)
    detail_bundle = get_detail_bundle(path, session, tfl_session_val, client_name)
    payload = _app_state_context(services, path)
    payload = _merge_bundle_context(payload, detail_bundle)
    payload.update(
        {
            "client_detail_bundle": detail_bundle,
            "client_scope_bundle": scope_bundle,
            "all_clients": scope_bundle.overview,
            "all_stats": scope_bundle.stats,
            "_prepared_client_workspace": True,
        }
    )
    return ClientWorkspacePreparedContext(
        selector=selector,
        app_lookups=AppLookupMaps.from_mapping(payload),
        scope_bundle=scope_bundle,
        detail_bundle=detail_bundle,
        payload=payload,
    )


def _rehydrate_member_workspace_ctx(
    services: WorkspaceServices,
    selector: MemberWorkspaceSelector,
) -> MemberWorkspacePreparedContext | MemberWorkspaceSelector:
    path = selector.path
    session = selector.member_session
    member_name = selector.member_name
    tfl_session_val = selector.tfl_session_val
    get_session_bundle = services.get("get_member_session_bundle")
    get_detail_bundle = services.get("get_member_workspace_detail_bundle")
    if not path or not callable(get_session_bundle) or not callable(get_detail_bundle):
        return selector

    session_bundle = get_session_bundle(path, session)
    detail_bundle = get_detail_bundle(path, session, tfl_session_val, member_name)
    payload = _app_state_context(services, path)
    payload = _merge_bundle_context(payload, detail_bundle)
    payload.update(
        {
            "member_detail_bundle": detail_bundle,
            "member_session_bundle": session_bundle,
            "all_legislators": session_bundle.all_legislators,
            "all_leg_stats": session_bundle.stats,
            "_prepared_member_workspace": True,
        }
    )
    return MemberWorkspacePreparedContext(
        selector=selector,
        app_lookups=AppLookupMaps.from_mapping(payload),
        session_bundle=session_bundle,
        detail_bundle=detail_bundle,
        payload=payload,
    )


def _rehydrate_lobby_workspace_ctx(
    services: WorkspaceServices,
    selector: LobbyWorkspaceSelector,
) -> LobbyWorkspacePreparedContext | LobbyWorkspaceSelector:
    path = selector.path
    scope = selector.scope
    session = selector.session
    tfl_session_val = selector.tfl_session_val
    get_scope_bundle = services.get("get_lobby_scope_bundle")
    get_detail_bundle = services.get("get_lobby_workspace_detail_bundle")
    if not path or scope is None or not callable(get_scope_bundle) or not callable(get_detail_bundle):
        return selector

    scope_bundle = get_scope_bundle(path, scope, tfl_session_val)
    detail_bundle = get_detail_bundle(
        path,
        session,
        tfl_session_val,
        selector.lobbyshort,
        selector.typed_norms_tuple,
        selector.selected_names,
        selector.selected_filer_ids,
    )
    payload = _app_state_context(services, path)
    payload = _merge_bundle_context(payload, detail_bundle)
    payload.update(
        {
            "lobby_detail_bundle": detail_bundle,
            "lobby_scope_bundle": scope_bundle,
            "all_pivot": scope_bundle.all_pivot,
            "all_stats": scope_bundle.all_stats,
            "_prepared_lobby_workspace": True,
        }
    )
    return LobbyWorkspacePreparedContext(
        selector=selector,
        app_lookups=AppLookupMaps.from_mapping(payload),
        scope_bundle=scope_bundle,
        detail_bundle=detail_bundle,
        payload=payload,
    )


def _rehydrate_fragment_ctx(*args: Any) -> Any:
    if len(args) == 3 and isinstance(args[0], WorkspaceServices):
        services = args[0]
        storage_key = str(args[1])
        selector = _selector_from_payload(storage_key, dict(args[2] or {}))
    elif len(args) == 2:
        services = _resolve_legacy_services()
        storage_key = str(args[0])
        selector = _selector_from_payload(storage_key, dict(args[1] or {}))
    else:
        raise TypeError("_rehydrate_fragment_ctx expects (services, storage_key, ctx) or (storage_key, ctx)")

    if storage_key == "_client_workspace_ctx":
        return _rehydrate_client_workspace_ctx(services, selector)
    if storage_key == "_member_workspace_ctx":
        return _rehydrate_member_workspace_ctx(services, selector)
    if storage_key == "_lobby_workspace_ctx":
        return _rehydrate_lobby_workspace_ctx(services, selector)
    return selector


def _selector_signature(storage_key: str, selector_payload: dict[str, Any]) -> str:
    payload = {key: selector_payload.get(key) for key in _SELECTOR_KEYS.get(storage_key, ())}
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha1(encoded.encode("utf-8")).hexdigest()


def _run_fragment(services: WorkspaceServices, storage_key: str) -> None:
    selector_payload: dict[str, Any] = {}
    if hasattr(st, "session_state"):
        raw = st.session_state.get(storage_key, {})
        if isinstance(raw, dict):
            selector_payload = dict(raw)
    selector = _selector_from_payload(storage_key, selector_payload)
    selector_signature = _selector_signature(storage_key, selector_payload)
    ctx = _prepared_context(storage_key, selector_signature)
    if ctx is None:
        ctx = _rehydrate_fragment_ctx(
            services,
            storage_key,
            selector.to_payload() if hasattr(selector, "to_payload") else selector_payload,
        )
        _remember_prepared_context(storage_key, selector_signature, ctx)
    if hasattr(st, "session_state"):
        st.session_state[storage_key] = _session_selector_context(
            storage_key,
            selector,
            selector_signature=selector_signature,
        )
    renderer_name = _RENDERERS.get(storage_key)
    if not renderer_name:
        return
    module = importlib.import_module("tfl_app.ui.renderers")
    getattr(module, renderer_name)(ctx, services)


@st.fragment
def render_client_workspace_fragment(services: WorkspaceServices, storage_key: str = "_client_workspace_ctx") -> None:
    _run_fragment(services, storage_key)


@st.fragment
def render_member_workspace_fragment(services: WorkspaceServices, storage_key: str = "_member_workspace_ctx") -> None:
    _run_fragment(services, storage_key)


@st.fragment
def render_lobby_workspace_fragment(services: WorkspaceServices, storage_key: str = "_lobby_workspace_ctx") -> None:
    _run_fragment(services, storage_key)
