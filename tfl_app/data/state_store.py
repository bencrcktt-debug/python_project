from __future__ import annotations

import os
from dataclasses import dataclass

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

        @staticmethod
        def error(*args, **kwargs) -> None:
            return None

        @staticmethod
        def stop() -> None:
            raise RuntimeError("streamlit stop")

    st = _StreamlitStub()

import tfl_app.data.loaders as _loaders
import tfl_app.map.state as _map_page_state
import tfl_app.shared.names as _shared_names
from tfl_app.data.catalog import (
    APP_STATE_BOOTSTRAP_COLUMNS,
    BASE_APP_STATE_TABLE_KEYS,
    FILER_NORMALIZED_TABLE_KEYS,
    SESSION_SCOPED_TABLE_KEYS,
    WORKBOOK_TABLE_COLUMNS,
)
from tfl_app.map.geo_runtime import (
    build_tfl_political_subdivision_matches,
    classify_requested_entity_type,
)
from tfl_app.map.reference_runtime import (
    fetch_nctcog_transit_provider_centroids,
    fetch_tceq_groundwater_district_centroids,
    fetch_tceq_water_district_centroids,
    fetch_tea_county_centroids,
    fetch_tea_school_district_centroids,
    fetch_texas_city_centroids,
    fetch_texas_junior_college_centroids,
    fetch_texas_navigation_district_centroids,
    fetch_texas_rma_centroids,
    fetch_txdot_seaport_centroids,
    get_reference_snapshot_version,
)
from tfl_app.search.indexes import (
    AppState,
    _ensure_witness_search_columns,
    _fill_missing_witness_lobbyshorts,
    build_app_state,
)

_is_url = _loaders._is_url
_table_keys_tuple = _loaders._table_keys_tuple
_dedupe_columns = _loaders._dedupe_columns
_postprocess_table_for_state = _loaders._postprocess_table_for_state
_read_table_source = _loaders._read_table_source
_ensure_filer_base_columns = _loaders._ensure_filer_base_columns
get_dataset_version = _loaders.get_dataset_version


@dataclass(frozen=True)
class SessionOverlayBundle:
    session: str | None
    tables: dict[str, pd.DataFrame]
    witness_search: pd.DataFrame


@st.cache_resource(show_spinner=False, max_entries=128)
def _load_table_resource(path: str, table_key: str, data_version: str) -> pd.DataFrame:
    del data_version
    raw = _read_table_source(path, table_key, WORKBOOK_TABLE_COLUMNS.get(table_key, []))
    return _postprocess_table_for_state(table_key, raw)


def get_app_table(path: str, table_key: str, *, copy: bool = True) -> pd.DataFrame:
    data = _load_table_resource(path, table_key, get_dataset_version(path))
    return data.copy() if copy else data


def get_app_tables(path: str, keys: tuple[str, ...] | list[str], *, copy: bool = True) -> dict[str, pd.DataFrame]:
    return {key: get_app_table(path, key, copy=copy) for key in _table_keys_tuple(keys)}


def get_app_table_readonly(path: str, table_key: str) -> pd.DataFrame:
    return get_app_table(path, table_key, copy=False)


def get_app_tables_readonly(path: str, keys: tuple[str, ...] | list[str]) -> dict[str, pd.DataFrame]:
    return {key: get_app_table_readonly(path, key) for key in _table_keys_tuple(keys)}


@st.cache_resource(show_spinner=False, max_entries=64)
def _load_projected_table_resource(path: str, table_key: str, columns_key: tuple[str, ...], data_version: str) -> pd.DataFrame:
    del data_version
    raw = _read_table_source(path, table_key, list(columns_key))
    return _postprocess_table_for_state(table_key, raw)


def _get_app_state_bootstrap_tables(path: str, data_version: str, *, copy: bool = True) -> dict[str, pd.DataFrame]:
    tables: dict[str, pd.DataFrame] = {}
    for table_key in _table_keys_tuple(BASE_APP_STATE_TABLE_KEYS):
        columns = tuple(_dedupe_columns(APP_STATE_BOOTSTRAP_COLUMNS.get(table_key, WORKBOOK_TABLE_COLUMNS.get(table_key, []))))
        frame = _load_projected_table_resource(path, table_key, columns, data_version)
        tables[table_key] = frame.copy() if copy else frame
    tables["table_manifest"] = _loaders.get_table_manifest(path)
    return tables


