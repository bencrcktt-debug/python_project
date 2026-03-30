from __future__ import annotations

from typing import Callable

import pandas as pd

import tfl_app.bundles.page_bundles as _page_bundles
import tfl_app.bundles.page_detail_bundles as _page_detail_bundles
from tfl_app.search.indexes import AppState

from . import shared as _shared


def build_lobby_scope_bundle(
    app_state: AppState,
    scope: str,
    session_val: str | None,
) -> _page_bundles.LobbyScopeBundle:
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
        all_stats=_shared.build_lobby_scope_stats(all_pivot),
        trend_group=app_state.lobby_scope_trend_group,
        top_clients=top_clients,
        lobby_display=app_state.lobby_display,
    )


def build_lobby_workspace_detail_bundle(
    app_state: AppState,
    path: str,
    session_val: str | None,
    tfl_session_val: str | None,
    lobbyshort: str,
    typed_norms_tuple: tuple[str, ...],
    selected_names: tuple[str, ...],
    selected_filer_ids: tuple[int, ...],
    *,
    witness_name_match_loader: Callable[[str, str | None], pd.DataFrame],
) -> _page_detail_bundles.LobbyWorkspaceDetailBundle:
    return _page_detail_bundles.build_lobby_workspace_detail_bundle(
        _shared.lobby_workspace_data(
            app_state,
            path,
            session_val,
            include_witness_name_columns=bool(selected_names),
            witness_name_match_loader=witness_name_match_loader,
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
