from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

import tfl_app.ui.fragments.map_workspace_fragments as map_fragments
from tfl_app.services import MapServices
from tfl_app.ui.contexts import MapWorkspacePreparedContext, MapWorkspaceSelector


def test_refresh_map_runtime_context_rebuilds_current_map_bundle() -> None:
    old_session_state = dict(map_fragments.st.session_state)

    calls: dict[str, object] = {}

    class _Runtime:
        @staticmethod
        def build_selected_subdivision_signature(ctx: dict[str, object]) -> str:
            calls["signature_ctx"] = dict(ctx)
            return "fresh-signature"

    bundle = SimpleNamespace(
        totals=pd.DataFrame([{"total": 1}]),
        tfl_spend=pd.DataFrame([{"Client": "Fresh Entity", "High": 125.0}]),
        subdivision_matches=pd.DataFrame(
            [
                {
                    "subdivision_type": "County",
                    "subdivision_name": "Fresh County",
                    "subdivision_code": "001",
                    "match_count": 1,
                    "match_clients": ["Fresh Entity"],
                }
            ]
        ),
        matched_clients=frozenset({"Fresh Entity"}),
        total_tfl=4,
        total_high=500.0,
        mapped_high=250.0,
        mapped_rate=0.5,
        unmapped_count=2,
        hotspot_label="County - Fresh County",
        hotspot_high=125.0,
    )
    atlas_bundle = SimpleNamespace(
        map_payload_signature="atlas-sig",
        prepared_overlap_pools={},
        spend_lookup={"Fresh Entity": {"EntityType": "County", "Low": 25.0, "High": 125.0, "Lobbyists": 1}},
    )

    def _get_map_forensics_bundle(path: str, scope: str, session_for_filter: str, signature: str):
        calls["forensics_args"] = (path, scope, session_for_filter, signature)
        return bundle

    def _get_map_atlas_bundle(path: str, scope: str, session_for_filter: str):
        calls["atlas_args"] = (path, scope, session_for_filter)
        return atlas_bundle

    services = MapServices.build(
        PATH="memory://map",
        get_map_state=lambda _path: SimpleNamespace(map_sessions={"89R"}),
        _tfl_session_for_filter=lambda session_val, tfl_sessions: (
            "89R" if str(session_val).strip() == "891" and "89R" in tfl_sessions else session_val
        ),
        _map_runtime=_Runtime(),
        get_map_forensics_bundle=_get_map_forensics_bundle,
        get_map_atlas_bundle=_get_map_atlas_bundle,
    )

    try:
        map_fragments.st.session_state.clear()
        map_fragments.st.session_state.update(
            {
                "map_session": "891",
                "map_scope": "This Session",
                "map_watchlist": [{"TFL Entity": "Fresh Entity"}],
                "map_selected_subdivision_context": {"subdivision_name": "Fresh County"},
            }
        )

        refreshed = map_fragments._refresh_map_runtime_context(
            services,
            {
                "subdivision_matches": pd.DataFrame(),
                "_atlas_label": "stale",
                "_docket_label": "stale",
            }
        )

        assert calls["forensics_args"] == (
            "memory://map",
            "This Session",
            "89R",
            "fresh-signature",
        )
        assert calls["atlas_args"] == ("memory://map", "This Session", "89R")
        assert refreshed.payload["totals"] is bundle.totals
        assert refreshed.payload["tfl_spend"] is bundle.tfl_spend
        assert refreshed.payload["subdivision_matches"] is bundle.subdivision_matches
        assert list(refreshed.payload["subdivision_matches"]["subdivision_name"]) == ["Fresh County"]
        assert refreshed.payload["session_for_filter"] == "89R"
        assert refreshed.payload["_atlas_label"].endswith("(1)")
        assert refreshed.payload["_docket_label"].endswith("(1)")
        assert refreshed.payload["total_high"] == 500.0
        assert "_map_forensics_source_signature" in refreshed.payload
    finally:
        map_fragments.st.session_state.clear()
        map_fragments.st.session_state.update(old_session_state)


