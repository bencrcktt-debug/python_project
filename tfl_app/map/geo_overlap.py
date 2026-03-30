from __future__ import annotations

import difflib
import html
import re
from typing import Any, Callable

import pandas as pd

from tfl_app.bundles.page_bundles import ensure_cols
from tfl_app.map.geo_matching import (
    PORT_AUTHORITY_ROOT_PATTERNS,
    SPECIAL_NAME_ANCHORED_ENTITY_TYPES,
    SUBDIVISION_TYPE_COLORS,
    TRANSIT_AUTHORITY_ROOT_PATTERNS,
    WATER_DISTRICT_TYPE_ROOT_PATTERNS,
    _city_root_key,
    _county_root_key,
    _resolve_special_anchor_keys,
    _school_district_root_key,
    _subdivision_root_from_patterns,
)
from tfl_app.shared.names import norm_name


def _subdivision_name_key(subdivision_type: str, subdivision_name: str) -> str:
    lowered = str(subdivision_type).strip().lower()
    if lowered == "school district":
        return _school_district_root_key(subdivision_name)
    if lowered == "county":
        return _county_root_key(subdivision_name)
    if lowered == "city":
        return _city_root_key(subdivision_name)
    for water_type, root_patterns in WATER_DISTRICT_TYPE_ROOT_PATTERNS.items():
        if lowered == water_type.lower():
            return _subdivision_root_from_patterns(subdivision_name, root_patterns)
    if lowered == "transit authority":
        return _subdivision_root_from_patterns(subdivision_name, TRANSIT_AUTHORITY_ROOT_PATTERNS)
    if lowered == "port authority":
        return _subdivision_root_from_patterns(subdivision_name, PORT_AUTHORITY_ROOT_PATTERNS)
    if lowered == "hospital district":
        return _subdivision_root_from_patterns(subdivision_name, [r"\bHOSPITAL\s+DISTRICT\b", r"\bDISTRICT\b"])
    if lowered == "emergency services district":
        return _subdivision_root_from_patterns(
            subdivision_name,
            [r"\bEMERGENCY\s+SERVICES\s+DISTRICT\b", r"\bDISTRICT\b", r"\bE\.?S\.?D\.?\b"],
        )
    if lowered == "appraisal district":
        return _subdivision_root_from_patterns(
            subdivision_name,
            [r"\bAPPRAISAL\s+DISTRICT\b", r"\bDISTRICT\b", r"\bC\.?A\.?D\.?\b"],
        )
    if lowered == "local government corporation":
        return _subdivision_root_from_patterns(
            subdivision_name,
            [r"\bLOCAL\s+GOVERNMENT\s+CORPORATION\b", r"\bDEVELOPMENT\s+CORPORATION\b", r"\bCORPORATION\b"],
        )
    if lowered == "groundwater conservation district":
        return _subdivision_root_from_patterns(
            subdivision_name,
            [r"\bGROUNDWATER\s+CONSERVATION\s+DISTRICT\b", r"\bDISTRICT\b"],
        )
    if lowered == "regional mobility authority":
        return _subdivision_root_from_patterns(
            subdivision_name,
            [r"\bREGIONAL\s+MOBILITY\s+AUTHORITY\b", r"\bAUTHORITY\b", r"\bRMA\b"],
        )
    if lowered == "junior college district":
        return _subdivision_root_from_patterns(
            subdivision_name,
            [
                r"\bCOMMUNITY\s+COLLEGE\b",
                r"\bJUNIOR\s+COLLEGE\b",
                r"\bCOLLEGE\s+DISTRICT\b",
                r"\bSERVICE\s+AREA\b",
                r"\bCOLLEGE\b",
                r"\bDISTRICT\b",
            ],
        )
    return norm_name(subdivision_name)


def _subdivision_code_key(subdivision_code: str) -> str:
    return norm_name(str(subdivision_code).strip())


