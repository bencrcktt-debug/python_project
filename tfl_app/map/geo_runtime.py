from __future__ import annotations

import difflib
import functools
import hashlib
import html
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

import pandas as pd

try:
    import streamlit as st
except ModuleNotFoundError:  # pragma: no cover - import smoke fallback
    class _CacheStub:
        def __call__(self, *decorator_args, **decorator_kwargs):
            if decorator_args and callable(decorator_args[0]) and len(decorator_args) == 1 and not decorator_kwargs:
                func = decorator_args[0]
                func.clear = lambda: None
                return func

            def decorator(func):
                func.clear = lambda: None
                return func

            return decorator

    class _StreamlitStub:
        cache_data = _CacheStub()

        @staticmethod
        def markdown(*args, **kwargs) -> None:
            return None

    st = _StreamlitStub()

from tfl_app.shared.names import norm_name
from tfl_app.bundles.page_bundles import ensure_cols
import tfl_app.map.geo_matching as _geo_matching
import tfl_app.map.geo_overlap as _geo_overlap
from tfl_app.map.geo_queries import (
    _canonical_water_district_type,
    geocode_address_arcgis,
    geocode_texas_entity_arcgis,
    query_texas_county_for_point,
    query_texas_subdivisions_for_point,
)
from tfl_app.map.reference_runtime import (
    ARCGIS_GEOCODER_URL,
    CENSUS_ARCGIS_TEXAS_CITY_LAYER_URL,
    NCTCOG_TRANSIT_PROVIDERS_LAYER_URL,
    TCEQ_GROUNDWATER_DISTRICTS_LAYER_URL,
    TCEQ_WATER_DISTRICTS_LAYER_URL,
    TEA_ARCGIS_COUNTY_LAYER_URL,
    TEA_ARCGIS_SCHOOL_DISTRICT_LAYER_URL,
    TEXAS_JUNIOR_COLLEGE_LAYER_URL,
    TEXAS_NAVIGATION_DISTRICT_LAYER_URL,
    TEXAS_RMA_LAYER_URL,
    TXDOT_SEAPORTS_LAYER_URL,
    fetch_nctcog_transit_provider_centroids,
    fetch_tceq_groundwater_district_centroids,
    fetch_tceq_water_district_centroids,
    fetch_tea_county_centroids,
    fetch_tea_school_district_centroids,
    fetch_texas_city_centroids,
    fetch_texas_junior_college_centroids,
    fetch_texas_navigation_district_centroids,
    fetch_texas_rma_centroids,
    fetch_txdot_seaport_centroids,
)


def _hash_dataframe_for_cache(df: pd.DataFrame) -> str:
    try:
        digest = hashlib.sha1()
        digest.update(repr(tuple(df.columns)).encode("utf-8"))
        digest.update(repr(tuple(str(dtype) for dtype in df.dtypes)).encode("utf-8"))
        digest.update(pd.util.hash_pandas_object(df, index=False, categorize=False).to_numpy(dtype="uint64", copy=False).tobytes())
        return digest.hexdigest()
    except Exception:
        return f"{len(df)}:{len(df.columns)}"


