from __future__ import annotations

import pandas as pd

import tfl_app.bundles.page_bundles as _page_bundles
import tfl_app.bundles.page_detail_bundles as _page_detail_bundles
import tfl_app.data.state_store as _state_store
from tfl_app.search.indexes import AppState

from . import shared as _shared


def build_member_session_bundle(
    path: str,
    app_state: AppState,
    data_version: str,
    session_val: str | None,
) -> _page_bundles.MemberSessionBundle:
    session = str(session_val or "").strip()
    witness_rows = _state_store._get_witness_rows_for_session(
        path,
        data_version,
        session_val,
        include_name_columns=True,
    )
    registered_lobbyshorts: frozenset[str] = frozenset()
    lobby_pivot = getattr(app_state, "lobby_scope_pivot_by_session", pd.DataFrame())
    if isinstance(lobby_pivot, pd.DataFrame) and not lobby_pivot.empty and session:
        session_rows = lobby_pivot[lobby_pivot["SessionKey"].astype(str).str.strip() == session]
        registered_lobbyshorts = frozenset(
            session_rows.get("LobbyShort", pd.Series(dtype=object))
            .dropna()
            .astype(str)
            .str.strip()
            .loc[lambda s: s != ""]
            .tolist()
        )
    return _page_bundles.build_member_session_bundle(
        app_state.author_bills_all,
        witness_rows,
        session,
        filerid_to_short=app_state.filerid_to_short,
        name_to_short=app_state.name_to_short,
        registered_lobbyshorts=registered_lobbyshorts,
    )


def build_member_workspace_detail_bundle(
    app_state: AppState,
    path: str,
    session_val: str | None,
    tfl_session_val: str | None,
    member_name: str,
) -> _page_detail_bundles.MemberWorkspaceDetailBundle:
    return _page_detail_bundles.build_member_workspace_detail_bundle(
        _shared.member_workspace_data(app_state, path, session_val),
        author_bills_all=app_state.author_bills_all,
        name_to_short=app_state.name_to_short,
        short_to_names=app_state.short_to_names,
        initial_to_short=app_state.initial_to_short,
        session=str(session_val or ""),
        tfl_session_val=tfl_session_val,
        member_name=str(member_name or ""),
    )