def _subdivision_numeric_code_key(subdivision_code: str) -> str:
    digits = re.sub(r"\D+", "", str(subdivision_code).strip())
    if not digits:
        return ""
    stripped = digits.lstrip("0")
    return stripped if stripped else digits


def prepare_subdivision_match_pool(pool: pd.DataFrame, subdivision_type: str) -> pd.DataFrame:
    if pool.empty:
        return pool
    out = pool.copy()
    code_series = (
        out["subdivision_code"].astype(str)
        if "subdivision_code" in out.columns
        else pd.Series([""] * len(out), index=out.index, dtype=object).astype(str)
    )
    name_series = (
        out["subdivision_name"].astype(str)
        if "subdivision_name" in out.columns
        else pd.Series([""] * len(out), index=out.index, dtype=object).astype(str)
    )
    out["_code_key"] = code_series.map(_subdivision_code_key)
    out["_code_numeric_key"] = code_series.map(_subdivision_numeric_code_key)
    out["_name_key"] = name_series.map(lambda value: _subdivision_name_key(subdivision_type, value))
    return out


def _pick_overlap_subdivision_matches(
    pool: pd.DataFrame,
    subdivision_type: str,
    subdivision_name: str,
    subdivision_code: str,
) -> tuple[pd.DataFrame, str]:
    if pool.empty:
        return pd.DataFrame(), ""
    code_key = _subdivision_code_key(subdivision_code)
    if code_key and "_code_key" in pool.columns:
        picked = pool[pool["_code_key"].astype(str) == code_key]
        if not picked.empty:
            return picked, "Spatial boundary (code)"
    numeric_code_key = _subdivision_numeric_code_key(subdivision_code)
    if numeric_code_key and "_code_numeric_key" in pool.columns:
        picked = pool[pool["_code_numeric_key"].astype(str) == numeric_code_key]
        if not picked.empty:
            return picked, "Spatial boundary (code)"
    name_key = _subdivision_name_key(subdivision_type, subdivision_name)
    if name_key and "_name_key" in pool.columns:
        picked = pool[pool["_name_key"].astype(str) == name_key]
        if not picked.empty:
            return picked, "Spatial boundary (name)"
        if len(name_key) >= 6:
            name_pool = pool[pool["_name_key"].astype(str) != ""].copy()
            if not name_pool.empty:
                name_pool["_name_score"] = name_pool["_name_key"].astype(str).map(
                    lambda value: difflib.SequenceMatcher(None, name_key, str(value)).ratio()
                )
                name_pool = name_pool[name_pool["_name_score"] >= 0.90]
                if not name_pool.empty:
                    best_score = float(name_pool["_name_score"].max())
                    picked = name_pool[name_pool["_name_score"] >= max(0.90, best_score - 0.03)]
                    if not picked.empty:
                        return picked.drop(columns=["_name_score"], errors="ignore"), "Spatial boundary (fuzzy)"
    return pd.DataFrame(), ""


def _match_confidence_from_method(match_method: str) -> str:
    method = str(match_method).strip().lower()
    if method in {"spatial boundary (code)", "spatial boundary (name)"}:
        return "High"
    if method == "spatial boundary (fuzzy)":
        return "Medium"
    if method in {"name anchored", "name + geocode context"}:
        return "Low"
    return "Unknown"


def _subdivision_color_hex(subdivision_type: str) -> str:
    return SUBDIVISION_TYPE_COLORS.get(str(subdivision_type).strip(), "#718191")


def _hex_to_rgba(color_hex: str, alpha: float = 0.88) -> list[float]:
    color = str(color_hex).strip().lstrip("#")
    if len(color) != 6 or not re.match(r"^[0-9a-fA-F]{6}$", color):
        return [113, 129, 145, alpha]
    return [int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16), alpha]


