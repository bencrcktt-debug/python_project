from __future__ import annotations

from typing import Any

_MISSING = object()


def configure_helpers(module_globals: dict[str, Any], **helpers: Any) -> None:
    module_globals.update(helpers)


def push_context(module_globals: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    previous: dict[str, Any] = {}
    for key, value in ctx.items():
        previous[key] = module_globals.get(key, _MISSING)
        module_globals[key] = value
    return previous


def pop_context(module_globals: dict[str, Any], previous: dict[str, Any], ctx: dict[str, Any]) -> None:
    for key in ctx.keys():
        old_value = previous.get(key, _MISSING)
        if old_value is _MISSING:
            module_globals.pop(key, None)
        else:
            module_globals[key] = old_value
