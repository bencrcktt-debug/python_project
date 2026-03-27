from __future__ import annotations

import pandas as pd

import tfl_app.ui.renderers._workspace_core as page_workspace_renderers


class _Tab:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _SessionState(dict):
    def __getattr__(self, name: str):
        return self[name]

    def __setattr__(self, name: str, value):
        self[name] = value


class _StreamlitStub:
    def __init__(self) -> None:
        self.session_state = _SessionState(scope="This Session", session=None, lobbyshort="")

    def tabs(self, labels):
        return [_Tab() for _ in labels]

    def markdown(self, *args, **kwargs):
        return None

    def info(self, *args, **kwargs):
        return None


def test_render_lobby_workspace_resolves_scope_table_from_context(monkeypatch) -> None:
    stub = _StreamlitStub()
    captured: dict[str, pd.DataFrame] = {}

    monkeypatch.setattr(page_workspace_renderers, "st", stub)

    def fake_require_columns(df: pd.DataFrame, required: list[str], label: str, hint: str = "") -> bool:
        captured["df"] = df
        raise RuntimeError("validated")

    monkeypatch.setattr(page_workspace_renderers, "require_columns", fake_require_columns, raising=False)

    try:
        page_workspace_renderers.render_lobby_workspace(
            {
                "Lobby_TFL_Client_All": pd.DataFrame([{"Session": "89R", "LobbyShort": "SMITHJ"}]),
                "all_pivot": pd.DataFrame(),
                "all_stats": {},
                "scope": "This Session",
            }
        )
    except RuntimeError as exc:
        assert str(exc) == "validated"

    assert list(captured["df"].columns) == ["Session", "LobbyShort"]

