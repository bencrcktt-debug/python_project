from __future__ import annotations

from dataclasses import dataclass
import difflib
import functools
import re
from typing import Any

import pandas as pd

from tfl_app.map.geo_queries import _canonical_subdivision_text
from tfl_app.map.reference_runtime import (
    CENSUS_ARCGIS_TEXAS_CITY_LAYER_URL,
    TEA_ARCGIS_COUNTY_LAYER_URL,
)
from tfl_app.shared.names import norm_name


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
    "Water Supply Corporation": "#2980B9",
    "Electric Cooperative": "#D4AC0D",
    "Airport": "#6C7A89",
    "University": "#8E44AD",
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
    "Water Supply Corporation",
    "Electric Cooperative",
    "Airport",
    "University",
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
    "Electric Cooperative",
    "Airport",
    "University",
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
    if not text or "COUNTY" not in text:
        return False
    if re.search(
        r"\b(ASSOCIATION|COALITION|COMMITTEE|BOARD|CHAMBER|FEDERATION"
        r"|RETIREMENT|EMPLOYEES|MEDICAL|SOCIETY|SCHOOLS|NETWORK"
        r"|GENERATION|FOUNDATION|FINANCE|LLC|INC|ADVISORY|LEGISLATIVE"
        r"|COLISEUM|HOSPITAL|SHERIFFS?|DEPUTIES?|CLERKS?"
        r"|TREASURERS?|JUDGES?|COMMISSIONERS?"
        r"|COLLEGE|ATTORNEYS?|DBA)\b",
        text,
    ):
        return False
    return True


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
    if re.search(r"\bUNDERGROUND\s+WATER\b", text):
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
    if re.search(r"\bWATER\s+AUTHORITY\b", text):
        return "River Authority"
    if re.search(r"\bMUNICIPAL\s+WATER\s+DISTRICT\b", text):
        return "River Authority"
    if re.search(r"\bAQUIFER\s+AUTHORITY\b", text):
        return "River Authority"
    if re.search(r"\bWASTE\s+DISPOSAL\s+AUTHORITY\b", text):
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
    if re.search(r"\bFLOOD\s+CONTROL\s+DISTRICT\b", text):
        return "Water Control & Improvement District"
    if re.search(r"\bSUBSIDENCE\s+DISTRICT\b", text):
        return "Groundwater Conservation District"
    if re.search(r"\bCONSERVATION\s+(AND\s+)?(RECLAMATION\s+)?DISTRICT\b", text):
        return "Groundwater Conservation District"
    if re.search(r"\bWATER\s+SUPPLY\b", text):
        return "Water Supply Corporation"
    if re.search(r"\bWATER\s+SYSTEM\b", text):
        return "Water Supply Corporation"
    if re.search(r"\bMANAGEMENT\s+DISTRICT\b", text):
        return "Municipal Management District"
    if re.search(r"\bIMPROVEMENT\s+DISTRICT\b", text):
        return "Municipal Management District"
    if re.search(r"\bTOLL\s*(ROAD|WAY)\s+AUTHORITY\b", text):
        return "Regional Mobility Authority"
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
    if "PORT AUTHORITY" in text or re.search(r"\bPORT OF\b|\bSEAPORT\b", text):
        return "Port Authority"
    if "HOUSING AUTHORITY" in text:
        return "Housing Authority"
    if "APPRAISAL DISTRICT" in text:
        return "Appraisal District"
    if re.search(r"\bHOSPITAL\s+AUTHORITY\b", text):
        return "Hospital District"
    if re.search(r"\bHEALTH\s+SYSTEM\b", text) and not re.search(r"\bASSOCIATION\b|\bINC\b|\bLLC\b", text):
        return "Hospital District"
    if re.search(r"\bMEDICAL\s+CENTER\b", text) and not re.search(r"\bASSOCIATION\b|\bINC\b|\bLLC\b", text):
        return "Hospital District"
    if re.search(r"\bELECTRIC\s+COOPERATIVE\b|\bELECTRIC\s+COOP\b|\bRURAL\s+ELECTRIC\b", text):
        return "Electric Cooperative"
    if re.search(r"\bAIRPORT\b", text) and not re.search(r"\bASSOCIATION\b|\bINC\b|\bLLC\b", text):
        return "Airport"
    if re.search(r"\bUNIVERSITY\b", text) and not re.search(r"\bASSOCIATION\b|\bINC\b|\bLLC\b|\bCHAPTER\b|\bFOUNDATION\b", text):
        return "University"
    if re.search(r"\bCOLLEGE\b", text) and not re.search(r"\bASSOCIATION\b|\bINC\b|\bLLC\b|\bCHAPTER\b|\bPHYSICIAN\b|\bOBSTETRICIAN\b|\bFOUNDATION\b|\bBOARD\b", text):
        return "University"
    if _looks_like_school_district_name(value):
        return "School District"
    if _looks_like_county_name(value):
        return "County"
    if _looks_like_city_name(value):
        return "City"
    return ""


def _looks_like_city_name(value: str) -> bool:
    text = _canonical_city_name(value)
    if not text:
        return False
    if not re.search(r"\b(CITY|TOWN|VILLAGE)\b", text):
        return False
    if re.search(
        r"\b(COMMITTEE|STEERING|CHAMBER|COMMERCE|RETIREMENT|EMPLOYEES"
        r"|HOSPITAL|PLAN|TRUST|ASSOCIATION|COALITION|FOUNDATION"
        r"|SYSTEM|DBA)\b",
        text,
    ):
        return False
    return True


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
            base = str(getattr(row, "basename", "")).strip() or re.sub(
                r"\s+(city|town|village)\s*$",
                "",
                raw_name,
                flags=re.IGNORECASE,
            ).strip()
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
    return pd.DataFrame(out_rows, columns=cols).sort_values(
        ["subdivision_type", "match_count", "subdivision_name"],
        ascending=[True, False, True],
    )


__all__ = [
    "PORT_AUTHORITY_ROOT_PATTERNS",
    "SPECIAL_NAME_ANCHORED_ENTITY_TYPES",
    "SUBDIVISION_TYPE_COLORS",
    "TRANSIT_AUTHORITY_ROOT_PATTERNS",
    "WATER_DISTRICT_TYPE_ROOT_PATTERNS",
    "SpecialAnchorLookup",
    "_build_layer_subdivision_matches",
    "_build_special_anchor_lookup",
    "_canonical_city_name",
    "_canonical_county_name",
    "_canonical_school_district_name",
    "_city_root_key",
    "_county_root_key",
    "_looks_like_city_name",
    "_looks_like_county_name",
    "_looks_like_entity_type",
    "_looks_like_school_district_name",
    "_match_preview",
    "_merge_subdivision_match_rows",
    "_resolve_special_anchor_keys",
    "_resolve_special_anchor_record",
    "_school_district_root_key",
    "_subdivision_root_from_patterns",
    "classify_requested_entity_type",
]
