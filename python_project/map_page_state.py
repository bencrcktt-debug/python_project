from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Callable, Mapping

import pandas as pd


_MAP_MATCH_COLUMNS = [
    "subdivision_type",
    "subdivision_name",
    "subdivision_code",
    "lon",
    "lat",
    "match_count",
    "match_clients",
    "match_clients_preview",
    "source_name",
    "source_url",
]
_MAP_EDGE_COLUMNS = [
    "Client",
    "subdivision_type",
    "subdivision_name",
    "subdivision_code",
    "lon",
    "lat",
    "source_name",
    "source_url",
]
_ATLAS_MATCH_COLUMNS = [
    "subdivision_type",
    "subdivision_name",
    "subdivision_code",
    "lon",
    "lat",
    "match_count",
    "match_clients",
    "match_clients_preview",
    "source_name",
    "source_url",
    "low_total",
    "high_total",
]


@dataclass(frozen=True)
class MapState:
    path: str
    lobby_tfl_client_all: pd.DataFrame
    map_sessions: tuple[str, ...]
    default_map_session: str | None
    tfl_entity_names_all: tuple[str, ...]
    entity_type_by_client: dict[str, str]
    reference_tables: dict[str, pd.DataFrame]
    client_subdivision_matches_all: pd.DataFrame
    client_subdivision_edges_all: pd.DataFrame
    client_subdivision_edges_by_type: dict[str, pd.DataFrame]


@dataclass(frozen=True)
class AtlasBundle:
    scope: str
    session_for_filter: str | None
    totals: pd.DataFrame
    tfl_spend: pd.DataFrame
    subdivision_matches: pd.DataFrame
    matched_clients: frozenset[str]
    total_tfl: int
    total_high: float
    mapped_high: float
    mapped_rate: float
    unmapped_count: int
    prepared_overlap_pools: dict[str, pd.DataFrame]
    spend_lookup: dict[str, dict[str, Any]]
    map_payload: tuple[dict[str, Any], ...]
    map_payload_signature: str


def _dataframe_or_empty(value: object, columns: list[str] | None = None) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value.copy()
    return pd.DataFrame(columns=columns or [])


def _session_sort_key(session_val: str) -> tuple[int, int, int]:
    s = str(session_val).strip()
    if not s:
        return (0, 2, 0)
    if s.isdigit():
        base = int(s[:-1]) if len(s) >= 2 else int(s)
        special = int(s[-1]) if len(s) >= 2 else 0
        return (base, 1, special)
    match = re.match(r"^(\d+)\s*R$", s, flags=re.IGNORECASE)
    if match:
        return (int(match.group(1)), 0, 0)
    return (0, 2, 0)


def _default_session_from_list(sessions: list[str]) -> str:
    if not sessions:
        return ""
    if "89R" in sessions:
        return "89R"
    regular = [
        s
        for s in sessions
        if str(s).strip().upper().endswith("R") and str(s).strip()[:-1].isdigit()
    ]
    if regular:
        return sorted(regular, key=_session_sort_key)[-1]
    return sorted(sessions, key=_session_sort_key)[-1]


def _clean_sessions(series: pd.Series) -> tuple[str, ...]:
    if not isinstance(series, pd.Series):
        return ()
    sessions = [
        str(value).strip()
        for value in series.dropna().astype(str).tolist()
        if str(value).strip()
    ]
    if not sessions:
        return ()
    return tuple(sorted(set(sessions), key=_session_sort_key))


