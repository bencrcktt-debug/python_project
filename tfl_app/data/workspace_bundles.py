from __future__ import annotations

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
        cache_resource = _CacheStub()

    st = _StreamlitStub()

import tfl_app.bundles.page_bundles as _page_bundles
import tfl_app.bundles.page_detail_bundles as _page_detail_bundles
import tfl_app.data.state_store as _state_store
import tfl_app.map.runtime as _map_runtime
import tfl_app.map.state as _map_page_state
from tfl_app.data.catalog import CLIENT_DETAIL_TABLE_KEYS, LOBBY_DETAIL_TABLE_KEYS, MEMBER_DETAIL_TABLE_KEYS
from tfl_app.map.reference_runtime import get_reference_snapshot_version
from tfl_app.search.indexes import AppState

get_dataset_version = _state_store.get_dataset_version


def _build_client_scope_stats(overview: pd.DataFrame) -> dict[str, Any]:
    if overview.empty:
        return {}
    return {
        "total_clients": int(overview["Client"].nunique()),
        "tfl_clients": int((overview["IsTFL"] == 1).sum()),
        "private_clients": int((overview["IsTFL"] == 0).sum()),
        "tfl_low_total": float(overview.loc[overview["IsTFL"] == 1, "Low"].sum()),
        "tfl_high_total": float(overview.loc[overview["IsTFL"] == 1, "High"].sum()),
        "pri_low_total": float(overview.loc[overview["IsTFL"] == 0, "Low"].sum()),
        "pri_high_total": float(overview.loc[overview["IsTFL"] == 0, "High"].sum()),
    }


def _build_lobby_scope_stats(all_pivot: pd.DataFrame) -> dict[str, Any]:
    if all_pivot.empty:
        return {}
    return {
        "total_lobbyists": int(all_pivot["LobbyShort"].nunique()),
        "has_tfl": int(all_pivot["Has_TFL"].sum()),
        "only_private": int(all_pivot["Only_Private"].sum()),
        "only_tfl": int(all_pivot["Only_TFL"].sum()),
        "mixed": int(all_pivot["Mixed"].sum()),
        "tfl_low_total": float(all_pivot["Low_TFL"].sum()),
        "tfl_high_total": float(all_pivot["High_TFL"].sum()),
        "pri_low_total": float(all_pivot["Low_Private"].sum()),
        "pri_high_total": float(all_pivot["High_Private"].sum()),
    }


@st.cache_resource(show_spinner=False, max_entries=16)
def _get_map_atlas_bundle_cached(
    path: str,
    scope: str,
    session_for_filter: str | None,
    data_version: str,
    reference_version: str,
) -> _map_page_state.AtlasBundle:
    map_state = _state_store._get_map_state_cached(path, data_version, reference_version)
    active_tfl_clients = _map_page_state.resolve_active_tfl_clients(
        map_state,
        scope=scope,
        session_for_filter=session_for_filter,
    )
    client_edges = _state_store._build_map_client_edges_cached(active_tfl_clients)
    return _map_page_state.build_atlas_bundle(
        map_state,
        scope=scope,
        session_for_filter=session_for_filter,
        client_subdivision_edges_all=client_edges,
    )


def get_map_atlas_bundle(path: str, scope: str, session_for_filter: str | None) -> _map_page_state.AtlasBundle:
    return _get_map_atlas_bundle_cached(
        path,
        scope,
        session_for_filter,
        get_dataset_version(path),
        get_reference_snapshot_version(),
    )


get_map_atlas_bundle.clear = getattr(_get_map_atlas_bundle_cached, "clear", lambda: None)