SUBDIVISION_TYPE_COLORS = _geo_matching.SUBDIVISION_TYPE_COLORS
WATER_DISTRICT_TYPE_ROOT_PATTERNS = _geo_matching.WATER_DISTRICT_TYPE_ROOT_PATTERNS
TRANSIT_AUTHORITY_ROOT_PATTERNS = _geo_matching.TRANSIT_AUTHORITY_ROOT_PATTERNS
PORT_AUTHORITY_ROOT_PATTERNS = _geo_matching.PORT_AUTHORITY_ROOT_PATTERNS
SPECIAL_NAME_ANCHORED_ENTITY_TYPES = _geo_matching.SPECIAL_NAME_ANCHORED_ENTITY_TYPES
SpecialAnchorLookup = _geo_matching.SpecialAnchorLookup
_canonical_school_district_name = _geo_matching._canonical_school_district_name
_looks_like_school_district_name = _geo_matching._looks_like_school_district_name
_school_district_root_key = _geo_matching._school_district_root_key
_canonical_county_name = _geo_matching._canonical_county_name
_looks_like_county_name = _geo_matching._looks_like_county_name
_county_root_key = _geo_matching._county_root_key
_canonical_city_name = _geo_matching._canonical_city_name
_subdivision_root_from_patterns = _geo_matching._subdivision_root_from_patterns
classify_requested_entity_type = _geo_matching.classify_requested_entity_type
_looks_like_city_name = _geo_matching._looks_like_city_name
_looks_like_entity_type = _geo_matching._looks_like_entity_type
_city_root_key = _geo_matching._city_root_key
_build_special_anchor_lookup = _geo_matching._build_special_anchor_lookup
_resolve_special_anchor_record = _geo_matching._resolve_special_anchor_record
_resolve_special_anchor_keys = _geo_matching._resolve_special_anchor_keys
_match_preview = _geo_matching._match_preview
_build_layer_subdivision_matches = _geo_matching._build_layer_subdivision_matches


@st.cache_data(show_spinner=False, ttl=3600, max_entries=8)
def build_tfl_school_district_matches(tfl_client_names: tuple[str, ...]) -> pd.DataFrame:
    cols = [
        "fid",
        "district_name",
        "district_code",
        "lon",
        "lat",
        "match_count",
        "match_clients",
        "match_clients_preview",
        "source_name",
        "source_url",
    ]
    if not tfl_client_names:
        return pd.DataFrame(columns=cols)
    districts = fetch_tea_school_district_centroids()
    if districts.empty:
        return pd.DataFrame(columns=cols)

    exact_index: dict[str, set[str]] = {}
    root_index: dict[str, set[str]] = {}
    unique_clients = sorted({str(name).strip() for name in tfl_client_names if str(name).strip()})
    for client in unique_clients:
        canon_key = norm_name(_canonical_school_district_name(client))
        if canon_key:
            exact_index.setdefault(canon_key, set()).add(client)
        if _looks_like_school_district_name(client):
            root_key = _school_district_root_key(client)
            if root_key:
                root_index.setdefault(root_key, set()).add(client)
    if not exact_index and not root_index:
        return pd.DataFrame(columns=cols)

    out_rows: list[dict[str, Any]] = []
    for row in districts.itertuples(index=False):
        candidates = [row.name20, row.name, row.name2]
        if row.name2:
            candidates.append(f"{row.name2} ISD")
            candidates.append(f"{row.name2} Independent School District")
        variant_keys = {norm_name(_canonical_school_district_name(candidate)) for candidate in candidates if candidate}
        variant_keys = {key for key in variant_keys if key}
        matched_clients: set[str] = set()
        for key in variant_keys:
            matched_clients |= exact_index.get(key, set())
        root_key = _school_district_root_key(row.name20 or row.name or row.name2)
        if root_key:
            matched_clients |= root_index.get(root_key, set())
        if not matched_clients:
            continue
        matched_sorted = sorted(matched_clients)
        out_rows.append(
            {
                "fid": int(row.fid),
                "district_name": row.name20 or row.name or row.name2 or "",
                "district_code": row.district_code or row.district_code_compact or "",
                "lon": float(row.lon),
                "lat": float(row.lat),
                "match_count": int(len(matched_sorted)),
                "match_clients": matched_sorted,
                "match_clients_preview": _match_preview(matched_sorted),
                "source_name": "TEA School District boundaries (FeatureServer/0)",
                "source_url": TEA_ARCGIS_SCHOOL_DISTRICT_LAYER_URL,
            }
        )
    if not out_rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(out_rows, columns=cols).sort_values(["match_count", "district_name"], ascending=[False, True])