def test_refresh_map_runtime_context_invalidates_stale_forensics_session_cache() -> None:
    old_session_state = dict(map_fragments.st.session_state)

    bundle = SimpleNamespace(
        totals=pd.DataFrame(),
        tfl_spend=pd.DataFrame(),
        subdivision_matches=pd.DataFrame(),
        matched_clients=frozenset(),
        total_tfl=0,
        total_high=0.0,
        mapped_high=0.0,
        mapped_rate=0.0,
        unmapped_count=0,
        hotspot_label="--",
        hotspot_high=0.0,
    )
    atlas_bundle = SimpleNamespace(
        map_payload_signature="atlas-sig-2",
        prepared_overlap_pools={},
        spend_lookup={"Port of Houston Authority": {"EntityType": "Port Authority", "Low": 1.0, "High": 2.0, "Lobbyists": 1}},
    )

    services = MapServices.build(
        PATH="memory://map",
        get_map_state=lambda _path: SimpleNamespace(map_sessions={"89R"}),
        _tfl_session_for_filter=lambda session_val, tfl_sessions: session_val,
        _map_runtime=SimpleNamespace(build_selected_subdivision_signature=lambda _ctx: "sig-2"),
        get_map_forensics_bundle=lambda *args: bundle,
        get_map_atlas_bundle=lambda *args: atlas_bundle,
    )

    try:
        map_fragments.st.session_state.clear()
        map_fragments.st.session_state.update(
            {
                "map_session": "89R",
                "map_scope": "This Session",
                "_mp5_forensics_bundle_v1": {"key": "stale"},
                "_mp5_forensics_rows_v1": {"key": "stale"},
                "_mp5_filtered_forensics_bundle_v1": {"signature": "stale"},
            }
        )

        refreshed = map_fragments._refresh_map_runtime_context(
            services,
            {"_map_forensics_source_signature": "old-signature"}
        )

        assert refreshed.payload["_map_forensics_source_signature"] != "old-signature"
        assert "_mp5_forensics_bundle_v1" not in map_fragments.st.session_state
        assert "_mp5_forensics_rows_v1" not in map_fragments.st.session_state
        assert "_mp5_filtered_forensics_bundle_v1" not in map_fragments.st.session_state
    finally:
        map_fragments.st.session_state.clear()
        map_fragments.st.session_state.update(old_session_state)


def test_run_fragment_persists_only_runtime_markers(monkeypatch) -> None:
    old_session_state = dict(map_fragments.st.session_state)
    old_transient = dict(map_fragments._TRANSIENT_CONTEXTS)
    render_calls: list[dict[str, object]] = []
    services = MapServices.build()

    fake_renderer = SimpleNamespace(
        render_map_workspace=lambda ctx, services_arg: render_calls.append(
            {"ctx": dict(ctx.payload), "services": services_arg}
        ),
    )

    def fake_refresh(services_arg: MapServices, ctx: dict[str, object]) -> MapWorkspacePreparedContext:
        assert services_arg is services
        updated = dict(ctx)
        updated.update(
            {
                "_map_runtime_signature": "runtime-sig",
                "_map_forensics_source_signature": "source-sig",
                "subdivision_matches": pd.DataFrame([{"subdivision_name": "Fresh County"}]),
                "total_high": 500.0,
            }
        )
        return MapWorkspacePreparedContext(
            selector=MapWorkspaceSelector(
                path=str(updated.get("PATH", "") or ""),
                runtime_signature="runtime-sig",
                forensics_source_signature="source-sig",
            ),
            payload=updated,
        )

    try:
        monkeypatch.setattr(map_fragments, "_refresh_map_runtime_context", fake_refresh)
        monkeypatch.setattr(map_fragments.importlib, "import_module", lambda name: fake_renderer)

        map_fragments.st.session_state.clear()
        map_fragments.st.session_state["_map_workspace_ctx"] = {"PATH": "memory://map"}
        map_fragments.remember_map_workspace_transient_context(
            "_map_workspace_ctx",
            {"_open_client": lambda value: value},
        )

        map_fragments._run_fragment(services, "_map_workspace_ctx")

        persisted = map_fragments.st.session_state["_map_workspace_ctx"]
        assert persisted == {
            "PATH": "memory://map",
            "_map_runtime_signature": "runtime-sig",
            "_map_forensics_source_signature": "source-sig",
        }
        assert render_calls[0]["services"] is services
        assert callable(render_calls[0]["ctx"]["_open_client"])
        assert list(render_calls[0]["ctx"]["subdivision_matches"]["subdivision_name"]) == ["Fresh County"]
    finally:
        map_fragments._TRANSIENT_CONTEXTS.clear()
        map_fragments._TRANSIENT_CONTEXTS.update(old_transient)
        map_fragments.st.session_state.clear()
        map_fragments.st.session_state.update(old_session_state)

