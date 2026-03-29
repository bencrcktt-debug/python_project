from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from tfl_app.services import WorkspaceServices
from tfl_app.ui.contexts import AppLookupMaps, LobbyWorkspacePreparedContext, LobbyWorkspaceSelector
import tfl_app.ui.renderers.lobby_workspace as page_workspace_renderers


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

    prepared = LobbyWorkspacePreparedContext(
        selector=LobbyWorkspaceSelector(
            path="test-path",
            scope="This Session",
            session="89R",
            tfl_session_val="89R",
            lobbyshort="SMITHJ",
        ),
        app_lookups=AppLookupMaps({}, {}, {}),
        scope_bundle=SimpleNamespace(
            all_pivot=pd.DataFrame(),
            all_stats={},
            trend_group=pd.DataFrame(),
            top_clients=pd.DataFrame(),
            lobby_display=pd.DataFrame(),
        ),
        detail_bundle=SimpleNamespace(context={}),
        payload={
            "Lobby_TFL_Client_All": pd.DataFrame([{"Session": "89R", "LobbyShort": "SMITHJ"}]),
        },
    )

    try:
        page_workspace_renderers.render_lobby_workspace(
            prepared,
            WorkspaceServices.build(PATH="test-path", require_columns=fake_require_columns),
        )
    except RuntimeError as exc:
        assert str(exc) == "validated"

    assert list(captured["df"].columns) == ["Session", "LobbyShort"]


def test_normalize_policy_mentions_frame_coerces_object_share_dtype() -> None:
    source = pd.DataFrame(
        [
            {"Subject": "Education", "Mentions": "2", "Share": "0.5"},
            {"Subject": "Health", "Mentions": None, "Share": None},
        ],
        dtype=object,
    )

    normalized = page_workspace_renderers._normalize_policy_mentions_frame(source)

    assert list(normalized["Subject"]) == ["Education", "Health"]
    assert list(normalized["Mentions"]) == [2.0, 0.0]
    assert list(normalized["Share"]) == [0.5, 0.0]
    assert normalized["Share"].dtype.kind == "f"

