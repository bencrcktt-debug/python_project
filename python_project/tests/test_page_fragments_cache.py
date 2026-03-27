from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

import src.page_fragments as page_fragments


def test_run_fragment_reuses_prepared_context_when_selectors_do_not_change(monkeypatch) -> None:
    old_session_state = dict(page_fragments.st.session_state)
    old_cache = dict(page_fragments._PREPARED_CONTEXT_CACHE)
    rehydrate_calls: list[dict[str, object]] = []
    render_calls: list[dict[str, object]] = []

    def fake_rehydrate(storage_key: str, ctx: dict[str, object]) -> dict[str, object]:
        rehydrate_calls.append(dict(ctx))
        updated = dict(ctx)
        updated["prepared_value"] = len(rehydrate_calls)
        return updated

    fake_renderer = SimpleNamespace(
        configure_helpers=lambda **helpers: None,
        render_client_workspace=lambda ctx: render_calls.append(dict(ctx)),
    )

    try:
        monkeypatch.setattr(page_fragments, "_rehydrate_fragment_ctx", fake_rehydrate)
        monkeypatch.setattr(page_fragments.importlib, "import_module", lambda name: fake_renderer)

        page_fragments.st.session_state.clear()
        page_fragments.st.session_state["_client_workspace_ctx"] = {
            "PATH": "demo.parquet",
            "client_scope": "This Session",
            "client_session": "89R",
            "client_name": "City of Austin",
            "tfl_session_val": "89R",
        }

        page_fragments._run_fragment("_client_workspace_ctx")
        page_fragments._run_fragment("_client_workspace_ctx")

        assert len(rehydrate_calls) == 1
        assert len(render_calls) == 2
        assert render_calls[0]["prepared_value"] == 1
        assert render_calls[1]["prepared_value"] == 1
        persisted = page_fragments.st.session_state["_client_workspace_ctx"]
        assert persisted["client_name"] == "City of Austin"
        assert persisted["_prepared_signature"]
        assert "prepared_value" not in persisted

        page_fragments.st.session_state["_client_workspace_ctx"]["client_name"] = "County of Travis"
        page_fragments._run_fragment("_client_workspace_ctx")

        assert len(rehydrate_calls) == 2
        assert render_calls[-1]["prepared_value"] == 2
    finally:
        page_fragments._PREPARED_CONTEXT_CACHE.clear()
        page_fragments._PREPARED_CONTEXT_CACHE.update(old_cache)
        page_fragments.st.session_state.clear()
        page_fragments.st.session_state.update(old_session_state)


def test_merge_fragment_session_context_keeps_only_selector_payload() -> None:
    old_session_state = dict(page_fragments.st.session_state)
    old_cache = dict(page_fragments._PREPARED_CONTEXT_CACHE)
    try:
        page_fragments.st.session_state.clear()
        page_fragments.st.session_state["_client_workspace_ctx"] = {
            "PATH": "demo.parquet",
            "client_scope": "This Session",
            "_prepared_signature": "prepared",
            "_prepared_client_workspace": True,
            "prepared_value": 7,
        }

        merged = page_fragments.merge_fragment_session_context(
            "_client_workspace_ctx",
            {"client_scope": "This Session", "client_name": "City of Austin"},
        )

        assert merged["_prepared_signature"] == "prepared"
        assert merged["client_name"] == "City of Austin"
        assert "_prepared_client_workspace" not in merged
        assert "prepared_value" not in merged
    finally:
        page_fragments._PREPARED_CONTEXT_CACHE.clear()
        page_fragments._PREPARED_CONTEXT_CACHE.update(old_cache)
        page_fragments.st.session_state.clear()
        page_fragments.st.session_state.update(old_session_state)


def test_app_state_context_keeps_only_small_lookup_maps(monkeypatch) -> None:
    app_state = SimpleNamespace(
        data={
            "Wit_All": pd.DataFrame([{"Session": "89R", "LobbyShort": "SMITHJ"}]),
            "Lobby_TFL_Client_All": pd.DataFrame([{"Session": "89R", "Client": "City of Austin"}]),
        },
        name_to_short={"SMITHJOHN": "SMITHJ"},
        short_to_names={"SMITHJ": ["Smith, John"]},
        filerid_to_short={101: "SMITHJ"},
        author_bills_all=pd.DataFrame([{"Session": "89R", "Bill": "HB 1"}]),
        lobbyist_index=pd.DataFrame([{"LobbyShort": "SMITHJ"}]),
    )

    monkeypatch.setattr(page_fragments, "_helper", lambda name: (lambda path: app_state) if name == "get_app_state" else None)

    ctx = page_fragments._app_state_context("demo.parquet")

    assert ctx == {
        "name_to_short": {"SMITHJOHN": "SMITHJ"},
        "short_to_names": {"SMITHJ": ["Smith, John"]},
        "filerid_to_short": {101: "SMITHJ"},
    }
