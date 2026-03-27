from __future__ import annotations

from dataclasses import dataclass

from tfl_app.services import MapServices, WorkspaceServices

from . import map_fragments as _map_fragments
from . import page_fragments as _page_fragments


@dataclass(frozen=True)
class BoundPageFragments:
    services: WorkspaceServices

    def merge_fragment_session_context(self, storage_key: str, selector_updates: dict[str, object]) -> dict[str, object]:
        return _page_fragments.merge_fragment_session_context(storage_key, selector_updates)

    def render_client_workspace_fragment(self, storage_key: str = "_client_workspace_ctx") -> None:
        _page_fragments.render_client_workspace_fragment(self.services, storage_key)

    def render_member_workspace_fragment(self, storage_key: str = "_member_workspace_ctx") -> None:
        _page_fragments.render_member_workspace_fragment(self.services, storage_key)

    def render_lobby_workspace_fragment(self, storage_key: str = "_lobby_workspace_ctx") -> None:
        _page_fragments.render_lobby_workspace_fragment(self.services, storage_key)


@dataclass(frozen=True)
class BoundMapFragments:
    services: MapServices

    def merge_fragment_session_context(self, storage_key: str, selector_updates: dict[str, object]) -> dict[str, object]:
        return _page_fragments.merge_fragment_session_context(storage_key, selector_updates)

    def remember_map_workspace_transient_context(self, storage_key: str, ctx: dict[str, object]) -> None:
        _map_fragments.remember_map_workspace_transient_context(storage_key, ctx)

    def render_map_workspace_fragment(self, storage_key: str = "_map_workspace_ctx") -> None:
        _map_fragments.render_map_workspace_fragment(self.services, storage_key)