def render_subdivision_map_legend(type_counts: dict[str, int], *, markdown: Callable[..., None]) -> None:
    items = []
    for subtype, count in sorted(type_counts.items(), key=lambda item: (-int(item[1]), str(item[0]))):
        safe_type = html.escape(str(subtype), quote=True)
        safe_count = f"{int(count):,}"
        color = _subdivision_color_hex(str(subtype))
        items.append(
            f"""
<div class="map-legend-item">
  <div class="map-legend-left">
    <span class="map-legend-chip" style="background:{color};"></span>
    <span>{safe_type}</span>
  </div>
  <strong>{safe_count}</strong>
</div>
"""
        )
    if items:
        markdown(f'<div class="map-legend">{"".join(items)}</div>', unsafe_allow_html=True)


def build_address_overlap_spending_rows_impl(
    overlap_subdivisions: pd.DataFrame,
    subdivision_matches: pd.DataFrame,
    tfl_spending: pd.DataFrame,
    *,
    prepared_overlap_pools: dict[str, pd.DataFrame] | None = None,
    spend_lookup: dict[str, dict[str, object]] | None = None,
    classify_requested_entity_type,
    geocode_texas_entity_arcgis,
    query_texas_county_for_point,
    prepare_subdivision_match_pool_cached,
) -> pd.DataFrame:
    cols = ["Subdivision Type", "Subdivision", "Code", "Entity Type", "TFL Entity", "Match Method", "Match Confidence", "Map Source", "Low", "High", "Mid", "Lobbyists"]
    if overlap_subdivisions.empty or subdivision_matches.empty or tfl_spending.empty:
        return pd.DataFrame(columns=cols)

    spend_lookup_local = dict(spend_lookup or {})
    if not spend_lookup_local:
        spend = ensure_cols(tfl_spending.copy(), {"Client": "", "Low": 0.0, "High": 0.0, "Lobbyists": 0})
        spend["Client"] = spend["Client"].fillna("").astype(str).str.strip()
        spend = spend[spend["Client"] != ""]
        if spend.empty:
            return pd.DataFrame(columns=cols)
        spend["Low"] = pd.to_numeric(spend["Low"], errors="coerce").fillna(0.0)
        spend["High"] = pd.to_numeric(spend["High"], errors="coerce").fillna(0.0)
        spend["Lobbyists"] = pd.to_numeric(spend["Lobbyists"], errors="coerce").fillna(0).astype(int)
        spend["EntityType"] = spend["Client"].map(classify_requested_entity_type)
        spend = spend.groupby("Client", as_index=False).agg(Low=("Low", "sum"), High=("High", "sum"), Lobbyists=("Lobbyists", "max"), EntityType=("EntityType", "first"))
        spend_lookup_local = {str(row.Client): {"Low": float(row.Low), "High": float(row.High), "Lobbyists": int(row.Lobbyists), "EntityType": str(row.EntityType).strip()} for row in spend.itertuples(index=False)}

    rows: list[dict[str, Any]] = []
    existing_keys: set[tuple[str, str, str, str]] = set()
    prepared_overlap_pools = prepared_overlap_pools or {}
    pool_cache: dict[str, pd.DataFrame] = {}
    for overlap in overlap_subdivisions.itertuples(index=False):
        subdivision_type = str(overlap.subdivision_type).strip()
        subdivision_name = str(overlap.subdivision_name).strip()
        subdivision_code = str(overlap.subdivision_code).strip()
        if subdivision_type in prepared_overlap_pools:
            pool = prepared_overlap_pools.get(subdivision_type, pd.DataFrame())
        else:
            if subdivision_type not in pool_cache:
                base_pool = subdivision_matches[subdivision_matches["subdivision_type"].astype(str) == subdivision_type]
                pool_cache[subdivision_type] = prepare_subdivision_match_pool_cached(subdivision_type, base_pool)
            pool = pool_cache.get(subdivision_type, pd.DataFrame())
        if pool.empty:
            continue
        picked, spatial_match_method = _pick_overlap_subdivision_matches(pool, subdivision_type, subdivision_name, subdivision_code)
        if picked.empty:
            continue
        matched_clients: set[str] = set()
        picked_source_names = {str(value).strip() for value in picked.get("source_name", pd.Series(dtype=object)).dropna().astype(str).tolist() if str(value).strip()}
        picked_source = "; ".join(sorted(picked_source_names))
        for client_list in picked.get("match_clients", pd.Series(dtype=object)).tolist():
            if isinstance(client_list, list):
                matched_clients.update({str(value).strip() for value in client_list if str(value).strip()})
        for client in sorted(matched_clients):
            spend_vals = spend_lookup_local.get(client, {"Low": 0.0, "High": 0.0, "Lobbyists": 0, "EntityType": ""})
            low = float(spend_vals.get("Low", 0.0))
            high = float(spend_vals.get("High", 0.0))
            entity_type = str(spend_vals.get("EntityType", "")).strip()
            method = spatial_match_method or "Spatial boundary (name)"
            rows.append({"Subdivision Type": subdivision_type, "Subdivision": subdivision_name, "Code": subdivision_code, "Entity Type": entity_type, "TFL Entity": client, "Match Method": method, "Match Confidence": _match_confidence_from_method(method), "Map Source": picked_source, "Low": low, "High": high, "Mid": (low + high) / 2, "Lobbyists": int(spend_vals.get("Lobbyists", 0))})
            existing_keys.add((subdivision_type, subdivision_name, subdivision_code, client))

    unsupported_types = {"Hospital District", "Emergency Services District", "Local Government Corporation", "Transit Authority", "Port Authority", "Housing Authority", "Appraisal District"}
    county_lookup = {_county_root_key(str(row.subdivision_name)): (str(row.subdivision_name), str(row.subdivision_code)) for row in overlap_subdivisions.itertuples(index=False) if str(row.subdivision_type).strip() == "County" and _county_root_key(str(row.subdivision_name))}
    city_lookup = {_city_root_key(str(row.subdivision_name)): (str(row.subdivision_name), str(row.subdivision_code)) for row in overlap_subdivisions.itertuples(index=False) if str(row.subdivision_type).strip() == "City" and _city_root_key(str(row.subdivision_name))}
    school_lookup = {_school_district_root_key(str(row.subdivision_name)): (str(row.subdivision_name), str(row.subdivision_code)) for row in overlap_subdivisions.itertuples(index=False) if str(row.subdivision_type).strip() == "School District" and _school_district_root_key(str(row.subdivision_name))}
    county_lookup_keys = tuple(key for key in county_lookup.keys() if key)
    city_lookup_keys = tuple(key for key in city_lookup.keys() if key)

    for client, spend_vals in spend_lookup_local.items():
        entity_type = str(spend_vals.get("EntityType", "")).strip()
        if entity_type not in unsupported_types:
            continue
        low = float(spend_vals.get("Low", 0.0))
        high = float(spend_vals.get("High", 0.0))
        lobbyists = int(spend_vals.get("Lobbyists", 0))
        matched_targets: list[tuple[str, str, str, str, str]] = []
        anchor_keys = _resolve_special_anchor_keys(client_name=client, entity_type=entity_type, county_lookup_keys=county_lookup_keys, city_lookup_keys=city_lookup_keys)
        county_key = str(anchor_keys.get("county_key", "")).strip()
        if county_key and county_key in county_lookup:
            name, code = county_lookup[county_key]
            matched_targets.append(("County", name, code, "Name anchored", "Name anchored via overlapping core boundaries"))
        city_key = str(anchor_keys.get("city_key", "")).strip()
        if city_key and city_key in city_lookup:
            name, code = city_lookup[city_key]
            matched_targets.append(("City", name, code, "Name anchored", "Name anchored via overlapping core boundaries"))
        school_key = _school_district_root_key(client)
        if school_key and school_key in school_lookup:
            name, code = school_lookup[school_key]
            matched_targets.append(("School District", name, code, "Name anchored", "Name anchored via overlapping core boundaries"))

        geocoded = geocode_texas_entity_arcgis(client)
        geocode_score = float(geocoded.get("score", 0.0)) if geocoded else 0.0
        if geocoded and geocode_score >= 70:
            try:
                geo_lon = float(geocoded.get("lon", 0.0))
                geo_lat = float(geocoded.get("lat", 0.0))
            except Exception:
                geo_lon = 0.0
                geo_lat = 0.0
            county_info = query_texas_county_for_point(round(geo_lon, 6), round(geo_lat, 6))
            geo_county = str(county_info.get("county_name", "")).strip()
            geo_county_key = _county_root_key(f"{geo_county} County") if geo_county else ""
            if geo_county_key and geo_county_key in county_lookup:
                name, code = county_lookup[geo_county_key]
                matched_targets.append(("County", name, code, "Name + geocode context", "ArcGIS geocoded entity centroid (Texas)"))
            geo_city = str(geocoded.get("city", "")).strip()
            geo_city_key = _city_root_key(f"{geo_city} City") if geo_city else ""
            if geo_city_key and geo_city_key in city_lookup:
                name, code = city_lookup[geo_city_key]
                matched_targets.append(("City", name, code, "Name + geocode context", "ArcGIS geocoded entity centroid (Texas)"))

        for subdivision_type, subdivision_name, subdivision_code, match_method, map_source in matched_targets:
            row_key = (subdivision_type, subdivision_name, subdivision_code, client)
            if row_key in existing_keys:
                continue
            rows.append({"Subdivision Type": subdivision_type, "Subdivision": subdivision_name, "Code": subdivision_code, "Entity Type": entity_type, "TFL Entity": client, "Match Method": match_method, "Match Confidence": _match_confidence_from_method(match_method), "Map Source": map_source, "Low": low, "High": high, "Mid": (low + high) / 2, "Lobbyists": lobbyists})
            existing_keys.add(row_key)

    if not rows:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame(rows, columns=cols)
    out["_method_order"] = out["Match Method"].map({"Spatial boundary (code)": 0, "Spatial boundary (name)": 1, "Spatial boundary (fuzzy)": 2, "Name anchored": 3, "Name + geocode context": 4}).fillna(9)
    out = out.sort_values(["_method_order", "Mid", "High", "Low", "Subdivision Type", "Subdivision", "TFL Entity"], ascending=[True, False, False, False, True, True, True])
    out = out.drop_duplicates(["Subdivision Type", "Subdivision", "Code", "TFL Entity"], keep="first")
    return out.drop(columns=["_method_order"], errors="ignore")


