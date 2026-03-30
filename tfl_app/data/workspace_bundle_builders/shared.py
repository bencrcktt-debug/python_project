from __future__ import annotations

from typing import Any, Callable

import pandas as pd

import tfl_app.data.state_store as _state_store
from tfl_app.data.catalog import CLIENT_DETAIL_TABLE_KEYS, LOBBY_DETAIL_TABLE_KEYS, MEMBER_DETAIL_TABLE_KEYS
from tfl_app.search.indexes import AppState


def build_client_scope_stats(overview: pd.DataFrame) -> dict[str, Any]:
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


def build_lobby_scope_stats(all_pivot: pd.DataFrame) -> dict[str, Any]:
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


def detail_base_data(app_state: AppState, path: str) -> dict[str, object]:
    return {
        "Lobby_TFL_Client_All": _state_store.get_app_table_readonly(path, "Lobby_TFL_Client_All"),
        "Staff_All": _state_store.get_app_table_readonly(path, "Staff_All"),
        "filerid_to_short": app_state.filerid_to_short,
    }


def client_workspace_data(app_state: AppState, path: str, session_val: str | None) -> dict[str, object]:
    data = detail_base_data(app_state, path)
    data.update(
        _state_store._get_workspace_table_overlays_for_keys(
            path,
            app_state.data_version,
            session_val,
            CLIENT_DETAIL_TABLE_KEYS,
        )
    )
    return data


def member_workspace_data(app_state: AppState, path: str, session_val: str | None) -> dict[str, object]:
    data = detail_base_data(app_state, path)
    data.update(
        _state_store._get_workspace_table_overlays_for_keys(
            path,
            app_state.data_version,
            session_val,
            MEMBER_DETAIL_TABLE_KEYS,
        )
    )
    return data


def witness_name_match_table(path: str, data_version: str, session_val: str | None) -> pd.DataFrame:
    overlay_bundle = _state_store._get_session_overlay_bundle(path, data_version, session_val)
    return overlay_bundle.witness_search.copy()


def lobby_workspace_data(
    app_state: AppState,
    path: str,
    session_val: str | None,
    *,
    include_witness_name_columns: bool,
    witness_name_match_loader: Callable[[str, str | None], pd.DataFrame],
) -> dict[str, object]:
    data = detail_base_data(app_state, path)
    overlays = _state_store._get_workspace_table_overlays_for_keys(
        path,
        app_state.data_version,
        session_val,
        LOBBY_DETAIL_TABLE_KEYS,
    )
    if include_witness_name_columns:
        overlays["Wit_All"] = witness_name_match_loader(path, session_val)
    data.update(overlays)
    return data