def _normalize_lobby_tfl_client_all(
    lobby_tfl_client_all: pd.DataFrame,
    classify_entity_type: Callable[[str], str],
) -> pd.DataFrame:
    base = _dataframe_or_empty(lobby_tfl_client_all).copy()
    required_defaults = {
        "Session": "",
        "Client": "",
        "LobbyShort": "",
        "IsTFL": 0,
        "Low_num": 0.0,
        "High_num": 0.0,
        "Low": 0.0,
        "High": 0.0,
    }
    for column, default in required_defaults.items():
        if column not in base.columns:
            base[column] = default
    base["Session"] = base["Session"].fillna("").astype(str).str.strip()
    base["Client"] = base["Client"].fillna("").astype(str).str.strip()
    base["ClientNorm"] = base["Client"].str.upper().str.replace(r"[^\w]+", "", regex=True)
    base["LobbyShort"] = base["LobbyShort"].fillna("").astype(str).str.strip()
    base["IsTFL"] = pd.to_numeric(base["IsTFL"], errors="coerce").fillna(0).astype(int)
    low_source = base["Low_num"] if "Low_num" in base.columns else base["Low"]
    high_source = base["High_num"] if "High_num" in base.columns else base["High"]
    base["Low_num"] = pd.to_numeric(low_source, errors="coerce").fillna(0.0)
    base["High_num"] = pd.to_numeric(high_source, errors="coerce").fillna(0.0)
    base["Entity Type"] = base["Client"].map(lambda value: str(classify_entity_type(str(value).strip()) or "").strip())
    return base


def _unique_tfl_entity_names(base: pd.DataFrame) -> tuple[str, ...]:
    if base.empty:
        return ()
    values = (
        base.loc[base["IsTFL"] == 1, "Client"]
        .dropna()
        .astype(str)
        .str.strip()
        .tolist()
    )
    return tuple(sorted({value for value in values if value}))


def _expand_client_subdivision_edges(matches: pd.DataFrame) -> pd.DataFrame:
    if matches.empty:
        return pd.DataFrame(columns=_MAP_EDGE_COLUMNS)
    rows: list[dict[str, Any]] = []
    for row in matches.itertuples(index=False):
        clients = getattr(row, "match_clients", [])
        if not isinstance(clients, list):
            continue
        for client in clients:
            client_name = str(client).strip()
            if not client_name:
                continue
            rows.append(
                {
                    "Client": client_name,
                    "subdivision_type": str(getattr(row, "subdivision_type", "")).strip(),
                    "subdivision_name": str(getattr(row, "subdivision_name", "")).strip(),
                    "subdivision_code": str(getattr(row, "subdivision_code", "")).strip(),
                    "lon": float(getattr(row, "lon", 0.0) or 0.0),
                    "lat": float(getattr(row, "lat", 0.0) or 0.0),
                    "source_name": str(getattr(row, "source_name", "")).strip(),
                    "source_url": str(getattr(row, "source_url", "")).strip(),
                }
            )
    if not rows:
        return pd.DataFrame(columns=_MAP_EDGE_COLUMNS)
    out = pd.DataFrame(rows, columns=_MAP_EDGE_COLUMNS)
    out = out.drop_duplicates(
        ["Client", "subdivision_type", "subdivision_name", "subdivision_code"],
        keep="first",
    )
    return out.sort_values(
        ["subdivision_type", "subdivision_name", "Client"],
        ascending=[True, True, True],
    ).reset_index(drop=True)


def build_map_state_from_sources(
    path: str,
    workbook: Mapping[str, object],
    *,
    classify_entity_type: Callable[[str], str],
    fetch_reference_tables: Callable[[], Mapping[str, pd.DataFrame]],
    build_client_matches: Callable[[tuple[str, ...], Mapping[str, pd.DataFrame]], pd.DataFrame],
) -> MapState:
    data = dict(workbook or {})
    lobby_tfl_client_all = _normalize_lobby_tfl_client_all(
        _dataframe_or_empty(data.get("Lobby_TFL_Client_All")),
        classify_entity_type,
    )
    map_sessions = _clean_sessions(lobby_tfl_client_all.get("Session", pd.Series(dtype=object)))
    default_map_session = _default_session_from_list(list(map_sessions)) if map_sessions else None
    tfl_entity_names_all = _unique_tfl_entity_names(lobby_tfl_client_all)
    entity_type_by_client = {
        client: str(classify_entity_type(client) or "").strip()
        for client in tfl_entity_names_all
    }
    reference_tables = {
        str(key): _dataframe_or_empty(value)
        for key, value in dict(fetch_reference_tables() or {}).items()
    }
    client_subdivision_matches_all = _dataframe_or_empty(
        build_client_matches(tfl_entity_names_all, reference_tables),
        columns=_MAP_MATCH_COLUMNS,
    )
    client_subdivision_edges_all = _expand_client_subdivision_edges(client_subdivision_matches_all)
    client_subdivision_edges_by_type: dict[str, pd.DataFrame] = {}
    if not client_subdivision_edges_all.empty:
        for subdivision_type, piece in client_subdivision_edges_all.groupby("subdivision_type", sort=False):
            key = str(subdivision_type).strip()
            if key:
                client_subdivision_edges_by_type[key] = piece.reset_index(drop=True).copy()
    return MapState(
        path=path,
        lobby_tfl_client_all=lobby_tfl_client_all,
        map_sessions=map_sessions,
        default_map_session=default_map_session,
        tfl_entity_names_all=tfl_entity_names_all,
        entity_type_by_client=entity_type_by_client,
        reference_tables=reference_tables,
        client_subdivision_matches_all=client_subdivision_matches_all,
        client_subdivision_edges_all=client_subdivision_edges_all,
        client_subdivision_edges_by_type=client_subdivision_edges_by_type,
    )


