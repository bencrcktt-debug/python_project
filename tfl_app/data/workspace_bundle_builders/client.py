from __future__ import annotations

import tfl_app.bundles.page_bundles as _page_bundles
import tfl_app.bundles.page_detail_bundles as _page_detail_bundles
from tfl_app.search.indexes import AppState

from . import shared as _shared


def build_client_scope_bundle(
    app_state: AppState,
    scope: str,
    session_val: str | None,
) -> _page_bundles.ClientScopeBundle:
    overview = app_state.client_scope_overview_all
    session = str(session_val or "").strip()
    if scope == "This Session" and session:
        overview = app_state.client_scope_overview_by_session
        overview = overview[overview["SessionKey"].astype(str) == session].drop(columns=["SessionKey"], errors="ignore")
    overview = overview.reset_index(drop=True).copy()
    return _page_bundles.ClientScopeBundle(
        overview=overview,
        stats=_shared.build_client_scope_stats(overview),
        category_chart_data=app_state.client_category_chart_data,
    )


def build_client_workspace_detail_bundle(
    app_state: AppState,
    path: str,
    session_val: str | None,
    tfl_session_val: str | None,
    client_name: str,
) -> _page_detail_bundles.ClientWorkspaceDetailBundle:
    return _page_detail_bundles.build_client_workspace_detail_bundle(
        _shared.client_workspace_data(app_state, path, session_val),
        name_to_short=app_state.name_to_short,
        session=str(session_val or ""),
        tfl_session_val=tfl_session_val,
        client_name=str(client_name or ""),
    )
