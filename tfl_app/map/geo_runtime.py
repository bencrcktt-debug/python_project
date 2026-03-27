from __future__ import annotations

from dataclasses import dataclass
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

from tfl_app.search.state import norm_name
from tfl_app.bundles.page_bundles import ensure_cols
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
    arcgis_get_json,
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


SUBDIVISION_TYPE_COLORS = {
    "School District": "#1769AA",
    "County": "#7A3E00",
    "City": "#9E2A2B",
    "Junior College District": "#1E58A5",
    "Groundwater Conservation District": "#0B8F6A",
    "Municipal Utility District": "#5B3FB0",
    "Drainage District": "#CC6B2C",
    "Fresh Water Supply District": "#3382CC",
    "Irrigation District": "#5A8B2D",
    "Levee Improvement District": "#8A6A1F",
    "Municipal Management District": "#7D3FA0",
    "Regional District": "#8A7E24",
    "River Authority": "#0E8791",
    "Soil & Water Control District": "#2E8D73",
    "Special Utility District": "#31688E",
    "Water Improvement District": "#4D6FA9",
    "Water Control & Improvement District": "#2F6DA4",
    "Regional Mobility Authority": "#B08900",
    "Navigation District": "#2C3E50",
    "Transit Authority": "#5A657A",
    "Port Authority": "#3B6F8C",
    "Hospital District": "#9B3E56",
    "Emergency Services District": "#B15C2E",
    "Appraisal District": "#6D5A90",
    "Local Government Corporation": "#4E7A52",
}
WATER_DISTRICT_TYPE_ROOT_PATTERNS = {
    "Municipal Utility District": [r"\bMUNICIPAL\s+UTILITY\s+DISTRICT\b", r"\bDISTRICT\b"],
    "Drainage District": [r"\bDRAINAGE\s+DISTRICT\b", r"\bDISTRICT\b"],
    "Fresh Water Supply District": [r"\bFRESH\s+WATER\s+SUPPLY\s+DISTRICT\b", r"\bDISTRICT\b"],
    "Irrigation District": [r"\bIRRIGATION\s+DISTRICT\b", r"\bDISTRICT\b"],
    "Levee Improvement District": [r"\bLEVEE\s+IMPROVEMENT\s+DISTRICT\b", r"\bDISTRICT\b"],
    "Municipal Management District": [r"\bMUNICIPAL\s+MANAGEMENT\s+DISTRICT\b", r"\bDISTRICT\b"],
    "Regional District": [r"\bREGIONAL\s+DISTRICT\b", r"\bDISTRICT\b"],
    "River Authority": [r"\bRIVER\s+AUTHORITY\b", r"\bAUTHORITY\b"],
    "Soil & Water Control District": [r"\bSOIL\s+(AND\s+)?WATER\s+CONTROL\s+DISTRICT\b", r"\bDISTRICT\b"],
    "Special Utility District": [r"\bSPECIAL\s+UTILITY\s+DISTRICT\b", r"\bDISTRICT\b"],
    "Water Improvement District": [r"\bWATER\s+IMPROVEMENT\s+DISTRICT\b", r"\bDISTRICT\b"],
    "Water Control & Improvement District": [r"\bWATER\s+CONTROL\s+(AND\s+)?IMPROVEMENT\s+DISTRICT\b", r"\bDISTRICT\b"],
}
TRANSIT_AUTHORITY_ROOT_PATTERNS = [
    r"\bMETROPOLITAN\s+TRANSIT\s+AUTHORITY\b",
    r"\bTRANSIT\s+AUTHORITY\b",
    r"\bAREA\s+RAPID\s+TRANSIT\b",
    r"\bREGIONAL\s+TRANSPORTATION\s+AUTHORITY\b",
    r"\bTRANSPORTATION\s+AUTHORITY\b",
]
PORT_AUTHORITY_ROOT_PATTERNS = [
    r"\bPORT\s+AUTHORITY\b",
    r"\bPORT\s+OF\b",
    r"\bNAVIGATION\s+DISTRICT\b",
    r"\bPORT\b",
    r"\bAUTHORITY\b",
    r"\bDISTRICT\b",
]
SPECIAL_NAME_ANCHORED_ENTITY_TYPES = {
    "Hospital District",
    "Emergency Services District",
    "Appraisal District",
    "Local Government Corporation",
    "Transit Authority",
    "Port Authority",
}
COUNTY_BIASED_SPECIAL_ENTITY_TYPES = {
    "Hospital District",
    "Emergency Services District",
    "Appraisal District",
}
CITY_BIASED_SPECIAL_ENTITY_TYPES = {
    "Local Government Corporation",
    "Transit Authority",
    "Port Authority",
}


@dataclass(frozen=True)
class SpecialAnchorLookup:
    county_lookup: dict[str, dict[str, Any]]
    city_lookup: dict[str, dict[str, Any]]
    county_lookup_keys: tuple[str, ...]
    city_lookup_keys: tuple[str, ...]


def _canonical_school_district_name(value: str) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).upper().replace("&", " AND ").replace("/", " ")
    text = re.sub(r"\bC\.?I\.?S\.?D\.?\b", " CONSOLIDATED INDEPENDENT SCHOOL DISTRICT ", text)
    text = re.sub(r"\bI\.?S\.?D\.?\b", " INDEPENDENT SCHOOL DISTRICT ", text)
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _looks_like_school_district_name(value: str) -> bool:
    text = _canonical_school_district_name(value)
    return bool(text) and ("SCHOOL DISTRICT" in text)


@functools.lru_cache(maxsize=2048)
def _school_district_root_key(value: str) -> str:
    text = _canonical_school_district_name(value)
    if not text:
        return ""
    text = re.sub(r"\bTHE\b", " ", text)
    text = re.sub(r"\b(CONSOLIDATED\s+)?INDEPENDENT\s+SCHOOL\s+DISTRICT\b", " ", text)
    text = re.sub(r"\bSCHOOL\s+DISTRICT\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return norm_name(text)


def _canonical_county_name(value: str) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).upper().replace("&", " AND ").replace("/", " ")
    text = re.sub(r"\bCTY\.?\b", " COUNTY ", text)
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _looks_like_county_name(value: str) -> bool:
    text = _canonical_county_name(value)
    return bool(text) and ("COUNTY" in text)