def _filter_table_by_session(df: pd.DataFrame, session_val: str | None, *, copy: bool = True) -> pd.DataFrame:
    session = str(session_val or "").strip()
    if not session or not isinstance(df, pd.DataFrame) or df.empty:
        return df.copy() if copy else df
    if "SessionKey" in df.columns:
        session_key = df["SessionKey"]
        if session_key.hasnans:
            session_key = session_key.fillna("")
        out = df.loc[session_key == session]
        return out.copy() if copy else out
    if "Session" in df.columns:
        session_col = df["Session"].fillna("").astype(str).str.strip()
        out = df.loc[session_col == session]
        return out.copy() if copy else out
    if "session" in df.columns:
        session_col = df["session"].fillna("").astype(str).str.strip()
        out = df.loc[session_col == session]
        return out.copy() if copy else out
    return df.copy() if copy else df


def _ensure_filer_lookup_columns(
    df: pd.DataFrame,
    *,
    name_to_short: dict[str, str],
    filerid_to_short: dict[int, str],
) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return df

    required = {"FilerID", "FilerShortFromId", "FilerNormRaw", "FilerNormClean", "FilerSortNorm", "FilerShortMapped"}
    if required.issubset(set(df.columns)):
        return df

    data = _ensure_filer_base_columns(df)
    if "FilerNormRaw" not in data.columns:
        filer_name = data.get("filerName", pd.Series("", index=data.index))
        if isinstance(filer_name, pd.DataFrame):
            filer_name = filer_name.iloc[:, 0]
        data["FilerNormRaw"] = _shared_names.norm_name_series(filer_name)
    if "FilerNormClean" not in data.columns:
        filer_name = data.get("filerName", pd.Series("", index=data.index))
        if isinstance(filer_name, pd.DataFrame):
            filer_name = filer_name.iloc[:, 0]
        filer_clean = _shared_names.clean_filer_name_series(filer_name)
        data["FilerNormClean"] = _shared_names.norm_name_series(filer_clean)
    if "FilerSortNorm" not in data.columns:
        filer_sort = data.get("filerSort", pd.Series("", index=data.index))
        if isinstance(filer_sort, pd.DataFrame):
            filer_sort = filer_sort.iloc[:, 0]
        data["FilerSortNorm"] = _shared_names.norm_name_series(filer_sort)
    if "FilerShortFromId" not in data.columns:
        data["FilerShortFromId"] = data["FilerID"].map(filerid_to_short).fillna("") if filerid_to_short else ""
    if "FilerShortMapped" not in data.columns:
        mapped = data["FilerNormRaw"].map(name_to_short)
        mapped = mapped.where(mapped.notna(), data["FilerNormClean"].map(name_to_short))
        mapped = mapped.where(mapped.notna(), data["FilerSortNorm"].map(name_to_short))
        data["FilerShortMapped"] = mapped.fillna("")
    return data


@st.cache_resource(show_spinner=False, max_entries=2)
def _get_app_state_cached(path: str, data_version: str) -> AppState:
    return build_app_state(path, _get_app_state_bootstrap_tables(path, data_version, copy=False), data_version=data_version)


def get_app_state(path: str) -> AppState:
    return _get_app_state_cached(path, get_dataset_version(path))


get_app_state.clear = getattr(_get_app_state_cached, "clear", lambda: None)


@st.cache_resource(show_spinner=False, max_entries=16)
def _get_witness_table_resource(path: str, data_version: str) -> pd.DataFrame:
    app_state = _get_app_state_cached(path, data_version)
    witness = get_app_table_readonly(path, "Wit_All")
    return _fill_missing_witness_lobbyshorts(witness, name_to_short=app_state.name_to_short)


@st.cache_resource(show_spinner=False, max_entries=16)
def _get_witness_search_table_resource(path: str, data_version: str) -> pd.DataFrame:
    return _ensure_witness_search_columns(_get_witness_table_resource(path, data_version))