def _build_client_totals(
    base: pd.DataFrame,
    scope: str,
    session_for_filter: str | None,
) -> pd.DataFrame:
    cols = ["Client", "Low", "High", "Lobbyists", "IsTFL", "Entity Type"]
    if base.empty:
        return pd.DataFrame(columns=cols)
    scoped = base
    if str(scope).strip() == "This Session" and session_for_filter:
        scoped = scoped[scoped["Session"].astype(str).str.strip() == str(session_for_filter).strip()]
    if scoped.empty:
        return pd.DataFrame(columns=cols)
    grouped = (
        scoped.groupby("Client", as_index=False)
        .agg(
            Low=("Low_num", "sum"),
            High=("High_num", "sum"),
            Lobbyists=("LobbyShort", lambda series: series.dropna().astype(str).str.strip().replace("", pd.NA).dropna().nunique()),
            IsTFL=("IsTFL", "max"),
            EntityType=("Entity Type", lambda series: next((str(value).strip() for value in series if str(value).strip()), "")),
        )
        .rename(columns={"EntityType": "Entity Type"})
    )
    grouped["Low"] = pd.to_numeric(grouped["Low"], errors="coerce").fillna(0.0)
    grouped["High"] = pd.to_numeric(grouped["High"], errors="coerce").fillna(0.0)
    grouped["Lobbyists"] = pd.to_numeric(grouped["Lobbyists"], errors="coerce").fillna(0).astype(int)
    grouped["IsTFL"] = pd.to_numeric(grouped["IsTFL"], errors="coerce").fillna(0).astype(int)
    return grouped[cols]


def _match_preview(values: list[str], limit: int = 6) -> str:
    if not values:
        return ""
    preview = ", ".join(values[:limit])
    if len(values) > limit:
        return f"{preview}, +{len(values) - limit} more"
    return preview


