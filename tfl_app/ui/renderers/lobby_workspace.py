from __future__ import annotations

from typing import Any

from tfl_app.services import WorkspaceServices

from . import _workspace_core as _core


def _runtime_ctx(ctx: dict[str, Any], services: WorkspaceServices | None) -> dict[str, Any]:
    runtime_ctx = dict(getattr(services, "values", {}))
    runtime_ctx.update(dict(ctx or {}))
    return runtime_ctx


def render_lobby_workspace(ctx: dict[str, Any], services: WorkspaceServices | None = None):
    return _core.render_lobby_workspace(_runtime_ctx(ctx, services))