@st.cache_data(show_spinner=False, max_entries=16)
def _get_client_scope_bundle_cached(path: str, scope: str, session_val: str | None, data_version: str) -> _page_bundles.ClientScopeBundle:
    app_state = _state_store._get_app_state_cached(path, data_version)
    overview = app_state.client_scope_overview_all
    session = str(session_val or "").strip()
    if scope == "This Session" and session:
        overview = app_state.client_scope_overview_by_session
        overview = overview[overview["SessionKey"].astype(str) == session].drop(columns=["SessionKey"], errors="ignore")
    overview = overview.reset_index(drop=True).copy()
    return _page_bundles.ClientScopeBundle(
        overview=overview,
        stats=_build_client_scope_stats(overview),
        category_chart_data=app_state.client_category_chart_data,
    )


def get_client_scope_bundle(path: str, scope: str, session_val: str | None) -> _page_bundles.ClientScopeBundle:
    return _get_client_scope_bundle_cached(path, scope, session_val, get_dataset_version(path))


get_client_scope_bundle.clear = getattr(_get_client_scope_bundle_cached, "clear", lambda: None)


@st.cache_data(show_spinner=False, max_entries=16)
def _get_lobby_scope_bundle_cached(path: str, scope: str, session_val: str | None, data_version: str) -> _page_bundles.LobbyScopeBundle:
    app_state = _state_store._get_app_state_cached(path, data_version)
    session = str(session_val or "").strip()
    all_pivot = app_state.lobby_scope_pivot_all
    top_clients = app_state.lobby_scope_top_clients_all
    if scope == "This Session" and session:
        all_pivot = app_state.lobby_scope_pivot_by_session
        all_pivot = all_pivot[all_pivot["SessionKey"].astype(str) == session].drop(columns=["SessionKey"], errors="ignore")
        top_clients = app_state.lobby_scope_top_clients_by_session
        top_clients = top_clients[top_clients["SessionKey"].astype(str) == session].drop(columns=["SessionKey"], errors="ignore")
    all_pivot = all_pivot.reset_index(drop=True).copy()
    top_clients = top_clients.reset_index(drop=True).copy()
    return _page_bundles.LobbyScopeBundle(
        all_pivot=all_pivot,
        all_stats=_build_lobby_scope_stats(all_pivot),
        trend_group=app_state.lobby_scope_trend_group,
        top_clients=top_clients,
        lobby_display=app_state.lobby_display,
    )


def get_lobby_scope_bundle(path: str, scope: str, session_val: str | None) -> _page_bundles.LobbyScopeBundle:
    return _get_lobby_scope_bundle_cached(path, scope, session_val, get_dataset_version(path))


get_lobby_scope_bundle.clear = getattr(_get_lobby_scope_bundle_cached, "clear", lambda: None)


@st.cache_data(show_spinner=False, max_entries=16)
def _get_member_session_bundle_cached(path: str, session_val: str | None, data_version: str) -> _page_bundles.MemberSessionBundle:
    app_state = _state_store._get_app_state_cached(path, data_version)
    witness_rows = _state_store._get_witness_rows_for_session(path, data_version, session_val, include_name_columns=False)
    return _page_bundles.build_member_session_bundle(app_state.author_bills_all, witness_rows, str(session_val or ""))


def get_member_session_bundle(path: str, session_val: str | None) -> _page_bundles.MemberSessionBundle:
    return _get_member_session_bundle_cached(path, session_val, get_dataset_version(path))


get_member_session_bundle.clear = getattr(_get_member_session_bundle_cached, "clear", lambda: None)


def _detail_base_data(app_state: AppState, path: str) -> dict[str, object]:
    return {
        "Lobby_TFL_Client_All": _state_store.get_app_table_readonly(path, "Lobby_TFL_Client_All"),
        "Staff_All": _state_store.get_app_table_readonly(path, "Staff_All"),
        "filerid_to_short": app_state.filerid_to_short,
    }


def _client_workspace_data(app_state: AppState, path: str, session_val: str | None) -> dict[str, object]:
    data = _detail_base_data(app_state, path)
    data.update(_state_store._get_workspace_table_overlays_for_keys(path, app_state.data_version, session_val, CLIENT_DETAIL_TABLE_KEYS))
    return data


