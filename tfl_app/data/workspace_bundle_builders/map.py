from __future__ import annotations

import tfl_app.data.state_store as _state_store
import tfl_app.map.runtime as _map_runtime
import tfl_app.map.state as _map_page_state


def build_map_atlas_bundle(
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


def build_map_forensics_bundle(
    path: str,
    scope: str,
    session_for_filter: str | None,
    selected_subdivision_signature: str,
    data_version: str,
    reference_version: str,
) -> _map_runtime.MapForensicsBundle:
    atlas_bundle = build_map_atlas_bundle(
        path,
        scope,
        session_for_filter,
        data_version,
        reference_version,
    )
    return _map_runtime.build_map_forensics_bundle(
        atlas_bundle,
        selected_subdivision_signature=selected_subdivision_signature,
    )