@st.cache_resource(show_spinner=False, max_entries=16)
def _get_lobby_sub_lookup_table_resource(path: str, data_version: str) -> pd.DataFrame:
    app_state = _get_app_state_cached(path, data_version)
    lobby_sub = get_app_table_readonly(path, "Lobby_Sub_All")
    if lobby_sub.empty:
        return lobby_sub
    data = lobby_sub.copy()
    if "LobbyShort" not in data.columns:
        data["LobbyShort"] = ""
    else:
        data["LobbyShort"] = data["LobbyShort"].fillna("").astype(str).str.strip()
    if app_state.filerid_to_short and "FilerID" in data.columns:
        fid = pd.to_numeric(data["FilerID"], errors="coerce").fillna(-1).astype(int)
        missing = data["LobbyShort"].eq("")
        if missing.any():
            data.loc[missing, "LobbyShort"] = fid.loc[missing].map(app_state.filerid_to_short).fillna("")
    if "LobbyShortNorm" not in data.columns:
        data["LobbyShortNorm"] = _shared_names.norm_name_series(data["LobbyShort"])
    return data


@st.cache_resource(show_spinner=False, max_entries=64)
def _get_filer_lookup_table_resource(path: str, table_key: str, data_version: str) -> pd.DataFrame:
    app_state = _get_app_state_cached(path, data_version)
    rows = get_app_table_readonly(path, table_key)
    return _ensure_filer_lookup_columns(rows, name_to_short=app_state.name_to_short, filerid_to_short=app_state.filerid_to_short)


@st.cache_data(show_spinner=False, max_entries=64)
def _get_witness_rows_for_session(path: str, data_version: str, session_val: str | None, *, include_name_columns: bool) -> pd.DataFrame:
    witness_table = _get_witness_search_table_resource(path, data_version) if include_name_columns else _get_witness_table_resource(path, data_version)
    return _filter_table_by_session(witness_table, session_val, copy=True)


@st.cache_data(show_spinner=False, max_entries=64)
def _get_lobby_sub_rows_for_session(path: str, data_version: str, session_val: str | None) -> pd.DataFrame:
    return _filter_table_by_session(_get_lobby_sub_lookup_table_resource(path, data_version), session_val, copy=True)


@st.cache_data(show_spinner=False, max_entries=128)
def _get_filer_rows_for_session(path: str, table_key: str, data_version: str, session_val: str | None) -> pd.DataFrame:
    return _filter_table_by_session(_get_filer_lookup_table_resource(path, table_key, data_version), session_val, copy=True)


@st.cache_data(show_spinner=False, max_entries=32)
def _get_session_overlay_bundle(path: str, data_version: str, session_val: str | None) -> SessionOverlayBundle:
    session = str(session_val or "").strip()
    tables: dict[str, pd.DataFrame] = {
        "Wit_All": _get_witness_rows_for_session(path, data_version, session, include_name_columns=False),
        "Lobby_Sub_All": _get_lobby_sub_rows_for_session(path, data_version, session),
    }
    witness_search_rows = _get_witness_rows_for_session(path, data_version, session, include_name_columns=True)
    for table_key in FILER_NORMALIZED_TABLE_KEYS:
        tables[table_key] = _get_filer_rows_for_session(path, table_key, data_version, session)
    for table_key in SESSION_SCOPED_TABLE_KEYS:
        if table_key in tables:
            continue
        tables[table_key] = _filter_table_by_session(get_app_table_readonly(path, table_key), session, copy=True)
    return SessionOverlayBundle(session=session or None, tables=tables, witness_search=witness_search_rows)


@st.cache_data(show_spinner=False, max_entries=64)
def _get_workspace_table_overlays_for_keys(path: str, data_version: str, session_val: str | None, keys: tuple[str, ...]) -> dict[str, pd.DataFrame]:
    overlay_bundle = _get_session_overlay_bundle(path, data_version, session_val)
    overlays: dict[str, pd.DataFrame] = {}
    for key in _table_keys_tuple(keys):
        table = overlay_bundle.tables.get(key)
        if isinstance(table, pd.DataFrame):
            overlays[key] = table.copy()
            continue
        overlays[key] = _filter_table_by_session(get_app_table(path, key, copy=False), overlay_bundle.session, copy=True)
    return overlays