def _build_spend_lookup(tfl_spend: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if tfl_spend.empty:
        return {}
    spend = tfl_spend.copy()
    spend["Client"] = spend["Client"].fillna("").astype(str).str.strip()
    spend = spend[spend["Client"] != ""]
    if spend.empty:
        return {}
    spend["Low"] = pd.to_numeric(spend.get("Low", 0.0), errors="coerce").fillna(0.0)
    spend["High"] = pd.to_numeric(spend.get("High", 0.0), errors="coerce").fillna(0.0)
    spend["Lobbyists"] = pd.to_numeric(spend.get("Lobbyists", 0), errors="coerce").fillna(0).astype(int)
    if "EntityType" not in spend.columns:
        if "Entity Type" in spend.columns:
            spend["EntityType"] = spend["Entity Type"]
        elif "Entity_Type" in spend.columns:
            spend["EntityType"] = spend["Entity_Type"]
        else:
            spend["EntityType"] = ""
    spend["EntityType"] = spend["EntityType"].fillna("").astype(str).str.strip()
    return {
        str(record["Client"]): {
            "Low": float(record["Low"]),
            "High": float(record["High"]),
            "Lobbyists": int(record["Lobbyists"]),
            "EntityType": str(record.get("EntityType", "")).strip(),
        }
        for record in spend[["Client", "Low", "High", "Lobbyists", "EntityType"]].to_dict("records")
    }


def _aggregate_subdivision_matches(
    edges_all: pd.DataFrame,
    tfl_spend: pd.DataFrame,
) -> pd.DataFrame:
    if edges_all.empty or tfl_spend.empty:
        return pd.DataFrame(columns=_ATLAS_MATCH_COLUMNS)
    active_clients = {
        str(value).strip()
        for value in tfl_spend["Client"].dropna().astype(str).tolist()
        if str(value).strip()
    }
    if not active_clients:
        return pd.DataFrame(columns=_ATLAS_MATCH_COLUMNS)
    scoped_edges = edges_all[edges_all["Client"].astype(str).isin(active_clients)].copy()
    if scoped_edges.empty:
        return pd.DataFrame(columns=_ATLAS_MATCH_COLUMNS)
    spend = tfl_spend[["Client", "Low", "High"]].copy()
    spend["Client"] = spend["Client"].fillna("").astype(str).str.strip()
    spend = spend[spend["Client"] != ""]
    spend["Low"] = pd.to_numeric(spend["Low"], errors="coerce").fillna(0.0)
    spend["High"] = pd.to_numeric(spend["High"], errors="coerce").fillna(0.0)
    scoped_edges = scoped_edges.merge(spend, on="Client", how="left")
    scoped_edges["Low"] = pd.to_numeric(scoped_edges.get("Low", 0.0), errors="coerce").fillna(0.0)
    scoped_edges["High"] = pd.to_numeric(scoped_edges.get("High", 0.0), errors="coerce").fillna(0.0)
    grouped = (
        scoped_edges.groupby(
            ["subdivision_type", "subdivision_name", "subdivision_code", "lon", "lat"],
            as_index=False,
            sort=False,
        )
        .agg(
            match_clients=("Client", lambda series: sorted({str(value).strip() for value in series if str(value).strip()})),
            low_total=("Low", "sum"),
            high_total=("High", "sum"),
            source_name=("source_name", lambda series: "; ".join(sorted({str(value).strip() for value in series if str(value).strip()}))),
            source_url=("source_url", lambda series: "; ".join(sorted({str(value).strip() for value in series if str(value).strip()}))),
        )
    )
    if grouped.empty:
        return pd.DataFrame(columns=_ATLAS_MATCH_COLUMNS)
    grouped["match_count"] = grouped["match_clients"].map(len).astype(int)
    grouped["match_clients_preview"] = grouped["match_clients"].map(_match_preview)
    grouped["low_total"] = pd.to_numeric(grouped["low_total"], errors="coerce").fillna(0.0)
    grouped["high_total"] = pd.to_numeric(grouped["high_total"], errors="coerce").fillna(0.0)
    grouped = grouped.sort_values(
        ["subdivision_type", "match_count", "subdivision_name"],
        ascending=[True, False, True],
    )
    return grouped[_ATLAS_MATCH_COLUMNS].reset_index(drop=True)


def _coverage_metrics(
    subdivision_matches: pd.DataFrame,
    tfl_spend: pd.DataFrame,
) -> tuple[frozenset[str], int, float, float, float, int]:
    matched_clients: set[str] = set()
    if not subdivision_matches.empty:
        for values in subdivision_matches.get("match_clients", pd.Series(dtype=object)).tolist():
            if isinstance(values, list):
                matched_clients.update({str(value).strip() for value in values if str(value).strip()})
    total_tfl = int(tfl_spend["Client"].astype(str).nunique()) if not tfl_spend.empty else 0
    total_high = (
        float(pd.to_numeric(tfl_spend.get("High", 0.0), errors="coerce").fillna(0.0).sum())
        if not tfl_spend.empty
        else 0.0
    )
    mapped_high = 0.0
    if not tfl_spend.empty and matched_clients:
        mapped_high = float(
            pd.to_numeric(
                tfl_spend[tfl_spend["Client"].astype(str).isin(matched_clients)]["High"],
                errors="coerce",
            )
            .fillna(0.0)
            .sum()
        )
    mapped_rate = (len(matched_clients) / total_tfl) if total_tfl else 0.0
    unmapped_count = max(0, total_tfl - len(matched_clients))
    return frozenset(matched_clients), total_tfl, total_high, mapped_high, mapped_rate, unmapped_count


def build_compact_map_payload(
    subdivision_matches: pd.DataFrame,
    *,
    client_preview_limit: int = 14,
) -> tuple[dict[str, Any], ...]:
    if subdivision_matches.empty:
        return ()
    rows: list[dict[str, Any]] = []
    for row in subdivision_matches.itertuples(index=False):
        match_clients = getattr(row, "match_clients", [])
        safe_clients = [str(value).strip() for value in match_clients if str(value).strip()] if isinstance(match_clients, list) else []
        preview = ", ".join(safe_clients[:client_preview_limit])
        rows.append(
            {
                "subdivision_type": str(getattr(row, "subdivision_type", "")).strip(),
                "subdivision_name": str(getattr(row, "subdivision_name", "")).strip(),
                "subdivision_code": str(getattr(row, "subdivision_code", "")).strip(),
                "source_name": str(getattr(row, "source_name", "")).strip(),
                "lon": round(float(getattr(row, "lon", 0.0) or 0.0), 6),
                "lat": round(float(getattr(row, "lat", 0.0) or 0.0), 6),
                "match_count": int(getattr(row, "match_count", 0) or 0),
                "high_total": round(float(getattr(row, "high_total", 0.0) or 0.0), 2),
                "match_clients_preview": preview,
                "extra_count": max(0, len(safe_clients) - client_preview_limit),
            }
        )
    return tuple(rows)


def build_payload_signature(payload: tuple[dict[str, Any], ...] | list[dict[str, Any]]) -> str:
    payload_json = json.dumps(list(payload), ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha1(payload_json.encode("utf-8")).hexdigest()


def build_atlas_bundle(
    map_state: MapState,
    scope: str,
    session_for_filter: str | None,
    *,
    prepare_overlap_pool: Callable[[pd.DataFrame, str], pd.DataFrame] | None = None,
) -> AtlasBundle:
    totals = _build_client_totals(
        map_state.lobby_tfl_client_all,
        scope=scope,
        session_for_filter=session_for_filter,
    )
    tfl_spend = totals[totals["IsTFL"] == 1].reset_index(drop=True).copy()
    subdivision_matches = _aggregate_subdivision_matches(
        map_state.client_subdivision_edges_all,
        tfl_spend,
    )
    matched_clients, total_tfl, total_high, mapped_high, mapped_rate, unmapped_count = _coverage_metrics(
        subdivision_matches,
        tfl_spend,
    )
    prepared_overlap_pools: dict[str, pd.DataFrame] = {}
    if prepare_overlap_pool is not None and not subdivision_matches.empty:
        for subdivision_type, piece in subdivision_matches.groupby("subdivision_type", sort=False):
            key = str(subdivision_type).strip()
            if key:
                prepared_overlap_pools[key] = prepare_overlap_pool(piece.copy(), key)
    map_payload = build_compact_map_payload(subdivision_matches)
    return AtlasBundle(
        scope=str(scope).strip(),
        session_for_filter=str(session_for_filter).strip() if session_for_filter else None,
        totals=totals.reset_index(drop=True).copy(),
        tfl_spend=tfl_spend,
        subdivision_matches=subdivision_matches,
        matched_clients=matched_clients,
        total_tfl=total_tfl,
        total_high=total_high,
        mapped_high=mapped_high,
        mapped_rate=mapped_rate,
        unmapped_count=unmapped_count,
        prepared_overlap_pools=prepared_overlap_pools,
        spend_lookup=_build_spend_lookup(tfl_spend),
        map_payload=map_payload,
        map_payload_signature=build_payload_signature(map_payload),
    )
