from __future__ import annotations

from typing import Any

from tfl_app.services import MapServices, WorkspaceServices
from tfl_app.ui.contexts import (
    ClientWorkspacePreparedContext,
    LobbyWorkspacePreparedContext,
    MapWorkspacePreparedContext,
    MemberWorkspacePreparedContext,
)


def normalize_client_workspace_context(ctx: Any) -> dict[str, Any]:
    if isinstance(ctx, ClientWorkspacePreparedContext):
        payload = dict(ctx.payload)
        payload.update(
            {
                "PATH": ctx.selector.path,
                "client_scope": ctx.selector.client_scope,
                "client_session": ctx.selector.client_session,
                "client_name": ctx.selector.client_name,
                "tfl_session_val": ctx.selector.tfl_session_val,
                "name_to_short": ctx.app_lookups.name_to_short,
                "short_to_names": ctx.app_lookups.short_to_names,
                "filerid_to_short": ctx.app_lookups.filerid_to_short,
                "client_scope_bundle": ctx.scope_bundle,
                "client_detail_bundle": ctx.detail_bundle,
                "_prepared_client_workspace": True,
            }
        )
        return payload
    return dict(getattr(ctx, "payload", ctx) or {})


def normalize_member_workspace_context(ctx: Any) -> dict[str, Any]:
    if isinstance(ctx, MemberWorkspacePreparedContext):
        payload = dict(ctx.payload)
        payload.update(
            {
                "PATH": ctx.selector.path,
                "member_session": ctx.selector.member_session,
                "member_name": ctx.selector.member_name,
                "tfl_session_val": ctx.selector.tfl_session_val,
                "name_to_short": ctx.app_lookups.name_to_short,
                "short_to_names": ctx.app_lookups.short_to_names,
                "filerid_to_short": ctx.app_lookups.filerid_to_short,
                "member_session_bundle": ctx.session_bundle,
                "member_detail_bundle": ctx.detail_bundle,
                "_prepared_member_workspace": True,
            }
        )
        return payload
    return dict(getattr(ctx, "payload", ctx) or {})


def normalize_lobby_workspace_context(ctx: Any) -> dict[str, Any]:
    if isinstance(ctx, LobbyWorkspacePreparedContext):
        payload = dict(ctx.payload)
        payload.update(
            {
                "PATH": ctx.selector.path,
                "scope": ctx.selector.scope,
                "session": ctx.selector.session,
                "tfl_session_val": ctx.selector.tfl_session_val,
                "lobbyshort": ctx.selector.lobbyshort,
                "typed_norms_tuple": ctx.selector.typed_norms_tuple,
                "selected_names": ctx.selector.selected_names,
                "selected_filer_ids": ctx.selector.selected_filer_ids,
                "name_to_short": ctx.app_lookups.name_to_short,
                "short_to_names": ctx.app_lookups.short_to_names,
                "filerid_to_short": ctx.app_lookups.filerid_to_short,
                "lobby_scope_bundle": ctx.scope_bundle,
                "lobby_detail_bundle": ctx.detail_bundle,
                "_prepared_lobby_workspace": True,
            }
        )
        return payload
    return dict(getattr(ctx, "payload", ctx) or {})


def normalize_map_workspace_context(ctx: Any) -> dict[str, Any]:
    if isinstance(ctx, MapWorkspacePreparedContext):
        payload = dict(ctx.payload)
        payload.update(
            {
                "PATH": ctx.selector.path,
                "_map_runtime_signature": ctx.selector.runtime_signature,
                "_map_forensics_source_signature": ctx.selector.forensics_source_signature,
            }
        )
        return payload
    return dict(getattr(ctx, "payload", ctx) or {})


def merge_workspace_runtime_context(
    payload: dict[str, Any],
    services: WorkspaceServices | MapServices | None,
) -> dict[str, Any]:
    runtime_ctx = dict(getattr(services, "values", {}))
    runtime_ctx.update(dict(payload or {}))
    return runtime_ctx