@functools.lru_cache(maxsize=512)
def _county_root_key(value: str) -> str:
    text = _canonical_county_name(value)
    if not text:
        return ""
    text = re.sub(r"\bTHE\b", " ", text)
    text = re.sub(r"\bCOUNTY OF\b", " ", text)
    text = re.sub(r"\bCOMMISSIONERS? COURT\b", " ", text)
    text = re.sub(r"\bCOUNTY\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return norm_name(text)


def _canonical_city_name(value: str) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).upper().replace("&", " AND ").replace("/", " ")
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


@functools.lru_cache(maxsize=4096)
def _canonical_subdivision_text(value: str) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).upper().replace("&", " AND ").replace("/", " ")
    replacements = [
        (r"\bM\.?U\.?D\.?\b", " MUNICIPAL UTILITY DISTRICT "),
        (r"\bW\.?C\.?I\.?D\.?\b", " WATER CONTROL AND IMPROVEMENT DISTRICT "),
        (r"\bW\.?I\.?D\.?\b", " WATER IMPROVEMENT DISTRICT "),
        (r"\bF\.?W\.?S\.?D\.?\b", " FRESH WATER SUPPLY DISTRICT "),
        (r"\bL\.?I\.?D\.?\b", " LEVEE IMPROVEMENT DISTRICT "),
        (r"\bM\.?M\.?D\.?\b", " MUNICIPAL MANAGEMENT DISTRICT "),
        (r"\bS\.?U\.?D\.?\b", " SPECIAL UTILITY DISTRICT "),
        (r"\bS\.?W\.?C\.?D\.?\b", " SOIL AND WATER CONTROL DISTRICT "),
        (r"\bG\.?C\.?D\.?\b", " GROUNDWATER CONSERVATION DISTRICT "),
        (r"\bE\.?S\.?D\.?\b", " EMERGENCY SERVICES DISTRICT "),
        (r"\bR\.?M\.?A\.?\b", " REGIONAL MOBILITY AUTHORITY "),
        (r"\bM\.?T\.?A\.?\b", " METROPOLITAN TRANSIT AUTHORITY "),
        (r"\bD\.?A\.?R\.?T\.?\b", " DALLAS AREA RAPID TRANSIT "),
        (r"\bC\.?A\.?D\.?\b", " APPRAISAL DISTRICT "),
        (r"\bL\.?G\.?C\.?\b", " LOCAL GOVERNMENT CORPORATION "),
        (r"\bCORPERATION\b", " CORPORATION "),
        (r"\bHOSP\.?\s+DIST\.?\b", " HOSPITAL DISTRICT "),
        (r"\bNAV\.?\s+DIST\.?\b", " NAVIGATION DISTRICT "),
        (r"\bDIST\.?\b", " DISTRICT "),
        (r"\bNO\.?\b", " "),
        (r"\bNUMBER\b", " "),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _subdivision_root_from_patterns(value: str, remove_patterns: list[str]) -> str:
    text = _canonical_subdivision_text(value)
    if not text:
        return ""
    text = re.sub(r"\bTHE\b", " ", text)
    for pattern in remove_patterns:
        text = re.sub(pattern, " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return norm_name(text)


@functools.lru_cache(maxsize=2048)
def classify_requested_entity_type(value: str) -> str:
    text = _canonical_subdivision_text(value)
    if not text:
        return ""
    if re.search(r"\b(JUNIOR|COMMUNITY)\s+COLLEGE\b|\bCOLLEGE\s+DISTRICT\b", text):
        return "Junior College District"
    if "HOSPITAL DISTRICT" in text:
        return "Hospital District"
    if "MUNICIPAL UTILITY DISTRICT" in text:
        return "Municipal Utility District"
    if "EMERGENCY SERVICES DISTRICT" in text:
        return "Emergency Services District"
    if "GROUNDWATER CONSERVATION DISTRICT" in text:
        return "Groundwater Conservation District"
    if re.search(r"\bLOCAL\s+GOVERNMENT\s+CORPORATION\b|\bDEVELOPMENT\s+CORPORATION\b", text):
        return "Local Government Corporation"
    if "DRAINAGE DISTRICT" in text:
        return "Drainage District"
    if "FRESH WATER SUPPLY DISTRICT" in text:
        return "Fresh Water Supply District"
    if "IRRIGATION DISTRICT" in text:
        return "Irrigation District"
    if "LEVEE IMPROVEMENT DISTRICT" in text:
        return "Levee Improvement District"
    if "MUNICIPAL MANAGEMENT DISTRICT" in text:
        return "Municipal Management District"
    if "REGIONAL DISTRICT" in text:
        return "Regional District"
    if "RIVER AUTHORITY" in text:
        return "River Authority"
    if re.search(r"\bSOIL\s+(AND\s+)?WATER\s+CONTROL\s+DISTRICT\b", text):
        return "Soil & Water Control District"
    if "SPECIAL UTILITY DISTRICT" in text:
        return "Special Utility District"
    if "WATER IMPROVEMENT DISTRICT" in text:
        return "Water Improvement District"
    if "REGIONAL MOBILITY AUTHORITY" in text:
        return "Regional Mobility Authority"
    if re.search(r"\bWATER\s+CONTROL\s+(AND\s+)?IMPROVEMENT\s+DISTRICT\b", text):
        return "Water Control & Improvement District"
    if "NAVIGATION DISTRICT" in text:
        return "Navigation District"
    if (
        "TRANSIT AUTHORITY" in text
        or "METROPOLITAN TRANSIT AUTHORITY" in text
        or "TRANSPORTATION AUTHORITY" in text
        or re.search(r"\bAREA\s+RAPID\s+TRANSIT\b|\bRAPID\s+TRANSIT\b|\bMASS\s+TRANSIT\b|\bDART\b", text)
        or re.search(r"\bTRANSIT\b", text)
    ):
        return "Transit Authority"
    if "PORT AUTHORITY" in text:
        return "Port Authority"
    if "HOUSING AUTHORITY" in text:
        return "Housing Authority"
    if "APPRAISAL DISTRICT" in text:
        return "Appraisal District"
    return ""


@functools.lru_cache(maxsize=512)
def _canonical_water_district_type(value: str) -> str:
    text = _canonical_subdivision_text(value)
    if not text:
        return ""
    if "MUNICIPAL UTILITY DISTRICT" in text:
        return "Municipal Utility District"
    if "DRAINAGE DISTRICT" in text:
        return "Drainage District"
    if "FRESH WATER SUPPLY DISTRICT" in text:
        return "Fresh Water Supply District"
    if "IRRIGATION DISTRICT" in text:
        return "Irrigation District"
    if "LEVEE IMPROVEMENT DISTRICT" in text:
        return "Levee Improvement District"
    if "MUNICIPAL MANAGEMENT DISTRICT" in text:
        return "Municipal Management District"
    if "REGIONAL DISTRICT" in text:
        return "Regional District"
    if "RIVER AUTHORITY" in text:
        return "River Authority"
    if re.search(r"\bSOIL\s+(AND\s+)?WATER\s+CONTROL\s+DISTRICT\b", text):
        return "Soil & Water Control District"
    if "SPECIAL UTILITY DISTRICT" in text:
        return "Special Utility District"
    if "WATER IMPROVEMENT DISTRICT" in text:
        return "Water Improvement District"
    if re.search(r"\bWATER\s+CONTROL\s+(AND\s+)?IMPROVEMENT\s+DISTRICT\b", text):
        return "Water Control & Improvement District"
    if "NAVIGATION DISTRICT" in text:
        return "Navigation District"
    return ""


def _looks_like_city_name(value: str) -> bool:
    text = _canonical_city_name(value)
    return bool(text) and bool(re.search(r"\b(CITY|TOWN|VILLAGE)\b", text))


def _looks_like_entity_type(value: str, entity_type: str) -> bool:
    return classify_requested_entity_type(value) == str(entity_type).strip()


@functools.lru_cache(maxsize=2048)
def _city_root_key(value: str) -> str:
    text = _canonical_city_name(value)
    if not text:
        return ""
    text = re.sub(r"\bTHE\b", " ", text)
    text = re.sub(r"\b(CITY|TOWN|VILLAGE)\s+OF\b", " ", text)
    text = re.sub(r"\b(CITY|TOWN|VILLAGE)\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return norm_name(text)


def _special_entity_root_patterns(entity_type: str) -> list[str]:
    entity_type = str(entity_type).strip()
    if entity_type == "Hospital District":
        return [r"\bHOSPITAL\s+DISTRICT\b", r"\bDISTRICT\b"]
    if entity_type == "Emergency Services District":
        return [r"\bEMERGENCY\s+SERVICES\s+DISTRICT\b", r"\bDISTRICT\b", r"\bE\.?S\.?D\.?\b"]
    if entity_type == "Appraisal District":
        return [r"\bAPPRAISAL\s+DISTRICT\b", r"\bDISTRICT\b", r"\bC\.?A\.?D\.?\b"]
    if entity_type == "Local Government Corporation":
        return [r"\bLOCAL\s+GOVERNMENT\s+CORPORATION\b", r"\bDEVELOPMENT\s+CORPORATION\b", r"\bCORPORATION\b"]
    if entity_type == "Transit Authority":
        return TRANSIT_AUTHORITY_ROOT_PATTERNS
    if entity_type == "Port Authority":
        return PORT_AUTHORITY_ROOT_PATTERNS
    return []


def _anchor_key_variants(value: str) -> set[str]:
    root = norm_name(value)
    if not root:
        return set()
    variants: set[str] = {root}
    no_digits = re.sub(r"\d+", "", root)
    if no_digits:
        variants.add(no_digits)
    no_geo_terms = re.sub(r"(COUNTY|CITY|TOWN|VILLAGE|OF)", "", no_digits).strip()
    if no_geo_terms:
        variants.add(no_geo_terms)
    return {variant for variant in variants if variant}


@functools.lru_cache(maxsize=32)
def _lookup_key_prefix_index(lookup_keys: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
    groups: dict[str, list[str]] = {}
    for raw_key in lookup_keys:
        key = str(raw_key).strip()
        if len(key) < 4:
            continue
        groups.setdefault(key[:4], []).append(key)
    return {prefix: tuple(values) for prefix, values in groups.items()}


def _best_lookup_key_for_candidates(lookup_keys: tuple[str, ...], candidates: set[str]) -> tuple[str, float]:
    if not lookup_keys or not candidates:
        return "", -1.0
    best_key = ""
    best_score = -1.0
    exact_keys = frozenset(str(key).strip() for key in lookup_keys if str(key).strip())
    prefix_index = _lookup_key_prefix_index(lookup_keys)
    candidate_values = [str(candidate).strip() for candidate in candidates if str(candidate).strip()]
    scan_keys: set[str] = set()
    for candidate in candidate_values:
        if candidate in exact_keys:
            score = 1000.0 + float(len(candidate))
            if score > best_score:
                best_score = score
                best_key = candidate
            continue
        if len(candidate) >= 4:
            scan_keys.update(prefix_index.get(candidate[:4], ()))
    if best_score >= 1000.0:
        return best_key, best_score
    keys_to_scan = tuple(scan_keys) if scan_keys else lookup_keys
    for candidate in candidate_values:
        if not candidate:
            continue
        for key in keys_to_scan:
            resolved = str(key).strip()
            if not resolved:
                continue
            score = -1.0
            if candidate == resolved:
                score = 1000.0 + float(len(resolved))
            elif len(candidate) >= 4 and len(resolved) >= 4 and (candidate in resolved or resolved in candidate):
                score = float(min(len(candidate), len(resolved)))
            if score > best_score:
                best_score = score
                best_key = resolved
    if best_score < 0.0 and scan_keys and len(scan_keys) < len(lookup_keys):
        for candidate in candidate_values:
            if not candidate:
                continue
            for key in lookup_keys:
                resolved = str(key).strip()
                if not resolved:
                    continue
                score = -1.0
                if candidate == resolved:
                    score = 1000.0 + float(len(resolved))
                elif len(candidate) >= 4 and len(resolved) >= 4 and (candidate in resolved or resolved in candidate):
                    score = float(min(len(candidate), len(resolved)))
                if score > best_score:
                    best_score = score
                    best_key = resolved
    return best_key, best_score


def _resolve_special_anchor_keys(
    client_name: str,
    entity_type: str,
    county_lookup_keys: tuple[str, ...] = (),
    city_lookup_keys: tuple[str, ...] = (),
    *,
    lookup: SpecialAnchorLookup | None = None,
) -> dict[str, Any]:
    if lookup is not None:
        county_lookup_keys = lookup.county_lookup_keys
        city_lookup_keys = lookup.city_lookup_keys
    candidates: set[str] = set()
    candidates |= _anchor_key_variants(_county_root_key(client_name))
    candidates |= _anchor_key_variants(_city_root_key(client_name))
    root_patterns = _special_entity_root_patterns(entity_type)
    if root_patterns:
        candidates |= _anchor_key_variants(_subdivision_root_from_patterns(client_name, root_patterns))

    county_key, county_score = _best_lookup_key_for_candidates(county_lookup_keys, candidates)
    city_key, city_score = _best_lookup_key_for_candidates(city_lookup_keys, candidates)
    canonical = _canonical_subdivision_text(client_name)
    weighted_county = county_score
    weighted_city = city_score
    if "COUNTY" in canonical:
        weighted_county += 6.0
    if re.search(r"\b(CITY|TOWN|VILLAGE)\b", canonical):
        weighted_city += 6.0
    if entity_type in COUNTY_BIASED_SPECIAL_ENTITY_TYPES:
        weighted_county += 4.0
    if entity_type in CITY_BIASED_SPECIAL_ENTITY_TYPES:
        weighted_city += 3.0

    preferred_scope = ""
    if county_key and (not city_key or weighted_county >= weighted_city):
        preferred_scope = "county"
    elif city_key:
        preferred_scope = "city"
    return {
        "county_key": county_key,
        "city_key": city_key,
        "county_score": county_score,
        "city_score": city_score,
        "preferred_scope": preferred_scope,
    }


def _build_special_anchor_lookup(
    counties: pd.DataFrame,
    cities: pd.DataFrame,
) -> SpecialAnchorLookup:
    county_lookup: dict[str, dict[str, Any]] = {}
    if not counties.empty:
        for row in counties.itertuples(index=False):
            county_name = str(getattr(row, "name", "")).strip()
            if not county_name:
                continue
            key = _county_root_key(f"{county_name} County")
            if not key or key in county_lookup:
                continue
            county_lookup[key] = {
                "code": str(getattr(row, "fips", "")).strip(),
                "lon": float(getattr(row, "lon", 0.0)),
                "lat": float(getattr(row, "lat", 0.0)),
                "source_name": "Name-anchored county centroid proxy",
                "source_url": TEA_ARCGIS_COUNTY_LAYER_URL,
            }

    city_lookup: dict[str, dict[str, Any]] = {}
    if not cities.empty:
        for row in cities.itertuples(index=False):
            raw_name = str(getattr(row, "name", "")).strip()
            base = str(getattr(row, "basename", "")).strip() or re.sub(r"\s+(city|town|village)\s*$", "", raw_name, flags=re.IGNORECASE).strip()
            if not base:
                continue
            display_name = base if re.search(r"\b(CITY|TOWN|VILLAGE)\b$", base, flags=re.IGNORECASE) else f"{base} City"
            key = _city_root_key(display_name)
            if not key or key in city_lookup:
                continue
            city_lookup[key] = {
                "code": str(getattr(row, "geoid", "")).strip(),
                "lon": float(getattr(row, "lon", 0.0)),
                "lat": float(getattr(row, "lat", 0.0)),
                "source_name": "Name-anchored city centroid proxy",
                "source_url": CENSUS_ARCGIS_TEXAS_CITY_LAYER_URL,
            }

    return SpecialAnchorLookup(
        county_lookup=county_lookup,
        city_lookup=city_lookup,
        county_lookup_keys=tuple(county_lookup.keys()),
        city_lookup_keys=tuple(city_lookup.keys()),
    )


def _resolve_special_anchor_record(
    client_name: str,
    entity_type: str,
    lookup: SpecialAnchorLookup,
) -> dict[str, Any]:
    anchor_keys = _resolve_special_anchor_keys(
        client_name=client_name,
        entity_type=entity_type,
        lookup=lookup,
    )
    county_key = str(anchor_keys.get("county_key", "")).strip()
    city_key = str(anchor_keys.get("city_key", "")).strip()
    preferred_scope = str(anchor_keys.get("preferred_scope", "")).strip()
    if preferred_scope == "county" and county_key in lookup.county_lookup:
        return lookup.county_lookup[county_key]
    if preferred_scope == "city" and city_key in lookup.city_lookup:
        return lookup.city_lookup[city_key]
    if county_key in lookup.county_lookup:
        return lookup.county_lookup[county_key]
    if city_key in lookup.city_lookup:
        return lookup.city_lookup[city_key]
    return {}


def _match_preview(values: list[str], limit: int = 6) -> str:
    if not values:
        return ""
    preview = ", ".join(values[:limit])
    if len(values) > limit:
        return f"{preview}, +{len(values) - limit} more"
    return preview


def _build_layer_subdivision_matches(
    tfl_client_names: tuple[str, ...],
    layer_df: pd.DataFrame,
    subdivision_type: str,
    layer_name_cols: list[str],
    layer_code_cols: list[str],
    root_patterns: list[str],
    include_client_fn,
    extra_candidate_builder=None,
    source_name: str = "",
    source_url: str = "",
) -> pd.DataFrame:
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
    if not tfl_client_names or layer_df.empty:
        return pd.DataFrame(columns=cols)

    exact_index: dict[str, set[str]] = {}
    root_index: dict[str, set[str]] = {}
    unique_clients = sorted({str(name).strip() for name in tfl_client_names if str(name).strip()})
    for client in unique_clients:
        canon_key = norm_name(_canonical_subdivision_text(client))
        if canon_key:
            exact_index.setdefault(canon_key, set()).add(client)
        try:
            include_client = bool(include_client_fn(client))
        except Exception:
            include_client = False
        if include_client:
            root_key = _subdivision_root_from_patterns(client, root_patterns)
            if root_key:
                root_index.setdefault(root_key, set()).add(client)
    if not exact_index and not root_index:
        return pd.DataFrame(columns=cols)
    known_root_keys = tuple(root_index.keys())

    out_rows: list[dict[str, Any]] = []
    for row in layer_df.itertuples(index=False):
        names: list[str] = []
        for col in layer_name_cols:
            value = getattr(row, col, "")
            if value is not None and str(value).strip():
                names.append(str(value).strip())
        if extra_candidate_builder is not None:
            try:
                names.extend(extra_candidate_builder(row) or [])
            except Exception:
                pass
        names = [name for name in names if name]
        if not names:
            continue

        variant_keys = {norm_name(_canonical_subdivision_text(name)) for name in names}
        variant_keys = {key for key in variant_keys if key}
        candidate_root_keys = {_subdivision_root_from_patterns(name, root_patterns) for name in names}
        candidate_root_keys = {key for key in candidate_root_keys if key}
        matched_clients: set[str] = set()
        for key in variant_keys:
            matched_clients |= exact_index.get(key, set())
        for root_key in candidate_root_keys:
            matched_clients |= root_index.get(root_key, set())
        if not matched_clients and candidate_root_keys and known_root_keys:
            for candidate_root in candidate_root_keys:
                if len(candidate_root) < 6:
                    continue
                close_roots = difflib.get_close_matches(candidate_root, known_root_keys, n=3, cutoff=0.93)
                for close_root in close_roots:
                    ratio = difflib.SequenceMatcher(None, candidate_root, close_root).ratio()
                    if ratio >= 0.95 or candidate_root in close_root or close_root in candidate_root:
                        matched_clients |= root_index.get(close_root, set())
        if not matched_clients:
            continue

        primary_name = names[0]
        code = ""
        for code_col in layer_code_cols:
            code_value = getattr(row, code_col, "")
            if code_value is not None and str(code_value).strip():
                code = str(code_value).strip()
                break
        matched_sorted = sorted(matched_clients)
        out_rows.append(
            {
                "subdivision_type": subdivision_type,
                "subdivision_name": primary_name,
                "subdivision_code": code,
                "lon": float(getattr(row, "lon", 0.0)),
                "lat": float(getattr(row, "lat", 0.0)),
                "match_count": int(len(matched_sorted)),
                "match_clients": matched_sorted,
                "match_clients_preview": _match_preview(matched_sorted),
                "source_name": str(source_name).strip(),
                "source_url": str(source_url).strip(),
            }
        )
    if not out_rows:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame(out_rows, columns=cols)
    return out.sort_values(["match_count", "subdivision_name"], ascending=[False, True])


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


@st.cache_data(show_spinner=False, ttl=604800, max_entries=4096)
def geocode_texas_entity_arcgis(entity_name: str) -> dict[str, Any]:
    query = str(entity_name).strip()
    if not query:
        return {}
    candidates_to_try = [f"{query}, Texas", query]
    network_error = False
    for candidate_query in candidates_to_try:
        try:
            payload = arcgis_get_json(
                ARCGIS_GEOCODER_URL,
                params={
                    "SingleLine": candidate_query,
                    "outFields": "Match_addr,Addr_type,City,Region,RegionAbbr,Postal",
                    "maxLocations": 1,
                    "searchExtent": "-106.65,25.84,-93.51,36.50",
                    "f": "json",
                },
                timeout=35,
            )
            candidates = payload.get("candidates", [])
            if not candidates:
                continue
            best = candidates[0]
            location = best.get("location") or {}
            raw_x, raw_y = location.get("x"), location.get("y")
            if raw_x is None or raw_y is None:
                continue
            lon, lat = float(raw_x), float(raw_y)
            attrs = best.get("attributes") or {}
            region_abbr = str(attrs.get("RegionAbbr", "")).strip().upper()
            if region_abbr and region_abbr != "TX":
                continue
            return {
                "input": query,
                "matched_address": str(best.get("address", "")).strip(),
                "score": float(best.get("score", 0.0)),
                "lon": lon,
                "lat": lat,
                "city": str(attrs.get("City", "")).strip(),
                "region_abbr": region_abbr,
                "postal": str(attrs.get("Postal", "")).strip(),
            }
        except Exception:
            network_error = True
            continue
    if network_error:
        geocode_texas_entity_arcgis.clear()
    return {}


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


def _merge_subdivision_match_rows(df: pd.DataFrame) -> pd.DataFrame:
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
    if df.empty:
        return pd.DataFrame(columns=cols)
    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in df.itertuples(index=False):
        subdivision_type = str(getattr(row, "subdivision_type", "")).strip()
        subdivision_name = str(getattr(row, "subdivision_name", "")).strip()
        subdivision_code = str(getattr(row, "subdivision_code", "")).strip()
        if not subdivision_type or not subdivision_name:
            continue
        key = (subdivision_type, subdivision_name, subdivision_code)
        clients = getattr(row, "match_clients", [])
        client_set = {str(value).strip() for value in clients if str(value).strip()} if isinstance(clients, list) else set()
        source_name = str(getattr(row, "source_name", "")).strip()
        source_url = str(getattr(row, "source_url", "")).strip()
        if key not in merged:
            merged[key] = {
                "subdivision_type": subdivision_type,
                "subdivision_name": subdivision_name,
                "subdivision_code": subdivision_code,
                "lon": float(getattr(row, "lon", 0.0)),
                "lat": float(getattr(row, "lat", 0.0)),
                "match_clients": set(client_set),
                "source_names": {source_name} if source_name else set(),
                "source_urls": {source_url} if source_url else set(),
            }
        else:
            merged[key]["match_clients"].update(client_set)
            if source_name:
                merged[key]["source_names"].add(source_name)
            if source_url:
                merged[key]["source_urls"].add(source_url)
    out_rows = []
    for rec in merged.values():
        matched_sorted = sorted(rec["match_clients"])
        out_rows.append(
            {
                "subdivision_type": rec["subdivision_type"],
                "subdivision_name": rec["subdivision_name"],
                "subdivision_code": rec["subdivision_code"],
                "lon": rec["lon"],
                "lat": rec["lat"],
                "match_count": int(len(matched_sorted)),
                "match_clients": matched_sorted,
                "match_clients_preview": _match_preview(matched_sorted),
                "source_name": "; ".join(sorted(rec.get("source_names", set()))),
                "source_url": "; ".join(sorted(rec.get("source_urls", set()))),
            }
        )
    if not out_rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(out_rows, columns=cols).sort_values(["subdivision_type", "match_count", "subdivision_name"], ascending=[True, False, True])


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


@st.cache_data(show_spinner=False, ttl=86400, max_entries=256)
def geocode_address_arcgis(address: str) -> dict[str, Any]:
    query = str(address).strip()
    if not query:
        return {}
    try:
        payload = arcgis_get_json(
            ARCGIS_GEOCODER_URL,
            params={
                "SingleLine": query,
                "outFields": "Match_addr,Addr_type,City,Region,RegionAbbr,Postal",
                "maxLocations": 1,
                "f": "json",
            },
            timeout=40,
        )
        candidates = payload.get("candidates", [])
        if not candidates:
            return {}
        best = candidates[0]
        location = best.get("location") or {}
        raw_x, raw_y = location.get("x"), location.get("y")
        if raw_x is None or raw_y is None:
            return {}
        lon, lat = float(raw_x), float(raw_y)
        attrs = best.get("attributes") or {}
        return {
            "input": query,
            "matched_address": str(best.get("address", "")).strip(),
            "score": float(best.get("score", 0.0)),
            "lon": lon,
            "lat": lat,
            "region": str(attrs.get("Region", "")).strip(),
            "region_abbr": str(attrs.get("RegionAbbr", "")).strip(),
            "city": str(attrs.get("City", "")).strip(),
            "postal": str(attrs.get("Postal", "")).strip(),
        }
    except Exception:
        geocode_address_arcgis.clear()
        return {}


@st.cache_data(show_spinner=False, ttl=604800, max_entries=8192)
def query_texas_county_for_point(lon: float, lat: float) -> dict[str, Any]:
    try:
        payload = arcgis_get_json(
            f"{TEA_ARCGIS_COUNTY_LAYER_URL}/query",
            params={
                "geometry": f"{lon},{lat}",
                "geometryType": "esriGeometryPoint",
                "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": "FENAME,FIPS",
                "returnGeometry": "false",
                "f": "json",
            },
        )
        features = payload.get("features", [])
        if not features:
            return {}
        attrs = features[0].get("attributes", {}) or {}
        return {"county_name": str(attrs.get("FENAME", "")).strip(), "county_fips": str(attrs.get("FIPS", "")).strip()}
    except Exception:
        return {}


@st.cache_data(show_spinner=False, ttl=86400, max_entries=512)
def query_texas_subdivisions_for_point(lon: float, lat: float) -> pd.DataFrame:
    cols = ["subdivision_type", "subdivision_name", "subdivision_code", "source_name", "source_url"]
    geo_point = f"{lon},{lat}"
    base_params = {
        "geometry": geo_point,
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "returnGeometry": "false",
        "f": "json",
    }

    def _fetch_school_districts() -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        try:
            payload = arcgis_get_json(f"{TEA_ARCGIS_SCHOOL_DISTRICT_LAYER_URL}/query", params={**base_params, "outFields": "NAME,NAME20,DISTRICT,DISTRICT_C"})
            for feat in payload.get("features", []):
                attrs = feat.get("attributes", {}) or {}
                name = str(attrs.get("NAME20", "")).strip() or str(attrs.get("NAME", "")).strip()
                code = str(attrs.get("DISTRICT", "")).strip() or str(attrs.get("DISTRICT_C", "")).strip()
                if name:
                    result.append({"subdivision_type": "School District", "subdivision_name": name, "subdivision_code": code, "source_name": "TEA School District boundaries (FeatureServer/0)", "source_url": TEA_ARCGIS_SCHOOL_DISTRICT_LAYER_URL})
        except Exception:
            pass
        return result

    def _fetch_counties() -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        try:
            payload = arcgis_get_json(f"{TEA_ARCGIS_COUNTY_LAYER_URL}/query", params={**base_params, "outFields": "FENAME,FIPS"})
            for feat in payload.get("features", []):
                attrs = feat.get("attributes", {}) or {}
                county_name = str(attrs.get("FENAME", "")).strip()
                if county_name:
                    result.append({"subdivision_type": "County", "subdivision_name": f"{county_name} County", "subdivision_code": str(attrs.get("FIPS", "")).strip(), "source_name": "TEA County boundaries (FeatureServer/0)", "source_url": TEA_ARCGIS_COUNTY_LAYER_URL})
        except Exception:
            pass
        return result

    def _fetch_cities() -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        try:
            payload = arcgis_get_json(f"{CENSUS_ARCGIS_TEXAS_CITY_LAYER_URL}/query", params={**base_params, "where": "STATE='48'", "outFields": "NAME,BASENAME,GEOID"})
            for feat in payload.get("features", []):
                attrs = feat.get("attributes", {}) or {}
                name = str(attrs.get("NAME", "")).strip()
                base = str(attrs.get("BASENAME", "")).strip() or re.sub(r"\s+(city|town|village)\s*$", "", name, flags=re.IGNORECASE).strip()
                if base:
                    display = base if re.search(r"\b(CITY|TOWN|VILLAGE)\b$", base, flags=re.IGNORECASE) else f"{base} City"
                    result.append({"subdivision_type": "City", "subdivision_name": display, "subdivision_code": str(attrs.get("GEOID", "")).strip(), "source_name": "U.S. Census TIGERweb Texas Places (MapServer/25)", "source_url": CENSUS_ARCGIS_TEXAS_CITY_LAYER_URL})
        except Exception:
            pass
        return result

    def _fetch_water_districts() -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        try:
            payload = arcgis_get_json(f"{TCEQ_WATER_DISTRICTS_LAYER_URL}/query", params={**base_params, "outFields": "NAME,DISTRICT_ID,TYPE,TYPE_DESCRIPTION"})
            for feat in payload.get("features", []):
                attrs = feat.get("attributes", {}) or {}
                mapped_type = _canonical_water_district_type(str(attrs.get("TYPE_DESCRIPTION", "")).strip())
                if mapped_type == "Navigation District":
                    mapped_type = ""
                if not mapped_type:
                    continue
                name = str(attrs.get("NAME", "")).strip()
                if name:
                    result.append({"subdivision_type": mapped_type, "subdivision_name": name, "subdivision_code": str(attrs.get("DISTRICT_ID", "")).strip(), "source_name": "TCEQ Water Districts (FeatureServer/0)", "source_url": TCEQ_WATER_DISTRICTS_LAYER_URL})
        except Exception:
            pass
        return result

    def _fetch_groundwater() -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        try:
            payload = arcgis_get_json(f"{TCEQ_GROUNDWATER_DISTRICTS_LAYER_URL}/query", params={**base_params, "outFields": "DISTNAME,DIST_NUM,SHORTNAM"})
            for feat in payload.get("features", []):
                attrs = feat.get("attributes", {}) or {}
                name = str(attrs.get("DISTNAME", "")).strip() or str(attrs.get("SHORTNAM", "")).strip()
                if name:
                    result.append({"subdivision_type": "Groundwater Conservation District", "subdivision_name": name, "subdivision_code": str(attrs.get("DIST_NUM", "")).strip(), "source_name": "TCEQ Groundwater Conservation Districts (FeatureServer/0)", "source_url": TCEQ_GROUNDWATER_DISTRICTS_LAYER_URL})
        except Exception:
            pass
        return result

    def _fetch_rma() -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        try:
            payload = arcgis_get_json(f"{TEXAS_RMA_LAYER_URL}/query", params={**base_params, "outFields": "OBJECTID,RMA,Label"})
            for feat in payload.get("features", []):
                attrs = feat.get("attributes", {}) or {}
                name = str(attrs.get("Label", "")).strip() or str(attrs.get("RMA", "")).strip()
                if name:
                    result.append({"subdivision_type": "Regional Mobility Authority", "subdivision_name": name, "subdivision_code": str(attrs.get("OBJECTID", "")).strip(), "source_name": "Texas Regional Mobility Authorities (FeatureServer/0)", "source_url": TEXAS_RMA_LAYER_URL})
        except Exception:
            pass
        return result

    def _fetch_junior_colleges() -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        try:
            payload = arcgis_get_json(f"{TEXAS_JUNIOR_COLLEGE_LAYER_URL}/query", params={**base_params, "outFields": "DISTRICT,NAME1,NAME2"})
            for feat in payload.get("features", []):
                attrs = feat.get("attributes", {}) or {}
                name = str(attrs.get("NAME1", "")).strip() or str(attrs.get("NAME2", "")).strip()
                if name:
                    result.append({"subdivision_type": "Junior College District", "subdivision_name": name, "subdivision_code": str(attrs.get("DISTRICT", "")).strip(), "source_name": "Texas Junior College Service Areas (FeatureServer/0)", "source_url": TEXAS_JUNIOR_COLLEGE_LAYER_URL})
        except Exception:
            pass
        return result

    def _fetch_navigation() -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        try:
            payload = arcgis_get_json(f"{TEXAS_NAVIGATION_DISTRICT_LAYER_URL}/query", params={**base_params, "outFields": "OBJECTID,DISTRICT_N"})
            for feat in payload.get("features", []):
                attrs = feat.get("attributes", {}) or {}
                name = str(attrs.get("DISTRICT_N", "")).strip()
                if name:
                    result.append({"subdivision_type": "Navigation District", "subdivision_name": name, "subdivision_code": str(attrs.get("OBJECTID", "")).strip(), "source_name": "Texas Navigation Districts (FeatureServer/29)", "source_url": TEXAS_NAVIGATION_DISTRICT_LAYER_URL})
        except Exception:
            pass
        return result

    def _fetch_transit() -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        try:
            payload = arcgis_get_json(f"{NCTCOG_TRANSIT_PROVIDERS_LAYER_URL}/query", params={**base_params, "outFields": "OBJECTID,Name,Classification"})
            for feat in payload.get("features", []):
                attrs = feat.get("attributes", {}) or {}
                name = str(attrs.get("Name", "")).strip()
                if name:
                    result.append({"subdivision_type": "Transit Authority", "subdivision_name": name, "subdivision_code": str(attrs.get("OBJECTID", "")).strip(), "source_name": "NCTCOG Transit Providers (MapServer/10)", "source_url": NCTCOG_TRANSIT_PROVIDERS_LAYER_URL})
        except Exception:
            pass
        return result

    def _fetch_seaports() -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        try:
            payload = arcgis_get_json(f"{TXDOT_SEAPORTS_LAYER_URL}/query", params={**base_params, "distance": 25, "units": "esriSRUnit_StatuteMile", "outFields": "OBJECTID,PORT_NM"})
            for feat in payload.get("features", []):
                attrs = feat.get("attributes", {}) or {}
                name = str(attrs.get("PORT_NM", "")).strip()
                if name:
                    result.append({"subdivision_type": "Port Authority", "subdivision_name": name, "subdivision_code": str(attrs.get("OBJECTID", "")).strip(), "source_name": "TxDOT Seaports (FeatureServer/0)", "source_url": TXDOT_SEAPORTS_LAYER_URL})
        except Exception:
            pass
        return result

    fetchers = [_fetch_school_districts, _fetch_counties, _fetch_cities, _fetch_water_districts, _fetch_groundwater, _fetch_rma, _fetch_junior_colleges, _fetch_navigation, _fetch_transit, _fetch_seaports]
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=len(fetchers)) as pool:
        futures = {pool.submit(fn): fn.__name__ for fn in fetchers}
        for future in as_completed(futures):
            try:
                rows.extend(future.result())
            except Exception:
                pass
    if not rows:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame(rows, columns=cols).drop_duplicates()
    return out.sort_values(["subdivision_type", "subdivision_name"], ascending=[True, True])


@functools.lru_cache(maxsize=4096)
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
        return _subdivision_root_from_patterns(subdivision_name, [r"\bEMERGENCY\s+SERVICES\s+DISTRICT\b", r"\bDISTRICT\b", r"\bE\.?S\.?D\.?\b"])
    if lowered == "appraisal district":
        return _subdivision_root_from_patterns(subdivision_name, [r"\bAPPRAISAL\s+DISTRICT\b", r"\bDISTRICT\b", r"\bC\.?A\.?D\.?\b"])
    if lowered == "local government corporation":
        return _subdivision_root_from_patterns(subdivision_name, [r"\bLOCAL\s+GOVERNMENT\s+CORPORATION\b", r"\bDEVELOPMENT\s+CORPORATION\b", r"\bCORPORATION\b"])
    if lowered == "groundwater conservation district":
        return _subdivision_root_from_patterns(subdivision_name, [r"\bGROUNDWATER\s+CONSERVATION\s+DISTRICT\b", r"\bDISTRICT\b"])
    if lowered == "regional mobility authority":
        return _subdivision_root_from_patterns(subdivision_name, [r"\bREGIONAL\s+MOBILITY\s+AUTHORITY\b", r"\bAUTHORITY\b", r"\bRMA\b"])
    if lowered == "junior college district":
        return _subdivision_root_from_patterns(subdivision_name, [r"\bCOMMUNITY\s+COLLEGE\b", r"\bJUNIOR\s+COLLEGE\b", r"\bCOLLEGE\s+DISTRICT\b", r"\bSERVICE\s+AREA\b", r"\bCOLLEGE\b", r"\bDISTRICT\b"])
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
    code_series = out["subdivision_code"].astype(str) if "subdivision_code" in out.columns else pd.Series([""] * len(out), index=out.index, dtype=object).astype(str)
    name_series = out["subdivision_name"].astype(str) if "subdivision_name" in out.columns else pd.Series([""] * len(out), index=out.index, dtype=object).astype(str)
    out["_code_key"] = code_series.map(_subdivision_code_key)
    out["_code_numeric_key"] = code_series.map(_subdivision_numeric_code_key)
    out["_name_key"] = name_series.map(lambda value: _subdivision_name_key(subdivision_type, value))
    return out


@st.cache_data(show_spinner=False, max_entries=256, hash_funcs={pd.DataFrame: _hash_dataframe_for_cache})
def _prepare_subdivision_match_pool_cached(subdivision_type: str, pool: pd.DataFrame) -> pd.DataFrame:
    return prepare_subdivision_match_pool(pool, subdivision_type)


def _pick_overlap_subdivision_matches(pool: pd.DataFrame, subdivision_type: str, subdivision_name: str, subdivision_code: str) -> tuple[pd.DataFrame, str]:
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
                name_pool["_name_score"] = name_pool["_name_key"].astype(str).map(lambda value: difflib.SequenceMatcher(None, name_key, str(value)).ratio())
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


def build_address_overlap_spending_rows(
    overlap_subdivisions: pd.DataFrame,
    subdivision_matches: pd.DataFrame,
    tfl_spending: pd.DataFrame,
    *,
    prepared_overlap_pools: dict[str, pd.DataFrame] | None = None,
    spend_lookup: dict[str, dict[str, object]] | None = None,
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
                pool_cache[subdivision_type] = _prepare_subdivision_match_pool_cached(subdivision_type, base_pool)
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


def _subdivision_color_hex(subdivision_type: str) -> str:
    return SUBDIVISION_TYPE_COLORS.get(str(subdivision_type).strip(), "#718191")


def _hex_to_rgba(color_hex: str, alpha: float = 0.88) -> list[float]:
    color = str(color_hex).strip().lstrip("#")
    if len(color) != 6 or not re.match(r"^[0-9a-fA-F]{6}$", color):
        return [113, 129, 145, alpha]
    return [int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16), alpha]


def render_subdivision_map_legend(type_counts: dict[str, int]) -> None:
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
        st.markdown(f'<div class="map-legend">{"".join(items)}</div>', unsafe_allow_html=True)


def build_overlap_map_points(
    overlap_subdivisions: pd.DataFrame,
    subdivision_matches: pd.DataFrame,
    *,
    prepared_overlap_pools: dict[str, pd.DataFrame] | None = None,
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
                pool_cache[subdivision_type] = _prepare_subdivision_match_pool_cached(subdivision_type, base_pool)
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