def build_overlap_map_points_impl(
    overlap_subdivisions: pd.DataFrame,
    subdivision_matches: pd.DataFrame,
    *,
    prepared_overlap_pools: dict[str, pd.DataFrame] | None = None,
    prepare_subdivision_match_pool_cached,
) -> pd.DataFrame:
    cols = ["subdivision_type", "subdivision_name", "subdivision_code", "lon", "lat", "match_count", "high_total", "match_method", "source_name"]
    if overlap_subdivisions.empty or subdivision_matches.empty:
        return pd.DataFrame(columns=cols)
    rows: list[dict[str, Any]] = []
    prepared_overlap_pools = prepared_overlap_pools or {}
    pool_cache: dict[str, pd.DataFrame] = {}
    seen_keys: set[tuple[str, str, str]] = set()
    for overlap in overlap_subdivisions.itertuples(index=False):
        subdivision_type = str(overlap.subdivision_type).strip()
        subdivision_name = str(overlap.subdivision_name).strip()
        subdivision_code = str(overlap.subdivision_code).strip()
        if not subdivision_type or not subdivision_name:
            continue
        if subdivision_type in prepared_overlap_pools:
            pool = prepared_overlap_pools.get(subdivision_type, pd.DataFrame())
        else:
            if subdivision_type not in pool_cache:
                base_pool = subdivision_matches[subdivision_matches["subdivision_type"].astype(str) == subdivision_type]
                pool_cache[subdivision_type] = prepare_subdivision_match_pool_cached(subdivision_type, base_pool)
            pool = pool_cache.get(subdivision_type, pd.DataFrame())
        if pool.empty:
            continue
        picked, match_method = _pick_overlap_subdivision_matches(pool, subdivision_type, subdivision_name, subdivision_code)
        if picked.empty:
            continue
        picked = picked.copy()
        picked["match_count"] = pd.to_numeric(picked.get("match_count", 0), errors="coerce").fillna(0)
        picked = picked.sort_values(["match_count"], ascending=[False])
        best = picked.iloc[0]
        key = (subdivision_type, subdivision_name, subdivision_code)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        rows.append({"subdivision_type": subdivision_type, "subdivision_name": subdivision_name, "subdivision_code": subdivision_code, "lon": float(best.get("lon", 0.0)), "lat": float(best.get("lat", 0.0)), "match_count": int(float(best.get("match_count", 0.0))), "high_total": float(best.get("high_total", 0.0)), "match_method": match_method or "Spatial boundary (name)", "source_name": str(best.get("source_name", "")).strip()})

    overlap_county_keys = {_county_root_key(str(row.subdivision_name)) for row in overlap_subdivisions.itertuples(index=False) if str(row.subdivision_type).strip() == "County" and _county_root_key(str(row.subdivision_name))}
    overlap_city_keys = {_city_root_key(str(row.subdivision_name)) for row in overlap_subdivisions.itertuples(index=False) if str(row.subdivision_type).strip() == "City" and _city_root_key(str(row.subdivision_name))}
    if overlap_county_keys or overlap_city_keys:
        special_types = set(SPECIAL_NAME_ANCHORED_ENTITY_TYPES) | {"Housing Authority"}
        special_matches = subdivision_matches[subdivision_matches["subdivision_type"].astype(str).isin(special_types)]
        county_lookup_keys = tuple(sorted(overlap_county_keys))
        city_lookup_keys = tuple(sorted(overlap_city_keys))
        for row in special_matches.itertuples(index=False):
            subdivision_type = str(getattr(row, "subdivision_type", "")).strip()
            subdivision_name = str(getattr(row, "subdivision_name", "")).strip()
            subdivision_code = str(getattr(row, "subdivision_code", "")).strip()
            if not subdivision_type or not subdivision_name:
                continue
            clients = getattr(row, "match_clients", [])
            client_list = clients if isinstance(clients, list) else [subdivision_name]
            include_point = False
            for client_name in client_list:
                anchor_keys = _resolve_special_anchor_keys(client_name=str(client_name), entity_type=subdivision_type, county_lookup_keys=county_lookup_keys, city_lookup_keys=city_lookup_keys)
                county_key = str(anchor_keys.get("county_key", "")).strip()
                city_key = str(anchor_keys.get("city_key", "")).strip()
                if (county_key and county_key in overlap_county_keys) or (city_key and city_key in overlap_city_keys):
                    include_point = True
                    break
            if not include_point:
                continue
            key = (subdivision_type, subdivision_name, subdivision_code)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            rows.append({"subdivision_type": subdivision_type, "subdivision_name": subdivision_name, "subdivision_code": subdivision_code, "lon": float(getattr(row, "lon", 0.0)), "lat": float(getattr(row, "lat", 0.0)), "match_count": int(getattr(row, "match_count", 0) or 0), "high_total": float(getattr(row, "high_total", 0.0) or 0.0), "match_method": "Name anchored", "source_name": str(getattr(row, "source_name", "")).strip()})

    if not rows:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame(rows, columns=cols).drop_duplicates(["subdivision_type", "subdivision_name", "subdivision_code"])
    return out.sort_values(["subdivision_type", "subdivision_name"], ascending=[True, True])


__all__ = [
    "_hex_to_rgba",
    "_subdivision_color_hex",
    "build_address_overlap_spending_rows_impl",
    "build_overlap_map_points_impl",
    "prepare_subdivision_match_pool",
    "render_subdivision_map_legend",
]
