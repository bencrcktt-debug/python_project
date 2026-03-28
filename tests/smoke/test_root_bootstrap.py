from __future__ import annotations

import importlib
from pathlib import Path


def test_root_main_bootstrap_compiles() -> None:
    source = Path("main.py").read_text(encoding="utf-8")
    compile(source, "main.py", "exec")


def test_root_main_bootstrap_targets_streamlit_entrypoint() -> None:
    source = Path("main.py").read_text(encoding="utf-8")
    assert "tfl_app.entrypoints" in source


def test_streamlit_entrypoint_imports() -> None:
    module = importlib.import_module("tfl_app.entrypoints.streamlit_app")
    assert hasattr(module, "render_app")
