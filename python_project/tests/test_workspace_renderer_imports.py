from __future__ import annotations

import importlib


def test_page_workspace_renderers_import() -> None:
    module = importlib.import_module("src.page_workspace_renderers")
    assert hasattr(module, "render_client_workspace")
    assert hasattr(module, "render_member_workspace")
    assert hasattr(module, "render_lobby_workspace")


def test_map_workspace_renderer_import() -> None:
    module = importlib.import_module("src.map_workspace_renderer")
    assert hasattr(module, "render_map_workspace")


def test_page_modules_import() -> None:
    module_names = [
        "src.pages.about",
        "src.pages.clients",
        "src.pages.legislators",
        "src.pages.lobbyists",
        "src.pages.map_address",
        "src.pages.multimedia",
        "src.pages.solutions",
    ]
    for module_name in module_names:
        module = importlib.import_module(module_name)
        assert hasattr(module, "HELPER_KEYS")
        assert hasattr(module, "configure_helpers")
        assert hasattr(module, "render_page")