@st.cache_data(show_spinner=False, ttl=3600, max_entries=8)
def build_tfl_county_matches(tfl_client_names: tuple[str, ...]) -> pd.DataFrame:
    cols = [
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
    if not tfl_client_names:
        return pd.DataFrame(columns=cols)
    counties = fetch_tea_county_centroids()
    if counties.empty:
        return pd.DataFrame(columns=cols)

    exact_index: dict[str, set[str]] = {}
    root_index: dict[str, set[str]] = {}
    unique_clients = sorted({str(name).strip() for name in tfl_client_names if str(name).strip()})
    for client in unique_clients:
        canon_key = norm_name(_canonical_county_name(client))
        if canon_key:
            exact_index.setdefault(canon_key, set()).add(client)
        if _looks_like_county_name(client):
            root_key = _county_root_key(client)
            if root_key:
                root_index.setdefault(root_key, set()).add(client)
    if not exact_index and not root_index:
        return pd.DataFrame(columns=cols)

    out_rows: list[dict[str, Any]] = []
    for row in counties.itertuples(index=False):
        candidates = [row.name, f"{row.name} County", f"County of {row.name}"]
        variant_keys = {norm_name(_canonical_county_name(candidate)) for candidate in candidates if candidate}
        variant_keys = {key for key in variant_keys if key}
        matched_clients: set[str] = set()
        for key in variant_keys:
            matched_clients |= exact_index.get(key, set())
        root_key = _county_root_key(f"{row.name} County")
        if root_key:
            matched_clients |= root_index.get(root_key, set())
        if not matched_clients:
            continue
        matched_sorted = sorted(matched_clients)
        out_rows.append(
            {
                "subdivision_type": "County",
                "subdivision_name": f"{row.name} County",
                "subdivision_code": row.fips,
                "lon": float(row.lon),
                "lat": float(row.lat),
                "match_count": int(len(matched_sorted)),
                "match_clients": matched_sorted,
                "match_clients_preview": _match_preview(matched_sorted),
                "source_name": "TEA County boundaries (FeatureServer/0)",
                "source_url": TEA_ARCGIS_COUNTY_LAYER_URL,
            }
        )
    if not out_rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(out_rows, columns=cols).sort_values(["match_count", "subdivision_name"], ascending=[False, True])


@st.cache_data(show_spinner=False, ttl=3600, max_entries=8)
def build_tfl_city_matches(tfl_client_names: tuple[str, ...]) -> pd.DataFrame:
    cols = [
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
    if not tfl_client_names:
        return pd.DataFrame(columns=cols)
    cities = fetch_texas_city_centroids()
    if cities.empty:
        return pd.DataFrame(columns=cols)

    exact_index: dict[str, set[str]] = {}
    root_index: dict[str, set[str]] = {}
    unique_clients = sorted({str(name).strip() for name in tfl_client_names if str(name).strip()})
    for client in unique_clients:
        canon_key = norm_name(_canonical_city_name(client))
        if canon_key:
            exact_index.setdefault(canon_key, set()).add(client)
        if _looks_like_city_name(client):
            root_key = _city_root_key(client)
            if root_key:
                root_index.setdefault(root_key, set()).add(client)
    if not exact_index and not root_index:
        return pd.DataFrame(columns=cols)

    out_rows: list[dict[str, Any]] = []
    for row in cities.itertuples(index=False):
        base = row.basename or re.sub(r"\s+(city|town|village)\s*$", "", row.name, flags=re.IGNORECASE).strip()
        if not base:
            continue
        display_name = base if re.search(r"\b(CITY|TOWN|VILLAGE)\b$", base, flags=re.IGNORECASE) else f"{base} City"
        candidates = [base, row.name, f"City of {base}", f"{base} City", f"Town of {base}", f"{base} Town"]
        variant_keys = {norm_name(_canonical_city_name(candidate)) for candidate in candidates if candidate}
        variant_keys = {key for key in variant_keys if key}
        matched_clients: set[str] = set()
        for key in variant_keys:
            matched_clients |= exact_index.get(key, set())
        root_key = _city_root_key(f"City of {base}")
        if root_key:
            matched_clients |= root_index.get(root_key, set())
        if not matched_clients:
            continue
        matched_sorted = sorted(matched_clients)
        out_rows.append(
            {
                "subdivision_type": "City",
                "subdivision_name": display_name,
                "subdivision_code": row.geoid,
                "lon": float(row.lon),
                "lat": float(row.lat),
                "match_count": int(len(matched_sorted)),
                "match_clients": matched_sorted,
                "match_clients_preview": _match_preview(matched_sorted),
                "source_name": "U.S. Census TIGERweb Texas Places (MapServer/25)",
                "source_url": CENSUS_ARCGIS_TEXAS_CITY_LAYER_URL,
            }
        )
    if not out_rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(out_rows, columns=cols).sort_values(["match_count", "subdivision_name"], ascending=[False, True])


@st.cache_data(show_spinner=False, ttl=3600, max_entries=8)
def build_tfl_transit_authority_matches(tfl_client_names: tuple[str, ...]) -> pd.DataFrame:
    providers = fetch_nctcog_transit_provider_centroids()
    if providers.empty:
        return pd.DataFrame(columns=["subdivision_type", "subdivision_name", "subdivision_code", "lon", "lat", "match_count", "match_clients", "match_clients_preview", "source_name", "source_url"])
    return _build_layer_subdivision_matches(
        tfl_client_names=tfl_client_names,
        layer_df=providers,
        subdivision_type="Transit Authority",
        layer_name_cols=["provider_name", "classification"],
        layer_code_cols=["district_code"],
        root_patterns=TRANSIT_AUTHORITY_ROOT_PATTERNS + [r"\bTRANSIT\b"],
        include_client_fn=lambda client: _looks_like_entity_type(client, "Transit Authority"),
        extra_candidate_builder=lambda row: [
            f"{str(getattr(row, 'provider_name', '')).strip()} Transit Authority",
            f"{str(getattr(row, 'provider_name', '')).strip()} Transportation Authority",
            f"{str(getattr(row, 'provider_name', '')).strip()} Transit",
            "Dallas Area Rapid Transit" if re.search(r"\bDART\b", str(getattr(row, 'provider_name', '')), flags=re.IGNORECASE) else "",
        ],
        source_name="NCTCOG Transit Providers (MapServer/10)",
        source_url=NCTCOG_TRANSIT_PROVIDERS_LAYER_URL,
    )


@st.cache_data(show_spinner=False, ttl=3600, max_entries=8)
def build_tfl_port_authority_matches(tfl_client_names: tuple[str, ...]) -> pd.DataFrame:
    ports = fetch_txdot_seaport_centroids()
    if ports.empty:
        return pd.DataFrame(columns=["subdivision_type", "subdivision_name", "subdivision_code", "lon", "lat", "match_count", "match_clients", "match_clients_preview", "source_name", "source_url"])

    def _port_aliases(row) -> list[str]:
        raw = str(getattr(row, "port_name", "")).strip()
        base = re.sub(r"^\s*PORT\s+OF\s+", "", raw, flags=re.IGNORECASE).strip()
        aliases: list[str] = []
        if raw:
            aliases.extend([raw, f"{raw} Port Authority", f"{raw} Navigation District"])
        if base and base.lower() != raw.lower():
            aliases.extend([f"Port of {base}", f"{base} Port Authority", f"{base} Navigation District", f"{base} Port"])
        if re.search(r"\bNAVIGATION\s+DISTRICT\b", raw, flags=re.IGNORECASE):
            nav_base = re.sub(r"\bNAVIGATION\s+DISTRICT\b", "", raw, flags=re.IGNORECASE).strip(" -")
            if nav_base:
                aliases.extend([f"Port of {nav_base}", f"{nav_base} Port Authority"])
        return [alias for alias in aliases if str(alias).strip()]

    return _build_layer_subdivision_matches(
        tfl_client_names=tfl_client_names,
        layer_df=ports,
        subdivision_type="Port Authority",
        layer_name_cols=["port_name"],
        layer_code_cols=["port_code"],
        root_patterns=PORT_AUTHORITY_ROOT_PATTERNS,
        include_client_fn=lambda client: _looks_like_entity_type(client, "Port Authority"),
        extra_candidate_builder=_port_aliases,
        source_name="TxDOT Seaports (FeatureServer/0)",
        source_url=TXDOT_SEAPORTS_LAYER_URL,
    )


@st.cache_data(show_spinner=False, ttl=3600, max_entries=8)
def build_tfl_name_anchored_special_matches(tfl_client_names: tuple[str, ...]) -> pd.DataFrame:
    cols = [
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
    if not tfl_client_names:
        return pd.DataFrame(columns=cols)
    counties = fetch_tea_county_centroids()
    cities = fetch_texas_city_centroids()
    if counties.empty and cities.empty:
        return pd.DataFrame(columns=cols)
    lookup = _build_special_anchor_lookup(counties, cities)
    rows: list[dict[str, Any]] = []
    unresolved: list[tuple[str, str]] = []
    for client in sorted({str(name).strip() for name in tfl_client_names if str(name).strip()}):
        entity_type = classify_requested_entity_type(client)
        if entity_type not in SPECIAL_NAME_ANCHORED_ENTITY_TYPES:
            continue
        anchor = _resolve_special_anchor_record(client, entity_type, lookup)
        if not anchor:
            unresolved.append((client, entity_type))
            continue
        rows.append(
            {
                "subdivision_type": entity_type,
                "subdivision_name": client,
                "subdivision_code": str(anchor.get("code", "")).strip(),
                "lon": float(anchor.get("lon", 0.0)),
                "lat": float(anchor.get("lat", 0.0)),
                "match_count": 1,
                "match_clients": [client],
                "match_clients_preview": client,
                "source_name": str(anchor.get("source_name", "")).strip(),
                "source_url": str(anchor.get("source_url", "")).strip(),
            }
        )
    if unresolved:
        geocoded_by_client: dict[str, dict[str, Any]] = {}
        max_workers = min(8, len(unresolved))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(geocode_texas_entity_arcgis, client): client for client, _ in unresolved}
            for future in as_completed(futures):
                client = futures[future]
                try:
                    geocoded_by_client[client] = future.result() or {}
                except Exception:
                    geocoded_by_client[client] = {}
        for client, entity_type in unresolved:
            geocoded = geocoded_by_client.get(client, {})
            score = float(geocoded.get("score", 0.0)) if geocoded else 0.0
            if not geocoded or score < 70:
                continue
            rows.append(
                {
                    "subdivision_type": entity_type,
                    "subdivision_name": client,
                    "subdivision_code": str(geocoded.get("postal", "")).strip(),
                    "lon": float(geocoded.get("lon", 0.0)),
                    "lat": float(geocoded.get("lat", 0.0)),
                    "match_count": 1,
                    "match_clients": [client],
                    "match_clients_preview": client,
                    "source_name": "ArcGIS geocoded entity centroid (Texas)",
                    "source_url": ARCGIS_GEOCODER_URL,
                }
            )
    if not rows:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame(rows, columns=cols).drop_duplicates(["subdivision_type", "subdivision_name", "subdivision_code"])
    return out.sort_values(["subdivision_type", "subdivision_name"], ascending=[True, True])


@st.cache_data(show_spinner=False, ttl=3600, max_entries=8)
def build_tfl_water_district_type_matches(tfl_client_names: tuple[str, ...]) -> pd.DataFrame:
    cols = [
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
    if not tfl_client_names:
        return pd.DataFrame(columns=cols)
    water = fetch_tceq_water_district_centroids()
    if water.empty:
        return pd.DataFrame(columns=cols)
    water = water.copy()
    water["type_label"] = water["type_desc"].astype(str).map(_canonical_water_district_type)

    parts: list[pd.DataFrame] = []
    for subtype, root_patterns in WATER_DISTRICT_TYPE_ROOT_PATTERNS.items():
        if subtype == "Navigation District":
            continue
        subset = water[water["type_label"].astype(str) == subtype]
        if subset.empty:
            continue
        piece = _build_layer_subdivision_matches(
            tfl_client_names=tfl_client_names,
            layer_df=subset,
            subdivision_type=subtype,
            layer_name_cols=["district_name"],
            layer_code_cols=["district_code"],
            root_patterns=root_patterns,
            include_client_fn=lambda client, target=subtype: _looks_like_entity_type(client, target),
            source_name="TCEQ Water Districts (FeatureServer/0)",
            source_url=TCEQ_WATER_DISTRICTS_LAYER_URL,
        )
        if not piece.empty:
            parts.append(piece)
    if not parts:
        return pd.DataFrame(columns=cols)
    return pd.concat(parts, ignore_index=True).sort_values(["subdivision_type", "match_count", "subdivision_name"], ascending=[True, False, True])


@st.cache_data(show_spinner=False, ttl=3600, max_entries=8)
def build_tfl_groundwater_district_matches(tfl_client_names: tuple[str, ...]) -> pd.DataFrame:
    districts = fetch_tceq_groundwater_district_centroids()
    if districts.empty:
        return pd.DataFrame(columns=["subdivision_type", "subdivision_name", "subdivision_code", "lon", "lat", "match_count", "match_clients", "match_clients_preview", "source_name", "source_url"])
    return _build_layer_subdivision_matches(
        tfl_client_names=tfl_client_names,
        layer_df=districts,
        subdivision_type="Groundwater Conservation District",
        layer_name_cols=["district_name"],
        layer_code_cols=["district_code"],
        root_patterns=[r"\bGROUNDWATER\s+CONSERVATION\s+DISTRICT\b", r"\bDISTRICT\b"],
        include_client_fn=lambda client: _looks_like_entity_type(client, "Groundwater Conservation District"),
        source_name="TCEQ Groundwater Conservation Districts (FeatureServer/0)",
        source_url=TCEQ_GROUNDWATER_DISTRICTS_LAYER_URL,
    )


@st.cache_data(show_spinner=False, ttl=3600, max_entries=8)
def build_tfl_regional_mobility_authority_matches(tfl_client_names: tuple[str, ...]) -> pd.DataFrame:
    districts = fetch_texas_rma_centroids()
    if districts.empty:
        return pd.DataFrame(columns=["subdivision_type", "subdivision_name", "subdivision_code", "lon", "lat", "match_count", "match_clients", "match_clients_preview", "source_name", "source_url"])
    return _build_layer_subdivision_matches(
        tfl_client_names=tfl_client_names,
        layer_df=districts,
        subdivision_type="Regional Mobility Authority",
        layer_name_cols=["district_name"],
        layer_code_cols=["district_code"],
        root_patterns=[r"\bREGIONAL\s+MOBILITY\s+AUTHORITY\b", r"\bAUTHORITY\b", r"\bRMA\b"],
        include_client_fn=lambda client: _looks_like_entity_type(client, "Regional Mobility Authority"),
        extra_candidate_builder=lambda row: [str(getattr(row, "district_name", "")).replace("RMA", "Regional Mobility Authority").strip()],
        source_name="Texas Regional Mobility Authorities (FeatureServer/0)",
        source_url=TEXAS_RMA_LAYER_URL,
    )


@st.cache_data(show_spinner=False, ttl=3600, max_entries=8)
def build_tfl_junior_college_matches(tfl_client_names: tuple[str, ...]) -> pd.DataFrame:
    districts = fetch_texas_junior_college_centroids()
    if districts.empty:
        return pd.DataFrame(columns=["subdivision_type", "subdivision_name", "subdivision_code", "lon", "lat", "match_count", "match_clients", "match_clients_preview", "source_name", "source_url"])
    return _build_layer_subdivision_matches(
        tfl_client_names=tfl_client_names,
        layer_df=districts,
        subdivision_type="Junior College District",
        layer_name_cols=["district_name", "name2"],
        layer_code_cols=["district_code"],
        root_patterns=[r"\bCOMMUNITY\s+COLLEGE\b", r"\bJUNIOR\s+COLLEGE\b", r"\bCOLLEGE\s+DISTRICT\b", r"\bSERVICE\s+AREA\b", r"\bCOLLEGE\b", r"\bDISTRICT\b"],
        include_client_fn=lambda client: _looks_like_entity_type(client, "Junior College District"),
        extra_candidate_builder=lambda row: [
            f"{str(getattr(row, 'district_name', '')).strip()} District",
            f"{str(getattr(row, 'district_name', '')).strip()} Community College District",
        ],
        source_name="Texas Junior College Service Areas (FeatureServer/0)",
        source_url=TEXAS_JUNIOR_COLLEGE_LAYER_URL,
    )


@st.cache_data(show_spinner=False, ttl=3600, max_entries=8)
def build_tfl_navigation_district_matches(tfl_client_names: tuple[str, ...]) -> pd.DataFrame:
    districts = fetch_texas_navigation_district_centroids()
    if districts.empty:
        return pd.DataFrame(columns=["subdivision_type", "subdivision_name", "subdivision_code", "lon", "lat", "match_count", "match_clients", "match_clients_preview", "source_name", "source_url"])

    def _nav_aliases(row) -> list[str]:
        raw = str(getattr(row, "district_name", "")).strip()
        if not raw:
            return []
        base = re.sub(r"\bNAVIGATION\s+DISTRICT\b", "", raw, flags=re.IGNORECASE).strip(" -")
        aliases = [raw, f"{raw} Port Authority", f"{base} Port Authority" if base else "", f"Port of {base}" if base else ""]
        return [alias for alias in aliases if str(alias).strip()]

    return _build_layer_subdivision_matches(
        tfl_client_names=tfl_client_names,
        layer_df=districts,
        subdivision_type="Navigation District",
        layer_name_cols=["district_name"],
        layer_code_cols=["district_code"],
        root_patterns=[r"\bNAVIGATION\s+DISTRICT\b", r"\bPORT\s+AUTHORITY\b", r"\bPORT\s+OF\b", r"\bAUTHORITY\b", r"\bDISTRICT\b"],
        include_client_fn=lambda client: _looks_like_entity_type(client, "Navigation District") or _looks_like_entity_type(client, "Port Authority"),
        extra_candidate_builder=_nav_aliases,
        source_name="Texas Navigation Districts (FeatureServer/29)",
        source_url=TEXAS_NAVIGATION_DISTRICT_LAYER_URL,
    )


_merge_subdivision_match_rows = _geo_matching._merge_subdivision_match_rows


@st.cache_data(show_spinner=False, ttl=3600, max_entries=8)
def build_tfl_political_subdivision_matches(tfl_client_names: tuple[str, ...]) -> pd.DataFrame:
    cols = [
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
    if not tfl_client_names:
        return pd.DataFrame(columns=cols)
    entity_types = {
        classify_requested_entity_type(str(client).strip())
        for client in tfl_client_names
        if str(client).strip()
    }
    entity_types.discard("")

    def _school():
        return build_tfl_school_district_matches(tfl_client_names).rename(columns={"district_name": "subdivision_name", "district_code": "subdivision_code"}).assign(subdivision_type="School District")

    builders: list[Callable[[], pd.DataFrame]] = []
    if "School District" in entity_types:
        builders.append(_school)
    if "County" in entity_types:
        builders.append(lambda: build_tfl_county_matches(tfl_client_names))
    if "City" in entity_types:
        builders.append(lambda: build_tfl_city_matches(tfl_client_names))
    if "Junior College District" in entity_types:
        builders.append(lambda: build_tfl_junior_college_matches(tfl_client_names))
    if "Groundwater Conservation District" in entity_types:
        builders.append(lambda: build_tfl_groundwater_district_matches(tfl_client_names))
    if entity_types.intersection(set(WATER_DISTRICT_TYPE_ROOT_PATTERNS.keys()) | {"Navigation District"}):
        builders.append(lambda: build_tfl_water_district_type_matches(tfl_client_names))
    if "Transit Authority" in entity_types:
        builders.append(lambda: build_tfl_transit_authority_matches(tfl_client_names))
    if "Port Authority" in entity_types:
        builders.append(lambda: build_tfl_port_authority_matches(tfl_client_names))
    if "Regional Mobility Authority" in entity_types:
        builders.append(lambda: build_tfl_regional_mobility_authority_matches(tfl_client_names))
    if entity_types.intersection({"Navigation District", "Port Authority"}):
        builders.append(lambda: build_tfl_navigation_district_matches(tfl_client_names))
    if entity_types.intersection(SPECIAL_NAME_ANCHORED_ENTITY_TYPES):
        builders.append(lambda: build_tfl_name_anchored_special_matches(tfl_client_names))
    if not builders:
        return pd.DataFrame(columns=cols)
    parts: list[pd.DataFrame] = []
    for fn in builders:
        try:
            result = fn()
            if isinstance(result, pd.DataFrame) and not result.empty:
                parts.append(result)
        except Exception:
            continue
    if not parts:
        return pd.DataFrame(columns=cols)
    out = pd.concat(parts, ignore_index=True)
    keep = [column for column in cols if column in out.columns]
    return _merge_subdivision_match_rows(out[keep])


def prepare_subdivision_match_pool(pool: pd.DataFrame, subdivision_type: str) -> pd.DataFrame:
    return _geo_overlap.prepare_subdivision_match_pool(pool, subdivision_type)


@st.cache_data(show_spinner=False, max_entries=256, hash_funcs={pd.DataFrame: _hash_dataframe_for_cache})
def _prepare_subdivision_match_pool_cached(subdivision_type: str, pool: pd.DataFrame) -> pd.DataFrame:
    return prepare_subdivision_match_pool(pool, subdivision_type)


def build_address_overlap_spending_rows(
    overlap_subdivisions: pd.DataFrame,
    subdivision_matches: pd.DataFrame,
    tfl_spending: pd.DataFrame,
    *,
    prepared_overlap_pools: dict[str, pd.DataFrame] | None = None,
    spend_lookup: dict[str, dict[str, object]] | None = None,
) -> pd.DataFrame:
    return _geo_overlap.build_address_overlap_spending_rows_impl(
        overlap_subdivisions,
        subdivision_matches,
        tfl_spending,
        prepared_overlap_pools=prepared_overlap_pools,
        spend_lookup=spend_lookup,
        classify_requested_entity_type=classify_requested_entity_type,
        geocode_texas_entity_arcgis=geocode_texas_entity_arcgis,
        query_texas_county_for_point=query_texas_county_for_point,
        prepare_subdivision_match_pool_cached=_prepare_subdivision_match_pool_cached,
    )


_subdivision_color_hex = _geo_overlap._subdivision_color_hex
_hex_to_rgba = _geo_overlap._hex_to_rgba


def render_subdivision_map_legend(type_counts: dict[str, int]) -> None:
    _geo_overlap.render_subdivision_map_legend(type_counts, markdown=st.markdown)


def build_overlap_map_points(
    overlap_subdivisions: pd.DataFrame,
    subdivision_matches: pd.DataFrame,
    *,
    prepared_overlap_pools: dict[str, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    return _geo_overlap.build_overlap_map_points_impl(
        overlap_subdivisions,
        subdivision_matches,
        prepared_overlap_pools=prepared_overlap_pools,
        prepare_subdivision_match_pool_cached=_prepare_subdivision_match_pool_cached,
    )


__all__ = [
    "SPECIAL_NAME_ANCHORED_ENTITY_TYPES",
    "SUBDIVISION_TYPE_COLORS",
    "WATER_DISTRICT_TYPE_ROOT_PATTERNS",
    "_hex_to_rgba",
    "build_address_overlap_spending_rows",
    "build_overlap_map_points",
    "build_tfl_city_matches",
    "build_tfl_county_matches",
    "build_tfl_groundwater_district_matches",
    "build_tfl_junior_college_matches",
    "build_tfl_name_anchored_special_matches",
    "build_tfl_navigation_district_matches",
    "build_tfl_political_subdivision_matches",
    "build_tfl_port_authority_matches",
    "build_tfl_regional_mobility_authority_matches",
    "build_tfl_school_district_matches",
    "build_tfl_transit_authority_matches",
    "build_tfl_water_district_type_matches",
    "classify_requested_entity_type",
    "geocode_address_arcgis",
    "geocode_texas_entity_arcgis",
    "prepare_subdivision_match_pool",
    "query_texas_county_for_point",
    "query_texas_subdivisions_for_point",
    "render_subdivision_map_legend",
]