@st.cache_data(show_spinner=False, max_entries=32)
def get_workspace_table_overlays(path: str, session_val: str | None, tfl_session_val: str | None) -> dict[str, pd.DataFrame]:
    del tfl_session_val
    return _get_workspace_table_overlays_for_keys(path, get_dataset_version(path), session_val, SESSION_SCOPED_TABLE_KEYS)


@st.cache_data(show_spinner=False, max_entries=1)
def _fetch_map_reference_tables_cached(reference_version: str) -> dict[str, pd.DataFrame]:
    del reference_version
    return {
        "school_districts": fetch_tea_school_district_centroids(),
        "counties": fetch_tea_county_centroids(),
        "cities": fetch_texas_city_centroids(),
        "water_districts": fetch_tceq_water_district_centroids(),
        "groundwater_districts": fetch_tceq_groundwater_district_centroids(),
        "regional_mobility_authorities": fetch_texas_rma_centroids(),
        "junior_colleges": fetch_texas_junior_college_centroids(),
        "navigation_districts": fetch_texas_navigation_district_centroids(),
        "transit_providers": fetch_nctcog_transit_provider_centroids(),
        "seaports": fetch_txdot_seaport_centroids(),
    }


@st.cache_data(show_spinner=False, ttl=3600, max_entries=8)
def _build_map_client_matches_cached(tfl_client_names: tuple[str, ...]) -> pd.DataFrame:
    return build_tfl_political_subdivision_matches(tfl_client_names)


@st.cache_data(show_spinner=False, ttl=3600, max_entries=16)
def _build_map_client_edges_cached(tfl_client_names: tuple[str, ...]) -> pd.DataFrame:
    matches = _build_map_client_matches_cached(tfl_client_names)
    return _map_page_state.build_client_subdivision_edges(matches)


@st.cache_resource(show_spinner=False, max_entries=2)
def _get_map_state_cached(path: str, data_version: str, reference_version: str) -> _map_page_state.MapState:
    del data_version
    return _map_page_state.build_map_state_from_sources(
        path,
        get_app_tables(path, ("Lobby_TFL_Client_All",), copy=False),
        classify_entity_type=classify_requested_entity_type,
        fetch_reference_tables=lambda: _fetch_map_reference_tables_cached(reference_version),
    )


def get_map_state(path: str) -> _map_page_state.MapState:
    return _get_map_state_cached(path, get_dataset_version(path), get_reference_snapshot_version())


get_map_state.clear = getattr(_get_map_state_cached, "clear", lambda: None)


def require_app_state(path: str, *, missing_path_message: str, missing_file_message: str) -> AppState:
    if not path:
        st.error(missing_path_message)
        st.stop()
    if not _is_url(path) and not os.path.exists(path):
        st.error(missing_file_message)
        st.stop()
    return get_app_state(path)


def require_map_state(path: str, *, missing_path_message: str, missing_file_message: str) -> _map_page_state.MapState:
    if not path:
        st.error(missing_path_message)
        st.stop()
    if not _is_url(path) and not os.path.exists(path):
        st.error(missing_file_message)
        st.stop()
    return get_map_state(path)


__all__ = [
    "SessionOverlayBundle",
    "_filter_table_by_session",
    "_get_app_state_cached",
    "_get_filer_lookup_table_resource",
    "_get_filer_rows_for_session",
    "_get_lobby_sub_lookup_table_resource",
    "_get_lobby_sub_rows_for_session",
    "_get_map_state_cached",
    "_get_session_overlay_bundle",
    "_get_witness_rows_for_session",
    "_get_witness_search_table_resource",
    "_get_witness_table_resource",
    "_get_workspace_table_overlays_for_keys",
    "_load_projected_table_resource",
    "_load_table_resource",
    "_table_keys_tuple",
    "get_app_state",
    "get_app_table",
    "get_app_table_readonly",
    "get_app_tables",
    "get_app_tables_readonly",
    "get_dataset_version",
    "get_map_state",
    "get_workspace_table_overlays",
    "require_app_state",
    "require_map_state",
]