def _member_workspace_data(app_state: AppState, path: str, session_val: str | None) -> dict[str, object]:
    data = _detail_base_data(app_state, path)
    data.update(_state_store._get_workspace_table_overlays_for_keys(path, app_state.data_version, session_val, MEMBER_DETAIL_TABLE_KEYS))
    return data


def get_witness_name_match_table(path: str, session_val: str | None) -> pd.DataFrame:
    overlay_bundle = _state_store._get_session_overlay_bundle(path, get_dataset_version(path), session_val)
    return overlay_bundle.witness_search.copy()


get_witness_name_match_table.clear = getattr(_state_store._get_witness_rows_for_session, "clear", lambda: None)
if hasattr(_state_store._get_session_overlay_bundle, "clear"):
    get_witness_name_match_table.clear = _state_store._get_session_overlay_bundle.clear


def _lobby_workspace_data(
    app_state: AppState,
    path: str,
    session_val: str | None,
    *,
    include_witness_name_columns: bool,
) -> dict[str, object]:
    data = _detail_base_data(app_state, path)
    overlays = _state_store._get_workspace_table_overlays_for_keys(path, app_state.data_version, session_val, LOBBY_DETAIL_TABLE_KEYS)
    if include_witness_name_columns:
        overlays["Wit_All"] = get_witness_name_match_table(path, session_val)
    data.update(overlays)
    return data


@st.cache_data(show_spinner=False, max_entries=16)
def _get_client_workspace_detail_bundle_cached(
    path: str,
    session_val: str | None,
    tfl_session_val: str | None,
    client_name: str,
    data_version: str,
) -> _page_detail_bundles.ClientWorkspaceDetailBundle:
    app_state = _state_store._get_app_state_cached(path, data_version)
    return _page_detail_bundles.build_client_workspace_detail_bundle(
        _client_workspace_data(app_state, path, session_val),
        name_to_short=app_state.name_to_short,
        session=str(session_val or ""),
        tfl_session_val=tfl_session_val,
        client_name=str(client_name or ""),
    )


def get_client_workspace_detail_bundle(path: str, session_val: str | None, tfl_session_val: str | None, client_name: str) -> _page_detail_bundles.ClientWorkspaceDetailBundle:
    return _get_client_workspace_detail_bundle_cached(path, session_val, tfl_session_val, client_name, get_dataset_version(path))


get_client_workspace_detail_bundle.clear = getattr(_get_client_workspace_detail_bundle_cached, "clear", lambda: None)


@st.cache_data(show_spinner=False, max_entries=16)
def _get_member_workspace_detail_bundle_cached(
    path: str,
    session_val: str | None,
    tfl_session_val: str | None,
    member_name: str,
    data_version: str,
) -> _page_detail_bundles.MemberWorkspaceDetailBundle:
    app_state = _state_store._get_app_state_cached(path, data_version)
    return _page_detail_bundles.build_member_workspace_detail_bundle(
        _member_workspace_data(app_state, path, session_val),
        author_bills_all=app_state.author_bills_all,
        name_to_short=app_state.name_to_short,
        short_to_names=app_state.short_to_names,
        initial_to_short=app_state.initial_to_short,
        session=str(session_val or ""),
        tfl_session_val=tfl_session_val,
        member_name=str(member_name or ""),
    )


def get_member_workspace_detail_bundle(path: str, session_val: str | None, tfl_session_val: str | None, member_name: str) -> _page_detail_bundles.MemberWorkspaceDetailBundle:
    return _get_member_workspace_detail_bundle_cached(path, session_val, tfl_session_val, member_name, get_dataset_version(path))


get_member_workspace_detail_bundle.clear = getattr(_get_member_workspace_detail_bundle_cached, "clear", lambda: None)


