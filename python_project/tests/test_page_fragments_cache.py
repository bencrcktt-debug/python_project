from __future__ import annotations

from types import SimpleNamespace

import src.page_fragments as page_fragments


def test_run_fragment_reuses_prepared_context_when_selectors_do_not_change(monkeypatch) -> None:
    old_session_state = dict(page_fragments.st.session_state)
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

        page_fragments.st.session_state["_client_workspace_ctx"]["client_name"] = "County of Travis"
        page_fragments._run_fragment("_client_workspace_ctx")

        assert len(rehydrate_calls) == 2
        assert render_calls[-1]["prepared_value"] == 2
    finally:
        page_fragments.st.session_state.clear()
        page_fragments.st.session_state.update(old_session_state)


def test_merge_fragment_session_context_preserves_prepared_payload() -> None:
    old_session_state = dict(page_fragments.st.session_state)
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
        assert merged["_prepared_client_workspace"] is True
        assert merged["prepared_value"] == 7
        assert merged["client_name"] == "City of Austin"
    finally:
        page_fragments.st.session_state.clear()
        page_fragments.st.session_state.update(old_session_state)
