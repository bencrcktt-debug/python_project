from __future__ import annotations

from tfl_app.config.paths import COMPONENTS_DIR


def test_component_asset_directories_exist() -> None:
    assert (COMPONENTS_DIR / "_atlas_bridge").exists()
    assert (COMPONENTS_DIR / "_persistent_html_frame").exists()
    assert (COMPONENTS_DIR / "_tfl_subdivision_map").exists()