@st.cache_data(show_spinner=False, max_entries=16)
def _get_lobby_workspace_detail_bundle_cached(
    path: str,
    session_val: str | None,
    tfl_session_val: str | None,
    lobbyshort: str,
    typed_norms_tuple: tuple[str, ...],
    selected_names: tuple[str, ...],
    selected_filer_ids: tuple[int, ...],
    data_version: str,
) -> _page_detail_bundles.LobbyWorkspaceDetailBundle:
    app_state = _state_store._get_app_state_cached(path, data_version)
    return _page_detail_bundles.build_lobby_workspace_detail_bundle(
        _lobby_workspace_data(
            app_state,
            path,
            session_val,
            include_witness_name_columns=bool(selected_names),
        ),
        name_to_short=app_state.name_to_short,
        short_to_names=app_state.short_to_names,
        session=str(session_val or ""),
        tfl_session_val=tfl_session_val,
        lobbyshort=str(lobbyshort or ""),
        typed_norms_tuple=typed_norms_tuple or tuple(),
        selected_names=selected_names or tuple(),
        selected_filer_ids=selected_filer_ids or tuple(),
    )


def get_lobby_workspace_detail_bundle(
    path: str,
    session_val: str | None,
    tfl_session_val: str | None,
    lobbyshort: str,
    typed_norms_tuple: tuple[str, ...],
    selected_names: tuple[str, ...],
    selected_filer_ids: tuple[int, ...],
) -> _page_detail_bundles.LobbyWorkspaceDetailBundle:
    return _get_lobby_workspace_detail_bundle_cached(
        path,
        session_val,
        tfl_session_val,
        lobbyshort,
        typed_norms_tuple,
        selected_names,
        selected_filer_ids,
        get_dataset_version(path),
    )


get_lobby_workspace_detail_bundle.clear = getattr(_get_lobby_workspace_detail_bundle_cached, "clear", lambda: None)


@st.cache_data(show_spinner=False, max_entries=16)
def _get_map_forensics_bundle_cached(
    path: str,
    scope: str,
    session_for_filter: str | None,
    selected_subdivision_signature: str,
    data_version: str,
    reference_version: str,
) -> _map_runtime.MapForensicsBundle:
    atlas_bundle = _get_map_atlas_bundle_cached(path, scope, session_for_filter, data_version, reference_version)
    return _map_runtime.build_map_forensics_bundle(
        atlas_bundle,
        selected_subdivision_signature=selected_subdivision_signature,
    )


def get_map_forensics_bundle(path: str, scope: str, session_for_filter: str | None, selected_subdivision_signature: str) -> _map_runtime.MapForensicsBundle:
    return _get_map_forensics_bundle_cached(
        path,
        scope,
        session_for_filter,
        selected_subdivision_signature,
        get_dataset_version(path),
        get_reference_snapshot_version(),
    )


get_map_forensics_bundle.clear = getattr(_get_map_forensics_bundle_cached, "clear", lambda: None)


__all__ = [
    "_build_client_scope_stats",
    "_build_lobby_scope_stats",
    "_client_workspace_data",
    "_detail_base_data",
    "_get_client_scope_bundle_cached",
    "_get_client_workspace_detail_bundle_cached",
    "_get_lobby_scope_bundle_cached",
    "_get_lobby_workspace_detail_bundle_cached",
    "_get_map_atlas_bundle_cached",
    "_get_map_forensics_bundle_cached",
    "_get_member_session_bundle_cached",
    "_get_member_workspace_detail_bundle_cached",
    "_lobby_workspace_data",
    "_member_workspace_data",
    "get_client_scope_bundle",
    "get_client_workspace_detail_bundle",
    "get_lobby_scope_bundle",
    "get_lobby_workspace_detail_bundle",
    "get_map_atlas_bundle",
    "get_map_forensics_bundle",
    "get_member_session_bundle",
    "get_member_workspace_detail_bundle",
    "get_witness_name_match_table",
]
