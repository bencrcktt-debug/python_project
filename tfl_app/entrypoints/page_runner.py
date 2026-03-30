from __future__ import annotations

import functools
import importlib
from typing import Callable

from tfl_app.services import AppServices


@functools.lru_cache(maxsize=None)
def load_page_renderer_module(module_name: str):
    return importlib.import_module(module_name)


def build_page_renderer(get_app_services: Callable[[], AppServices]):
    def run_page_renderer(module_name: str, ctx: dict[str, object] | None = None) -> None:
        module = load_page_renderer_module(module_name)
        module.render_page(services=get_app_services(), ctx=ctx or {})

    return run_page_renderer

