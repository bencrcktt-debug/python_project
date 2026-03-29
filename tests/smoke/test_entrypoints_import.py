from __future__ import annotations

import importlib


def test_page_registry_import() -> None:
    module = importlib.import_module("tfl_app.entrypoints.page_registry")
    assert hasattr(module, "build_page_registry")
    assert hasattr(module, "PageRegistry")


def test_nav_search_import() -> None:
    module = importlib.import_module("tfl_app.entrypoints.nav_search")
    assert hasattr(module, "prefetch_nav_search_bundle")
    assert hasattr(module, "render_nav_suggestions")
    assert hasattr(module, "handle_nav_search_submission")


def test_bootstrap_import() -> None:
    module = importlib.import_module("tfl_app.entrypoints.bootstrap")
    assert hasattr(module, "configure_page")
    assert hasattr(module, "render_global_styles")
    assert hasattr(module, "render_global_ux")
