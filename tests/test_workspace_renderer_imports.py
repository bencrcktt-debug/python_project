from __future__ import annotations

import importlib
import inspect


def test_page_workspace_renderers_import() -> None:
    module = importlib.import_module("tfl_app.ui.renderers")
    assert hasattr(module, "render_client_workspace")
    assert hasattr(module, "render_member_workspace")
    assert hasattr(module, "render_lobby_workspace")


def test_map_workspace_renderer_import() -> None:
    module = importlib.import_module("tfl_app.ui.renderers.map_workspace")
    assert hasattr(module, "render_map_workspace")


def test_page_modules_import() -> None:
    module_names = [
        "tfl_app.ui.pages.about",
        "tfl_app.ui.pages.clients",
        "tfl_app.ui.pages.legislators",
        "tfl_app.ui.pages.lobbyists",
        "tfl_app.ui.pages.map_address",
        "tfl_app.ui.pages.multimedia",
        "tfl_app.ui.pages.solutions",
    ]
    for module_name in module_names:
        module = importlib.import_module(module_name)
        assert hasattr(module, "render_page")
        signature = inspect.signature(module.render_page)
        assert "services" in signature.parameters
        assert "ctx" in signature.parameters

