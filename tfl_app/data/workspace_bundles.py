from __future__ import annotations

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

import tfl_app.data.state_store as _state_store
from tfl_app.map.reference_runtime import get_reference_snapshot_version
from tfl_app.data.workspace_bundle_builders import client as _client_builder
from tfl_app.data.workspace_bundle_builders import lobby as _lobby_builder
from tfl_app.data.workspace_bundle_builders import map as _map_builder
from tfl_app.data.workspace_bundle_builders import member as _member_builder
from tfl_app.data.workspace_bundle_builders import shared as _shared_builder

get_dataset_version = _state_store.get_dataset_version

_build_client_scope_stats = _shared_builder.build_client_scope_stats
_build_lobby_scope_stats = _shared_builder.build_lobby_scope_stats
_detail_base_data = _shared_builder.detail_base_data
_client_workspace_data = _shared_builder.client_workspace_data
_member_workspace_data = _shared_builder.member_workspace_data


@st.cache_resource(show_spinner=False, max_entries=16)
def _get_map_atlas_bundle_cached(
    path: str,
    scope: str,
    session_for_filter: str | None,
    data_version: str,
    reference_version: str,
):
    return _map_builder.build_map_atlas_bundle(
        path,
        scope,
        session_for_filter,
        data_version,
        reference_version,
    )


def get_map_atlas_bundle(path: str, scope: str, session_for_filter: str | None):
    return _get_map_atlas_bundle_cached(
        path,
        scope,
        session_for_filter,
        get_dataset_version(path),
        get_reference_snapshot_version(),
    )


get_map_atlas_bundle.clear = getattr(_get_map_atlas_bundle_cached, "clear", lambda: None)


@st.cache_data(show_spinner=False, max_entries=16)
def _get_client_scope_bundle_cached(path: str, scope: str, session_val: str | None, data_version: str):
    app_state = _state_store._get_app_state_cached(path, data_version)
    return _client_builder.build_client_scope_bundle(app_state, scope, session_val)


def get_client_scope_bundle(path: str, scope: str, session_val: str | None):
    return _get_client_scope_bundle_cached(path, scope, session_val, get_dataset_version(path))


get_client_scope_bundle.clear = getattr(_get_client_scope_bundle_cached, "clear", lambda: None)


@st.cache_data(show_spinner=False, max_entries=16)
def _get_lobby_scope_bundle_cached(path: str, scope: str, session_val: str | None, data_version: str):
    app_state = _state_store._get_app_state_cached(path, data_version)
    return _lobby_builder.build_lobby_scope_bundle(app_state, scope, session_val)


def get_lobby_scope_bundle(path: str, scope: str, session_val: str | None):
    return _get_lobby_scope_bundle_cached(path, scope, session_val, get_dataset_version(path))


get_lobby_scope_bundle.clear = getattr(_get_lobby_scope_bundle_cached, "clear", lambda: None)


@st.cache_data(show_spinner=False, max_entries=16)
def _get_member_session_bundle_cached(path: str, session_val: str | None, data_version: str):
    app_state = _state_store._get_app_state_cached(path, data_version)
    return _member_builder.build_member_session_bundle(path, app_state, data_version, session_val)


def get_member_session_bundle(path: str, session_val: str | None):
    return _get_member_session_bundle_cached(path, session_val, get_dataset_version(path))


get_member_session_bundle.clear = getattr(_get_member_session_bundle_cached, "clear", lambda: None)


def get_witness_name_match_table(path: str, session_val: str | None) -> pd.DataFrame:
    return _shared_builder.witness_name_match_table(path, get_dataset_version(path), session_val)


get_witness_name_match_table.clear = getattr(_state_store._get_witness_rows_for_session, "clear", lambda: None)
if hasattr(_state_store._get_session_overlay_bundle, "clear"):
    get_witness_name_match_table.clear = _state_store._get_session_overlay_bundle.clear


def _lobby_workspace_data(
    app_state,
    path: str,
    session_val: str | None,
    *,
    include_witness_name_columns: bool,
):
    return _shared_builder.lobby_workspace_data(
        app_state,
        path,
        session_val,
        include_witness_name_columns=include_witness_name_columns,
        witness_name_match_loader=get_witness_name_match_table,
    )


@st.cache_data(show_spinner=False, max_entries=16)
def _get_client_workspace_detail_bundle_cached(
    path: str,
    session_val: str | None,
    tfl_session_val: str | None,
    client_name: str,
    data_version: str,
):
    app_state = _state_store._get_app_state_cached(path, data_version)
    return _client_builder.build_client_workspace_detail_bundle(
        app_state,
        path,
        session_val,
        tfl_session_val,
        client_name,
    )


def get_client_workspace_detail_bundle(path: str, session_val: str | None, tfl_session_val: str | None, client_name: str):
    return _get_client_workspace_detail_bundle_cached(path, session_val, tfl_session_val, client_name, get_dataset_version(path))


get_client_workspace_detail_bundle.clear = getattr(_get_client_workspace_detail_bundle_cached, "clear", lambda: None)


@st.cache_data(show_spinner=False, max_entries=16)
def _get_member_workspace_detail_bundle_cached(
    path: str,
    session_val: str | None,
    tfl_session_val: str | None,
    member_name: str,
    data_version: str,
):
    app_state = _state_store._get_app_state_cached(path, data_version)
    return _member_builder.build_member_workspace_detail_bundle(
        app_state,
        path,
        session_val,
        tfl_session_val,
        member_name,
    )


def get_member_workspace_detail_bundle(path: str, session_val: str | None, tfl_session_val: str | None, member_name: str):
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
):
    app_state = _state_store._get_app_state_cached(path, data_version)
    return _lobby_builder.build_lobby_workspace_detail_bundle(
        app_state,
        path,
        session_val,
        tfl_session_val,
        lobbyshort,
        typed_norms_tuple,
        selected_names,
        selected_filer_ids,
        witness_name_match_loader=get_witness_name_match_table,
    )


def get_lobby_workspace_detail_bundle(
    path: str,
    session_val: str | None,
    tfl_session_val: str | None,
    lobbyshort: str,
    typed_norms_tuple: tuple[str, ...],
    selected_names: tuple[str, ...],
    selected_filer_ids: tuple[int, ...],
):
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
):
    return _map_builder.build_map_forensics_bundle(
        path,
        scope,
        session_for_filter,
        selected_subdivision_signature,
        data_version,
        reference_version,
    )


def get_map_forensics_bundle(path: str, scope: str, session_for_filter: str | None, selected_subdivision_signature: str):
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
    "_state_store",
    "get_client_scope_bundle",
    "get_client_workspace_detail_bundle",
    "get_dataset_version",
    "get_lobby_scope_bundle",
    "get_lobby_workspace_detail_bundle",
    "get_map_atlas_bundle",
    "get_map_forensics_bundle",
    "get_member_session_bundle",
    "get_member_workspace_detail_bundle",
    "get_witness_name_match_table",
]
