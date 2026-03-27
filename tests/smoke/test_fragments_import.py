from __future__ import annotations

import importlib


def test_page_fragments_import_without_streamlit() -> None:
    module = importlib.import_module("tfl_app.ui.fragments.page_fragments")
    assert hasattr(module, "render_client_workspace_fragment")
    assert hasattr(module, "render_member_workspace_fragment")
    assert hasattr(module, "render_lobby_workspace_fragment")


def test_map_fragments_import_without_streamlit() -> None:
    module = importlib.import_module("tfl_app.ui.fragments.map_fragments")
    assert hasattr(module, "render_map_workspace_fragment")

