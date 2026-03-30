from __future__ import annotations

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
    witness_rows = _state_store._get_witness_rows_for_session(
        path,
        data_version,
        session_val,
        include_name_columns=False,
    )
    return _page_bundles.build_member_session_bundle(
        app_state.author_bills_all,
        witness_rows,
        str(session_val or ""),
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
