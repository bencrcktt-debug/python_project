from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import functools
import re
from typing import Any

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

    st = _StreamlitStub()

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
)


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
        (r"\bHOSP\.?\s+DIST\.?\b", " HOSPITAL DISTRICT "),
        (r"\bNAV\.?\s+DIST\.?\b", " NAVIGATION DISTRICT "),
        (r"\bDIST\.?\b", " DISTRICT "),
        (r"\bNO\.?\b", " "),
        (r"\bNUMBER\b", " "),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)
    misspellings = [
        (r"\bGROUNDATER\b", "GROUNDWATER"),
        (r"\bDISTR[IT]{1,2}CT\b(?<!\bDISTRICT\b)", "DISTRICT"),
        (r"\bDISTSRICT\b", "DISTRICT"),
        (r"\bCONVERSATION\b", "CONSERVATION"),
        (r"\bAQUIFIER\b", "AQUIFER"),
        (r"\bCREEEK\b", "CREEK"),
        (r"\bAUTHORTIY\b", "AUTHORITY"),
        (r"\bCORPERATION\b", "CORPORATION"),
        (r"\bINDEPENDEND\b", "INDEPENDENT"),
        (r"\bINDEPENDENDENT\b", "INDEPENDENT"),
        (r"\bLONGIVEW\b", "LONGVIEW"),
        (r"\bBANCH\b", "BRANCH"),
        (r"\bBURLESOM\b", "BURLESON"),
        (r"\bBEXAS\b", "BEXAR"),
    ]
    for pattern, replacement in misspellings:
        text = re.sub(pattern, replacement, text)
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    abbreviations = [
        (r"\bFT\b", "FORT"),
    ]
    for pattern, replacement in abbreviations:
        text = re.sub(pattern, replacement, text)
    text = re.sub(r"\s+TEXAS\s*$", "", text)
    text = re.sub(r"\s+TX\s*$", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


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
    if re.search(r"\bWATER\s+AUTHORITY\b|\bAQUIFER\s+AUTHORITY\b|\bWASTE\s+DISPOSAL\s+AUTHORITY\b|\bSUBSIDENCE\s+DISTRICT\b", text):
        return "River Authority"
    return ""


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


__all__ = [
    "_canonical_subdivision_text",
    "_canonical_water_district_type",
    "geocode_address_arcgis",
    "geocode_texas_entity_arcgis",
    "query_texas_county_for_point",
    "query_texas_subdivisions_for_point",
]

