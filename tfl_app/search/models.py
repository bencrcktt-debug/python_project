from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class AppState:
    path: str
    data_version: str
    data: dict[str, object]
    tables: dict[str, pd.DataFrame]
    table_manifest: dict[str, dict[str, Any]]
    client_index: pd.DataFrame
    author_bills_all: pd.DataFrame
    member_index: pd.DataFrame
    lobby_index: pd.DataFrame
    lobbyist_index: pd.DataFrame
    name_to_short: dict[str, str]
    short_to_names: dict[str, list[str]]
    known_shorts: frozenset[str]
    filerid_to_short: dict[int, str]
    initial_to_short: dict[str, str]
    lobbyshort_to_name: dict[str, str]
    client_scope_overview_all: pd.DataFrame
    client_scope_overview_by_session: pd.DataFrame
    client_category_chart_data: pd.DataFrame
    lobby_scope_pivot_all: pd.DataFrame
    lobby_scope_pivot_by_session: pd.DataFrame
    lobby_scope_trend_group: pd.DataFrame
    lobby_scope_top_clients_all: pd.DataFrame
    lobby_scope_top_clients_by_session: pd.DataFrame
    lobby_display: pd.DataFrame
    shared_sessions: tuple[str, ...]
    default_shared_session: str | None
    map_sessions: tuple[str, ...]
    default_map_session: str | None
    tfl_sessions: frozenset[str]


@dataclass(frozen=True)
class LobbyLookupState:
    lobby_index: pd.DataFrame
    lobbyist_index: pd.DataFrame
    name_to_short: dict[str, str]
    short_to_names: dict[str, list[str]]
    known_shorts: frozenset[str]
    filerid_to_short: dict[int, str]


@dataclass(frozen=True)
class NavSearchBundle:
    query: str
    normalized_query: str
    bill_query: str
    client_suggestions: tuple[str, ...]
    member_suggestions: tuple[str, ...]
    lobby_candidates: tuple[dict[str, Any], ...]
    lobby_suggestions: tuple[str, ...]
    nav_suggestions: tuple[str, ...]
    nav_suggestion_map: dict[str, tuple[str, Any]]
    resolved_client: str = ""
    resolved_member: str = ""
    resolved_lobby: str = ""
    resolved_lobby_filer: int | None = None
    resolved_lobby_name: str = ""


@dataclass(frozen=True)
class NavQueryKey:
    raw: str
