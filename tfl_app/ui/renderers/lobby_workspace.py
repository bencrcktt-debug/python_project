from __future__ import annotations

from typing import Any

from tfl_app.services import WorkspaceServices

from . import _workspace_core as _core
from .context_adapters import merge_workspace_runtime_context, normalize_lobby_workspace_context

st = _core.st


_normalize_policy_mentions_frame = _core._normalize_policy_mentions_frame


def _runtime_ctx(ctx: Any, services: WorkspaceServices | None) -> dict[str, Any]:
    return merge_workspace_runtime_context(normalize_lobby_workspace_context(ctx), services)


def render_lobby_workspace(ctx: Any, services: WorkspaceServices | None = None) -> None:
    runtime_ctx = _runtime_ctx(ctx, services)
    _core.st = st
    _core.render_lobby_workspace(runtime_ctx)
