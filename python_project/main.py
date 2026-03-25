import gc
import hashlib
import os
import re
import difflib
import functools
import importlib
import html
import json
import logging
import math
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from io import BytesIO
from pathlib import Path
import pandas as pd
pd.options.mode.copy_on_write = True  # PERFORMANCE: deferred copy — makes .copy() nearly free
import streamlit as st
import streamlit.components.v1 as components
import plotly.express as px
import plotly.io as pio
from fpdf import FPDF, XPos, YPos
import map_page_state as _map_page_state
import shared_search_state as _shared_search_state
import src.map_runtime as _map_runtime
import src.map_fragments as _map_fragments
import src.page_bundles as _page_bundles
import src.page_fragments as _page_fragments

# =========================================================
# PERFORMANCE: Pre-compiled regex patterns
# =========================================================
_RE_WHITESPACE = re.compile(r"\s+")
_RE_BILL_PATTERN = re.compile(
    r"\b(HB|SB|HR|SR|HCR|SCR|HJR|SJR)\s*(\d+)\b", re.IGNORECASE
)
_RE_PARENS = re.compile(r"\([^)]*\)")

# =========================================================
# PERFORMANCE: Vectorized display helpers (avoid .apply())
# =========================================================
def _vectorized_person_display(org: pd.Series, last: pd.Series, first: pd.Series) -> pd.Series:
    """Vectorized version of person_display — avoids row-by-row .apply()."""
    org_s = org.fillna("").astype(str).str.strip()
    last_s = last.fillna("").astype(str).str.strip()
    first_s = first.fillna("").astype(str).str.strip()
    # Priority: org if non-empty, then "last, first", then whichever exists
    result = org_s.where(org_s != "", last_s + ", " + first_s)
    # Fix cases where only last or only first
    both = (last_s != "") & (first_s != "")
    only_last = (last_s != "") & (first_s == "")
    only_first = (last_s == "") & (first_s != "")
    neither = (last_s == "") & (first_s == "")
    result = result.where(~(~(org_s != "")) | True, result)  # keep org priority
    # Rebuild for non-org cases
    no_org = org_s == ""
    result = result.where(~no_org, pd.Series("", index=org.index))
    result[no_org & both] = last_s[no_org & both] + ", " + first_s[no_org & both]
    result[no_org & only_last] = last_s[no_org & only_last]
    result[no_org & only_first] = first_s[no_org & only_first]
    result[no_org & neither] = ""
    result[~no_org] = org_s[~no_org]
    return result.str.strip()


def _vectorized_amount_display(exact: pd.Series, low: pd.Series, high: pd.Series, code: pd.Series | None = None) -> pd.Series:
    """Vectorized version of amount_display — avoids row-by-row .apply()."""
    exact_s = exact.fillna("").astype(str).str.strip()
    low_s = low.fillna("").astype(str).str.strip()
    high_s = high.fillna("").astype(str).str.strip()
    code_s = code.fillna("").astype(str).str.strip() if code is not None else pd.Series("", index=exact.index)
    # Priority: exact -> low--high or low -> code -> ""
    result = pd.Series("", index=exact.index)
    has_exact = exact_s != ""
    has_low = low_s != ""
    has_high = high_s != ""
    has_code = code_s != ""
    result = result.where(~has_exact, exact_s)
    need_range = ~has_exact & has_low & has_high
    result[need_range] = low_s[need_range] + "--" + high_s[need_range]
    need_low_only = ~has_exact & has_low & ~has_high
    result[need_low_only] = low_s[need_low_only]
    need_code = ~has_exact & ~has_low & has_code
    result[need_code] = code_s[need_code]
    return result

# =========================================================
# CONFIG
# =========================================================
DEFAULT_DATA_FILENAME = "TFL Webstite books - combined.parquet"
TEA_ARCGIS_WEBAPP_URL = "https://tea-texas.maps.arcgis.com/apps/webappviewer/index.html?id=51f0c8fa684c4d399d8d182e6edd5d97"
TEA_ARCGIS_SCHOOL_DISTRICT_LAYER_URL = "https://services2.arcgis.com/5MVN2jsqIrNZD4tP/arcgis/rest/services/Map/FeatureServer/0"
TEA_ARCGIS_COUNTY_LAYER_URL = "https://services2.arcgis.com/5MVN2jsqIrNZD4tP/arcgis/rest/services/Counties2019/FeatureServer/0"
CENSUS_ARCGIS_TEXAS_CITY_LAYER_URL = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Places_CouSub_ConCity_SubMCD/MapServer/25"
ARCGIS_GEOCODER_URL = "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"
TCEQ_WATER_DISTRICTS_LAYER_URL = "https://services2.arcgis.com/LYMgRMwHfrWWEg3s/arcgis/rest/services/TCEQ_Water_Districts/FeatureServer/0"
TCEQ_GROUNDWATER_DISTRICTS_LAYER_URL = "https://services2.arcgis.com/LYMgRMwHfrWWEg3s/arcgis/rest/services/TCEQ_Groundwater_Conservation_Districts/FeatureServer/0"
TEXAS_RMA_LAYER_URL = "https://services.arcgis.com/KTcxiTD9dsQw4r7Z/arcgis/rest/services/Texas_Regional_Mobility_Authority_Boundaries/FeatureServer/0"
TEXAS_HOUSE_DISTRICTS_LAYER_URL = "https://services.arcgis.com/KTcxiTD9dsQw4r7Z/arcgis/rest/services/Texas_State_House_Districts/FeatureServer/0"
TEXAS_SENATE_DISTRICTS_LAYER_URL = "https://services.arcgis.com/KTcxiTD9dsQw4r7Z/arcgis/rest/services/Texas_State_Senate_Districts/FeatureServer/0"
TEXAS_JUNIOR_COLLEGE_LAYER_URL = "https://services1.arcgis.com/hVMNhMnY75fwfIFy/arcgis/rest/services/JuniorCollege_ServiceAreas/FeatureServer/0"
TEXAS_NAVIGATION_DISTRICT_LAYER_URL = "https://services1.arcgis.com/YWG34dhJxrbxQWdF/arcgis/rest/services/Navigation_Districts2/FeatureServer/29"
NCTCOG_TRANSIT_PROVIDERS_LAYER_URL = "https://geospatial.nctcog.org/map/rest/services/Transportation/DFWMaps_Transit/MapServer/10"
TXDOT_SEAPORTS_LAYER_URL = "https://services.arcgis.com/KTcxiTD9dsQw4r7Z/arcgis/rest/services/TxDOT_Seaports/FeatureServer/0"
MAP_BASEMAP_OPTIONS = {
    "Gray Canvas": "gray-vector",
    "Street Detail": "streets-vector",
    "Satellite": "hybrid",
}

# -- Atlas → Forensics / Batch bridge (invisible component relay) --
_TFL_BRIDGE_DIR = Path(__file__).parent / "_atlas_bridge"
_atlas_bridge = components.declare_component("atlas_bridge", path=str(_TFL_BRIDGE_DIR))
_PERSISTENT_HTML_FRAME_DIR = Path(__file__).parent / "_persistent_html_frame"
_persistent_html_frame = components.declare_component(
    "persistent_html_frame",
    path=str(_PERSISTENT_HTML_FRAME_DIR),
)
_TFL_SUBDIVISION_MAP_DIR = Path(__file__).parent / "_tfl_subdivision_map"
_tfl_subdivision_map_component = components.declare_component(
    "tfl_subdivision_map",
    path=str(_TFL_SUBDIVISION_MAP_DIR),
)


def _stable_json_signature(value) -> str:
    return hashlib.sha1(
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _clone_session_cache_value(value):
    if isinstance(value, pd.DataFrame):
        return value.copy()
    if isinstance(value, pd.Series):
        return value.copy()
    if isinstance(value, dict):
        return {k: _clone_session_cache_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clone_session_cache_value(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_clone_session_cache_value(v) for v in value)
    return value


def _session_cached_value(cache_key: str, signature: str, builder):
    cached = st.session_state.get(cache_key)
    if isinstance(cached, dict) and cached.get("signature") == signature and "value" in cached:
        return _clone_session_cache_value(cached["value"])
    value = builder()
    st.session_state[cache_key] = {
        "signature": signature,
        "value": _clone_session_cache_value(value),
    }
    return _clone_session_cache_value(value)
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
MAP_DATA_SOURCES = [
    (
        "TEA School District Locator (web app)",
        TEA_ARCGIS_WEBAPP_URL,
        "Reference viewer used for school district context.",
    ),
    (
        "TEA School District boundaries (FeatureServer/0)",
        TEA_ARCGIS_SCHOOL_DISTRICT_LAYER_URL,
        "School district polygons and centroids.",
    ),
    (
        "TEA County boundaries (FeatureServer/0)",
        TEA_ARCGIS_COUNTY_LAYER_URL,
        "County polygons and centroids.",
    ),
    (
        "U.S. Census TIGERweb Texas Places (MapServer/25)",
        CENSUS_ARCGIS_TEXAS_CITY_LAYER_URL,
        "City/place polygons and centroids for Texas (STATE=48).",
    ),
    (
        "TCEQ Water Districts (FeatureServer/0)",
        TCEQ_WATER_DISTRICTS_LAYER_URL,
        "Municipal utility, drainage, fresh water supply, irrigation, levee improvement, municipal management, regional, river authority, soil and water control, special utility, water improvement, and water control and improvement districts.",
    ),
    (
        "TCEQ Groundwater Conservation Districts (FeatureServer/0)",
        TCEQ_GROUNDWATER_DISTRICTS_LAYER_URL,
        "Groundwater conservation district boundaries.",
    ),
    (
        "Texas Regional Mobility Authorities (FeatureServer/0)",
        TEXAS_RMA_LAYER_URL,
        "Regional mobility authority boundaries.",
    ),
    (
        "Texas Junior College Service Areas (FeatureServer/0)",
        TEXAS_JUNIOR_COLLEGE_LAYER_URL,
        "Junior/community college service-area boundaries.",
    ),
    (
        "Texas Navigation Districts (FeatureServer/29)",
        TEXAS_NAVIGATION_DISTRICT_LAYER_URL,
        "Navigation district boundaries.",
    ),
    (
        "NCTCOG Transit Providers (MapServer/10)",
        NCTCOG_TRANSIT_PROVIDERS_LAYER_URL,
        "Transit provider/service-area polygons for the North Central Texas region.",
    ),
    (
        "TxDOT Seaports (FeatureServer/0)",
        TXDOT_SEAPORTS_LAYER_URL,
        "Texas seaport locations and attributes used for port-authority matching.",
    ),
    (
        "ArcGIS World Geocoding Service",
        ARCGIS_GEOCODER_URL,
        "Address geocoding for overlap point lookup plus centroid fallback for special subdivision types without statewide boundary layers.",
    ),
]


def _is_url(path: str) -> bool:
    return path.startswith("http://") or path.startswith("https://")


def _resolve_data_path() -> str:
    # Prefer environment variable, then local fallbacks.
    env_path = os.getenv("DATA_PATH", "").strip()
    if env_path:
        return env_path

    here = Path(__file__).resolve().parent
    candidates = [
        here / DEFAULT_DATA_FILENAME,
        here / "data" / DEFAULT_DATA_FILENAME,
        here.parent / "data" / DEFAULT_DATA_FILENAME,
        here.parent / DEFAULT_DATA_FILENAME,
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return ""


PATH = _resolve_data_path()

st.set_page_config(page_title="Texas Taxpayer Lobbying Transparency Center", layout="wide")

# =========================================================
# STYLE (unchanged)
# =========================================================
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;600;700&family=IBM+Plex+Serif:wght@400;600&family=Source+Sans+3:wght@400;600;700&display=swap');
:root{
    --bg: #071627;
    --panel: rgba(255,255,255,0.06);
    --panel2: rgba(255,255,255,0.04);
    --border: rgba(255,255,255,0.10);
    --text: rgba(255,255,255,0.92);
    --muted: rgba(255,255,255,0.70);
    --accent: #1e90ff;
    --accent2: #00e0b8;
    --nav-h: 72px;
    --nav-bg: rgba(6, 16, 30, 0.98);
    --nav-border: rgba(255,255,255,0.08);
    --nav-search-w: 320px;
    --nav-search-h: 38px;
    --space-1: 6px;
    --space-2: 10px;
    --space-3: 16px;
    --space-4: 22px;
    --radius-md: 14px;
    --radius-lg: 18px;
    --shadow-1: 0 10px 25px rgba(0,0,0,0.20);
    --shadow-2: 0 18px 32px rgba(0,0,0,0.28);
}

html, body, [data-testid="stAppViewContainer"]{
    background: radial-gradient(1200px 600px at 20% 15%, rgba(30,144,255,0.16), transparent 60%),
                            radial-gradient(900px 500px at 75% 30%, rgba(0,255,180,0.08), transparent 55%),
                            var(--bg) !important;
    color: var(--text) !important;
    font-family: 'IBM Plex Sans', system-ui, -apple-system, Segoe UI, sans-serif !important;
}

[data-testid="stAppViewContainer"]{
    position: relative;
}
[data-testid="stAppViewContainer"]::before{
    content: "";
    position: fixed;
    inset: 0;
    background-image:
        linear-gradient(transparent 26px, rgba(255,255,255,0.035) 27px),
        linear-gradient(90deg, transparent 26px, rgba(255,255,255,0.035) 27px);
    background-size: 32px 32px;
    opacity: 0.15;
    pointer-events: none;
    z-index: 0;
}
[data-testid="stAppViewContainer"] > div{
    position: relative;
    z-index: 1;
}

[data-testid="stHeader"]{ display: none !important; }
[data-testid="stToolbar"]{ right: 1rem; }
.block-container{
    padding-top: calc(var(--nav-h) + 0.8rem);
    padding-bottom: calc(1rem + env(safe-area-inset-bottom, 0px));
}

h1,h2,h3{ color: var(--text) !important; }
p,li,span,div{ color: var(--text); }

.small-muted{ color: var(--muted); font-size: 0.95rem; }
.hr{ height:1px; background: var(--border); margin: 1rem 0 1.2rem 0; }

.card{
    background: linear-gradient(180deg, var(--panel), var(--panel2));
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 16px 16px 14px 16px;
    box-shadow: var(--shadow-1);
}
div[data-testid="stPlotlyChart"]{
    background: linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.01));
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: var(--radius-lg);
    padding: 10px 12px 6px 12px;
    box-shadow: var(--shadow-2);
    box-sizing: border-box;
    margin-top: 0.35rem;
}
div[data-testid="stPlotlyChart"] > div{
    border-radius: 14px;
    overflow: hidden;
}
.about-wrap{
    display: flex;
    flex-direction: column;
    gap: 20px;
    width: 100%;
    max-width: 1200px;
    margin: 0 auto;
}
.about-hero{
    position: relative;
    overflow: hidden;
    padding: 24px 24px 20px 24px;
    border-radius: 22px;
    background: linear-gradient(135deg, rgba(0,224,184,0.22), rgba(30,144,255,0.14) 45%, rgba(7,22,39,0.82));
    border: 1px solid rgba(255,255,255,0.14);
    box-shadow: 0 20px 40px rgba(0,0,0,0.35);
    backdrop-filter: blur(6px);
}
.about-hero::before{
    content: "";
    position: absolute;
    inset: -40px -10px auto auto;
    width: 320px;
    height: 320px;
    background: radial-gradient(circle, rgba(30,144,255,0.35), transparent 70%);
    opacity: 0.6;
    pointer-events: none;
}
.about-hero::after{
    content: "";
    position: absolute;
    inset: 0;
    background-image:
        linear-gradient(transparent 24px, rgba(255,255,255,0.03) 25px),
        linear-gradient(90deg, transparent 24px, rgba(255,255,255,0.03) 25px);
    background-size: 32px 32px;
    opacity: 0.18;
    pointer-events: none;
}
.about-hero > *{
    position: relative;
    z-index: 1;
}
.about-hero p{
    max-width: 980px;
}
.about-kicker{
    text-transform: uppercase;
    letter-spacing: 0.18em;
    font-size: 0.68rem;
    color: var(--muted);
    margin-bottom: 8px;
}
.about-title{
    font-size: 2.2rem;
    font-weight: 700;
    margin: 0 0 0.4rem 0;
    text-shadow: 0 6px 16px rgba(0,0,0,0.35);
}
.about-lead{
    font-size: 1.05rem;
    line-height: 1.55;
    margin: 0.2rem 0 0.6rem 0;
}
.about-body{
    color: var(--muted);
    margin: 0 0 0.8rem 0;
}
.about-wrap p{
    line-height: 1.55;
}
.about-meta{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 0.6rem;
}
.about-meta .pill{
    background: rgba(7,22,39,0.35);
    border-color: rgba(255,255,255,0.18);
}
.about-shell{
    display: grid;
    grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.1fr);
    gap: 20px;
    align-items: start;
}
.about-sidebar{
    display: flex;
    flex-direction: column;
    gap: 20px;
}
.about-panel{
    padding: 18px 18px 16px 18px;
    border-left: 3px solid rgba(0,224,184,0.55);
    background: linear-gradient(180deg, rgba(255,255,255,0.08), rgba(255,255,255,0.02));
    border-color: rgba(255,255,255,0.12);
    box-shadow: 0 16px 26px rgba(0,0,0,0.26);
    backdrop-filter: blur(4px);
}
.about-panel-head{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 0.6rem;
}
.about-panel h3{
    margin: 0;
    font-size: 1.1rem;
}
.about-panel-tag{
    font-size: 0.65rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--muted);
    border: 1px solid rgba(255,255,255,0.16);
    padding: 3px 8px;
    border-radius: 999px;
    background: rgba(7,22,39,0.35);
}
.about-actions{
    display: grid;
    gap: 8px;
    margin-bottom: 0.6rem;
}
.about-action{
    display: flex;
    gap: 10px;
    align-items: flex-start;
    padding: 8px 10px;
    border-radius: 12px;
    background: rgba(7,22,39,0.4);
    border: 1px solid rgba(255,255,255,0.12);
    box-shadow: inset 0 0 0 1px rgba(255,255,255,0.02);
}
.about-action::before{
    content: "";
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--accent2);
    margin-top: 0.35rem;
    box-shadow: 0 0 0 3px rgba(0,224,184,0.18);
    flex: 0 0 auto;
}
.about-list-grid{
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 4px 12px;
    margin-top: 0.35rem;
}
.about-note{
    color: var(--muted);
    font-size: 0.95rem;
}
.about-checklist{
    list-style: none;
    padding: 0;
    margin: 0;
}
.about-checklist li{
    position: relative;
    padding-left: 1.4rem;
    margin: 0.35rem 0;
    line-height: 1.45;
}
.about-checklist li::before{
    content: "";
    position: absolute;
    left: 0;
    top: 0.5rem;
    width: 9px;
    height: 9px;
    border-radius: 3px;
    background: rgba(30,144,255,0.85);
    box-shadow: inset 0 0 0 2px rgba(30,144,255,0.15);
}
.about-main{
    display: flex;
    flex-direction: column;
    gap: 20px;
}
.about-section{
    position: relative;
    padding: 18px 18px 16px 26px;
    background: linear-gradient(180deg, rgba(255,255,255,0.07), rgba(255,255,255,0.02));
    border-color: rgba(255,255,255,0.12);
    box-shadow: 0 18px 30px rgba(0,0,0,0.28);
    backdrop-filter: blur(4px);
}
.about-section::before{
    content: "";
    position: absolute;
    left: 14px;
    top: 18px;
    bottom: 18px;
    width: 2px;
    background: linear-gradient(180deg, rgba(30,144,255,0.9), rgba(0,224,184,0.6));
    border-radius: 999px;
}
.about-section-head{
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 0.6rem;
}
.about-section-head h3{
    margin: 0;
    font-size: 1.35rem;
    letter-spacing: -0.01em;
}
.about-section-num{
    font-size: 0.68rem;
    letter-spacing: 0.2em;
    font-weight: 700;
    color: var(--accent2);
    border: 1px solid rgba(0,224,184,0.35);
    border-radius: 999px;
    padding: 4px 8px;
    background: rgba(0,224,184,0.12);
}
.source-grid{
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 14px;
    margin-top: 0.6rem;
}
.source-item{
    position: relative;
    overflow: hidden;
    background: rgba(7,22,39,0.4);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 14px;
    padding: 14px 12px 12px 12px;
    box-shadow: 0 14px 24px rgba(0,0,0,0.24);
    display: flex;
    flex-direction: column;
    gap: 4px;
}
.source-item::before{
    content: "";
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 2px;
    background: linear-gradient(90deg, rgba(0,224,184,0.8), rgba(30,144,255,0.8));
    opacity: 0.7;
}
.source-title{
    font-weight: 700;
    margin-bottom: 0.2rem;
}
.source-text{
    color: var(--muted);
    font-size: 0.93rem;
    margin-bottom: 0.25rem;
}
.source-note{
    color: var(--muted);
    font-size: 0.85rem;
    margin-top: 0.35rem;
}
.source-links{
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin-top: 0.35rem;
}
.video-grid{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 16px;
    margin-top: 0.4rem;
}
.video-card{
    background: rgba(7,22,39,0.4);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 16px;
    padding: 10px;
    box-shadow: 0 14px 24px rgba(0,0,0,0.24);
}
.video-card.is-active{
    border-color: rgba(30,144,255,0.55);
    box-shadow: 0 0 0 1px rgba(30,144,255,0.35), 0 14px 24px rgba(0,0,0,0.24);
}
.video-embed{
    position: relative;
    padding-top: 56.25%;
    border-radius: 12px;
    overflow: hidden;
    background: rgba(0,0,0,0.25);
}
.video-embed iframe{
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    border: 0;
}
.tap-hero{
    position: relative;
    overflow: hidden;
    padding: 18px 20px 16px 20px;
    border-radius: 20px;
    background: linear-gradient(135deg, rgba(30,144,255,0.18), rgba(0,224,184,0.12), rgba(7,22,39,0.85));
    border: 1px solid rgba(255,255,255,0.14);
    box-shadow: 0 18px 34px rgba(0,0,0,0.32);
}
.tap-hero::after{
    content: "";
    position: absolute;
    inset: auto -40px -50px -40px;
    height: 120px;
    background: radial-gradient(circle, rgba(30,144,255,0.25), transparent 70%);
    opacity: 0.6;
    pointer-events: none;
}
.tap-hero > *{ position: relative; z-index: 1; }
.tap-hero-kicker{
    text-transform: uppercase;
    letter-spacing: 0.2em;
    font-size: 0.7rem;
    color: var(--muted);
    margin-bottom: 6px;
}
.tap-hero-title{
    font-size: 2rem;
    font-weight: 700;
    margin: 0 0 0.4rem 0;
}
.tap-hero-lead{
    color: var(--muted);
    margin: 0;
    max-width: 860px;
    line-height: 1.55;
}
.tap-feature{
    margin-top: 1rem;
}
.tap-feature-head{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 12px;
    flex-wrap: wrap;
}
.tap-feature-kicker{
    text-transform: uppercase;
    letter-spacing: 0.18em;
    font-size: 0.65rem;
    color: var(--muted);
    margin-bottom: 6px;
}
.tap-feature-title{
    font-size: 1.5rem;
    font-weight: 700;
    margin: 0;
}
.tap-feature-summary{
    color: var(--muted);
    margin-top: 6px;
    font-size: 0.95rem;
}
.tap-feature-link{
    color: var(--text);
    text-decoration: none;
    font-weight: 600;
    border: 1px solid rgba(255,255,255,0.2);
    border-radius: 999px;
    padding: 6px 12px;
    background: rgba(7,22,39,0.35);
}
.tap-feature-link:hover{
    border-color: rgba(30,144,255,0.6);
}
.tap-gallery-title{
    margin-top: 1.4rem;
    font-size: 1.1rem;
    font-weight: 700;
    letter-spacing: 0.02em;
}
.tap-thumb{
    display: block;
    border-radius: 12px;
    overflow: hidden;
    margin-bottom: 10px;
    border: 1px solid rgba(255,255,255,0.08);
}
.tap-thumb img{
    width: 100%;
    display: block;
}
.tap-card-title{
    font-weight: 700;
    margin-bottom: 4px;
}
.tap-card-summary{
    color: var(--muted);
    font-size: 0.9rem;
    margin-bottom: 6px;
    line-height: 1.4;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
}
.tap-card-link{
    color: var(--accent);
    text-decoration: none;
    font-size: 0.85rem;
}
.tap-card-link:hover{
    text-decoration: underline;
}
.about-link{
    color: var(--accent);
    text-decoration: none;
}
.about-link:hover{
    text-decoration: underline;
}
@keyframes about-fade-up{
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
}
.fade-up{
    animation: about-fade-up 360ms ease both;
}
.about-hero,
.about-panel,
.about-section{
    animation: about-fade-up 420ms ease both;
}
.about-sidebar .about-panel:nth-child(1){ animation-delay: 60ms; }
.about-sidebar .about-panel:nth-child(2){ animation-delay: 120ms; }
.about-main .about-section:nth-child(1){ animation-delay: 80ms; }
.about-main .about-section:nth-child(2){ animation-delay: 140ms; }
.about-main .about-section:nth-child(3){ animation-delay: 200ms; }
@media (prefers-reduced-motion: reduce){
    .about-hero,
    .about-panel,
    .about-section{
        animation: none;
    }
    .fade-up{
        animation: none;
    }
}
.section-title{
    margin-top: 0.8rem;
    font-size: 1.6rem;
    font-weight: 700;
    letter-spacing: -0.01em;
    min-height: 3.6rem;
    display: flex;
    align-items: flex-end;
}
.section-sub{
    color: var(--muted);
    margin-top: -0.3rem;
    margin-bottom: 0.6rem;
}
.section-caption{
    color: var(--muted);
    font-size: 0.92rem;
    margin-top: 0.2rem;
}
.callout{
    border: 1px solid var(--border);
    background: linear-gradient(180deg, rgba(255,255,255,0.07), rgba(255,255,255,0.02));
    border-radius: var(--radius-md);
    padding: 12px 14px;
    box-shadow: 0 12px 22px rgba(0,0,0,0.22);
}
.callout-title{
    text-transform: uppercase;
    letter-spacing: 0.18em;
    font-size: 0.65rem;
    color: var(--muted);
    margin-bottom: 4px;
}
.callout-body{
    color: var(--text);
    font-size: 0.96rem;
    line-height: 1.5;
}
.geo-hero{
    margin-top: 0.4rem;
    background: linear-gradient(145deg, rgba(30,144,255,0.16), rgba(0,224,184,0.10), rgba(7,22,39,0.9));
    border: 1px solid rgba(255,255,255,0.14);
    box-shadow: 0 18px 30px rgba(0,0,0,0.30);
}
.geo-kicker{
    text-transform: uppercase;
    letter-spacing: 0.18em;
    font-size: 0.65rem;
    color: var(--muted);
    margin-bottom: 0.35rem;
}
.geo-title{
    font-size: 1.3rem;
    font-weight: 700;
    margin-bottom: 0.35rem;
}
.geo-lead{
    color: var(--muted);
    line-height: 1.45;
    margin-bottom: 0.6rem;
}
.geo-step{
    padding: 8px 10px;
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 12px;
    background: rgba(7,22,39,0.42);
    margin-top: 8px;
    line-height: 1.4;
}
.geo-step strong{
    color: var(--accent2);
    font-weight: 700;
}
.geo-note{
    margin-top: 0.4rem;
}
.filter-summary{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
    padding: 10px 12px;
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    background: rgba(7,22,39,0.55);
    box-shadow: inset 0 0 0 1px rgba(255,255,255,0.02);
}
.filter-summary-label{
    text-transform: uppercase;
    letter-spacing: 0.18em;
    font-size: 0.65rem;
    color: var(--muted);
    margin-right: 4px;
}
#filter-bar-marker + div[data-testid="stHorizontalBlock"],
#filter-summary-marker + div[data-testid="stHorizontalBlock"]{
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 18px;
    padding: 12px 14px;
    background: linear-gradient(180deg, rgba(255,255,255,0.06), rgba(255,255,255,0.02));
    box-shadow: 0 16px 28px rgba(0,0,0,0.24);
    animation: about-fade-up 360ms ease both;
}
#filter-summary-marker + div[data-testid="stHorizontalBlock"]{
    padding: 10px 12px;
}
.pill{
    display:inline-flex;
    align-items:center;
    gap:6px;
    padding: 4px 10px;
    border-radius: 999px;
    border: 1px solid rgba(255,255,255,0.12);
    background: rgba(255,255,255,0.04);
    font-size: 0.8rem;
}
.pill b{ font-weight: 700; }
.pill-list{
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 6px;
}
.pill.pill-muted{
    color: var(--muted);
    border-color: rgba(255,255,255,0.08);
    background: rgba(255,255,255,0.02);
}
.meta-card{
    margin-top: 0.4rem;
    background: linear-gradient(135deg, rgba(30,144,255,0.12), rgba(0,224,184,0.08), rgba(7,22,39,0.85));
    border: 1px solid rgba(255,255,255,0.16);
    box-shadow: 0 14px 28px rgba(0,0,0,0.26);
}
.meta-title{
    text-transform: uppercase;
    letter-spacing: 0.18em;
    font-size: 0.7rem;
    color: var(--muted);
}
.meta-sub{
    color: var(--muted);
    font-size: 0.9rem;
    margin-top: 4px;
}
.insight-panel{
    display: grid;
    grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr);
    gap: 16px;
    margin: 10px 0 4px 0;
}
.insight-card{
    background: linear-gradient(160deg, rgba(30,144,255,0.14), rgba(0,224,184,0.08), rgba(7,22,39,0.9));
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 18px;
    padding: 14px 16px;
    box-shadow: 0 16px 28px rgba(0,0,0,0.28);
}
.insight-kicker{
    text-transform: uppercase;
    letter-spacing: 0.18em;
    font-size: 0.65rem;
    color: var(--muted);
    margin-bottom: 6px;
}
.insight-title{
    font-size: 1.25rem;
    font-weight: 700;
    margin: 0 0 0.4rem 0;
}
.insight-list{
    list-style: none;
    padding: 0;
    margin: 0;
}
.insight-list li{
    position: relative;
    padding-left: 1.1rem;
    margin: 0.35rem 0;
    line-height: 1.45;
}
.insight-list li::before{
    content: "";
    position: absolute;
    left: 0;
    top: 0.55rem;
    width: 7px;
    height: 7px;
    border-radius: 2px;
    background: rgba(0,224,184,0.9);
    box-shadow: 0 0 0 2px rgba(0,224,184,0.15);
}
.mini-kpi-grid{
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
}
.mini-kpi{
    background: rgba(7,22,39,0.5);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 12px;
    padding: 10px 12px;
}
.mini-kpi .label{
    text-transform: uppercase;
    letter-spacing: 0.14em;
    font-size: 0.62rem;
    color: var(--muted);
    margin-bottom: 4px;
}
.mini-kpi .value{
    font-size: 1.15rem;
    font-weight: 700;
}
.mini-kpi .sub{
    color: var(--muted);
    font-size: 0.82rem;
    margin-top: 4px;
}

.kpi-title{ color: var(--muted); font-size: 0.85rem; margin-bottom: 8px; }
.kpi-value{ font-size: 2.0rem; font-weight: 700; line-height: 1.15; color: var(--text); }
.kpi-sub{ color: var(--muted); font-size: 0.9rem; margin-top: 6px; }

.big-title{
    font-size: 3.0rem;
    font-weight: 800;
    letter-spacing: -0.02em;
    margin: 0.1rem 0 0.2rem 0;
}

.subtitle{
    font-size: 1.2rem;
    color: var(--muted);
    margin-bottom: 1rem;
}

.stTabs [data-baseweb="tab-list"]{
    gap: 8px;
}
.stTabs [data-baseweb="tab"]{
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 14px;
    padding: 10px 14px;
}
.stTabs [aria-selected="true"]{
    border-color: rgba(30,144,255,0.55) !important;
    background: rgba(30,144,255,0.12) !important;
}

[data-testid="stTextInput"] input,
[data-testid="stTextInput"] textarea{
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.10) !important;
    color: var(--text) !important;
}

[data-testid="stSelectbox"] div[role="combobox"]{
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.10) !important;
}

.chip{
    display:inline-block;
    padding: 6px 10px;
    border-radius: 999px;
    border: 1px solid rgba(255,255,255,0.12);
    background: rgba(255,255,255,0.04);
    font-size: 0.85rem;
    margin-right: 6px;
}

[data-testid="stSidebar"]{
    background: rgba(255,255,255,0.02) !important;
    border-right: 1px solid rgba(255,255,255,0.07);
}

[data-testid="stDataFrame"]{
    border-radius: 16px;
    overflow: hidden;
    border: 1px solid rgba(255,255,255,0.10);
}
div[data-testid="stDataFrame"]{
    background: rgba(7, 22, 39, 0.65);
}

button[kind="primary"]{
    border-radius: 14px !important;
}

/* Force dark text for all selectbox and dropdown items */
[data-testid="stSelectbox"] [data-baseweb="select"] *,
[data-testid="stSelectbox"] [data-baseweb="select"] span,
[data-testid="stSelectbox"] [data-baseweb="select"] div,
[data-testid="stSelectbox"] [data-baseweb="select"] input,
[data-testid="stSelectbox"] [data-baseweb="select"] [role="option"],
[data-testid="stSelectbox"] [data-baseweb="select"] [role="listbox"] *,
[data-baseweb="popover"] ul[role="listbox"] *,
[data-baseweb="popover"] div[role="option"],
[data-baseweb="popover"] div[role="option"] * {
    color: #0b1a2b !important;
    background: white !important;
}

[data-testid="stSelectbox"] [data-baseweb="select"] ::placeholder{
    color: #405264 !important;
}
[data-testid="stSelectbox"] div[role="combobox"] *{
    color: #0b1a2b !important;
}

/* Improve selectbox readability */
[data-testid="stSelectbox"] [data-baseweb="select"] > div,
[data-testid="stSelectbox"] [data-baseweb="select"] span{
    color: #0b1a2b !important;
    font-weight: 700 !important;
    opacity: 1 !important;
}
[data-testid="stSelectbox"] [data-baseweb="select"] ::placeholder{
    color: #2b3c4d !important;
    opacity: 1 !important;
}
[data-baseweb="popover"] div[role="option"]{
    font-weight: 600;
}

/* Custom navigation header */
.custom-nav{
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: 1000;
    height: var(--nav-h);
    padding: 0 16px;
    background: linear-gradient(180deg, var(--nav-bg) 0%, rgba(6, 16, 30, 0.94) 70%, rgba(6, 16, 30, 0.9) 100%);
    border-bottom: 1px solid var(--nav-border);
    box-shadow: 0 12px 24px rgba(0,0,0,0.25);
    backdrop-filter: blur(8px);
}
.custom-nav::after{
    content: "";
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
    height: 1px;
    background: linear-gradient(90deg, rgba(255,255,255,0.02), rgba(255,255,255,0.16), rgba(255,255,255,0.02));
}
.custom-nav .nav-inner{
    max-width: 1280px;
    margin: 0 auto;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: flex-start;
    gap: 28px;
    padding-right: 0;
}
.custom-nav .brand{
    display: flex;
    flex-direction: column;
    gap: 2px;
    line-height: 1.05;
    color: var(--text);
    border-left: 3px solid var(--accent);
    padding-left: 12px;
}
.custom-nav .brand-top{
    font-size: 0.9rem;
    letter-spacing: 0.24em;
    text-transform: uppercase;
    opacity: 0.8;
}
.custom-nav .brand-bottom{
    font-size: 1.5rem;
    font-weight: 700;
    letter-spacing: -0.01em;
}
.custom-nav .nav-links{
    display: flex;
    gap: 22px;
    align-items: center;
    flex: 1 1 auto;
    margin-left: 12px;
    padding-right: calc(var(--nav-search-w) + 20px);
    white-space: nowrap;
}
.custom-nav .nav-link{
    position: relative;
    color: var(--muted);
    text-decoration: none;
    font-weight: 600;
    font-size: 0.98rem;
    letter-spacing: 0.01em;
    padding: 10px 2px;
    transition: color 120ms ease;
}
.custom-nav .nav-link::after{
    content: "";
    position: absolute;
    left: 0;
    right: 0;
    bottom: 2px;
    height: 2px;
    background: transparent;
    transition: background 120ms ease;
}
.custom-nav .nav-link:hover{
    color: var(--text);
}
.custom-nav .nav-link.active{
    color: var(--text);
}
.custom-nav .nav-link.active::after{
    background: var(--accent);
}

div[data-testid="stTextInput"]:has(input[aria-label="Nav search"]){
    position: fixed;
    top: 0;
    right: 18px;
    z-index: 1002;
    width: min(var(--nav-search-w), 38vw);
    height: var(--nav-h);
    display: flex;
    align-items: center;
}
div[data-testid="stTextInput"]:has(input[aria-label="Nav search"]) > div{
    width: 100%;
    margin: 0 !important;
}
div[data-testid="stTextInput"]:has(input[aria-label="Nav search"]) input{
    height: var(--nav-search-h) !important;
    border-radius: 999px !important;
    padding: 0 38px 0 14px !important;
    background: rgba(10, 18, 32, 0.75) !important;
    border: 1px solid rgba(255,255,255,0.18) !important;
    box-shadow: inset 0 0 0 1px rgba(255,255,255,0.03);
    color: var(--text) !important;
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%23b7c2d3' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><circle cx='11' cy='11' r='7'/><line x1='21' y1='21' x2='16.65' y2='16.65'/></svg>");
    background-repeat: no-repeat;
    background-position: right 12px center;
    background-size: 16px;
}
div[data-testid="stTextInput"]:has(input[aria-label="Nav search"]) input::placeholder{
    color: rgba(255,255,255,0.6);
}

/* Mobile responsive improvements */
@media (max-width: 768px) {
    :root{ --nav-h: 108px; --nav-search-w: 100%; }
    .block-container {
        padding-left: calc(0.5rem + env(safe-area-inset-left, 0px));
        padding-right: calc(0.5rem + env(safe-area-inset-right, 0px));
        padding-top: calc(var(--nav-h) + 3.6rem);
    }
    .section-title { font-size: 1.3rem; min-height: 2.5rem; }
    .big-title { font-size: 2rem; }
    .subtitle { font-size: 1rem; }
    [data-testid="stTextInput"] input { font-size: 16px !important; min-height: 44px !important; }
    [data-testid="stSelectbox"] div[role="combobox"] { font-size: 14px !important; min-height: 44px; }
    [data-testid="stMultiSelect"] div[role="combobox"] { min-height: 44px; }
    button { padding: 0.5rem 1rem !important; font-size: 14px !important; min-height: 44px; }
    .stTabs [data-baseweb="tab"] { padding: 10px 12px !important; font-size: 13px !important; min-height: 40px; }
    .stTabs [data-baseweb="tab-list"]{
        flex-wrap: nowrap;
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
        gap: 8px;
        padding-bottom: 6px;
    }
    .stTabs [data-baseweb="tab-list"]::-webkit-scrollbar{ display: none; }
    .stTabs [data-baseweb="tab"]{ flex: 0 0 auto; }
    .card{ padding: 12px 12px 10px 12px; border-radius: 16px; }
    .kpi-title{ font-size: 0.78rem; }
    .kpi-value{ font-size: 1.4rem; }
    .kpi-sub{ font-size: 0.85rem; }
    .section-sub{ font-size: 0.9rem; }
    .chip{ font-size: 0.75rem; padding: 4px 8px; margin-right: 4px; }
    [data-testid="stHorizontalBlock"]{ flex-direction: column; }
    [data-testid="column"]{ width: 100% !important; flex: 1 1 100% !important; }
    [data-testid="stDataFrame"]{ overflow-x: auto; -webkit-overflow-scrolling: touch; }
    button[kind="primary"]{ width: 100%; }
    .custom-nav{
        height: var(--nav-h);
        padding: 8px 12px;
    }
    .custom-nav .nav-inner{
        flex-direction: column;
        align-items: flex-start;
        gap: 6px;
        padding-right: 0;
    }
    .custom-nav .nav-links{
        flex-wrap: nowrap;
        gap: 14px;
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
        padding-right: 0;
        width: 100%;
    }
    .custom-nav .nav-links::-webkit-scrollbar{ display: none; }
    .custom-nav .nav-link{ font-size: 0.9rem; padding: 10px 6px; }
    .custom-nav .brand-top{ font-size: 0.8rem; }
    .custom-nav .brand-bottom{ font-size: 1.2rem; }
    .insight-panel{ grid-template-columns: 1fr; }
    .mini-kpi-grid{ grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .about-shell{ grid-template-columns: 1fr; }
    .about-hero{ padding: 18px 16px 16px 16px; }
    .about-title{ font-size: 1.6rem; }
    .about-panel-head{
        flex-direction: column;
        align-items: flex-start;
    }
    .about-list-grid{ grid-template-columns: 1fr; }
    .source-grid{ grid-template-columns: 1fr; }
    .about-section{ padding-left: 22px; }
    .about-section::before{ left: 12px; }
    .tap-hero{ padding: 16px 14px 14px 14px; }
    .tap-hero-title{ font-size: 1.5rem; }
    .tap-feature-head{ flex-direction: column; align-items: flex-start; }
    .geo-hero{ padding: 14px 12px 12px 12px; }
    .geo-title{ font-size: 1.05rem; }
    .geo-step{ padding: 7px 9px; }
    div[data-testid="stTextInput"]:has(input[aria-label="Nav search"]){
        top: calc(var(--nav-h) + 6px);
        left: calc(12px + env(safe-area-inset-left, 0px));
        right: calc(12px + env(safe-area-inset-right, 0px));
        width: auto;
        height: auto;
    }
    div[data-testid="stTextInput"]:has(input[aria-label="Nav search"]) input{
        width: 100%;
        height: 44px !important;
    }
    div[data-testid="stPlotlyChart"]{ padding: 6px 8px 4px 8px; border-radius: 16px; touch-action: pan-y; }
}
</style>
""",
    unsafe_allow_html=True,
)

st.markdown(
    """
<style>
:root{
    --bg: #0d1724;
    --bg-soft: #132133;
    --surface: #172638;
    --surface-2: #1c2d42;
    --surface-3: #22364f;
    --border: rgba(175, 194, 214, 0.30);
    --border-strong: rgba(198, 214, 231, 0.46);
    --text: #edf3fa;
    --muted: #b6c5d8;
    --accent: #86a7c6;
    --accent-2: #6f92b4;
    --radius-sm: 10px;
    --radius-md: 14px;
    --radius-lg: 18px;
    --shadow-1: 0 8px 18px rgba(2, 9, 16, 0.30);
    --shadow-2: 0 16px 30px rgba(2, 9, 16, 0.36);
}

html, body, [data-testid="stAppViewContainer"]{
    background:
        radial-gradient(900px 360px at 12% -12%, rgba(121, 152, 183, 0.18), transparent 62%),
        radial-gradient(820px 360px at 92% -10%, rgba(78, 108, 139, 0.16), transparent 62%),
        linear-gradient(180deg, #0d1724 0%, #121f2e 50%, #0d1724 100%) !important;
    color: var(--text) !important;
    font-family: 'IBM Plex Sans', 'Source Sans 3', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
}
[data-testid="stAppViewContainer"]::before{
    display: none !important;
}
.block-container{
    max-width: 1360px;
    padding-left: clamp(0.9rem, 1.9vw, 1.6rem);
    padding-right: clamp(0.9rem, 1.9vw, 1.6rem);
}
h1, h2, h3{
    color: var(--text) !important;
}

.card{
    border-radius: var(--radius-md);
    border: 1px solid var(--border);
    background: linear-gradient(180deg, rgba(26, 40, 57, 0.96), rgba(17, 29, 45, 0.94));
    box-shadow: var(--shadow-1);
}
div[data-testid="stPlotlyChart"]{
    border-radius: var(--radius-md);
    border: 1px solid rgba(175, 194, 214, 0.26);
    background: linear-gradient(180deg, rgba(23, 38, 56, 0.95), rgba(15, 26, 40, 0.94));
    box-shadow: var(--shadow-2);
}
[data-testid="stDataFrame"]{
    border-color: rgba(177, 196, 216, 0.30);
    background: rgba(12, 22, 35, 0.86);
    border-radius: var(--radius-md);
}

.custom-nav{
    background: rgba(11, 20, 31, 0.97);
    border-bottom: 1px solid rgba(171, 191, 212, 0.30);
    box-shadow: 0 10px 24px rgba(2, 9, 16, 0.42);
}
.custom-nav .brand{
    border-left-color: var(--accent);
    padding-left: 12px;
}
.custom-nav .brand-top{
    color: var(--muted);
    letter-spacing: 0.18em;
    font-size: 0.64rem;
    font-weight: 600;
}
.custom-nav .brand-bottom{
    font-size: 1.1rem;
    font-weight: 700;
    letter-spacing: 0.01em;
}
.custom-nav .nav-link{
    color: rgba(226, 236, 248, 0.84);
    font-size: 0.91rem;
    font-weight: 600;
}
.custom-nav .nav-link:hover{
    color: #f4f8fc;
}
.custom-nav .nav-link.active{
    color: #f5f9fd;
}
.custom-nav .nav-link.active::after{
    background: var(--accent);
    height: 3px;
}

.policy-hero{
    padding: 20px 22px 18px 22px;
    margin: 0 0 12px 0;
    border: 1px solid var(--border-strong);
    background:
        linear-gradient(128deg, rgba(94, 126, 157, 0.20), rgba(27, 42, 60, 0.92) 58%),
        linear-gradient(180deg, rgba(24, 37, 54, 0.96), rgba(15, 27, 41, 0.94));
}
.policy-kicker{
    text-transform: uppercase;
    letter-spacing: 0.17em;
    font-size: 0.65rem;
    font-weight: 600;
    color: var(--muted);
    margin-bottom: 7px;
}
.policy-title{
    font-family: 'IBM Plex Serif', 'Merriweather', Georgia, serif;
    font-size: clamp(1.76rem, 2.2vw, 2.25rem);
    font-weight: 600;
    line-height: 1.22;
    margin: 0;
}
.policy-subtitle{
    margin: 9px 0 0 0;
    color: var(--muted);
    line-height: 1.56;
    max-width: 940px;
    font-size: 0.99rem;
}
.policy-pill-list{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 12px;
}
.policy-pill{
    display: inline-flex;
    align-items: center;
    padding: 4px 11px 5px 11px;
    border-radius: 999px;
    border: 1px solid rgba(151, 180, 209, 0.46);
    background: rgba(97, 128, 160, 0.22);
    color: rgba(236, 243, 251, 0.98);
    font-size: 0.77rem;
    line-height: 1.2;
}

.workspace-links-heading{
    margin: 0.15rem 0 0.35rem 0;
    font-size: 0.72rem;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--muted);
    font-weight: 700;
}
.workspace-link-help{
    font-size: 0.82rem;
    line-height: 1.38;
    color: var(--muted);
    margin-top: 0.35rem;
    min-height: 2.45rem;
}

.policy-panel{
    padding: 14px 15px 12px 15px;
    border-radius: 12px;
    border: 1px solid var(--border);
    background: linear-gradient(180deg, rgba(30, 47, 67, 0.62), rgba(15, 27, 41, 0.88));
    margin-bottom: 11px;
}
.policy-panel h3{
    margin: 0 0 7px 0;
    font-size: 1.02rem;
    line-height: 1.32;
}
.policy-panel p{
    margin: 0;
    color: var(--muted);
    line-height: 1.5;
}

.section-title{
    font-family: 'IBM Plex Serif', 'Merriweather', Georgia, serif;
    letter-spacing: 0.01em;
}
.section-sub{
    color: rgba(193, 210, 227, 0.87);
}
.section-caption{
    color: rgba(185, 203, 222, 0.79);
}

.callout{
    border-radius: 12px;
    border-color: rgba(163, 183, 205, 0.30);
    background: linear-gradient(180deg, rgba(28, 45, 65, 0.60), rgba(15, 27, 41, 0.86));
}
.callout-title{
    letter-spacing: 0.15em;
}

.geo-hero{
    margin-top: 0.45rem;
    background:
        linear-gradient(145deg, rgba(88, 120, 150, 0.22), rgba(23, 39, 58, 0.92) 60%),
        linear-gradient(180deg, rgba(20, 34, 51, 0.96), rgba(14, 25, 39, 0.94));
    border: 1px solid rgba(170, 190, 211, 0.31);
    box-shadow: 0 17px 30px rgba(2, 9, 16, 0.42);
}
.geo-title{
    font-family: 'IBM Plex Serif', 'Merriweather', Georgia, serif;
    font-size: 1.2rem;
}
.geo-lead{
    line-height: 1.5;
}

.filter-summary{
    border: 1px solid rgba(166, 187, 208, 0.33);
    border-radius: 12px;
    background: rgba(13, 23, 35, 0.88);
    box-shadow: inset 0 0 0 1px rgba(150, 176, 202, 0.10);
}
.filter-summary-label{
    letter-spacing: 0.15em;
    color: rgba(188, 206, 227, 0.86);
}

.chip{
    border: 1px solid rgba(166, 187, 208, 0.32);
    background: rgba(76, 108, 140, 0.22);
}

.kpi-title{
    color: rgba(191, 208, 226, 0.86);
    font-size: 0.8rem;
    margin-bottom: 7px;
    letter-spacing: 0.02em;
}
.kpi-value{
    font-size: clamp(1.44rem, 2.1vw, 1.9rem);
    font-weight: 700;
    line-height: 1.16;
    color: var(--text);
}
.kpi-sub{
    color: rgba(186, 204, 224, 0.79);
    font-size: 0.85rem;
    margin-top: 5px;
    line-height: 1.36;
}

.insight-panel{
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
    margin-bottom: 0.9rem;
}
.insight-card{
    border: 1px solid rgba(168, 189, 211, 0.30);
    border-radius: 13px;
    padding: 12px 13px;
    background: linear-gradient(180deg, rgba(31, 48, 68, 0.62), rgba(15, 27, 41, 0.88));
}
.insight-kicker{
    font-size: 0.65rem;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 5px;
}
.insight-title{
    font-family: 'IBM Plex Serif', 'Merriweather', Georgia, serif;
    font-size: 1.05rem;
    margin-bottom: 0.35rem;
}
.insight-list{
    margin: 0.25rem 0 0 1rem;
    padding: 0;
}
.insight-list li{
    margin: 0.22rem 0;
    line-height: 1.45;
    color: var(--muted);
}
.mini-kpi-grid{
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
}
.mini-kpi{
    border: 1px solid rgba(165, 185, 206, 0.28);
    border-radius: 11px;
    padding: 8px 9px;
    background: rgba(17, 29, 44, 0.72);
}
.mini-kpi .label{
    font-size: 0.72rem;
    letter-spacing: 0.04em;
    color: var(--muted);
    margin-bottom: 3px;
}
.mini-kpi .value{
    font-size: 1.18rem;
    font-weight: 700;
    line-height: 1.12;
    margin-bottom: 2px;
}
.mini-kpi .sub{
    font-size: 0.77rem;
    color: rgba(187, 205, 224, 0.8);
    line-height: 1.3;
}

.app-note{
    border: 1px solid rgba(164, 185, 206, 0.34);
    border-radius: 11px;
    padding: 10px 12px;
    margin: 8px 0 10px 0;
    background: linear-gradient(180deg, rgba(29, 46, 66, 0.62), rgba(14, 24, 37, 0.88));
    color: rgba(198, 214, 233, 0.90);
    font-size: 0.9rem;
    line-height: 1.45;
}
.app-note strong{
    color: var(--text);
}

.handoff-card{
    border: 1px solid rgba(166, 187, 209, 0.34);
    border-radius: 12px;
    padding: 10px 12px 9px 12px;
    margin: 0.55rem 0 0.75rem 0;
    background: linear-gradient(180deg, rgba(32, 49, 69, 0.64), rgba(15, 27, 41, 0.89));
}
.handoff-kicker{
    font-size: 0.64rem;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 4px;
    font-weight: 700;
}
.handoff-title{
    font-size: 0.94rem;
    font-weight: 700;
    margin-bottom: 0.18rem;
}
.handoff-sub{
    color: var(--muted);
    font-size: 0.84rem;
    line-height: 1.4;
    margin-bottom: 0.25rem;
}

.map-legend{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(195px, 1fr));
    gap: 6px;
    margin: 0.4rem 0 0.65rem 0;
}
.map-legend-item{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    border: 1px solid rgba(158, 180, 203, 0.26);
    border-radius: 10px;
    padding: 5px 9px;
    background: rgba(15, 27, 41, 0.78);
    font-size: 0.82rem;
    transition: background 0.18s ease, border-color 0.18s ease;
}
.map-legend-item:hover{
    background: rgba(25, 42, 62, 0.88);
    border-color: rgba(158, 180, 203, 0.44);
}
.map-legend-left{
    display: flex;
    align-items: center;
    gap: 7px;
    min-width: 0;
}
.map-legend-left span{
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.map-legend-chip{
    width: 11px;
    height: 11px;
    border-radius: 50%;
    border: 1px solid rgba(255,255,255,0.26);
    flex-shrink: 0;
}
.map-toolbar-note{
    color: var(--muted);
    font-size: 0.86rem;
    margin: 0.2rem 0 0.42rem 0;
}
.map-tab-banner{
    position: relative;
    overflow: hidden;
    border: 1px solid rgba(255,255,255,0.14);
    border-radius: 16px;
    padding: 13px 16px 11px 16px;
    margin: 0.15rem 0 0.6rem 0;
    background: linear-gradient(135deg, rgba(30,144,255,0.16), rgba(0,224,184,0.08), rgba(10,22,34,0.92));
    box-shadow: 0 12px 24px rgba(0,0,0,0.22);
}
.map-tab-banner::before{
    content: "";
    position: absolute;
    top: 0; left: 0; width: 4px; height: 100%;
    background: linear-gradient(180deg, rgba(30,144,255,0.80), rgba(0,224,184,0.65));
    border-radius: 16px 0 0 16px;
}
.map-tab-banner::after{
    content: "";
    position: absolute;
    inset: 0;
    background-image:
        linear-gradient(transparent 19px, rgba(255,255,255,0.025) 20px),
        linear-gradient(90deg, transparent 19px, rgba(255,255,255,0.025) 20px);
    background-size: 24px 24px;
    opacity: 0.14;
    pointer-events: none;
}
.map-tab-banner > *{
    position: relative;
    z-index: 1;
}
.map-tab-title{
    font-size: 1.08rem;
    font-weight: 700;
    margin: 0;
    letter-spacing: -0.01em;
}
.map-tab-sub{
    color: var(--muted);
    margin-top: 0.2rem;
    line-height: 1.42;
    font-size: 0.86rem;
}
.map-tab-pill-row{
    margin-top: 0.52rem;
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
}
.map-tab-pill{
    display: inline-flex;
    align-items: center;
    border: 1px solid rgba(255,255,255,0.18);
    border-radius: 999px;
    padding: 3px 9px;
    font-size: 0.76rem;
    background: rgba(7,22,39,0.46);
    color: rgba(234,242,248,0.96);
}
.map-controls-shell{
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px;
    padding: 10px 12px 8px 12px;
    background: linear-gradient(180deg, rgba(255,255,255,0.06), rgba(255,255,255,0.02));
    box-shadow: 0 14px 26px rgba(0,0,0,0.22);
}
.map-workflow-card{
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 16px;
    padding: 10px 12px;
    background: linear-gradient(145deg, rgba(25, 63, 99, 0.52), rgba(13, 26, 38, 0.90));
}
.map-workflow-title{
    text-transform: uppercase;
    letter-spacing: 0.16em;
    font-size: 0.66rem;
    color: var(--muted);
    margin-bottom: 0.28rem;
}
.map-workflow-step{
    font-size: 0.88rem;
    margin: 0.18rem 0;
    color: rgba(232,241,249,0.96);
}
.map-workflow-step strong{
    color: var(--accent2);
}
.map-context-grid{
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 8px;
    margin-top: 0.4rem;
}
.map-context-card{
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 12px;
    padding: 8px 10px 8px 12px;
    background: rgba(7,22,39,0.54);
    position: relative;
    overflow: hidden;
}
.map-context-card::before{
    content: "";
    position: absolute;
    top: 0; left: 0; width: 3px; height: 100%;
    background: linear-gradient(180deg, rgba(30,144,255,0.65), rgba(0,224,184,0.50));
    border-radius: 12px 0 0 12px;
}
.map-context-label{
    text-transform: uppercase;
    letter-spacing: 0.14em;
    font-size: 0.58rem;
    color: var(--muted);
}
.map-context-value{
    margin-top: 2px;
    font-size: 0.88rem;
    font-weight: 600;
    color: rgba(242,248,252,0.96);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.map-stage-shell{
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 16px;
    padding: 11px 12px 10px 12px;
    background: linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.015));
    box-shadow: 0 12px 22px rgba(0,0,0,0.2);
    margin: 0.48rem 0 0.72rem 0;
}
.map-stage-title{
    margin: 0;
    font-size: 1rem;
    font-weight: 700;
}
.map-stage-sub{
    color: var(--muted);
    margin-top: 0.2rem;
    line-height: 1.42;
    font-size: 0.9rem;
}
.map-toolbar-strong{
    color: rgba(232,244,251,0.95);
    font-size: 0.87rem;
    margin: 0.2rem 0 0.45rem 0;
}
.map-side-stat-grid{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 8px;
}
.map-side-stat{
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 12px;
    background: rgba(13, 25, 39, 0.84);
    padding: 8px 10px;
}
.map-side-stat-label{
    text-transform: uppercase;
    letter-spacing: 0.14em;
    font-size: 0.62rem;
    color: var(--muted);
}
.map-side-stat-value{
    font-size: 1.02rem;
    font-weight: 700;
    margin-top: 2px;
}
.map-score-chip{
    display: inline-flex;
    align-items: center;
    border-radius: 999px;
    border: 1px solid rgba(255,255,255,0.18);
    padding: 3px 8px;
    font-size: 0.75rem;
    background: rgba(7,22,39,0.44);
    margin-right: 5px;
    margin-top: 4px;
}
.map-batch-rank-shell{
    position: relative;
    border: 1px solid rgba(0,224,184,0.22);
    border-radius: 14px;
    padding: 10px 12px 9px 14px;
    background: linear-gradient(135deg, rgba(0,224,184,0.06) 0%, rgba(11,22,34,0.82) 40%);
    overflow: hidden;
}
.map-batch-rank-shell::before{
    content:""; position:absolute; left:0; top:0; bottom:0; width:3px;
    background:linear-gradient(180deg, rgba(0,224,184,0.65), rgba(30,144,255,0.40));
    border-radius:14px 0 0 14px;
}
.map-flow-grid{
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
    margin: 0.5rem 0 0.65rem 0;
}
.map-flow-card{
    position: relative;
    border: 1px solid rgba(167, 188, 211, 0.22);
    border-radius: 14px;
    background: linear-gradient(180deg, rgba(30, 48, 68, 0.58), rgba(14, 26, 40, 0.90));
    padding: 11px 13px 10px 13px;
    transition: border-color 0.2s, box-shadow 0.2s, transform 0.15s;
    overflow: hidden;
}
.map-flow-card:hover{
    border-color: rgba(30,144,255,0.35);
    box-shadow: 0 4px 16px rgba(30,144,255,0.08);
    transform: translateY(-1px);
}
.map-flow-kicker{
    text-transform: uppercase;
    letter-spacing: 0.14em;
    font-size: 0.60rem;
    color: var(--muted);
    margin-bottom: 4px;
    display: flex;
    align-items: center;
}
.map-flow-title{
    font-size: 0.96rem;
    font-weight: 700;
    color: rgba(242,248,252,0.96);
}
.map-flow-sub{
    margin-top: 2px;
    color: rgba(193, 209, 227, 0.80);
    font-size: 0.80rem;
    line-height: 1.38;
}
.map-rail-title{
    text-transform: uppercase;
    letter-spacing: 0.15em;
    font-size: 0.64rem;
    color: var(--muted);
    margin: 0.2rem 0 0.42rem 0;
}
.map-control-stack{
    display: grid;
    gap: 0.68rem;
}
.map-inline-note{
    font-size: 0.82rem;
    color: rgba(190, 208, 226, 0.82);
    margin: 0.14rem 0 0.25rem 0;
    line-height: 1.38;
}
.map-insight-grid{
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 8px;
    margin: 0.35rem 0 0.55rem 0;
}
.map-insight{
    border: 1px solid rgba(165, 186, 208, 0.28);
    border-radius: 12px;
    padding: 8px 10px;
    background: rgba(15, 27, 41, 0.86);
}
.map-insight-label{
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.6rem;
    color: var(--muted);
}
.map-insight-value{
    margin-top: 3px;
    font-size: 1.06rem;
    font-weight: 700;
    line-height: 1.2;
}
.map-insight-sub{
    margin-top: 2px;
    font-size: 0.74rem;
    color: rgba(187, 204, 222, 0.78);
    line-height: 1.35;
}
.map-selected-shell{
    border: 1px solid rgba(170, 192, 215, 0.34);
    border-radius: 13px;
    padding: 9px 11px;
    background: linear-gradient(160deg, rgba(30, 144, 255, 0.16), rgba(0, 224, 184, 0.10), rgba(11, 22, 35, 0.90));
}
.map-selected-title{
    font-size: 0.86rem;
    font-weight: 700;
    margin-bottom: 2px;
}
.map-selected-sub{
    font-size: 0.8rem;
    color: rgba(193, 209, 227, 0.85);
    line-height: 1.38;
}
.map-score-chip.is-high{
    border-color: rgba(66, 210, 162, 0.42);
    background: rgba(22, 103, 80, 0.34);
}
.map-score-chip.is-medium{
    border-color: rgba(227, 192, 108, 0.42);
    background: rgba(102, 80, 32, 0.32);
}
.map-score-chip.is-low{
    border-color: rgba(206, 122, 122, 0.42);
    background: rgba(109, 48, 57, 0.30);
}
.map-score-chip.is-unknown{
    border-color: rgba(173, 192, 214, 0.30);
    background: rgba(32, 47, 67, 0.44);
}
.map-batch-head{
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 0.3rem;
}
.map-batch-head h4{
    margin: 0;
    font-size: 0.96rem;
    letter-spacing: -0.01em;
}
.map-batch-head .meta{
    color: var(--muted);
    font-size: 0.8rem;
}
/* batch status color indicators */
.map-batch-status-ok{
    display: inline-flex; align-items: center;
    padding: 2px 8px; border-radius: 999px; font-size: 0.72rem; font-weight: 600;
    background: rgba(22, 103, 80, 0.30); color: #42d2a2;
    border: 1px solid rgba(66, 210, 162, 0.35);
}
.map-batch-status-fail{
    display: inline-flex; align-items: center;
    padding: 2px 8px; border-radius: 999px; font-size: 0.72rem; font-weight: 600;
    background: rgba(109, 48, 57, 0.28); color: #ce7a7a;
    border: 1px solid rgba(206, 122, 122, 0.35);
}
.map-batch-status-warn{
    display: inline-flex; align-items: center;
    padding: 2px 8px; border-radius: 999px; font-size: 0.72rem; font-weight: 600;
    background: rgba(102, 80, 32, 0.28); color: #e3c06c;
    border: 1px solid rgba(227, 192, 108, 0.35);
}
.map-mission-shell{
    border: 1px solid rgba(171, 192, 214, 0.32);
    border-radius: 14px;
    padding: 10px 14px 10px 14px;
    margin: 0.4rem 0 0.5rem 0;
    background:
        linear-gradient(135deg, rgba(116, 147, 178, 0.16), rgba(19, 33, 48, 0.90) 62%),
        linear-gradient(180deg, rgba(24, 39, 57, 0.92), rgba(14, 25, 39, 0.90));
    box-shadow: 0 12px 22px rgba(2, 9, 16, 0.30);
    position: relative;
    overflow: hidden;
}
.map-mission-shell::before{
    content: "";
    position: absolute;
    top: 0; left: 0; width: 4px; height: 100%;
    background: linear-gradient(180deg, rgba(255, 200, 55, 0.80), rgba(255, 140, 40, 0.60));
    border-radius: 14px 0 0 14px;
}
.map-mission-title{
    text-transform: uppercase;
    letter-spacing: 0.14em;
    font-size: 0.62rem;
    color: rgba(194, 212, 230, 0.90);
    margin-bottom: 3px;
    font-weight: 700;
}
.map-mission-sub{
    color: rgba(211, 225, 239, 0.92);
    font-size: 0.85rem;
    line-height: 1.42;
}
/* evidence rating color coding */
.map-evidence-high{ color: #42d2a2; }
.map-evidence-moderate{ color: #e3c06c; }
.map-evidence-low{ color: #ce7a7a; }
.map-evidence-unknown{ color: rgba(173,192,214,0.82); }
.map-overview-shell{
    position: relative;
    border: 1px solid rgba(170, 191, 214, 0.28);
    border-radius: 14px;
    padding: 12px 14px;
    margin: 0.25rem 0 0.65rem 0;
    background:
        linear-gradient(145deg, rgba(116, 147, 178, 0.14), rgba(18, 31, 45, 0.92) 62%),
        linear-gradient(180deg, rgba(24, 39, 57, 0.92), rgba(14, 25, 39, 0.90));
    box-shadow: 0 14px 26px rgba(2, 9, 16, 0.32);
    overflow: hidden;
}
.map-overview-shell::before{
    content:""; position:absolute; left:0; top:0; bottom:0; width:3px;
    background:linear-gradient(180deg, rgba(30,144,255,0.55), rgba(0,224,184,0.35));
    border-radius:3px 0 0 3px;
}
.map-overview-title{
    text-transform: uppercase;
    letter-spacing: 0.14em;
    font-size: 0.66rem;
    color: rgba(194, 212, 230, 0.90);
    margin-bottom: 4px;
    font-weight: 700;
}
.map-overview-sub{
    color: rgba(214, 227, 240, 0.86);
    font-size: 0.82rem;
    line-height: 1.4;
    margin-bottom: 0.45rem;
}
.map-overview-grid{
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
}
.map-overview-card{
    position: relative;
    border: 1px solid rgba(167, 188, 210, 0.22);
    border-radius: 11px;
    padding: 8px 10px;
    background: rgba(11, 23, 36, 0.82);
    transition: border-color 0.2s, box-shadow 0.2s;
}
.map-overview-card:hover{
    border-color: rgba(30,144,255,0.35);
    box-shadow: 0 2px 8px rgba(30,144,255,0.08);
}
.map-overview-label{
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.56rem;
    color: rgba(188, 206, 224, 0.80);
}
.map-overview-value{
    margin-top: 3px;
    font-size: 1rem;
    font-weight: 700;
    color: var(--text);
    display: flex;
    align-items: baseline;
    gap: 6px;
}
.map-overview-subtext{
    margin-top: 2px;
    color: rgba(181, 199, 218, 0.72);
    font-size: 0.72rem;
    line-height: 1.32;
}
.map-overview-foot{
    margin-top: 0.48rem;
    color: rgba(201, 216, 233, 0.85);
    font-size: 0.76rem;
    line-height: 1.35;
    padding: 6px 8px;
    border-radius: 8px;
    background: rgba(255,193,7,0.06);
    border: 1px solid rgba(255,193,7,0.15);
}
.map-signal-grid{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
    margin: 0.5rem 0 0.75rem 0;
}
.map-signal{
    position: relative;
    border: 1px solid rgba(166, 188, 211, 0.22);
    border-radius: 14px;
    padding: 10px 12px 10px 12px;
    background: linear-gradient(135deg, rgba(13,24,37,0.92) 0%, rgba(18,30,45,0.88) 100%);
    transition: border-color 0.2s, box-shadow 0.2s, transform 0.15s;
    overflow: hidden;
}
.map-signal:hover{
    border-color: rgba(30,144,255,0.40);
    box-shadow: 0 2px 12px rgba(30,144,255,0.10);
    transform: translateY(-1px);
}
.map-signal-icon{
    font-size: 1.05rem;
    margin-bottom: 2px;
    line-height: 1;
}
.map-signal-label{
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.58rem;
    color: rgba(191, 208, 226, 0.82);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.map-signal-value{
    margin-top: 3px;
    font-size: 1.06rem;
    font-weight: 700;
    line-height: 1.22;
    color: var(--text);
    display: flex;
    align-items: baseline;
    gap: 6px;
    flex-wrap: wrap;
}
.map-signal-sub{
    margin-top: 2px;
    font-size: 0.72rem;
    color: rgba(184, 202, 221, 0.72);
    line-height: 1.34;
}
.map-brief-grid{
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 10px;
    margin: 0.35rem 0 0.55rem 0;
}
.map-brief-card{
    position: relative;
    border: 1px solid rgba(164, 186, 209, 0.22);
    border-radius: 12px;
    padding: 9px 11px;
    background: linear-gradient(180deg, rgba(28, 45, 65, 0.55), rgba(15, 27, 41, 0.88));
    transition: border-color 0.2s, box-shadow 0.2s;
    overflow: hidden;
}
.map-brief-card:hover{
    border-color: rgba(30,144,255,0.35);
    box-shadow: 0 2px 10px rgba(30,144,255,0.08);
}
.map-brief-label{
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.58rem;
    color: rgba(190, 208, 226, 0.80);
}
.map-brief-value{
    margin-top: 3px;
    font-size: 1.02rem;
    font-weight: 700;
    line-height: 1.2;
}
.map-brief-sub{
    margin-top: 2px;
    font-size: 0.72rem;
    color: rgba(183, 201, 220, 0.72);
    line-height: 1.33;
}
.map-lead-banner{
    border: 1px solid rgba(169, 191, 214, 0.32);
    border-radius: 11px;
    padding: 8px 12px 8px 14px;
    margin: 0.3rem 0 0.45rem 0;
    background: rgba(14, 27, 42, 0.88);
    font-size: 0.84rem;
    color: rgba(213, 226, 240, 0.92);
    position: relative;
    overflow: hidden;
}
.map-lead-banner::before{
    content: "";
    position: absolute;
    top: 0; left: 0; width: 3px; height: 100%;
    background: linear-gradient(180deg, rgba(66,210,162,0.75), rgba(30,144,255,0.60));
    border-radius: 11px 0 0 11px;
}

[data-testid="stTextInput"] input,
[data-testid="stTextInput"] textarea,
[data-testid="stSelectbox"] div[role="combobox"],
[data-testid="stMultiSelect"] div[role="combobox"]{
    border-radius: var(--radius-sm) !important;
    border: 1px solid rgba(162, 185, 209, 0.34) !important;
    background: rgba(15, 27, 41, 0.90) !important;
    color: var(--text) !important;
}
[data-testid="stTextInput"] input::placeholder{
    color: rgba(184, 201, 221, 0.74) !important;
}

button[kind="primary"],
button[kind="secondary"]{
    border-radius: 10px !important;
    border: 1px solid rgba(164, 185, 207, 0.30) !important;
}

.stTabs [data-baseweb="tab"]{
    border-radius: 10px;
    border-color: rgba(160, 182, 205, 0.26);
    background: linear-gradient(180deg, rgba(28, 44, 63, 0.72), rgba(14, 26, 40, 0.88));
    transition: background 0.2s ease, border-color 0.2s ease;
}
.stTabs [data-baseweb="tab"]:hover{
    border-color: rgba(160, 182, 205, 0.45);
    background: linear-gradient(180deg, rgba(38, 56, 78, 0.78), rgba(18, 30, 45, 0.90));
}
.stTabs [aria-selected="true"]{
    border-color: rgba(143, 174, 205, 0.75) !important;
    background: linear-gradient(180deg, rgba(58, 86, 115, 0.62), rgba(19, 33, 49, 0.92)) !important;
    box-shadow: 0 4px 12px rgba(30, 144, 255, 0.12) !important;
}

div[data-testid="stTextInput"]:has(input[aria-label="Nav search"]){
    top: calc(var(--nav-h) + 14px);
}
div[data-testid="stTextInput"]:has(input[aria-label="Nav search"]) input{
    border: 1px solid rgba(173, 194, 216, 0.44) !important;
    background: rgba(14, 24, 36, 0.97) !important;
}

@media (max-width: 950px){
    .insight-panel{
        grid-template-columns: 1fr;
    }
}
@media (max-width: 768px){
    .policy-title{
        font-size: 1.5rem;
    }
    .map-flow-grid{
        grid-template-columns: 1fr;
    }
    .map-insight-grid{
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .map-signal-grid{
        grid-template-columns: 1fr;
    }
    .map-brief-grid{
        grid-template-columns: 1fr;
    }
    .map-overview-grid{
        grid-template-columns: 1fr;
    }
    .policy-hero{
        padding: 16px 14px 14px 14px;
    }
    .policy-subtitle{
        font-size: 0.94rem;
    }
    .kpi-value{
        font-size: 1.3rem;
    }
    .workspace-link-help{
        min-height: 0;
    }
    .mini-kpi-grid{
        grid-template-columns: 1fr;
    }
}
</style>
""",
    unsafe_allow_html=True,
)

# =========================================================
# GLOBAL UX ENHANCEMENTS
# =========================================================
st.markdown(
    """
<style>
/* -- Data-table improvements -- */
[data-testid="stDataFrame"] table tbody tr:nth-child(even) td{
    background: rgba(255,255,255,0.025);
}
[data-testid="stDataFrame"] table tbody tr:hover td{
    background: rgba(30,144,255,0.08) !important;
    transition: background 120ms ease;
}
[data-testid="stDataFrame"] table thead th{
    position: sticky;
    top: 0;
    z-index: 2;
    background: rgba(15,27,42,0.97) !important;
    backdrop-filter: blur(6px);
    border-bottom: 2px solid rgba(160,185,210,0.22);
}

/* -- Smooth scroll behavior -- */
html{ scroll-behavior: smooth; }

/* -- Back-to-top floating button -- */
#tfl-back-to-top{
    position: fixed;
    bottom: 28px;
    right: 28px;
    z-index: 999;
    width: 42px;
    height: 42px;
    border-radius: 50%;
    border: 1px solid rgba(160,185,210,0.35);
    background: rgba(11,20,31,0.92);
    color: rgba(220,235,250,0.90);
    font-size: 18px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.3s ease, transform 0.3s ease, box-shadow 0.2s ease;
    box-shadow: 0 6px 18px rgba(0,0,0,0.28);
    backdrop-filter: blur(6px);
}
#tfl-back-to-top.visible{
    opacity: 1;
    pointer-events: auto;
}
#tfl-back-to-top:hover{
    border-color: rgba(134,167,198,0.65);
    box-shadow: 0 8px 22px rgba(0,0,0,0.35);
    transform: translateY(-2px);
}

/* -- Focus / keyboard accessibility -- */
button:focus-visible,
[data-testid="stSelectbox"] div[role="combobox"]:focus-visible,
[data-testid="stTextInput"] input:focus-visible{
    outline: 2px solid rgba(134,167,198,0.7);
    outline-offset: 2px;
}

/* -- Spinner quality of life -- */
[data-testid="stSpinner"] > div{
    animation: tfl-spinner-fade 0.35s ease both;
}
@keyframes tfl-spinner-fade{
    from{ opacity:0; transform:translateY(4px); }
    to{ opacity:1; transform:translateY(0); }
}

/* -- Toast notification -- */
.tfl-toast{
    position: fixed;
    bottom: 80px;
    right: 28px;
    z-index: 998;
    padding: 10px 18px;
    border-radius: 12px;
    border: 1px solid rgba(160,185,210,0.30);
    background: rgba(11,20,31,0.94);
    color: rgba(220,235,250,0.92);
    font-size: 0.88rem;
    font-family: 'IBM Plex Sans', system-ui, sans-serif;
    box-shadow: 0 8px 22px rgba(0,0,0,0.30);
    backdrop-filter: blur(6px);
    opacity: 0;
    pointer-events: none;
    transform: translateY(8px);
    transition: opacity 0.3s ease, transform 0.3s ease;
}
.tfl-toast.show{
    opacity: 1;
    pointer-events: auto;
    transform: translateY(0);
}

/* -- Print-friendly -- */
@media print{
    .custom-nav,
    #tfl-back-to-top,
    .tfl-toast,
    [data-testid="stSidebar"],
    [data-testid="stToolbar"],
    button[kind="primary"],
    button[kind="secondary"],
    [data-testid="stSpinner"]{ display: none !important; }

    html, body, [data-testid="stAppViewContainer"]{
        background: white !important;
        color: #1a1a1a !important;
    }
    .block-container{ padding-top: 0 !important; max-width: 100% !important; }
    h1, h2, h3{ color: #1a1a1a !important; }
    p, li, span, div{ color: #1a1a1a !important; }
    .card, div[data-testid="stPlotlyChart"]{
        box-shadow: none !important;
        border: 1px solid #ccc !important;
        background: white !important;
    }
    [data-testid="stDataFrame"]{ border-color: #ccc !important; }
    .kpi-title, .section-caption, .callout-title{ color: #555 !important; }
}
</style>

<!-- Back-to-top button -->
<button id="tfl-back-to-top" onclick="window.scrollTo({top:0, behavior:'smooth'})" title="Back to top">&#9650;</button>
<script>
(function(){
  const btn = document.getElementById('tfl-back-to-top');
  if (!btn) return;
  const container = window.parent.document.querySelector('[data-testid="stAppViewContainer"]') || window;
  const target = container.querySelector && container.querySelector('.main') || window;
  const checkScroll = () => {
    const scrollY = window.scrollY || document.documentElement.scrollTop || 0;
    btn.classList.toggle('visible', scrollY > 400);
  };
  window.addEventListener('scroll', checkScroll, {passive:true});
  checkScroll();
})();
</script>
""",
    unsafe_allow_html=True,
)


# =========================================================
# CRASH PROTECTION: Safe page wrapper
# =========================================================
def _safe_page(page_name: str):
    """Decorator that wraps page functions in try/except to prevent full app crashes."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except st.runtime.scriptrunner.StopException:
                raise  # Let Streamlit's st.stop() and st.switch_page() propagate
            except Exception as exc:
                logging.exception("Unhandled error in page %s", page_name)
                st.error(
                    f"An unexpected error occurred on the **{page_name}** page. "
                    f"Try refreshing the browser or clearing filters.\n\n"
                    f"Error details: `{type(exc).__name__}: {exc}`"
                )
                # Offer a reset button
                if st.button("Reset and reload", key=f"crash_reset_{page_name}"):
                    for key in list(st.session_state.keys()):
                        del st.session_state[key]
                    st.rerun()
        return wrapper
    return decorator


@_safe_page('About')
def _page_about():
    _run_page_renderer("src.pages.about")


@_safe_page('Media Briefings')
def _page_turn_off_tap():
    _run_page_renderer("src.pages.multimedia")


@_safe_page('Policy Context')
def _page_solutions():
    _run_page_renderer("src.pages.solutions")


@st.cache_data(show_spinner=False, ttl=300, max_entries=4)
def _build_category_chart_data(df: pd.DataFrame) -> pd.DataFrame:
    """Pre-compute expenditure-by-category data for 85th-89th TFL sessions (cached)."""
    cat_base = df.copy()
    cat_base["Session"] = cat_base["Session"].astype(str).str.strip()
    cat_base = ensure_cols(cat_base, {"Client": "", "Low_num": 0.0, "High_num": 0.0, "IsTFL": 0})
    cat_base["IsTFL"] = pd.to_numeric(cat_base["IsTFL"], errors="coerce").fillna(0)
    cat_base = cat_base[cat_base["IsTFL"] == 1]
    cat_base["SessionBase"] = _session_base_number_series(cat_base["Session"])
    cat_base = cat_base[cat_base["SessionBase"].between(85, 89)]
    cat_base = cat_base[cat_base["Client"].fillna("").astype(str).str.strip() != ""]
    if cat_base.empty:
        return pd.DataFrame(columns=["SessionBase", "Category", "Total", "SessionLabel"])
    cat_base["Category"] = cat_base["Client"].map(lambda x: match_entity_type(x)[1])
    cat_base["Low_num"] = pd.to_numeric(cat_base["Low_num"], errors="coerce").fillna(0)
    cat_base["High_num"] = pd.to_numeric(cat_base["High_num"], errors="coerce").fillna(0)
    cat_base["Mid"] = (cat_base["Low_num"] + cat_base["High_num"]) / 2
    cat_group = (
        cat_base.groupby(["SessionBase", "Category"], as_index=False)["Mid"]
        .sum()
        .rename(columns={"Mid": "Total"})
    )
    cat_group["SessionLabel"] = cat_group["SessionBase"].map(_session_base_label)
    return cat_group

@_safe_page('Clients')
def _page_client_lookup():
    _run_page_renderer("src.pages.clients")



def _page_member_lookup():
    _run_page_renderer("src.pages.legislators")



def _mp5_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in statute miles."""
    try:
        d_lat = math.radians(float(lat2) - float(lat1))
        d_lon = math.radians(float(lon2) - float(lon1))
        a = (
            math.sin(d_lat / 2) ** 2
            + math.cos(math.radians(float(lat1)))
            * math.cos(math.radians(float(lat2)))
            * (math.sin(d_lon / 2) ** 2)
        )
        return 3958.7613 * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))
    except Exception:
        return float("nan")


_MP5_METHOD_WEIGHTS: dict[str, float] = {
    "spatial boundary (code)": 1.00,
    "spatial boundary (name)": 0.94,
    "spatial boundary (fuzzy)": 0.78,
}


def _mp5_method_weight(method: str) -> float:
    m = str(method).strip().lower()
    w = _MP5_METHOD_WEIGHTS.get(m)
    if w is not None:
        return w
    if "name + geocode context" in m:
        return 0.62
    if "name anchored" in m:
        return 0.50
    return 0.66


_MP5_CONFIDENCE_WEIGHTS: dict[str, float] = {
    "high": 1.00,
    "medium": 0.72,
    "low": 0.46,
    "unknown": 0.28,
}


def _mp5_confidence_weight(conf: str) -> float:
    return _MP5_CONFIDENCE_WEIGHTS.get(str(conf).strip().lower(), 0.30)


def _mp5_priority_from_score(score: float) -> str:
    value = float(score or 0.0)
    if value >= 78:
        return "Tier 1"
    if value >= 58:
        return "Tier 2"
    return "Tier 3"


def _mp5_geocode_badge(score, floor: float) -> str:
    if score is None:
        return '<span class="mp5-badge mp5-badge-mid">Coordinate mode</span>'
    s = float(score)
    if s >= floor:
        return f'<span class="mp5-badge mp5-badge-high">Geocode {s:.0f}</span>'
    if s >= 70:
        return f'<span class="mp5-badge mp5-badge-mid">Geocode {s:.0f} \u2014 below floor</span>'
    return f'<span class="mp5-badge mp5-badge-low">Geocode {s:.0f} \u2014 weak</span>'


def _mp5_tier_html(tier: str) -> str:
    cls = {"Tier 1": "mp5-tier1", "Tier 2": "mp5-tier2"}.get(tier, "mp5-tier3")
    return f'<span class="{cls}">{html.escape(tier)}</span>'


# =========================================================
# PERFORMANCE: Cached helpers for map-address page
# =========================================================







def _build_filtered_atlas_bundle(
    subdivision_matches: pd.DataFrame,
    *,
    selected_types: list[str],
    min_match_count: int,
    query: str,
    sort_mode: str,
) -> dict[str, object]:
    filtered_cov = subdivision_matches.copy()
    if selected_types:
        filtered_cov = filtered_cov[
            filtered_cov["subdivision_type"].astype(str).isin(selected_types)
        ]
    else:
        filtered_cov = filtered_cov.iloc[0:0]
    filtered_cov = filtered_cov[
        pd.to_numeric(filtered_cov["match_count"], errors="coerce").fillna(0)
        >= int(min_match_count)
    ]

    query_norm = str(query).strip().lower()
    if query_norm:
        preview_col = filtered_cov.get(
            "match_clients_preview",
            pd.Series("", index=filtered_cov.index),
        ).fillna("").astype(str)
        filtered_cov = filtered_cov[
            filtered_cov["subdivision_name"].astype(str).str.lower().str.contains(query_norm, na=False)
            | preview_col.str.lower().str.contains(query_norm, na=False)
        ]

    _mc = pd.to_numeric(filtered_cov["match_count"], errors="coerce").fillna(0).clip(lower=0)
    filtered_cov["_signal"] = filtered_cov["high_total"] * (1 + _mc.map(math.log1p))
    if sort_mode == "Highest High":
        filtered_cov = filtered_cov.sort_values(["high_total", "match_count"], ascending=[False, False])
    elif sort_mode == "Most Matched Entities":
        filtered_cov = filtered_cov.sort_values(["match_count", "high_total"], ascending=[False, False])
    elif sort_mode == "Subdivision A-Z":
        filtered_cov = filtered_cov.sort_values(["subdivision_name", "subdivision_type"], ascending=[True, True])
    else:
        filtered_cov = filtered_cov.sort_values(["_signal", "high_total"], ascending=[False, False])

    cov_total_high_filtered = float(filtered_cov["high_total"].sum()) if not filtered_cov.empty else 0.0
    cov_total_low_filtered = float(filtered_cov["low_total"].sum()) if not filtered_cov.empty else 0.0
    cov_entity_count = 0
    if not filtered_cov.empty:
        cov_clients: set[str] = set()
        for vals in filtered_cov.get("match_clients", pd.Series(dtype=object)).tolist():
            if isinstance(vals, list):
                cov_clients.update({str(v).strip() for v in vals if str(v).strip()})
        cov_entity_count = len(cov_clients)
    cov_type_count = int(filtered_cov["subdivision_type"].astype(str).nunique()) if not filtered_cov.empty else 0
    cov_avg_match = float(pd.to_numeric(filtered_cov.get("match_count", 0), errors="coerce").fillna(0).mean()) if not filtered_cov.empty else 0.0
    cov_filter_pct = (len(filtered_cov) / len(subdivision_matches) * 100.0) if len(subdivision_matches) > 0 else 0.0
    return {
        "filtered_cov": filtered_cov,
        "cov_total_high_filtered": cov_total_high_filtered,
        "cov_total_low_filtered": cov_total_low_filtered,
        "cov_entity_count": cov_entity_count,
        "cov_type_count": cov_type_count,
        "cov_avg_match": cov_avg_match,
        "cov_filter_pct": cov_filter_pct,
    }


def _build_ranked_forensics_leads(filtered: pd.DataFrame) -> pd.DataFrame:
    if filtered.empty:
        return pd.DataFrame()
    leads = (
        filtered.groupby("TFL Entity", as_index=False).agg(
            EntityType=("Entity Type", lambda s: next((str(v).strip() for v in s if str(v).strip()), "")),
            Low=("Low", "sum"),
            High=("High", "sum"),
            Midpoint=("Mid", "sum"),
            OverlapRows=("TFL Entity", "size"),
            HighRows=("Match Confidence", lambda s: int((s.astype(str) == "High").sum())),
            BoundaryRows=("Boundary Match", lambda s: int(pd.Series(s).fillna(False).astype(bool).sum())),
            AvgDistance=("Distance Miles", "mean"),
            SignalScore=("Row Signal", "sum"),
        )
    )
    if leads.empty:
        return leads
    leads["HighShare"] = leads["HighRows"] / leads["OverlapRows"].replace(0, 1)
    leads["BoundaryShare"] = leads["BoundaryRows"] / leads["OverlapRows"].replace(0, 1)
    max_signal = float(leads["SignalScore"].max() or 0.0)
    leads["SignalNorm"] = (leads["SignalScore"] / max_signal * 100.0) if max_signal > 0 else 0.0
    lead_distance = leads["AvgDistance"].astype(float)
    leads["ProximityScore"] = (100.0 / (1.0 + (lead_distance.clip(lower=0.0) / 55.0))).fillna(44.0)
    leads["LeadScore"] = (
        leads["SignalNorm"] * 0.55
        + leads["HighShare"] * 100.0 * 0.2
        + leads["BoundaryShare"] * 100.0 * 0.15
        + leads["ProximityScore"] * 0.1
    )
    leads["Priority"] = leads["LeadScore"].map(_mp5_priority_from_score)
    return leads.sort_values(
        ["LeadScore", "SignalScore", "High"],
        ascending=[False, False, False],
    )


def _build_filtered_forensics_bundle(
    rows: pd.DataFrame,
    *,
    confidence_filters: list[str],
    method_filters: list[str],
    entity_query: str,
    min_high: float,
    dist_cap: float,
    focus_selected_subdivision: bool,
    selected_type: str,
    selected_name: str,
    focus_selected_clients: bool,
    selected_clients: list[str],
    sort_mode: str,
) -> dict[str, object]:
    filtered = rows.copy()
    if confidence_filters:
        filtered = filtered[
            filtered["Match Confidence"].astype(str).isin(confidence_filters)
        ]
    else:
        filtered = filtered.iloc[0:0]
    if method_filters:
        filtered = filtered[
            filtered["Match Method"].astype(str).isin(method_filters)
        ]
    else:
        filtered = filtered.iloc[0:0]

    entity_query_norm = str(entity_query).strip().lower()
    if entity_query_norm:
        filtered = filtered[
            filtered["TFL Entity"].astype(str).str.lower().str.contains(entity_query_norm, na=False)
        ]
    if float(min_high or 0.0) > 0:
        filtered = filtered[filtered["High"] >= float(min_high)]
    filtered = filtered[
        filtered["Distance Miles"].isna()
        | (pd.to_numeric(filtered["Distance Miles"], errors="coerce").fillna(float(dist_cap) + 1.0) <= float(dist_cap))
    ]
    if focus_selected_subdivision and str(selected_name).strip():
        filtered = filtered[
            (filtered["Subdivision Type"].astype(str) == str(selected_type))
            & (filtered["Subdivision"].astype(str) == str(selected_name))
        ]
    if focus_selected_clients and selected_clients:
        selected_client_set = {str(v).strip().lower() for v in selected_clients if str(v).strip()}
        filtered = filtered[
            filtered["TFL Entity"].astype(str).str.lower().isin(selected_client_set)
        ]

    if sort_mode == "Highest High":
        filtered = filtered.sort_values(["High", "Row Signal"], ascending=[False, False])
    elif sort_mode == "Closest Distance":
        filtered = filtered.sort_values(
            ["Distance Miles", "Row Signal"],
            ascending=[True, False],
            na_position="last",
        )
    elif sort_mode == "Entity A-Z":
        filtered = filtered.sort_values(["TFL Entity", "High"], ascending=[True, False])
    else:
        filtered = filtered.sort_values(["Row Signal", "High"], ascending=[False, False])
    return {
        "filtered": filtered,
        "leads": _build_ranked_forensics_leads(filtered),
    }


# =========================================================
# PERFORMANCE: Build the ~530-line mp5 CSS string once at
# module level instead of re-creating it on every Streamlit
# rerun when the map-address page renders.
# =========================================================
@functools.lru_cache(maxsize=1)
def _build_mp5_css() -> str:
    return """
<style>
/* -- mp5 shell ------------------------------------------- */
.mp5-glass{
  border:1px solid rgba(130,219,248,.22);
  border-radius:20px;
  padding:18px 20px 14px 20px;
  background:
    radial-gradient(960px 260px at 6% 0%,rgba(0,224,184,.12),transparent 66%),
    radial-gradient(840px 280px at 94% 8%,rgba(30,144,255,.14),transparent 60%),
    linear-gradient(138deg,rgba(7,26,41,.95),rgba(7,19,32,.93));
  box-shadow:0 16px 36px rgba(0,0,0,.28);
}
.mp5-glass-inner{
  border:1px solid rgba(255,255,255,.12);
  border-radius:16px;
  padding:14px 16px;
  background:
    linear-gradient(115deg,rgba(14,45,68,.86),rgba(9,26,41,.86)),
    radial-gradient(460px 180px at 88% 8%,rgba(245,166,68,.12),transparent 70%);
}
.mp5-kicker{
  text-transform:uppercase;
  letter-spacing:.12em;
  font-size:.68rem;
  font-weight:700;
  color:rgba(203,245,255,.88);
  margin-bottom:2px;
}
.mp5-title{
  font-size:1.08rem;
  font-weight:700;
  color:rgba(247,252,255,.97);
  margin-top:2px;
}
.mp5-sub{
  color:rgba(206,229,242,.82);
  font-size:.86rem;
  margin-top:4px;
  line-height:1.45;
}
/* -- metric grid ----------------------------------------- */
.mp5-metrics{
  display:grid;
  gap:10px;
  grid-template-columns:repeat(auto-fit,minmax(170px,1fr));
  margin-top:12px;
}
.mp5-card{
  border-radius:14px;
  border:1px solid rgba(255,255,255,.12);
  padding:11px 13px 9px 13px;
  background:rgba(255,255,255,.038);
  transition:border-color .18s,box-shadow .18s;
}
.mp5-card:hover{
  border-color:rgba(130,219,248,.38);
  box-shadow:0 0 14px rgba(130,219,248,.10);
}
.mp5-card-lbl{
  text-transform:uppercase;
  letter-spacing:.09em;
  font-size:.67rem;
  font-weight:600;
  color:rgba(180,216,235,.80);
}
.mp5-card-val{
  margin-top:3px;
  font-size:1.28rem;
  font-weight:800;
  color:rgba(247,253,255,.98);
  letter-spacing:-.01em;
}
.mp5-card-sub{
  margin-top:2px;
  font-size:.76rem;
  color:rgba(195,220,236,.78);
  line-height:1.35;
}
/* -- context anchor -------------------------------------- */
.mp5-anchor{
  border:1px solid rgba(255,255,255,.13);
  border-left:3px solid rgba(0,224,184,.82);
  border-radius:12px;
  padding:10px 13px;
  background:rgba(0,224,184,.045);
  margin-top:6px;
}
.mp5-anchor-empty{
  border:1px dashed rgba(255,255,255,.16);
  border-radius:12px;
  padding:10px 13px;
  background:rgba(255,255,255,.02);
  color:rgba(180,210,230,.70);
  font-size:.84rem;
  margin-top:6px;
}
/* -- badges ---------------------------------------------- */
.mp5-badge{
  display:inline-block;
  padding:3px 10px;
  border-radius:999px;
  font-size:.72rem;
  font-weight:700;
  letter-spacing:.02em;
}
.mp5-badge-high{
  border:1px solid rgba(143,235,197,.52);
  background:rgba(73,211,155,.14);
  color:rgba(220,255,240,.96);
}
.mp5-badge-mid{
  border:1px solid rgba(251,204,122,.52);
  background:rgba(255,190,76,.13);
  color:rgba(255,240,204,.96);
}
.mp5-badge-low{
  border:1px solid rgba(247,146,149,.52);
  background:rgba(247,85,97,.13);
  color:rgba(255,220,223,.96);
}
/* -- tier badges ----------------------------------------- */
.mp5-tier1{color:#6ee7b7;font-weight:700;}
.mp5-tier2{color:#fcd34d;font-weight:700;}
.mp5-tier3{color:#fca5a5;font-weight:700;}
/* -- section divider ------------------------------------- */
.mp5-divider{
  border:0;
  border-top:1px solid rgba(255,255,255,.08);
  margin:18px 0 14px 0;
}
/* -- narrative callout ----------------------------------- */
.mp5-narrative{
  border-left:3px solid rgba(100,180,255,.55);
  padding:8px 12px;
  background:rgba(100,180,255,.06);
  border-radius:0 10px 10px 0;
  font-size:.84rem;
  color:rgba(210,232,248,.90);
  line-height:1.5;
  margin:8px 0;
}
/* -- plotly chart container ------------------------------ */
.mp5-chart-wrap{
  border:1px solid rgba(255,255,255,.10);
  border-radius:14px;
  padding:8px;
  background:rgba(0,0,0,.12);
  margin-top:8px;
}

/* -- v6 ENHANCED DESIGN TOKENS --------------------------- */

/* -- animated gradient border cards ---------------------- */
.mp5-card{
  position:relative;
  overflow:hidden;
  transition:transform .22s ease,border-color .22s ease,box-shadow .22s ease;
}
.mp5-card::after{
  content:"";
  position:absolute;
  inset:0;
  border-radius:14px;
  background:linear-gradient(135deg,rgba(0,224,184,.06),transparent 40%,rgba(30,144,255,.06));
  opacity:0;
  transition:opacity .22s ease;
  pointer-events:none;
}
.mp5-card:hover{
  transform:translateY(-2px);
  border-color:rgba(130,219,248,.42);
  box-shadow:0 8px 24px rgba(0,224,184,.08),0 0 14px rgba(130,219,248,.10);
}
.mp5-card:hover::after{ opacity:1; }

/* -- progress / health bar ------------------------------- */
.mp5-health{
  margin:12px 0 8px 0;
}
.mp5-health-label{
  display:flex;
  justify-content:space-between;
  font-size:.72rem;
  color:rgba(195,220,236,.80);
  margin-bottom:4px;
  text-transform:uppercase;
  letter-spacing:.08em;
  font-weight:600;
}
.mp5-health-track{
  height:10px;
  border-radius:999px;
  background:rgba(255,255,255,.06);
  border:1px solid rgba(255,255,255,.08);
  overflow:hidden;
  position:relative;
}
.mp5-health-fill{
  height:100%;
  border-radius:999px;
  transition:width .6s ease;
  position:relative;
}
.mp5-health-fill.is-strong{
  background:linear-gradient(90deg,#10b981,#6ee7b7);
}
.mp5-health-fill.is-moderate{
  background:linear-gradient(90deg,#f59e0b,#fcd34d);
}
.mp5-health-fill.is-weak{
  background:linear-gradient(90deg,#ef4444,#fca5a5);
}

/* -- quick preset buttons -------------------------------- */
.mp5-preset-row{
  display:flex;
  flex-wrap:wrap;
  gap:6px;
  margin:8px 0 4px 0;
}
.mp5-preset-btn{
  display:inline-flex;
  align-items:center;
  gap:5px;
  padding:5px 12px;
  border-radius:999px;
  border:1px solid rgba(255,255,255,.16);
  background:rgba(255,255,255,.04);
  color:rgba(220,238,252,.92);
  font-size:.73rem;
  font-weight:600;
  cursor:pointer;
  transition:all .18s ease;
  text-decoration:none;
}
.mp5-preset-btn:hover{
  border-color:rgba(130,219,248,.5);
  background:rgba(130,219,248,.12);
  box-shadow:0 0 10px rgba(130,219,248,.12);
}
.mp5-preset-btn.is-active{
  border-color:rgba(0,224,184,.6);
  background:rgba(0,224,184,.14);
  color:#6ee7b7;
}

/* -- evidence quality meter ------------------------------ */
.mp5-meter{
  display:flex;
  align-items:center;
  gap:12px;
  padding:10px 14px;
  border-radius:14px;
  border:1px solid rgba(255,255,255,.12);
  background:rgba(255,255,255,.03);
  margin:8px 0;
}
.mp5-meter-gauge{
  position:relative;
  width:56px;
  height:56px;
  flex:0 0 56px;
}
.mp5-meter-gauge svg{
  width:100%;
  height:100%;
  transform:rotate(-90deg);
}
.mp5-meter-gauge .track{
  fill:none;
  stroke:rgba(255,255,255,.08);
  stroke-width:5;
}
.mp5-meter-gauge .fill{
  fill:none;
  stroke-width:5;
  stroke-linecap:round;
  transition:stroke-dashoffset .8s ease;
}
.mp5-meter-body{
  flex:1;
}
.mp5-meter-title{
  font-size:.86rem;
  font-weight:700;
  color:rgba(247,252,255,.96);
}
.mp5-meter-sub{
  font-size:.76rem;
  color:rgba(195,220,236,.78);
  margin-top:2px;
  line-height:1.38;
}

/* -- status tags for case docket ------------------------- */
.mp5-status{
  display:inline-flex;
  align-items:center;
  gap:4px;
  padding:3px 10px;
  border-radius:999px;
  font-size:.68rem;
  font-weight:700;
  letter-spacing:.03em;
}
.mp5-status-new{
  border:1px solid rgba(130,219,248,.45);
  background:rgba(130,219,248,.12);
  color:rgba(180,240,255,.96);
}
.mp5-status-investigating{
  border:1px solid rgba(251,204,122,.45);
  background:rgba(255,190,76,.11);
  color:rgba(255,240,204,.96);
}
.mp5-status-resolved{
  border:1px solid rgba(143,235,197,.45);
  background:rgba(73,211,155,.12);
  color:rgba(220,255,240,.96);
}

/* -- section hero banner --------------------------------- */
.mp5-section-hero{
  position:relative;
  overflow:hidden;
  border:1px solid rgba(130,219,248,.22);
  border-radius:16px;
  padding:14px 18px 12px 18px;
  margin-bottom:12px;
  background:
    linear-gradient(135deg,rgba(0,224,184,.08),transparent 45%,rgba(30,144,255,.10)),
    linear-gradient(180deg,rgba(14,30,48,.96),rgba(9,22,36,.92));
}
.mp5-section-hero::before{
  content:"";
  position:absolute;
  top:-20px;right:-20px;
  width:160px;height:160px;
  background:radial-gradient(circle,rgba(30,144,255,.2),transparent 70%);
  pointer-events:none;
}
.mp5-section-hero > *{ position:relative; z-index:1; }
.mp5-section-num{
  display:inline-flex;
  align-items:center;
  justify-content:center;
  width:26px;height:26px;
  border-radius:8px;
  background:rgba(0,224,184,.16);
  border:1px solid rgba(0,224,184,.35);
  color:#6ee7b7;
  font-size:.74rem;
  font-weight:800;
  margin-bottom:6px;
}

/* -- gap alert card -------------------------------------- */
.mp5-gap-alert{
  display:flex;
  align-items:flex-start;
  gap:10px;
  padding:10px 12px;
  border-radius:12px;
  border:1px solid rgba(247,146,149,.3);
  background:rgba(247,85,97,.06);
  margin-top:8px;
}
.mp5-gap-icon{
  flex:0 0 auto;
  width:28px;height:28px;
  border-radius:8px;
  background:rgba(247,85,97,.14);
  border:1px solid rgba(247,146,149,.3);
  display:flex;align-items:center;justify-content:center;
  color:#fca5a5;
  font-size:.86rem;
  font-weight:800;
}
.mp5-gap-body{
  flex:1;
}
.mp5-gap-title{
  font-size:.82rem;
  font-weight:700;
  color:rgba(255,220,223,.96);
}
.mp5-gap-sub{
  font-size:.74rem;
  color:rgba(247,186,189,.80);
  line-height:1.38;
  margin-top:2px;
}

/* -- info/action strip ----------------------------------- */
.mp5-action-strip{
  display:flex;
  flex-wrap:wrap;
  align-items:center;
  gap:8px;
  padding:8px 12px;
  border-radius:12px;
  border:1px solid rgba(255,255,255,.10);
  background:rgba(255,255,255,.025);
  margin:8px 0;
}
.mp5-action-label{
  font-size:.72rem;
  text-transform:uppercase;
  letter-spacing:.1em;
  font-weight:600;
  color:rgba(180,216,235,.72);
}

/* -- summary snapshot card ------------------------------- */
.mp5-snapshot{
  border:1px solid rgba(130,219,248,.24);
  border-radius:16px;
  padding:14px 16px;
  background:
    linear-gradient(145deg,rgba(14,45,68,.80),rgba(9,22,36,.90)),
    radial-gradient(380px 160px at 85% 10%,rgba(0,224,184,.10),transparent 65%);
  margin:10px 0;
}
.mp5-snapshot-head{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:10px;
  margin-bottom:8px;
}
.mp5-snapshot-grid{
  display:grid;
  grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
  gap:8px;
}
.mp5-snapshot-item{
  padding:6px 8px;
  border-radius:10px;
  background:rgba(255,255,255,.04);
  border:1px solid rgba(255,255,255,.08);
}
.mp5-snapshot-item-lbl{
  font-size:.6rem;
  text-transform:uppercase;
  letter-spacing:.1em;
  font-weight:600;
  color:rgba(180,216,235,.74);
}
.mp5-snapshot-item-val{
  font-size:.94rem;
  font-weight:700;
  color:rgba(247,253,255,.96);
  margin-top:1px;
}

/* -- cross-tab navigation strips ------------------------ */
.mp5-crosslink{
  display:flex;
  flex-wrap:wrap;
  align-items:center;
  gap:10px;
  padding:10px 14px;
  border-radius:14px;
  border:1px solid rgba(30,144,255,.18);
  background:linear-gradient(135deg,rgba(30,144,255,.08),rgba(0,224,184,.06));
  margin:10px 0;
  backdrop-filter:blur(2px);
}
.mp5-crosslink-title{
  font-size:.7rem;
  text-transform:uppercase;
  letter-spacing:.12em;
  font-weight:700;
  color:rgba(30,144,255,.82);
  flex-shrink:0;
}
.mp5-crosslink-sep{
  width:1px;
  height:18px;
  background:rgba(255,255,255,.12);
  flex-shrink:0;
}
.mp5-crosslink-hint{
  font-size:.72rem;
  color:rgba(210,230,245,.52);
  margin-left:auto;
}
.mp5-context-strip{
  display:flex;
  flex-wrap:wrap;
  align-items:center;
  gap:8px;
  padding:8px 12px;
  border-radius:12px;
  border:1px solid rgba(0,224,184,.18);
  background:linear-gradient(135deg,rgba(0,224,184,.06),rgba(30,144,255,.04));
  margin:4px 0 10px 0;
}
.mp5-context-badge{
  display:inline-flex;
  align-items:center;
  gap:4px;
  padding:3px 10px;
  border-radius:8px;
  font-size:.7rem;
  font-weight:600;
  background:rgba(0,224,184,.12);
  border:1px solid rgba(0,224,184,.22);
  color:rgba(210,240,230,.88);
}
.mp5-context-badge.docket{
  background:rgba(30,144,255,.12);
  border-color:rgba(30,144,255,.22);
  color:rgba(200,225,255,.88);
}
.mp5-context-badge.empty{
  background:rgba(255,255,255,.04);
  border-color:rgba(255,255,255,.10);
  color:rgba(210,230,245,.45);
}

/* -- responsive refinements ------------------------------ */
@media (max-width:768px){
  .mp5-metrics{ grid-template-columns:repeat(2,minmax(0,1fr)); }
  .mp5-preset-row{ gap:4px; }
  .mp5-preset-btn{ font-size:.66rem; padding:4px 8px; }
  .mp5-meter{ flex-direction:column; text-align:center; }
  .mp5-snapshot-grid{ grid-template-columns:1fr 1fr; }
  .mp5-crosslink{ flex-direction:column; align-items:flex-start; }
}
</style>
"""


@_safe_page('Map & Address Full')
def _page_map_address_full_pass():
    _run_page_renderer("src.pages.map_address")



@_safe_page("Map & Address Rebuild")
def _page_map_address_rebuild():
    # Route to the full redesign workspace implementation.
    _page_map_address_full_pass()


@_safe_page("Lobbyists")
def _page_lobby_lookup():
    _run_page_renderer("src.pages.lobbyists")

_about_page = st.Page(_page_about, title="Start Here", url_path="about", default=True)
_lobby_page = st.Page(_page_lobby_lookup, title="Lobbyists", url_path="lobbyists")
_client_page = st.Page(_page_client_lookup, title="Clients", url_path="clients")
_map_page = st.Page(_page_map_address_rebuild, title="Map & Address", url_path="map-address")
_member_page = st.Page(_page_member_lookup, title="Legislators", url_path="legislators")
_solutions_page = st.Page(_page_solutions, title="Policy Context", url_path="solutions")
_tap_page = st.Page(_page_turn_off_tap, title="Media Briefings", url_path="multimedia")
_pages = [
    _about_page,
    _lobby_page,
    _client_page,
    _map_page,
    _member_page,
    _solutions_page,
    _tap_page,
]
_active_page = st.navigation(_pages, position="hidden")

def _nav_href(page) -> str:
    url_path = page.url_path
    return "./" if url_path == "" else f"./{url_path}"

def _journey_steps() -> list[tuple[str, str, str, object]]:
    return []

def _render_page_intro(kicker: str, title: str, subtitle: str, pills: list[str] | None = None) -> None:
    kicker_safe = html.escape(kicker or "", quote=True)
    title_safe = html.escape(title or "", quote=True)
    subtitle_safe = html.escape(subtitle or "", quote=True)
    pill_html = ""
    if pills:
        tokens = [f'<span class="policy-pill">{html.escape(str(p), quote=True)}</span>' for p in pills if str(p).strip()]
        if tokens:
            pill_html = f'<div class="policy-pill-list">{"".join(tokens)}</div>'
    st.markdown(
        f"""
<div class="card policy-hero">
  <div class="policy-kicker">{kicker_safe}</div>
  <div class="policy-title">{title_safe}</div>
  <p class="policy-subtitle">{subtitle_safe}</p>
  {pill_html}
</div>
""",
        unsafe_allow_html=True,
    )

def _is_guided_mode() -> bool:
    return False

def _render_journey(current_key: str) -> None:
    return

def _render_workspace_guide(
    question: str,
    steps: list[str] | None = None,
    method_note: str | None = None,
) -> None:
    return

def _render_quickstart(
    page_key: str,
    steps: list[str],
    note: str | None = None,
) -> None:
    return

def _render_evidence_guardrails(
    can_answer: list[str] | None = None,
    cannot_answer: list[str] | None = None,
    next_checks: list[str] | None = None,
) -> None:
    return

def _render_workspace_links(
    key_prefix: str,
    actions: list[tuple[str, object, str]],
) -> None:
    valid_actions = [
        (label, page, help_text)
        for label, page, help_text in actions
        if str(label).strip()
    ]
    if not valid_actions:
        return
    st.markdown('<div class="workspace-links-heading">Continue The Investigation</div>', unsafe_allow_html=True)
    cols = st.columns(len(valid_actions))
    for idx, (label, page, help_text) in enumerate(valid_actions):
        with cols[idx]:
            if st.button(
                label,
                key=f"{key_prefix}_nav_{idx}",
                width="stretch",
                help=help_text,
            ):
                st.switch_page(page)
            if help_text:
                st.markdown(
                    f'<div class="workspace-link-help">{html.escape(help_text, quote=True)}</div>',
                    unsafe_allow_html=True,
                )

_nav_items = [
    (_about_page, "Start Here"),
    (_lobby_page, "Lobbyists"),
    (_client_page, "Clients"),
    (_map_page, "Map & Address"),
    (_member_page, "Legislators"),
    (_solutions_page, "Policy"),
    (_tap_page, "Media"),
]
_nav_links = []
for page, label in _nav_items:
    active = " active" if page == _active_page else ""
    _nav_links.append(
        f'<a class="nav-link{active}" href="{_nav_href(page)}" target="_self">{label}</a>'
    )

st.markdown(
    f"""
<div class="custom-nav">
  <div class="nav-inner">
    <div class="brand">
      <div class="brand-top">Texas Taxpayer Protection</div>
      <div class="brand-bottom">Lobbying Transparency Center</div>
    </div>
    <div class="nav-links">
      {''.join(_nav_links)}
    </div>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

if "nav_search_query" not in st.session_state:
    st.session_state.nav_search_query = ""
if "nav_search_last" not in st.session_state:
    st.session_state.nav_search_last = ""
if "nav_search_trigger" not in st.session_state:
    st.session_state.nav_search_trigger = False
def _nav_submit() -> None:
    st.session_state.nav_search_trigger = True

nav_query_raw = st.text_input(
    "Nav search",
    key="nav_search_query",
    placeholder="Global search: lobbyist, client, legislator, or bill (example: HB 4)",
    label_visibility="collapsed",
    on_change=_nav_submit,
    help="Routes to the best workspace and carries your query forward.",
)
nav_query = nav_query_raw.strip()
nav_search_submitted = False
if nav_query and st.session_state.nav_search_trigger:
    nav_search_submitted = True
    st.session_state.nav_search_last = nav_query
    st.session_state.nav_search_trigger = False
elif not nav_query:
    st.session_state.nav_search_trigger = False
nav_suggest_slot = st.empty()
nav_skip_submit = False

# =========================================================
# HELPERS
# =========================================================
_RE_NONWORD = re.compile(r"[^\w]+", flags=re.UNICODE)
_TITLE_WORDS = {"MR", "MRS", "MS", "MISS", "DR", "HON", "JR", "SR", "II", "III", "IV"}
_RE_TITLE_WORDS = re.compile(r"\b(" + "|".join(_TITLE_WORDS) + r")\b\.?", re.IGNORECASE)
_NICKNAME_MAP = {
    "CHUCK": {"CHARLES"},
    "CHARLIE": {"CHARLES"},
    "CHARLES": {"CHUCK", "CHARLIE"},
}

def norm_name(x) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return ""
    s = str(x).replace("\u00A0", " ").strip().upper()
    return _RE_NONWORD.sub("", s)

def norm_name_series(s: pd.Series) -> pd.Series:
    return (
        s.fillna("")
         .astype(str)
         .str.replace("\u00A0", " ", regex=False)
         .str.strip()
         .str.upper()
         .str.replace(_RE_NONWORD, "", regex=True)
    )

def clean_filer_name_series(s: pd.Series) -> pd.Series:
    s = s.fillna("").astype(str)
    s = s.str.replace(_RE_PARENS, "", regex=True)
    s = s.str.replace(_RE_TITLE_WORDS, "", regex=True)
    s = s.str.replace(_RE_WHITESPACE, " ", regex=True).str.strip()
    return s

def clean_person_name(name: str) -> str:
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return ""
    s = str(name).replace("\u00A0", " ").strip()
    if not s:
        return ""
    s = _RE_PARENS.sub("", s)
    s = _RE_TITLE_WORDS.sub("", s)
    s = _RE_WHITESPACE.sub(" ", s).strip()
    return s

# PERFORMANCE: shared urllib3 connection pool — keeps TCP connections alive
# across the ~10-layer parallel ArcGIS queries instead of opening a new
# socket for every single request.
try:
    import urllib3 as _urllib3
    _ARCGIS_HTTP = _urllib3.PoolManager(
        num_pools=16, maxsize=12, retries=False,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=_urllib3.Timeout(connect=10, read=30),
    )
except ImportError:
    _ARCGIS_HTTP = None  # type: ignore[assignment]

def _arcgis_get_json(url: str, params: dict | None = None, timeout: int = 30, _retries: int = 3) -> dict:
    target = url
    if params:
        target = f"{url}?{urllib.parse.urlencode(params)}"
    last_exc: Exception | None = None
    for attempt in range(_retries):
        try:
            if _ARCGIS_HTTP is not None:
                resp = _ARCGIS_HTTP.request(
                    "GET", target,
                    timeout=_urllib3.Timeout(connect=10, read=timeout),
                )
                return json.loads(resp.data.decode("utf-8"))
            else:
                req = urllib.request.Request(target, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            last_exc = exc
            if attempt < _retries - 1:
                time.sleep(min(2 ** attempt, 4))
    logging.warning("ArcGIS request failed after %d attempts: %s — %s", _retries, target[:120], last_exc)
    raise last_exc  # type: ignore[misc]

def _canonical_school_district_name(value: str) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    s = str(value).upper().replace("&", " AND ").replace("/", " ")
    s = re.sub(r"\bC\.?I\.?S\.?D\.?\b", " CONSOLIDATED INDEPENDENT SCHOOL DISTRICT ", s)
    s = re.sub(r"\bI\.?S\.?D\.?\b", " INDEPENDENT SCHOOL DISTRICT ", s)
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _looks_like_school_district_name(value: str) -> bool:
    s = _canonical_school_district_name(value)
    return bool(s) and ("SCHOOL DISTRICT" in s)

@functools.lru_cache(maxsize=2048)
def _school_district_root_key(value: str) -> str:
    s = _canonical_school_district_name(value)
    if not s:
        return ""
    s = re.sub(r"\bTHE\b", " ", s)
    s = re.sub(r"\b(CONSOLIDATED\s+)?INDEPENDENT\s+SCHOOL\s+DISTRICT\b", " ", s)
    s = re.sub(r"\bSCHOOL\s+DISTRICT\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return norm_name(s)

def _canonical_county_name(value: str) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    s = str(value).upper().replace("&", " AND ").replace("/", " ")
    s = re.sub(r"\bCTY\.?\b", " COUNTY ", s)
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _looks_like_county_name(value: str) -> bool:
    s = _canonical_county_name(value)
    return bool(s) and ("COUNTY" in s)

@functools.lru_cache(maxsize=512)
def _county_root_key(value: str) -> str:
    s = _canonical_county_name(value)
    if not s:
        return ""
    s = re.sub(r"\bTHE\b", " ", s)
    s = re.sub(r"\bCOUNTY OF\b", " ", s)
    s = re.sub(r"\bCOMMISSIONERS? COURT\b", " ", s)
    s = re.sub(r"\bCOUNTY\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return norm_name(s)

def _canonical_city_name(value: str) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    s = str(value).upper().replace("&", " AND ").replace("/", " ")
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

@functools.lru_cache(maxsize=4096)
def _canonical_subdivision_text(value: str) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    s = str(value).upper().replace("&", " AND ").replace("/", " ")
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
        s = re.sub(pattern, replacement, s)
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _subdivision_root_from_patterns(value: str, remove_patterns: list[str]) -> str:
    s = _canonical_subdivision_text(value)
    if not s:
        return ""
    s = re.sub(r"\bTHE\b", " ", s)
    for pattern in remove_patterns:
        s = re.sub(pattern, " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return norm_name(s)

@functools.lru_cache(maxsize=2048)
def classify_requested_entity_type(value: str) -> str:
    s = _canonical_subdivision_text(value)
    if not s:
        return ""
    if re.search(r"\b(JUNIOR|COMMUNITY)\s+COLLEGE\b|\bCOLLEGE\s+DISTRICT\b", s):
        return "Junior College District"
    if "HOSPITAL DISTRICT" in s:
        return "Hospital District"
    if "MUNICIPAL UTILITY DISTRICT" in s:
        return "Municipal Utility District"
    if "EMERGENCY SERVICES DISTRICT" in s:
        return "Emergency Services District"
    if "GROUNDWATER CONSERVATION DISTRICT" in s:
        return "Groundwater Conservation District"
    if re.search(r"\bLOCAL\s+GOVERNMENT\s+CORPORATION\b|\bDEVELOPMENT\s+CORPORATION\b", s):
        return "Local Government Corporation"
    if "DRAINAGE DISTRICT" in s:
        return "Drainage District"
    if "FRESH WATER SUPPLY DISTRICT" in s:
        return "Fresh Water Supply District"
    if "IRRIGATION DISTRICT" in s:
        return "Irrigation District"
    if "LEVEE IMPROVEMENT DISTRICT" in s:
        return "Levee Improvement District"
    if "MUNICIPAL MANAGEMENT DISTRICT" in s:
        return "Municipal Management District"
    if "REGIONAL DISTRICT" in s:
        return "Regional District"
    if "RIVER AUTHORITY" in s:
        return "River Authority"
    if re.search(r"\bSOIL\s+(AND\s+)?WATER\s+CONTROL\s+DISTRICT\b", s):
        return "Soil & Water Control District"
    if "SPECIAL UTILITY DISTRICT" in s:
        return "Special Utility District"
    if "WATER IMPROVEMENT DISTRICT" in s:
        return "Water Improvement District"
    if "REGIONAL MOBILITY AUTHORITY" in s:
        return "Regional Mobility Authority"
    if re.search(r"\bWATER\s+CONTROL\s+(AND\s+)?IMPROVEMENT\s+DISTRICT\b", s):
        return "Water Control & Improvement District"
    if "NAVIGATION DISTRICT" in s:
        return "Navigation District"
    if (
        "TRANSIT AUTHORITY" in s
        or "METROPOLITAN TRANSIT AUTHORITY" in s
        or "TRANSPORTATION AUTHORITY" in s
        or re.search(r"\bAREA\s+RAPID\s+TRANSIT\b|\bRAPID\s+TRANSIT\b|\bMASS\s+TRANSIT\b|\bDART\b", s)
        or re.search(r"\bTRANSIT\b", s)
    ):
        return "Transit Authority"
    if "PORT AUTHORITY" in s:
        return "Port Authority"
    if "HOUSING AUTHORITY" in s:
        return "Housing Authority"
    if "APPRAISAL DISTRICT" in s:
        return "Appraisal District"
    return ""

@functools.lru_cache(maxsize=512)
def _canonical_water_district_type(value: str) -> str:
    s = _canonical_subdivision_text(value)
    if not s:
        return ""
    if "MUNICIPAL UTILITY DISTRICT" in s:
        return "Municipal Utility District"
    if "DRAINAGE DISTRICT" in s:
        return "Drainage District"
    if "FRESH WATER SUPPLY DISTRICT" in s:
        return "Fresh Water Supply District"
    if "IRRIGATION DISTRICT" in s:
        return "Irrigation District"
    if "LEVEE IMPROVEMENT DISTRICT" in s:
        return "Levee Improvement District"
    if "MUNICIPAL MANAGEMENT DISTRICT" in s:
        return "Municipal Management District"
    if "REGIONAL DISTRICT" in s:
        return "Regional District"
    if "RIVER AUTHORITY" in s:
        return "River Authority"
    if re.search(r"\bSOIL\s+(AND\s+)?WATER\s+CONTROL\s+DISTRICT\b", s):
        return "Soil & Water Control District"
    if "SPECIAL UTILITY DISTRICT" in s:
        return "Special Utility District"
    if "WATER IMPROVEMENT DISTRICT" in s:
        return "Water Improvement District"
    if re.search(r"\bWATER\s+CONTROL\s+(AND\s+)?IMPROVEMENT\s+DISTRICT\b", s):
        return "Water Control & Improvement District"
    if "NAVIGATION DISTRICT" in s:
        return "Navigation District"
    return ""

def _looks_like_city_name(value: str) -> bool:
    s = _canonical_city_name(value)
    return bool(s) and bool(re.search(r"\b(CITY|TOWN|VILLAGE)\b", s))

def _looks_like_entity_type(value: str, entity_type: str) -> bool:
    return classify_requested_entity_type(value) == str(entity_type).strip()

@functools.lru_cache(maxsize=2048)
def _city_root_key(value: str) -> str:
    s = _canonical_city_name(value)
    if not s:
        return ""
    s = re.sub(r"\bTHE\b", " ", s)
    s = re.sub(r"\b(CITY|TOWN|VILLAGE)\s+OF\b", " ", s)
    s = re.sub(r"\b(CITY|TOWN|VILLAGE)\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return norm_name(s)

def _special_entity_root_patterns(entity_type: str) -> list[str]:
    et = str(entity_type).strip()
    if et == "Hospital District":
        return [r"\bHOSPITAL\s+DISTRICT\b", r"\bDISTRICT\b"]
    if et == "Emergency Services District":
        return [r"\bEMERGENCY\s+SERVICES\s+DISTRICT\b", r"\bDISTRICT\b", r"\bE\.?S\.?D\.?\b"]
    if et == "Appraisal District":
        return [r"\bAPPRAISAL\s+DISTRICT\b", r"\bDISTRICT\b", r"\bC\.?A\.?D\.?\b"]
    if et == "Local Government Corporation":
        return [r"\bLOCAL\s+GOVERNMENT\s+CORPORATION\b", r"\bDEVELOPMENT\s+CORPORATION\b", r"\bCORPORATION\b"]
    if et == "Transit Authority":
        return TRANSIT_AUTHORITY_ROOT_PATTERNS
    if et == "Port Authority":
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

    no_geo_terms = re.sub(r"(COUNTY|CITY|TOWN|VILLAGE|OF)", "", no_digits)
    no_geo_terms = no_geo_terms.strip()
    if no_geo_terms:
        variants.add(no_geo_terms)
    return {v for v in variants if v}

def _best_lookup_key_for_candidates(
    lookup_keys: tuple[str, ...],
    candidates: set[str],
) -> tuple[str, float]:
    if not lookup_keys or not candidates:
        return "", -1.0

    best_key = ""
    best_score = -1.0
    for candidate in candidates:
        c = str(candidate).strip()
        if not c:
            continue
        for key in lookup_keys:
            k = str(key).strip()
            if not k:
                continue
            score = -1.0
            if c == k:
                score = 1000.0 + float(len(k))
            elif len(c) >= 4 and len(k) >= 4 and (c in k or k in c):
                score = float(min(len(c), len(k)))
            if score > best_score:
                best_score = score
                best_key = k
    return best_key, best_score

def _resolve_special_anchor_keys(
    client_name: str,
    entity_type: str,
    county_lookup_keys: tuple[str, ...],
    city_lookup_keys: tuple[str, ...],
) -> dict:
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

def _match_preview(values: list[str], limit: int = 6) -> str:
    if not values:
        return ""
    preview = ", ".join(values[:limit])
    if len(values) > limit:
        return f"{preview}, +{len(values) - limit} more"
    return preview

@st.cache_data(show_spinner=False, ttl=600, max_entries=8)
def _attach_subdivision_spend_totals(matches: pd.DataFrame, client_totals: pd.DataFrame) -> pd.DataFrame:
    out = matches.copy() if isinstance(matches, pd.DataFrame) else pd.DataFrame()
    if out.empty:
        out["low_total"] = pd.Series(dtype=float)
        out["high_total"] = pd.Series(dtype=float)
        return out

    out["low_total"] = 0.0
    out["high_total"] = 0.0
    if not isinstance(client_totals, pd.DataFrame) or client_totals.empty:
        return out

    totals = ensure_cols(client_totals.copy(), {"Client": "", "Low": 0.0, "High": 0.0, "IsTFL": 0})
    totals = totals[totals["IsTFL"] == 1]
    if totals.empty:
        return out

    totals["Client"] = totals["Client"].fillna("").astype(str).str.strip()
    totals = totals[totals["Client"] != ""]
    if totals.empty:
        return out
    totals["Low"] = pd.to_numeric(totals["Low"], errors="coerce").fillna(0.0)
    totals["High"] = pd.to_numeric(totals["High"], errors="coerce").fillna(0.0)
    totals = (
        totals.groupby("Client", as_index=False)
        .agg(Low=("Low", "sum"), High=("High", "sum"))
    )
    spend_lookup = {
        str(r.Client): (float(r.Low), float(r.High))
        for r in totals.itertuples(index=False)
    }

    fallback_clients = pd.Series([[]] * len(out), index=out.index, dtype=object)
    client_series = out.get("match_clients", fallback_clients)
    low_vals: list[float] = []
    high_vals: list[float] = []
    for client_values in client_series.tolist():
        low_total = 0.0
        high_total = 0.0
        if isinstance(client_values, list):
            for raw_client in client_values:
                key = str(raw_client).strip()
                if not key:
                    continue
                low_v, high_v = spend_lookup.get(key, (0.0, 0.0))
                low_total += float(low_v)
                high_total += float(high_v)
        low_vals.append(low_total)
        high_vals.append(high_total)
    out["low_total"] = pd.array(low_vals, dtype="float64")
    out["high_total"] = pd.array(high_vals, dtype="float64")
    out["match_count"] = out.get("match_clients", pd.Series(dtype=object)).map(
        lambda v: len(v) if isinstance(v, list) else 0
    ).astype("int64")
    return out

@st.cache_data(show_spinner=False, ttl=43200, max_entries=2)
def fetch_tea_school_district_centroids() -> pd.DataFrame:
    cols = ["fid", "name", "name2", "name20", "district_code", "district_code_compact", "lon", "lat"]
    rows: list[dict] = []
    page_size = 1000
    offset = 0
    try:
        while True:
            payload = _arcgis_get_json(
                f"{TEA_ARCGIS_SCHOOL_DISTRICT_LAYER_URL}/query",
                params={
                    "where": "1=1",
                    "outFields": "FID,NAME,NAME2,NAME20,DISTRICT,DISTRICT_C",
                    "returnGeometry": "false",
                    "returnCentroid": "true",
                    "outSR": "4326",
                    "orderByFields": "FID ASC",
                    "resultRecordCount": page_size,
                    "resultOffset": offset,
                    "f": "json",
                },
            )
            features = payload.get("features", [])
            if not features:
                break
            for feat in features:
                attrs = feat.get("attributes", {}) or {}
                centroid = feat.get("centroid", {}) or {}
                fid = attrs.get("FID")
                if fid is None:
                    continue
                try:
                    lon = float(centroid.get("x"))
                    lat = float(centroid.get("y"))
                except (TypeError, ValueError):
                    continue
                rows.append(
                    {
                        "fid": int(fid),
                        "name": str(attrs.get("NAME", "")).strip(),
                        "name2": str(attrs.get("NAME2", "")).strip(),
                        "name20": str(attrs.get("NAME20", "")).strip(),
                        "district_code": str(attrs.get("DISTRICT", "")).strip(),
                        "district_code_compact": str(attrs.get("DISTRICT_C", "")).strip(),
                        "lon": lon,
                        "lat": lat,
                    }
                )
            if len(features) < page_size:
                break
            offset += len(features)
    except Exception:
        return pd.DataFrame(columns=cols)
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows, columns=cols)

@st.cache_data(show_spinner=False, ttl=43200, max_entries=2)
def fetch_tea_county_centroids() -> pd.DataFrame:
    cols = ["objectid", "name", "fips", "cntykey", "lon", "lat"]
    rows: list[dict] = []
    try:
        payload = _arcgis_get_json(
            f"{TEA_ARCGIS_COUNTY_LAYER_URL}/query",
            params={
                "where": "1=1",
                "outFields": "OBJECTID,FIPS,CNTYKEY,FENAME",
                "returnGeometry": "false",
                "returnCentroid": "true",
                "outSR": "4326",
                "orderByFields": "OBJECTID ASC",
                "resultRecordCount": 1000,
                "f": "json",
            },
        )
        for feat in payload.get("features", []):
            attrs = feat.get("attributes", {}) or {}
            centroid = feat.get("centroid", {}) or {}
            src_id = attrs.get("OBJECTID")
            if src_id is None:
                continue
            try:
                lon = float(centroid.get("x"))
                lat = float(centroid.get("y"))
            except (TypeError, ValueError):
                continue
            rows.append(
                {
                    "objectid": int(src_id),
                    "name": str(attrs.get("FENAME", "")).strip(),
                    "fips": str(attrs.get("FIPS", "")).strip(),
                    "cntykey": str(attrs.get("CNTYKEY", "")).strip(),
                    "lon": lon,
                    "lat": lat,
                }
            )
    except Exception:
        return pd.DataFrame(columns=cols)
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows, columns=cols)

@st.cache_data(show_spinner=False, ttl=43200, max_entries=2)
def fetch_texas_city_centroids() -> pd.DataFrame:
    cols = ["objectid", "name", "basename", "geoid", "lon", "lat"]
    rows: list[dict] = []
    page_size = 2000
    offset = 0
    try:
        while True:
            payload = _arcgis_get_json(
                f"{CENSUS_ARCGIS_TEXAS_CITY_LAYER_URL}/query",
                params={
                    "where": "STATE='48'",
                    "outFields": "OBJECTID,NAME,BASENAME,GEOID,CENTLON,CENTLAT",
                    "returnGeometry": "false",
                    "orderByFields": "OBJECTID ASC",
                    "resultRecordCount": page_size,
                    "resultOffset": offset,
                    "f": "json",
                },
            )
            features = payload.get("features", [])
            if not features:
                break
            for feat in features:
                attrs = feat.get("attributes", {}) or {}
                src_id = attrs.get("OBJECTID")
                if src_id is None:
                    continue
                try:
                    lon = float(str(attrs.get("CENTLON", "")).strip())
                    lat = float(str(attrs.get("CENTLAT", "")).strip())
                except (TypeError, ValueError):
                    continue
                rows.append(
                    {
                        "objectid": int(src_id),
                        "name": str(attrs.get("NAME", "")).strip(),
                        "basename": str(attrs.get("BASENAME", "")).strip(),
                        "geoid": str(attrs.get("GEOID", "")).strip(),
                        "lon": lon,
                        "lat": lat,
                    }
                )
            if len(features) < page_size:
                break
            offset += len(features)
    except Exception:
        return pd.DataFrame(columns=cols)
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows, columns=cols)

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

    out_rows: list[dict] = []
    for row in layer_df.itertuples(index=False):
        names = []
        for col in layer_name_cols:
            v = getattr(row, col, "")
            if v is not None and str(v).strip():
                names.append(str(v).strip())
        if extra_candidate_builder is not None:
            try:
                names.extend(extra_candidate_builder(row) or [])
            except Exception:
                pass
        names = [n for n in names if n]
        if not names:
            continue

        variant_keys = {norm_name(_canonical_subdivision_text(n)) for n in names}
        variant_keys = {k for k in variant_keys if k}
        candidate_root_keys = {_subdivision_root_from_patterns(n, root_patterns) for n in names}
        candidate_root_keys = {k for k in candidate_root_keys if k}
        matched_clients: set[str] = set()
        for key in variant_keys:
            matched_clients |= exact_index.get(key, set())

        for root_key in candidate_root_keys:
            matched_clients |= root_index.get(root_key, set())

        # Conservative fuzzy fallback for near-identical subdivision naming variants.
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
        for ccol in layer_code_cols:
            cv = getattr(row, ccol, "")
            if cv is not None and str(cv).strip():
                code = str(cv).strip()
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
    out = out.sort_values(["match_count", "subdivision_name"], ascending=[False, True])
    return out

@st.cache_data(show_spinner=False, ttl=43200, max_entries=2)
def fetch_tceq_water_district_centroids() -> pd.DataFrame:
    cols = ["district_name", "district_code", "type_code", "type_desc", "lon", "lat"]
    rows: list[dict] = []
    page_size = 2000
    offset = 0
    try:
        while True:
            payload = _arcgis_get_json(
                f"{TCEQ_WATER_DISTRICTS_LAYER_URL}/query",
                params={
                    "where": "1=1",
                    "outFields": "NAME,DISTRICT_ID,TYPE,TYPE_DESCRIPTION",
                    "returnGeometry": "false",
                    "returnCentroid": "true",
                    "outSR": "4326",
                    "orderByFields": "OBJECTID ASC",
                    "resultRecordCount": page_size,
                    "resultOffset": offset,
                    "f": "json",
                },
            )
            features = payload.get("features", [])
            if not features:
                break
            for feat in features:
                attrs = feat.get("attributes", {}) or {}
                centroid = feat.get("centroid", {}) or {}
                name = str(attrs.get("NAME", "")).strip()
                if not name:
                    continue
                try:
                    lon = float(centroid.get("x"))
                    lat = float(centroid.get("y"))
                except (TypeError, ValueError):
                    continue
                rows.append(
                    {
                        "district_name": name,
                        "district_code": str(attrs.get("DISTRICT_ID", "")).strip(),
                        "type_code": str(attrs.get("TYPE", "")).strip(),
                        "type_desc": str(attrs.get("TYPE_DESCRIPTION", "")).strip(),
                        "lon": lon,
                        "lat": lat,
                    }
                )
            if len(features) < page_size:
                break
            offset += len(features)
    except Exception:
        return pd.DataFrame(columns=cols)
    if not rows:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame(rows, columns=cols)
    out = (
        out.groupby(["district_name", "district_code", "type_code", "type_desc"], as_index=False)
        .agg(lon=("lon", "mean"), lat=("lat", "mean"))
    )
    return out

@st.cache_data(show_spinner=False, ttl=43200, max_entries=2)
def fetch_tceq_groundwater_district_centroids() -> pd.DataFrame:
    cols = ["district_name", "district_code", "lon", "lat"]
    rows: list[dict] = []
    page_size = 500
    offset = 0
    try:
        while True:
            payload = _arcgis_get_json(
                f"{TCEQ_GROUNDWATER_DISTRICTS_LAYER_URL}/query",
                params={
                    "where": "1=1",
                    "outFields": "DISTNAME,DIST_NUM,SHORTNAM",
                    "returnGeometry": "false",
                    "returnCentroid": "true",
                    "outSR": "4326",
                    "orderByFields": "OBJECTID ASC",
                    "resultRecordCount": page_size,
                    "resultOffset": offset,
                    "f": "json",
                },
            )
            features = payload.get("features", [])
            if not features:
                break
            for feat in features:
                attrs = feat.get("attributes", {}) or {}
                centroid = feat.get("centroid", {}) or {}
                name = str(attrs.get("DISTNAME", "")).strip() or str(attrs.get("SHORTNAM", "")).strip()
                if not name:
                    continue
                try:
                    lon = float(centroid.get("x"))
                    lat = float(centroid.get("y"))
                except (TypeError, ValueError):
                    continue
                rows.append(
                    {
                        "district_name": name,
                        "district_code": str(attrs.get("DIST_NUM", "")).strip(),
                        "lon": lon,
                        "lat": lat,
                    }
                )
            if len(features) < page_size:
                break
            offset += len(features)
    except Exception:
        return pd.DataFrame(columns=cols)
    if not rows:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame(rows, columns=cols)
    out = (
        out.groupby(["district_name", "district_code"], as_index=False)
        .agg(lon=("lon", "mean"), lat=("lat", "mean"))
    )
    return out

@st.cache_data(show_spinner=False, ttl=43200, max_entries=2)
def fetch_texas_rma_centroids() -> pd.DataFrame:
    cols = ["district_name", "district_code", "lon", "lat"]
    rows: list[dict] = []
    try:
        payload = _arcgis_get_json(
            f"{TEXAS_RMA_LAYER_URL}/query",
            params={
                "where": "1=1",
                "outFields": "OBJECTID,RMA,Label",
                "returnGeometry": "false",
                "returnCentroid": "true",
                "outSR": "4326",
                "orderByFields": "OBJECTID ASC",
                "resultRecordCount": 1000,
                "f": "json",
            },
        )
        for feat in payload.get("features", []):
            attrs = feat.get("attributes", {}) or {}
            centroid = feat.get("centroid", {}) or {}
            name = str(attrs.get("Label", "")).strip() or str(attrs.get("RMA", "")).strip()
            if not name:
                continue
            try:
                lon = float(centroid.get("x"))
                lat = float(centroid.get("y"))
            except (TypeError, ValueError):
                continue
            rows.append(
                {
                    "district_name": name,
                    "district_code": str(attrs.get("OBJECTID", "")).strip(),
                    "lon": lon,
                    "lat": lat,
                }
            )
    except Exception:
        return pd.DataFrame(columns=cols)
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows, columns=cols)

@st.cache_data(show_spinner=False, ttl=43200, max_entries=2)
def fetch_texas_junior_college_centroids() -> pd.DataFrame:
    cols = ["district_name", "district_code", "name2", "lon", "lat"]
    rows: list[dict] = []
    page_size = 500
    offset = 0
    try:
        while True:
            payload = _arcgis_get_json(
                f"{TEXAS_JUNIOR_COLLEGE_LAYER_URL}/query",
                params={
                    "where": "1=1",
                    "outFields": "OBJECTID,DISTRICT,NAME1,NAME2,NAME3",
                    "returnGeometry": "false",
                    "returnCentroid": "true",
                    "outSR": "4326",
                    "orderByFields": "OBJECTID ASC",
                    "resultRecordCount": page_size,
                    "resultOffset": offset,
                    "f": "json",
                },
            )
            features = payload.get("features", [])
            if not features:
                break
            for feat in features:
                attrs = feat.get("attributes", {}) or {}
                centroid = feat.get("centroid", {}) or {}
                name1 = str(attrs.get("NAME1", "")).strip()
                name2 = str(attrs.get("NAME2", "")).strip()
                name = name1 or name2
                if not name:
                    continue
                try:
                    lon = float(centroid.get("x"))
                    lat = float(centroid.get("y"))
                except (TypeError, ValueError):
                    continue
                rows.append(
                    {
                        "district_name": name,
                        "district_code": str(attrs.get("DISTRICT", "")).strip(),
                        "name2": name2,
                        "lon": lon,
                        "lat": lat,
                    }
                )
            if len(features) < page_size:
                break
            offset += len(features)
    except Exception:
        return pd.DataFrame(columns=cols)
    if not rows:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame(rows, columns=cols)
    out = (
        out.groupby(["district_name", "district_code", "name2"], as_index=False)
        .agg(lon=("lon", "mean"), lat=("lat", "mean"))
    )
    return out

@st.cache_data(show_spinner=False, ttl=43200, max_entries=2)
def fetch_texas_navigation_district_centroids() -> pd.DataFrame:
    cols = ["district_name", "district_code", "lon", "lat"]
    rows: list[dict] = []
    page_size = 1000
    offset = 0
    try:
        while True:
            payload = _arcgis_get_json(
                f"{TEXAS_NAVIGATION_DISTRICT_LAYER_URL}/query",
                params={
                    "where": "1=1",
                    "outFields": "OBJECTID,DISTRICT_N",
                    "returnGeometry": "false",
                    "returnCentroid": "true",
                    "outSR": "4326",
                    "orderByFields": "OBJECTID ASC",
                    "resultRecordCount": page_size,
                    "resultOffset": offset,
                    "f": "json",
                },
            )
            features = payload.get("features", [])
            if not features:
                break
            for feat in features:
                attrs = feat.get("attributes", {}) or {}
                centroid = feat.get("centroid", {}) or {}
                name = str(attrs.get("DISTRICT_N", "")).strip()
                if not name:
                    continue
                try:
                    lon = float(centroid.get("x"))
                    lat = float(centroid.get("y"))
                except (TypeError, ValueError):
                    continue
                rows.append(
                    {
                        "district_name": name,
                        "district_code": str(attrs.get("OBJECTID", "")).strip(),
                        "lon": lon,
                        "lat": lat,
                    }
                )
            if len(features) < page_size:
                break
            offset += len(features)
    except Exception:
        return pd.DataFrame(columns=cols)
    if not rows:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame(rows, columns=cols)
    out = (
        out.groupby(["district_name"], as_index=False)
        .agg(district_code=("district_code", "min"), lon=("lon", "mean"), lat=("lat", "mean"))
    )
    return out

@st.cache_data(show_spinner=False, ttl=43200, max_entries=2)
def fetch_nctcog_transit_provider_centroids() -> pd.DataFrame:
    cols = ["provider_name", "classification", "district_code", "lon", "lat"]
    rows: list[dict] = []
    page_size = 1000
    offset = 0
    try:
        while True:
            payload = _arcgis_get_json(
                f"{NCTCOG_TRANSIT_PROVIDERS_LAYER_URL}/query",
                params={
                    "where": "1=1",
                    "outFields": "OBJECTID,Name,Classification",
                    "returnGeometry": "true",
                    "outSR": "4326",
                    "orderByFields": "OBJECTID ASC",
                    "resultRecordCount": page_size,
                    "resultOffset": offset,
                    "f": "json",
                },
            )
            features = payload.get("features", [])
            if not features:
                break
            for feat in features:
                attrs = feat.get("attributes", {}) or {}
                geometry = feat.get("geometry", {}) or {}
                name = str(attrs.get("Name", "")).strip()
                if not name:
                    continue
                try:
                    rings = geometry.get("rings", []) or []
                    x_vals = [float(pt[0]) for ring in rings for pt in ring if isinstance(pt, list) and len(pt) >= 2]
                    y_vals = [float(pt[1]) for ring in rings for pt in ring if isinstance(pt, list) and len(pt) >= 2]
                    if not x_vals or not y_vals:
                        continue
                    lon = (min(x_vals) + max(x_vals)) / 2.0
                    lat = (min(y_vals) + max(y_vals)) / 2.0
                except (TypeError, ValueError, IndexError):
                    continue
                rows.append(
                    {
                        "provider_name": name,
                        "classification": str(attrs.get("Classification", "")).strip(),
                        "district_code": str(attrs.get("OBJECTID", "")).strip(),
                        "lon": lon,
                        "lat": lat,
                    }
                )
            if len(features) < page_size:
                break
            offset += len(features)
    except Exception:
        return pd.DataFrame(columns=cols)
    if not rows:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame(rows, columns=cols)
    out = (
        out.groupby(["provider_name", "classification", "district_code"], as_index=False)
        .agg(lon=("lon", "mean"), lat=("lat", "mean"))
    )
    return out

@st.cache_data(show_spinner=False, ttl=43200, max_entries=2)
def fetch_txdot_seaport_centroids() -> pd.DataFrame:
    cols = ["port_name", "port_type", "port_code", "lon", "lat"]
    rows: list[dict] = []
    page_size = 1000
    offset = 0
    try:
        while True:
            payload = _arcgis_get_json(
                f"{TXDOT_SEAPORTS_LAYER_URL}/query",
                params={
                    "where": "1=1",
                    "outFields": "OBJECTID,PORT_NM,PORT_TYPE",
                    "returnGeometry": "true",
                    "outSR": "4326",
                    "orderByFields": "OBJECTID ASC",
                    "resultRecordCount": page_size,
                    "resultOffset": offset,
                    "f": "json",
                },
            )
            features = payload.get("features", [])
            if not features:
                break
            for feat in features:
                attrs = feat.get("attributes", {}) or {}
                geometry = feat.get("geometry", {}) or {}
                name = str(attrs.get("PORT_NM", "")).strip()
                if not name:
                    continue
                try:
                    lon = float(geometry.get("x"))
                    lat = float(geometry.get("y"))
                except (TypeError, ValueError):
                    continue
                rows.append(
                    {
                        "port_name": name,
                        "port_type": str(attrs.get("PORT_TYPE", "")).strip(),
                        "port_code": str(attrs.get("OBJECTID", "")).strip(),
                        "lon": lon,
                        "lat": lat,
                    }
                )
            if len(features) < page_size:
                break
            offset += len(features)
    except Exception:
        return pd.DataFrame(columns=cols)
    if not rows:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame(rows, columns=cols)
    out = (
        out.groupby(["port_name", "port_type", "port_code"], as_index=False)
        .agg(lon=("lon", "mean"), lat=("lat", "mean"))
    )
    return out

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
        canon = _canonical_school_district_name(client)
        canon_key = norm_name(canon)
        if canon_key:
            exact_index.setdefault(canon_key, set()).add(client)
        if _looks_like_school_district_name(client):
            root_key = _school_district_root_key(client)
            if root_key:
                root_index.setdefault(root_key, set()).add(client)

    if not exact_index and not root_index:
        return pd.DataFrame(columns=cols)

    out_rows: list[dict] = []
    for row in districts.itertuples(index=False):
        candidates = [row.name20, row.name, row.name2]
        if row.name2:
            candidates.append(f"{row.name2} ISD")
            candidates.append(f"{row.name2} Independent School District")
        variant_keys = set()
        for candidate in candidates:
            canon = _canonical_school_district_name(candidate)
            key = norm_name(canon)
            if key:
                variant_keys.add(key)

        matched_clients: set[str] = set()
        for key in variant_keys:
            matched_clients |= exact_index.get(key, set())
        root_key = _school_district_root_key(row.name20 or row.name or row.name2)
        if root_key:
            matched_clients |= root_index.get(root_key, set())

        if not matched_clients:
            continue
        matched_sorted = sorted(matched_clients)
        preview = ", ".join(matched_sorted[:6])
        if len(matched_sorted) > 6:
            preview = f"{preview}, +{len(matched_sorted) - 6} more"
        out_rows.append(
            {
                "fid": int(row.fid),
                "district_name": row.name20 or row.name or row.name2 or "",
                "district_code": row.district_code or row.district_code_compact or "",
                "lon": float(row.lon),
                "lat": float(row.lat),
                "match_count": int(len(matched_sorted)),
                "match_clients": matched_sorted,
                "match_clients_preview": preview,
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

    out_rows: list[dict] = []
    for row in counties.itertuples(index=False):
        candidates = [row.name, f"{row.name} County", f"County of {row.name}"]
        variant_keys = {norm_name(_canonical_county_name(c)) for c in candidates if c}
        variant_keys = {k for k in variant_keys if k}

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

    out_rows: list[dict] = []
    for row in cities.itertuples(index=False):
        base = row.basename or re.sub(r"\s+(city|town|village)\s*$", "", row.name, flags=re.IGNORECASE).strip()
        if not base:
            continue
        display_name = base
        if not re.search(r"\b(CITY|TOWN|VILLAGE)\b$", display_name, flags=re.IGNORECASE):
            display_name = f"{display_name} City"
        candidates = [base, row.name, f"City of {base}", f"{base} City", f"Town of {base}", f"{base} Town"]
        variant_keys = {norm_name(_canonical_city_name(c)) for c in candidates if c}
        variant_keys = {k for k in variant_keys if k}

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
    providers = fetch_nctcog_transit_provider_centroids()
    if providers.empty:
        return pd.DataFrame(columns=cols)
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
            "Dallas Area Rapid Transit" if re.search(r"\bDART\b", str(getattr(row, "provider_name", "")), flags=re.IGNORECASE) else "",
        ],
        source_name="NCTCOG Transit Providers (MapServer/10)",
        source_url=NCTCOG_TRANSIT_PROVIDERS_LAYER_URL,
    )

@st.cache_data(show_spinner=False, ttl=3600, max_entries=8)
def build_tfl_port_authority_matches(tfl_client_names: tuple[str, ...]) -> pd.DataFrame:
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
    ports = fetch_txdot_seaport_centroids()
    if ports.empty:
        return pd.DataFrame(columns=cols)

    def _port_aliases(row) -> list[str]:
        raw = str(getattr(row, "port_name", "")).strip()
        base = re.sub(r"^\s*PORT\s+OF\s+", "", raw, flags=re.IGNORECASE).strip()
        aliases: list[str] = []
        if raw:
            aliases.extend(
                [
                    raw,
                    f"{raw} Port Authority",
                    f"{raw} Navigation District",
                ]
            )
        if base and base.lower() != raw.lower():
            aliases.extend(
                [
                    f"Port of {base}",
                    f"{base} Port Authority",
                    f"{base} Navigation District",
                    f"{base} Port",
                ]
            )
        if re.search(r"\bNAVIGATION\s+DISTRICT\b", raw, flags=re.IGNORECASE):
            nav_base = re.sub(r"\bNAVIGATION\s+DISTRICT\b", "", raw, flags=re.IGNORECASE).strip(" -")
            if nav_base:
                aliases.extend([f"Port of {nav_base}", f"{nav_base} Port Authority"])
        return [a for a in aliases if str(a).strip()]

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

    county_lookup: dict[str, dict] = {}
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

    city_lookup: dict[str, dict] = {}
    if not cities.empty:
        for row in cities.itertuples(index=False):
            raw_name = str(getattr(row, "name", "")).strip()
            base = str(getattr(row, "basename", "")).strip() or re.sub(
                r"\s+(city|town|village)\s*$", "", raw_name, flags=re.IGNORECASE
            ).strip()
            if not base:
                continue
            display_name = base
            if not re.search(r"\b(CITY|TOWN|VILLAGE)\b$", display_name, flags=re.IGNORECASE):
                display_name = f"{display_name} City"
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

    rows: list[dict] = []
    county_lookup_keys = tuple(county_lookup.keys())
    city_lookup_keys = tuple(city_lookup.keys())
    for client in sorted({str(name).strip() for name in tfl_client_names if str(name).strip()}):
        entity_type = classify_requested_entity_type(client)
        if entity_type not in SPECIAL_NAME_ANCHORED_ENTITY_TYPES:
            continue

        anchor = None
        anchor_keys = _resolve_special_anchor_keys(
            client_name=client,
            entity_type=entity_type,
            county_lookup_keys=county_lookup_keys,
            city_lookup_keys=city_lookup_keys,
        )
        county_key = str(anchor_keys.get("county_key", "")).strip()
        city_key = str(anchor_keys.get("city_key", "")).strip()
        preferred_scope = str(anchor_keys.get("preferred_scope", "")).strip()

        if preferred_scope == "county" and county_key in county_lookup:
            anchor = county_lookup[county_key]
        elif preferred_scope == "city" and city_key in city_lookup:
            anchor = city_lookup[city_key]
        elif county_key in county_lookup:
            anchor = county_lookup[county_key]
        elif city_key in city_lookup:
            anchor = city_lookup[city_key]

        if not anchor:
            geocoded = geocode_texas_entity_arcgis(client)
            score = float(geocoded.get("score", 0.0)) if geocoded else 0.0
            if geocoded and score >= 70:
                anchor = {
                    "code": str(geocoded.get("postal", "")).strip(),
                    "lon": float(geocoded.get("lon", 0.0)),
                    "lat": float(geocoded.get("lat", 0.0)),
                    "source_name": "ArcGIS geocoded entity centroid (Texas)",
                    "source_url": ARCGIS_GEOCODER_URL,
                }

        if not anchor:
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

    if not rows:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame(rows, columns=cols).drop_duplicates(
        ["subdivision_type", "subdivision_name", "subdivision_code"]
    )
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

    parts = []
    for subtype, root_patterns in WATER_DISTRICT_TYPE_ROOT_PATTERNS.items():
        if subtype == "Navigation District":
            # Use the dedicated statewide navigation-district layer for this type.
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
            extra_candidate_builder=None,
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
        return pd.DataFrame(
            columns=[
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
        )
    return _build_layer_subdivision_matches(
        tfl_client_names=tfl_client_names,
        layer_df=districts,
        subdivision_type="Groundwater Conservation District",
        layer_name_cols=["district_name"],
        layer_code_cols=["district_code"],
        root_patterns=[r"\bGROUNDWATER\s+CONSERVATION\s+DISTRICT\b", r"\bDISTRICT\b"],
        include_client_fn=lambda client: _looks_like_entity_type(client, "Groundwater Conservation District"),
        extra_candidate_builder=None,
        source_name="TCEQ Groundwater Conservation Districts (FeatureServer/0)",
        source_url=TCEQ_GROUNDWATER_DISTRICTS_LAYER_URL,
    )

@st.cache_data(show_spinner=False, ttl=3600, max_entries=8)
def build_tfl_regional_mobility_authority_matches(tfl_client_names: tuple[str, ...]) -> pd.DataFrame:
    districts = fetch_texas_rma_centroids()
    if districts.empty:
        return pd.DataFrame(
            columns=[
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
        )
    return _build_layer_subdivision_matches(
        tfl_client_names=tfl_client_names,
        layer_df=districts,
        subdivision_type="Regional Mobility Authority",
        layer_name_cols=["district_name"],
        layer_code_cols=["district_code"],
        root_patterns=[r"\bREGIONAL\s+MOBILITY\s+AUTHORITY\b", r"\bAUTHORITY\b", r"\bRMA\b"],
        include_client_fn=lambda client: _looks_like_entity_type(client, "Regional Mobility Authority"),
        extra_candidate_builder=lambda row: [
            str(getattr(row, "district_name", "")).replace("RMA", "Regional Mobility Authority").strip()
        ],
        source_name="Texas Regional Mobility Authorities (FeatureServer/0)",
        source_url=TEXAS_RMA_LAYER_URL,
    )

@st.cache_data(show_spinner=False, ttl=3600, max_entries=8)
def build_tfl_junior_college_matches(tfl_client_names: tuple[str, ...]) -> pd.DataFrame:
    districts = fetch_texas_junior_college_centroids()
    if districts.empty:
        return pd.DataFrame(
            columns=[
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
        )
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
        return pd.DataFrame(
            columns=[
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
        )

    def _nav_aliases(row) -> list[str]:
        raw = str(getattr(row, "district_name", "")).strip()
        if not raw:
            return []
        base = re.sub(r"\bNAVIGATION\s+DISTRICT\b", "", raw, flags=re.IGNORECASE).strip(" -")
        aliases = [
            raw,
            f"{raw} Port Authority",
            f"{base} Port Authority" if base else "",
            f"Port of {base}" if base else "",
        ]
        return [a for a in aliases if str(a).strip()]

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
    merged: dict[tuple[str, str, str], dict] = {}
    for row in df.itertuples(index=False):
        t = str(getattr(row, "subdivision_type", "")).strip()
        n = str(getattr(row, "subdivision_name", "")).strip()
        c = str(getattr(row, "subdivision_code", "")).strip()
        if not t or not n:
            continue
        key = (t, n, c)
        clients = getattr(row, "match_clients", [])
        client_set = {str(x).strip() for x in clients if str(x).strip()} if isinstance(clients, list) else set()
        source_name = str(getattr(row, "source_name", "")).strip()
        source_url = str(getattr(row, "source_url", "")).strip()
        if key not in merged:
            merged[key] = {
                "subdivision_type": t,
                "subdivision_name": n,
                "subdivision_code": c,
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
    for _, rec in merged.items():
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

    # PERFORMANCE: run all build_tfl_* functions concurrently so cold-start
    # ArcGIS fetch calls overlap instead of running sequentially.
    def _school():
        return build_tfl_school_district_matches(tfl_client_names).rename(
            columns={"district_name": "subdivision_name", "district_code": "subdivision_code"}
        ).assign(subdivision_type="School District")

    builders = [
        _school,
        lambda: build_tfl_county_matches(tfl_client_names),
        lambda: build_tfl_city_matches(tfl_client_names),
        lambda: build_tfl_junior_college_matches(tfl_client_names),
        lambda: build_tfl_groundwater_district_matches(tfl_client_names),
        lambda: build_tfl_water_district_type_matches(tfl_client_names),
        lambda: build_tfl_transit_authority_matches(tfl_client_names),
        lambda: build_tfl_port_authority_matches(tfl_client_names),
        lambda: build_tfl_regional_mobility_authority_matches(tfl_client_names),
        lambda: build_tfl_navigation_district_matches(tfl_client_names),
        lambda: build_tfl_name_anchored_special_matches(tfl_client_names),
    ]
    parts: list[pd.DataFrame] = []
    with ThreadPoolExecutor(max_workers=len(builders)) as pool:
        futures = {pool.submit(fn): fn for fn in builders}
        for future in as_completed(futures):
            try:
                result = future.result()
                if isinstance(result, pd.DataFrame) and not result.empty:
                    parts.append(result)
            except Exception:
                pass
    if not parts:
        return pd.DataFrame(columns=cols)
    out = pd.concat(parts, ignore_index=True)
    keep = [c for c in cols if c in out.columns]
    out = out[keep]
    return _merge_subdivision_match_rows(out)

@st.cache_data(show_spinner=False, ttl=86400, max_entries=256)
def geocode_address_arcgis(address: str) -> dict:
    q = str(address).strip()
    if not q:
        return {}
    try:
        payload = _arcgis_get_json(
            ARCGIS_GEOCODER_URL,
            params={
                "SingleLine": q,
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
            "input": q,
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
        # Don't cache network failures for 24 h — clear this entry so it retries.
        geocode_address_arcgis.clear()
        return {}

@st.cache_data(show_spinner=False, ttl=604800, max_entries=4096)
def geocode_texas_entity_arcgis(entity_name: str) -> dict:
    q = str(entity_name).strip()
    if not q:
        return {}
    candidates_to_try = [f"{q}, Texas", q]
    network_error = False
    for candidate_query in candidates_to_try:
        try:
            payload = _arcgis_get_json(
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
                "input": q,
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
        # Don't persist transient failures for 7 days — clear cache entry.
        geocode_texas_entity_arcgis.clear()
    return {}

@st.cache_data(show_spinner=False, ttl=604800, max_entries=8192)
def query_texas_county_for_point(lon: float, lat: float) -> dict:
    try:
        payload = _arcgis_get_json(
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
        county_name = str(attrs.get("FENAME", "")).strip()
        fips = str(attrs.get("FIPS", "")).strip()
        return {"county_name": county_name, "county_fips": fips}
    except Exception:
        return {}

@st.cache_data(show_spinner=False, ttl=86400, max_entries=512)
def query_texas_subdivisions_for_point(lon: float, lat: float) -> pd.DataFrame:
    """Query 10 ArcGIS layers in parallel for subdivisions overlapping a point."""
    cols = ["subdivision_type", "subdivision_name", "subdivision_code", "source_name", "source_url"]

    geo_point = f"{lon},{lat}"
    _base_params: dict = {
        "geometry": geo_point,
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "returnGeometry": "false",
        "f": "json",
    }

    # -- Helper closures (one per layer) --------------------------
    def _fetch_school_districts() -> list[dict]:
        result: list[dict] = []
        try:
            payload = _arcgis_get_json(
                f"{TEA_ARCGIS_SCHOOL_DISTRICT_LAYER_URL}/query",
                params={**_base_params, "outFields": "NAME,NAME20,DISTRICT,DISTRICT_C"},
            )
            for feat in payload.get("features", []):
                attrs = feat.get("attributes", {}) or {}
                name = str(attrs.get("NAME20", "")).strip() or str(attrs.get("NAME", "")).strip()
                code = str(attrs.get("DISTRICT", "")).strip() or str(attrs.get("DISTRICT_C", "")).strip()
                if name:
                    result.append({"subdivision_type": "School District", "subdivision_name": name,
                                   "subdivision_code": code, "source_name": "TEA School District boundaries (FeatureServer/0)",
                                   "source_url": TEA_ARCGIS_SCHOOL_DISTRICT_LAYER_URL})
        except Exception:
            pass
        return result

    def _fetch_counties() -> list[dict]:
        result: list[dict] = []
        try:
            payload = _arcgis_get_json(
                f"{TEA_ARCGIS_COUNTY_LAYER_URL}/query",
                params={**_base_params, "outFields": "FENAME,FIPS"},
            )
            for feat in payload.get("features", []):
                attrs = feat.get("attributes", {}) or {}
                county_name = str(attrs.get("FENAME", "")).strip()
                if county_name:
                    result.append({"subdivision_type": "County", "subdivision_name": f"{county_name} County",
                                   "subdivision_code": str(attrs.get("FIPS", "")).strip(),
                                   "source_name": "TEA County boundaries (FeatureServer/0)",
                                   "source_url": TEA_ARCGIS_COUNTY_LAYER_URL})
        except Exception:
            pass
        return result

    def _fetch_cities() -> list[dict]:
        result: list[dict] = []
        try:
            payload = _arcgis_get_json(
                f"{CENSUS_ARCGIS_TEXAS_CITY_LAYER_URL}/query",
                params={**_base_params, "where": "STATE='48'", "outFields": "NAME,BASENAME,GEOID"},
            )
            for feat in payload.get("features", []):
                attrs = feat.get("attributes", {}) or {}
                name = str(attrs.get("NAME", "")).strip()
                base = str(attrs.get("BASENAME", "")).strip() or re.sub(
                    r"\s+(city|town|village)\s*$", "", name, flags=re.IGNORECASE
                ).strip()
                if base:
                    display = base
                    if not re.search(r"\b(CITY|TOWN|VILLAGE)\b$", display, flags=re.IGNORECASE):
                        display = f"{display} City"
                    result.append({"subdivision_type": "City", "subdivision_name": display,
                                   "subdivision_code": str(attrs.get("GEOID", "")).strip(),
                                   "source_name": "U.S. Census TIGERweb Texas Places (MapServer/25)",
                                   "source_url": CENSUS_ARCGIS_TEXAS_CITY_LAYER_URL})
        except Exception:
            pass
        return result

    def _fetch_water_districts() -> list[dict]:
        result: list[dict] = []
        try:
            payload = _arcgis_get_json(
                f"{TCEQ_WATER_DISTRICTS_LAYER_URL}/query",
                params={**_base_params, "outFields": "NAME,DISTRICT_ID,TYPE,TYPE_DESCRIPTION"},
            )
            for feat in payload.get("features", []):
                attrs = feat.get("attributes", {}) or {}
                mapped_type = _canonical_water_district_type(str(attrs.get("TYPE_DESCRIPTION", "")).strip())
                if mapped_type == "Navigation District":
                    mapped_type = ""
                if not mapped_type:
                    continue
                name = str(attrs.get("NAME", "")).strip()
                if name:
                    result.append({"subdivision_type": mapped_type, "subdivision_name": name,
                                   "subdivision_code": str(attrs.get("DISTRICT_ID", "")).strip(),
                                   "source_name": "TCEQ Water Districts (FeatureServer/0)",
                                   "source_url": TCEQ_WATER_DISTRICTS_LAYER_URL})
        except Exception:
            pass
        return result

    def _fetch_groundwater() -> list[dict]:
        result: list[dict] = []
        try:
            payload = _arcgis_get_json(
                f"{TCEQ_GROUNDWATER_DISTRICTS_LAYER_URL}/query",
                params={**_base_params, "outFields": "DISTNAME,DIST_NUM,SHORTNAM"},
            )
            for feat in payload.get("features", []):
                attrs = feat.get("attributes", {}) or {}
                name = str(attrs.get("DISTNAME", "")).strip() or str(attrs.get("SHORTNAM", "")).strip()
                if name:
                    result.append({"subdivision_type": "Groundwater Conservation District", "subdivision_name": name,
                                   "subdivision_code": str(attrs.get("DIST_NUM", "")).strip(),
                                   "source_name": "TCEQ Groundwater Conservation Districts (FeatureServer/0)",
                                   "source_url": TCEQ_GROUNDWATER_DISTRICTS_LAYER_URL})
        except Exception:
            pass
        return result

    def _fetch_rma() -> list[dict]:
        result: list[dict] = []
        try:
            payload = _arcgis_get_json(
                f"{TEXAS_RMA_LAYER_URL}/query",
                params={**_base_params, "outFields": "OBJECTID,RMA,Label"},
            )
            for feat in payload.get("features", []):
                attrs = feat.get("attributes", {}) or {}
                name = str(attrs.get("Label", "")).strip() or str(attrs.get("RMA", "")).strip()
                if name:
                    result.append({"subdivision_type": "Regional Mobility Authority", "subdivision_name": name,
                                   "subdivision_code": str(attrs.get("OBJECTID", "")).strip(),
                                   "source_name": "Texas Regional Mobility Authorities (FeatureServer/0)",
                                   "source_url": TEXAS_RMA_LAYER_URL})
        except Exception:
            pass
        return result

    def _fetch_junior_colleges() -> list[dict]:
        result: list[dict] = []
        try:
            payload = _arcgis_get_json(
                f"{TEXAS_JUNIOR_COLLEGE_LAYER_URL}/query",
                params={**_base_params, "outFields": "DISTRICT,NAME1,NAME2"},
            )
            for feat in payload.get("features", []):
                attrs = feat.get("attributes", {}) or {}
                name = str(attrs.get("NAME1", "")).strip() or str(attrs.get("NAME2", "")).strip()
                if name:
                    result.append({"subdivision_type": "Junior College District", "subdivision_name": name,
                                   "subdivision_code": str(attrs.get("DISTRICT", "")).strip(),
                                   "source_name": "Texas Junior College Service Areas (FeatureServer/0)",
                                   "source_url": TEXAS_JUNIOR_COLLEGE_LAYER_URL})
        except Exception:
            pass
        return result

    def _fetch_navigation() -> list[dict]:
        result: list[dict] = []
        try:
            payload = _arcgis_get_json(
                f"{TEXAS_NAVIGATION_DISTRICT_LAYER_URL}/query",
                params={**_base_params, "outFields": "OBJECTID,DISTRICT_N"},
            )
            for feat in payload.get("features", []):
                attrs = feat.get("attributes", {}) or {}
                name = str(attrs.get("DISTRICT_N", "")).strip()
                if name:
                    result.append({"subdivision_type": "Navigation District", "subdivision_name": name,
                                   "subdivision_code": str(attrs.get("OBJECTID", "")).strip(),
                                   "source_name": "Texas Navigation Districts (FeatureServer/29)",
                                   "source_url": TEXAS_NAVIGATION_DISTRICT_LAYER_URL})
        except Exception:
            pass
        return result

    def _fetch_transit() -> list[dict]:
        result: list[dict] = []
        try:
            payload = _arcgis_get_json(
                f"{NCTCOG_TRANSIT_PROVIDERS_LAYER_URL}/query",
                params={**_base_params, "outFields": "OBJECTID,Name,Classification"},
            )
            for feat in payload.get("features", []):
                attrs = feat.get("attributes", {}) or {}
                name = str(attrs.get("Name", "")).strip()
                if name:
                    result.append({"subdivision_type": "Transit Authority", "subdivision_name": name,
                                   "subdivision_code": str(attrs.get("OBJECTID", "")).strip(),
                                   "source_name": "NCTCOG Transit Providers (MapServer/10)",
                                   "source_url": NCTCOG_TRANSIT_PROVIDERS_LAYER_URL})
        except Exception:
            pass
        return result

    def _fetch_seaports() -> list[dict]:
        result: list[dict] = []
        try:
            payload = _arcgis_get_json(
                f"{TXDOT_SEAPORTS_LAYER_URL}/query",
                params={**_base_params, "distance": 25, "units": "esriSRUnit_StatuteMile",
                        "outFields": "OBJECTID,PORT_NM"},
            )
            for feat in payload.get("features", []):
                attrs = feat.get("attributes", {}) or {}
                name = str(attrs.get("PORT_NM", "")).strip()
                if name:
                    result.append({"subdivision_type": "Port Authority", "subdivision_name": name,
                                   "subdivision_code": str(attrs.get("OBJECTID", "")).strip(),
                                   "source_name": "TxDOT Seaports (FeatureServer/0)",
                                   "source_url": TXDOT_SEAPORTS_LAYER_URL})
        except Exception:
            pass
        return result

    # -- Fire all queries concurrently ----------------------------
    fetchers = [
        _fetch_school_districts, _fetch_counties, _fetch_cities,
        _fetch_water_districts, _fetch_groundwater, _fetch_rma,
        _fetch_junior_colleges, _fetch_navigation, _fetch_transit,
        _fetch_seaports,
    ]
    rows: list[dict] = []
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
    t = str(subdivision_type).strip().lower()
    if t == "school district":
        return _school_district_root_key(subdivision_name)
    if t == "county":
        return _county_root_key(subdivision_name)
    if t == "city":
        return _city_root_key(subdivision_name)
    for water_type, root_patterns in WATER_DISTRICT_TYPE_ROOT_PATTERNS.items():
        if t == water_type.lower():
            return _subdivision_root_from_patterns(subdivision_name, root_patterns)
    if t == "transit authority":
        return _subdivision_root_from_patterns(subdivision_name, TRANSIT_AUTHORITY_ROOT_PATTERNS)
    if t == "port authority":
        return _subdivision_root_from_patterns(subdivision_name, PORT_AUTHORITY_ROOT_PATTERNS)
    if t == "hospital district":
        return _subdivision_root_from_patterns(subdivision_name, [r"\bHOSPITAL\s+DISTRICT\b", r"\bDISTRICT\b"])
    if t == "emergency services district":
        return _subdivision_root_from_patterns(subdivision_name, [r"\bEMERGENCY\s+SERVICES\s+DISTRICT\b", r"\bDISTRICT\b", r"\bE\.?S\.?D\.?\b"])
    if t == "appraisal district":
        return _subdivision_root_from_patterns(subdivision_name, [r"\bAPPRAISAL\s+DISTRICT\b", r"\bDISTRICT\b", r"\bC\.?A\.?D\.?\b"])
    if t == "local government corporation":
        return _subdivision_root_from_patterns(
            subdivision_name,
            [r"\bLOCAL\s+GOVERNMENT\s+CORPORATION\b", r"\bDEVELOPMENT\s+CORPORATION\b", r"\bCORPORATION\b"],
        )
    if t == "groundwater conservation district":
        return _subdivision_root_from_patterns(subdivision_name, [r"\bGROUNDWATER\s+CONSERVATION\s+DISTRICT\b", r"\bDISTRICT\b"])
    if t == "regional mobility authority":
        return _subdivision_root_from_patterns(subdivision_name, [r"\bREGIONAL\s+MOBILITY\s+AUTHORITY\b", r"\bAUTHORITY\b", r"\bRMA\b"])
    if t == "junior college district":
        return _subdivision_root_from_patterns(
            subdivision_name,
            [r"\bCOMMUNITY\s+COLLEGE\b", r"\bJUNIOR\s+COLLEGE\b", r"\bCOLLEGE\s+DISTRICT\b", r"\bSERVICE\s+AREA\b", r"\bCOLLEGE\b", r"\bDISTRICT\b"],
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

def _prepare_subdivision_match_pool(pool: pd.DataFrame, subdivision_type: str) -> pd.DataFrame:
    if pool.empty:
        return pool
    out = pool
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
    out["_name_key"] = name_series.map(
        lambda x: _subdivision_name_key(subdivision_type, x)
    )
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

        # Conservative fuzzy fallback for minor naming deltas between ArcGIS layers and matched records.
        if len(name_key) >= 6:
            name_pool = pool[pool["_name_key"].astype(str) != ""]
            if not name_pool.empty:
                name_pool["_name_score"] = name_pool["_name_key"].astype(str).map(
                    lambda x: difflib.SequenceMatcher(None, name_key, str(x)).ratio()
                )
                name_pool = name_pool[name_pool["_name_score"] >= 0.90]
                if not name_pool.empty:
                    best_score = float(name_pool["_name_score"].max())
                    picked = name_pool[name_pool["_name_score"] >= max(0.90, best_score - 0.03)]
                    if not picked.empty:
                        return picked.drop(columns=["_name_score"], errors="ignore"), "Spatial boundary (fuzzy)"

    return pd.DataFrame(), ""

def _match_confidence_from_method(match_method: str) -> str:
    m = str(match_method).strip().lower()
    if m in {"spatial boundary (code)", "spatial boundary (name)"}:
        return "High"
    if m == "spatial boundary (fuzzy)":
        return "Medium"
    if m in {"name anchored", "name + geocode context"}:
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
    cols = [
        "Subdivision Type",
        "Subdivision",
        "Code",
        "Entity Type",
        "TFL Entity",
        "Match Method",
        "Match Confidence",
        "Map Source",
        "Low",
        "High",
        "Mid",
        "Lobbyists",
    ]
    if overlap_subdivisions.empty or subdivision_matches.empty or tfl_spending.empty:
        return pd.DataFrame(columns=cols)

    spend_lookup_local = dict(spend_lookup or {})
    if not spend_lookup_local:
        spend = tfl_spending.copy()
        spend = ensure_cols(spend, {"Client": "", "Low": 0.0, "High": 0.0, "Lobbyists": 0})
        spend["Client"] = spend["Client"].fillna("").astype(str).str.strip()
        spend = spend[spend["Client"] != ""]
        if spend.empty:
            return pd.DataFrame(columns=cols)
        spend["Low"] = pd.to_numeric(spend["Low"], errors="coerce").fillna(0.0)
        spend["High"] = pd.to_numeric(spend["High"], errors="coerce").fillna(0.0)
        spend["Lobbyists"] = pd.to_numeric(spend["Lobbyists"], errors="coerce").fillna(0).astype(int)
        spend["EntityType"] = spend["Client"].map(classify_requested_entity_type)
        spend = (
            spend.groupby("Client", as_index=False)
            .agg(Low=("Low", "sum"), High=("High", "sum"), Lobbyists=("Lobbyists", "max"), EntityType=("EntityType", "first"))
        )
        spend_lookup_local = {
            str(r.Client): {
                "Low": float(r.Low),
                "High": float(r.High),
                "Lobbyists": int(r.Lobbyists),
                "EntityType": str(r.EntityType).strip(),
            }
            for r in spend.itertuples(index=False)
        }

    rows: list[dict] = []
    existing_keys: set[tuple[str, str, str, str]] = set()
    prepared_overlap_pools = prepared_overlap_pools or {}
    pool_cache: dict[str, pd.DataFrame] = {}
    for overlap in overlap_subdivisions.itertuples(index=False):
        t = str(overlap.subdivision_type).strip()
        n = str(overlap.subdivision_name).strip()
        c = str(overlap.subdivision_code).strip()
        if t in prepared_overlap_pools:
            pool = prepared_overlap_pools.get(t, pd.DataFrame())
        else:
            if t not in pool_cache:
                base_pool = subdivision_matches[subdivision_matches["subdivision_type"].astype(str) == t]
                pool_cache[t] = _prepare_subdivision_match_pool(base_pool, t)
            pool = pool_cache.get(t, pd.DataFrame())
        if pool.empty:
            continue

        picked, spatial_match_method = _pick_overlap_subdivision_matches(pool, t, n, c)
        if picked.empty:
            continue

        matched_clients: set[str] = set()
        picked_source_names = {
            str(v).strip()
            for v in picked.get("source_name", pd.Series(dtype=object)).dropna().astype(str).tolist()
            if str(v).strip()
        }
        picked_source = "; ".join(sorted(picked_source_names))
        for client_list in picked.get("match_clients", pd.Series(dtype=object)).tolist():
            if isinstance(client_list, list):
                matched_clients.update({str(x).strip() for x in client_list if str(x).strip()})

        for client in sorted(matched_clients):
            spend_vals = spend_lookup_local.get(client, {"Low": 0.0, "High": 0.0, "Lobbyists": 0, "EntityType": ""})
            low = float(spend_vals.get("Low", 0.0))
            high = float(spend_vals.get("High", 0.0))
            entity_type = str(spend_vals.get("EntityType", "")).strip()
            method = spatial_match_method or "Spatial boundary (name)"
            rows.append(
                {
                    "Subdivision Type": t,
                    "Subdivision": n,
                    "Code": c,
                    "Entity Type": entity_type,
                    "TFL Entity": client,
                    "Match Method": method,
                    "Match Confidence": _match_confidence_from_method(method),
                    "Map Source": picked_source,
                    "Low": low,
                    "High": high,
                    "Mid": (low + high) / 2,
                    "Lobbyists": int(spend_vals.get("Lobbyists", 0)),
                }
            )
            existing_keys.add((t, n, c, client))

    # Fallback for requested entity types without statewide polygon layers.
    unsupported_types = {
        "Hospital District",
        "Emergency Services District",
        "Local Government Corporation",
        "Transit Authority",
        "Port Authority",
        "Housing Authority",
        "Appraisal District",
    }
    county_lookup = {
        _county_root_key(str(r.subdivision_name)): (str(r.subdivision_name), str(r.subdivision_code))
        for r in overlap_subdivisions.itertuples(index=False)
        if str(r.subdivision_type).strip() == "County" and _county_root_key(str(r.subdivision_name))
    }
    city_lookup = {
        _city_root_key(str(r.subdivision_name)): (str(r.subdivision_name), str(r.subdivision_code))
        for r in overlap_subdivisions.itertuples(index=False)
        if str(r.subdivision_type).strip() == "City" and _city_root_key(str(r.subdivision_name))
    }
    school_lookup = {
        _school_district_root_key(str(r.subdivision_name)): (str(r.subdivision_name), str(r.subdivision_code))
        for r in overlap_subdivisions.itertuples(index=False)
        if str(r.subdivision_type).strip() == "School District" and _school_district_root_key(str(r.subdivision_name))
    }
    county_lookup_keys = tuple(k for k in county_lookup.keys() if k)
    city_lookup_keys = tuple(k for k in city_lookup.keys() if k)

    for client, spend_vals in spend_lookup_local.items():
        entity_type = str(spend_vals.get("EntityType", "")).strip()
        if entity_type not in unsupported_types:
            continue
        low = float(spend_vals.get("Low", 0.0))
        high = float(spend_vals.get("High", 0.0))
        lob = int(spend_vals.get("Lobbyists", 0))

        matched_targets: list[tuple[str, str, str, str, str]] = []
        anchor_keys = _resolve_special_anchor_keys(
            client_name=client,
            entity_type=entity_type,
            county_lookup_keys=county_lookup_keys,
            city_lookup_keys=city_lookup_keys,
        )
        county_key = str(anchor_keys.get("county_key", "")).strip()
        if county_key and county_key in county_lookup:
            n, c = county_lookup[county_key]
            matched_targets.append(("County", n, c, "Name anchored", "Name anchored via overlapping core boundaries"))

        city_key = str(anchor_keys.get("city_key", "")).strip()
        if city_key and city_key in city_lookup:
            n, c = city_lookup[city_key]
            matched_targets.append(("City", n, c, "Name anchored", "Name anchored via overlapping core boundaries"))

        school_key = _school_district_root_key(client)
        if school_key and school_key in school_lookup:
            n, c = school_lookup[school_key]
            matched_targets.append(("School District", n, c, "Name anchored", "Name anchored via overlapping core boundaries"))

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
                n, c = county_lookup[geo_county_key]
                matched_targets.append(("County", n, c, "Name + geocode context", "ArcGIS geocoded entity centroid (Texas)"))

            geo_city = str(geocoded.get("city", "")).strip()
            geo_city_key = _city_root_key(f"{geo_city} City") if geo_city else ""
            if geo_city_key and geo_city_key in city_lookup:
                n, c = city_lookup[geo_city_key]
                matched_targets.append(("City", n, c, "Name + geocode context", "ArcGIS geocoded entity centroid (Texas)"))

        for t, n, c, match_method, map_source in matched_targets:
            row_key = (t, n, c, client)
            if row_key in existing_keys:
                continue
            rows.append(
                {
                    "Subdivision Type": t,
                    "Subdivision": n,
                    "Code": c,
                    "Entity Type": entity_type,
                    "TFL Entity": client,
                    "Match Method": match_method,
                    "Match Confidence": _match_confidence_from_method(match_method),
                    "Map Source": map_source,
                    "Low": low,
                    "High": high,
                    "Mid": (low + high) / 2,
                    "Lobbyists": lob,
                }
            )
            existing_keys.add(row_key)

    if not rows:
        return pd.DataFrame(columns=cols)

    out = pd.DataFrame(rows, columns=cols)
    out["_method_order"] = out["Match Method"].map(
        {
            "Spatial boundary (code)": 0,
            "Spatial boundary (name)": 1,
            "Spatial boundary (fuzzy)": 2,
            "Name anchored": 3,
            "Name + geocode context": 4,
        }
    ).fillna(9)
    out = out.sort_values(
        ["_method_order", "Mid", "High", "Low", "Subdivision Type", "Subdivision", "TFL Entity"],
        ascending=[True, False, False, False, True, True, True],
    )
    out = out.drop_duplicates(["Subdivision Type", "Subdivision", "Code", "TFL Entity"], keep="first")
    out = out.drop(columns=["_method_order"], errors="ignore")
    return out

def _subdivision_color_hex(subdivision_type: str) -> str:
    key = str(subdivision_type).strip()
    return SUBDIVISION_TYPE_COLORS.get(key, "#718191")

def _hex_to_rgba(color_hex: str, alpha: float = 0.88) -> list[float]:
    color = str(color_hex).strip().lstrip("#")
    if len(color) != 6 or not re.match(r"^[0-9a-fA-F]{6}$", color):
        return [113, 129, 145, alpha]
    return [int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16), alpha]

def render_subdivision_map_legend(type_counts: dict[str, int]) -> None:
    items = []
    for subtype, count in sorted(type_counts.items(), key=lambda x: (-int(x[1]), str(x[0]))):
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
    cols = [
        "subdivision_type",
        "subdivision_name",
        "subdivision_code",
        "lon",
        "lat",
        "match_count",
        "high_total",
        "match_method",
        "source_name",
    ]
    if overlap_subdivisions.empty or subdivision_matches.empty:
        return pd.DataFrame(columns=cols)

    rows: list[dict] = []
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
                base_pool = subdivision_matches[
                    subdivision_matches["subdivision_type"].astype(str) == subdivision_type
                ]
                pool_cache[subdivision_type] = _prepare_subdivision_match_pool(base_pool, subdivision_type)
            pool = pool_cache.get(subdivision_type, pd.DataFrame())
        if pool.empty:
            continue

        picked, match_method = _pick_overlap_subdivision_matches(
            pool,
            subdivision_type,
            subdivision_name,
            subdivision_code,
        )
        if picked.empty:
            continue

        picked["match_count"] = pd.to_numeric(picked.get("match_count", 0), errors="coerce").fillna(0)
        picked = picked.sort_values(["match_count"], ascending=[False])
        best = picked.iloc[0]

        key = (subdivision_type, subdivision_name, subdivision_code)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        rows.append(
            {
                "subdivision_type": subdivision_type,
                "subdivision_name": subdivision_name,
                "subdivision_code": subdivision_code,
                "lon": float(best.get("lon", 0.0)),
                "lat": float(best.get("lat", 0.0)),
                "match_count": int(float(best.get("match_count", 0.0))),
                "high_total": float(best.get("high_total", 0.0)),
                "match_method": match_method or "Spatial boundary (name)",
                "source_name": str(best.get("source_name", "")).strip(),
            }
        )

    # Include name-anchored special-type points when their inferred county/city anchor
    # is present in the overlapping core boundaries for this address.
    overlap_county_keys = {
        _county_root_key(str(r.subdivision_name))
        for r in overlap_subdivisions.itertuples(index=False)
        if str(r.subdivision_type).strip() == "County" and _county_root_key(str(r.subdivision_name))
    }
    overlap_city_keys = {
        _city_root_key(str(r.subdivision_name))
        for r in overlap_subdivisions.itertuples(index=False)
        if str(r.subdivision_type).strip() == "City" and _city_root_key(str(r.subdivision_name))
    }
    if overlap_county_keys or overlap_city_keys:
        special_types = set(SPECIAL_NAME_ANCHORED_ENTITY_TYPES) | {"Housing Authority"}
        special_matches = subdivision_matches[
            subdivision_matches["subdivision_type"].astype(str).isin(special_types)
        ]
        county_lookup_keys = tuple(sorted(overlap_county_keys))
        city_lookup_keys = tuple(sorted(overlap_city_keys))
        for row in special_matches.itertuples(index=False):
            subdivision_type = str(getattr(row, "subdivision_type", "")).strip()
            subdivision_name = str(getattr(row, "subdivision_name", "")).strip()
            subdivision_code = str(getattr(row, "subdivision_code", "")).strip()
            if not subdivision_type or not subdivision_name:
                continue

            clients = getattr(row, "match_clients", [])
            client_list = clients if isinstance(clients, list) else []
            if not client_list:
                client_list = [subdivision_name]

            include_point = False
            for client_name in client_list:
                anchor_keys = _resolve_special_anchor_keys(
                    client_name=str(client_name),
                    entity_type=subdivision_type,
                    county_lookup_keys=county_lookup_keys,
                    city_lookup_keys=city_lookup_keys,
                )
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

            rows.append(
                {
                    "subdivision_type": subdivision_type,
                    "subdivision_name": subdivision_name,
                    "subdivision_code": subdivision_code,
                    "lon": float(getattr(row, "lon", 0.0)),
                    "lat": float(getattr(row, "lat", 0.0)),
                    "match_count": int(getattr(row, "match_count", 0) or 0),
                    "high_total": float(getattr(row, "high_total", 0.0) or 0.0),
                    "match_method": "Name anchored",
                    "source_name": str(getattr(row, "source_name", "")).strip(),
                }
            )

    if not rows:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame(rows, columns=cols).drop_duplicates(
        ["subdivision_type", "subdivision_name", "subdivision_code"]
    )
    return out.sort_values(["subdivision_type", "subdivision_name"], ascending=[True, True])

    if not rows:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame(rows, columns=cols).drop_duplicates(
        ["subdivision_type", "subdivision_name", "subdivision_code"]
    )
    return out.sort_values(["subdivision_type", "subdivision_name"], ascending=[True, True])


# =================================================================
# DRAW AREA & SEARCH ADDRESS MAP COMPONENT
# =================================================================
def render_draw_area_search_map(
    height: int = 520,
    basemap: str = "gray-vector",
    map_id: str = "tfl-draw-area-map",
    markers: list[dict] | None = None,
) -> None:
    """Render an ArcGIS JS 4.30 map with drawing tools, address search,
    click-to-reverse-geocode, and an address collector panel.

    Users can:
    * Click anywhere on the map to reverse-geocode that point
    * Use the Search widget to find an address
    * Draw polygon / circle / rectangle areas; all click-points within
      the area are collected
    * Copy discovered addresses from the in-map panel

    The map posts messages (``tfl-draw-address-found``, ``tfl-draw-area-addresses``)
    via ``window.parent.postMessage`` so that the Python layer can listen
    for them (via adjacent Streamlit widgets that manually capture the data).

    Parameters
    ----------
    height : int
        Map container height in pixels.
    basemap : str
        ArcGIS basemap identifier (``"gray-vector"``, ``"streets-vector"``, ``"hybrid"``).
    map_id : str
        HTML element id for the map container (must be unique per page render).
    markers : list[dict] | None
        Optional list of ``{"lat": float, "lon": float, "label": str}`` dicts
        to render pre-existing pins on the map (e.g. docket entity addresses).
    """
    basemap_safe = json.dumps(str(basemap).strip() or "gray-vector")
    markers_json = json.dumps(markers or [], ensure_ascii=True)
    draw_map_signature = _stable_json_signature(
        {
            "map_id": str(map_id).strip(),
            "markers": markers or [],
            "basemap": str(basemap).strip() or "gray-vector",
            "height": int(height),
        }
    )
    draw_map_cache_key = re.sub(r"[^0-9A-Za-z_]+", "_", str(map_id).strip()) or "tfl_draw_area_map"
    arcgis_html = _session_cached_value(
        f"_mp5_draw_map_html_{draw_map_cache_key}_v1",
        draw_map_signature,
        lambda: f"""
<link rel="stylesheet" href="https://js.arcgis.com/4.30/esri/themes/dark/main.css"/>
<style>
  #{map_id} {{ width:100%; height:{height}px; border-radius:14px; overflow:hidden; position:relative; }}

  /* Dark popup */
  .esri-popup__main-container {{
    background:rgba(13,23,36,0.96) !important; color:rgba(220,230,240,0.95) !important;
    border:1px solid rgba(100,140,180,0.22) !important; border-radius:10px !important;
    backdrop-filter:blur(10px) !important; box-shadow:0 8px 32px rgba(0,0,0,0.45) !important;
  }}
  .esri-popup__header-title {{ color:rgba(235,242,250,0.97) !important; font-weight:600 !important; }}
  .esri-popup__content {{ color:rgba(200,215,230,0.92) !important; }}
  .esri-popup__button {{ color:rgba(180,200,220,0.85) !important; }}
  .esri-popup__button:hover {{ color:#fff !important; background:rgba(100,180,255,0.18) !important; }}
  .esri-sketch {{ background:rgba(13,23,36,0.92) !important; border-radius:8px !important; border:1px solid rgba(100,140,180,0.22) !important; }}

  /* Coordinate bar */
  #tfl-draw-coord {{
    position:absolute; bottom:6px; left:50%; transform:translateX(-50%); z-index:90;
    background:rgba(10,20,32,0.88); border:1px solid rgba(100,140,180,0.15);
    border-radius:8px; padding:3px 10px; font-family:'Avenir Next LT Pro',system-ui,sans-serif;
    font-size:10.5px; color:rgba(180,200,220,0.75); white-space:nowrap;
    backdrop-filter:blur(6px); pointer-events:none;
  }}

  /* Address collector panel */
  #tfl-draw-collector {{
    position:absolute; top:12px; right:12px; z-index:95;
    background:rgba(10,20,32,0.94); border:1px solid rgba(30,144,255,0.22);
    border-radius:12px; padding:10px 12px; min-width:240px; max-width:300px;
    font-family:'Avenir Next LT Pro',system-ui,sans-serif; font-size:11.5px;
    color:rgba(210,225,240,0.90); backdrop-filter:blur(10px);
    max-height:{height - 40}px; overflow-y:auto;
    box-shadow:0 8px 28px rgba(0,0,0,0.40);
  }}
  #tfl-draw-collector .dc-title {{
    text-transform:uppercase; letter-spacing:0.14em; font-size:8.5px;
    color:rgba(30,144,255,0.82); font-weight:700; margin-bottom:6px;
    display:flex; align-items:center; justify-content:space-between;
  }}
  #tfl-draw-collector .dc-item {{
    display:flex; align-items:flex-start; gap:6px; padding:5px 0;
    border-bottom:1px solid rgba(255,255,255,0.06);
  }}
  #tfl-draw-collector .dc-item:last-child {{ border-bottom:none; }}
  #tfl-draw-collector .dc-num {{
    flex-shrink:0; width:18px; height:18px; border-radius:50%;
    background:rgba(30,144,255,0.18); border:1px solid rgba(30,144,255,0.30);
    display:flex; align-items:center; justify-content:center;
    font-size:9px; font-weight:700; color:rgba(30,144,255,0.90);
  }}
  #tfl-draw-collector .dc-addr {{
    font-size:11px; line-height:1.35; color:rgba(210,230,245,0.85);
  }}
  #tfl-draw-collector .dc-coord {{
    font-size:9px; color:rgba(160,185,210,0.55); margin-top:1px;
  }}
  #tfl-draw-collector .dc-empty {{
    text-align:center; padding:10px 0; color:rgba(180,200,220,0.45); font-size:10.5px;
  }}
  #tfl-draw-collector .dc-actions {{
    display:flex; gap:6px; margin-top:6px;
  }}
  #tfl-draw-collector .dc-btn {{
    flex:1; padding:5px 8px; border-radius:8px; border:1px solid rgba(30,144,255,0.25);
    background:rgba(30,144,255,0.10); color:rgba(30,144,255,0.90); cursor:pointer;
    font-size:10px; font-weight:600; text-align:center; transition:all 0.2s;
  }}
  #tfl-draw-collector .dc-btn:hover {{ background:rgba(30,144,255,0.22); border-color:rgba(30,144,255,0.40); }}
  #tfl-draw-collector .dc-btn.clear {{ background:rgba(255,80,80,0.08); border-color:rgba(255,80,80,0.20); color:rgba(255,120,120,0.85); }}
  #tfl-draw-collector .dc-btn.clear:hover {{ background:rgba(255,80,80,0.18); }}
  #tfl-draw-badge {{
    position:absolute; top:12px; left:12px; z-index:95;
    background:rgba(10,20,32,0.90); border:1px solid rgba(0,224,184,0.22);
    border-radius:10px; padding:6px 12px; font-family:'Avenir Next LT Pro',system-ui,sans-serif;
    font-size:10.5px; color:rgba(0,224,184,0.85); backdrop-filter:blur(8px);
  }}

  /* Loading overlay */
  @keyframes tfl-draw-pulse {{ 0%,100%{{transform:scale(1);opacity:0.92;}} 50%{{transform:scale(1.35);opacity:0.45;}} }}
  #tfl-draw-loading {{
    position:absolute; top:0; left:0; width:100%; height:100%;
    background:rgba(10,16,26,0.92); display:flex; flex-direction:column;
    align-items:center; justify-content:center; z-index:100;
    transition:opacity 0.5s ease;
  }}
  #tfl-draw-loading .ld-dot {{
    width:10px; height:10px; border-radius:50%; background:rgba(30,144,255,0.82);
    animation:tfl-draw-pulse 1.2s ease-in-out infinite;
  }}
  #tfl-draw-loading .ld-text {{
    margin-top:8px; font-family:'Avenir Next LT Pro',system-ui,sans-serif;
    font-size:11px; color:rgba(180,200,220,0.65);
  }}

  /* Pin markers */
  .tfl-pin-marker {{
    width:10px; height:10px; border-radius:50%;
    background:rgba(0,224,184,0.85); border:2px solid rgba(255,255,255,0.70);
    box-shadow:0 2px 8px rgba(0,0,0,0.35);
  }}
</style>

<div id="{map_id}" style="position:relative;">
  <div id="tfl-draw-loading"><div class="ld-dot"></div><div class="ld-text">Initializing map\u2026</div></div>
  <div id="tfl-draw-coord">\u2014</div>
  <div id="tfl-draw-badge">Click map or search to collect addresses</div>
  <div id="tfl-draw-collector">
    <div class="dc-title"><span>&#x1F4CD; Collected Addresses</span><span id="tfl-draw-count">0</span></div>
    <div id="tfl-draw-list"><div class="dc-empty">Click on the map, use Search, or draw an area to collect addresses.</div></div>
    <div class="dc-actions">
      <div class="dc-btn" id="tfl-draw-copy-btn">Copy All</div>
      <div class="dc-btn clear" id="tfl-draw-clear-btn">Clear</div>
    </div>
  </div>
</div>

<script src="https://js.arcgis.com/4.30/"></script>
<script>
  require([
    "esri/Map", "esri/views/MapView", "esri/layers/GraphicsLayer",
    "esri/Graphic", "esri/widgets/Home", "esri/widgets/BasemapToggle",
    "esri/widgets/ScaleBar", "esri/widgets/Compass", "esri/widgets/Fullscreen",
    "esri/widgets/Locate", "esri/widgets/Search", "esri/widgets/Sketch",
    "esri/widgets/Expand", "esri/geometry/geometryEngine",
    "esri/layers/FeatureLayer", "esri/rest/locator"
  ], (Map, MapView, GraphicsLayer, Graphic, Home, BasemapToggle, ScaleBar,
      Compass, Fullscreen, Locate, Search, Sketch, Expand, geometryEngine,
      FeatureLayer, locator) => {{

    const collectedAddresses = [];
    const markersLayer = new GraphicsLayer();
    const sketchLayer = new GraphicsLayer();
    const pinsLayer = new GraphicsLayer();

    /* Reference layers */
    const countyLayer = new FeatureLayer({{
      url: "{TEA_ARCGIS_COUNTY_LAYER_URL}",
      opacity: 0.35, labelsVisible: false, popupEnabled: false,
      renderer: {{ type:"simple", symbol:{{ type:"simple-fill", color:[0,0,0,0], outline:{{ color:[180,200,220,0.3], width:0.6 }} }} }}
    }});
    const cityLayer = new FeatureLayer({{
      url: "{CENSUS_ARCGIS_TEXAS_CITY_LAYER_URL}",
      definitionExpression: "STATE='48'", opacity: 0.30, labelsVisible: false, visible: false, popupEnabled: false,
      renderer: {{ type:"simple", symbol:{{ type:"simple-fill", color:[0,0,0,0], outline:{{ color:[150,190,210,0.25], width:0.5 }} }} }}
    }});
    const districtLayer = new FeatureLayer({{
      url: "{TEA_ARCGIS_SCHOOL_DISTRICT_LAYER_URL}",
      opacity: 0.25, labelsVisible: false, visible: false, popupEnabled: false,
      renderer: {{ type:"simple", symbol:{{ type:"simple-fill", color:[0,0,0,0], outline:{{ color:[100,160,200,0.22], width:0.4 }} }} }}
    }});

    const map = new Map({{
      basemap: {basemap_safe},
      layers: [countyLayer, cityLayer, districtLayer, markersLayer, pinsLayer, sketchLayer]
    }});

    const view = new MapView({{
      container: "{map_id}",
      map, center: [-99.0, 31.2], zoom: 6,
      constraints: {{ minZoom: 4, maxZoom: 18 }},
      popup: {{ dockEnabled: true, dockOptions: {{ breakpoint: false, position: "bottom-left" }} }}
    }});

    /* Pre-existing markers */
    const preMarkers = {markers_json};
    preMarkers.forEach((m, i) => {{
      markersLayer.add(new Graphic({{
        geometry: {{ type: "point", longitude: m.lon, latitude: m.lat }},
        symbol: {{ type: "simple-marker", style: "diamond", size: 11, color: [0,224,184,0.85], outline: {{ color: [255,255,255,0.75], width: 1.5 }} }},
        attributes: {{ label: m.label || "", lat: m.lat, lon: m.lon }},
        popupTemplate: {{ title: m.label || "Marker " + (i+1), content: "Lat: " + m.lat.toFixed(5) + ", Lon: " + m.lon.toFixed(5) }}
      }}));
    }});

    /* Geocoder URL */
    const geocodeUrl = "{ARCGIS_GEOCODER_URL}";

    /* Helpers */
    function updateCollectorUI() {{
      const listEl = document.getElementById("tfl-draw-list");
      const countEl = document.getElementById("tfl-draw-count");
      if (countEl) countEl.textContent = collectedAddresses.length;
      if (!listEl) return;
      if (collectedAddresses.length === 0) {{
        listEl.innerHTML = '<div class="dc-empty">Click on the map, use Search, or draw an area to collect addresses.</div>';
        return;
      }}
      listEl.innerHTML = collectedAddresses.map((a, i) =>
        '<div class="dc-item">'
        + '<div class="dc-num">' + (i + 1) + '</div>'
        + '<div><div class="dc-addr">' + (a.address || "Unknown") + '</div>'
        + '<div class="dc-coord">' + Number(a.lat).toFixed(5) + '\\u00b0 N, ' + Math.abs(a.lon).toFixed(5) + '\\u00b0 W</div>'
        + '</div></div>'
      ).join("");
    }}

    function addAddress(address, lat, lon) {{
      const exists = collectedAddresses.some(a =>
        Math.abs(a.lat - lat) < 0.0001 && Math.abs(a.lon - lon) < 0.0001
      );
      if (exists) return;
      collectedAddresses.push({{ address, lat, lon }});

      /* Drop a pin */
      pinsLayer.add(new Graphic({{
        geometry: {{ type: "point", longitude: lon, latitude: lat }},
        symbol: {{ type: "simple-marker", style: "circle", size: 10, color: [30,144,255,0.85], outline: {{ color: [255,255,255,0.80], width: 1.5 }} }},
        attributes: {{ address, lat, lon }},
        popupTemplate: {{ title: address || "Point", content: "Lat: " + lat.toFixed(5) + ", Lon: " + lon.toFixed(5) }}
      }}));

      updateCollectorUI();

      /* Notify parent */
      try {{
        window.parent.postMessage({{
          type: "tfl-draw-address-found",
          address: address, lat: lat, lon: lon,
          allAddresses: collectedAddresses.slice()
        }}, "*");
      }} catch(e) {{}}
    }}

    function reverseGeocode(lat, lon) {{
      const url = geocodeUrl.replace("findAddressCandidates", "reverseGeocode")
        + "?location=" + lon + "," + lat
        + "&outSR=4326&langCode=en&f=json";
      fetch(url).then(r => r.json()).then(data => {{
        const addr = (data.address && data.address.LongLabel) || (data.address && data.address.ShortLabel) || ("Point: " + lat.toFixed(5) + ", " + lon.toFixed(5));
        addAddress(addr, lat, lon);
      }}).catch(() => {{
        addAddress("Point: " + lat.toFixed(5) + ", " + lon.toFixed(5), lat, lon);
      }});
    }}

    /* Click → reverse geocode */
    view.on("click", (evt) => {{
      if (evt.mapPoint) {{
        reverseGeocode(evt.mapPoint.latitude, evt.mapPoint.longitude);
      }}
    }});

    /* Coordinate readout */
    view.on("pointer-move", (evt) => {{
      const pt = view.toMap(evt);
      const el = document.getElementById("tfl-draw-coord");
      if (pt && el) el.textContent = pt.latitude.toFixed(5) + "\\u00b0 N, " + Math.abs(pt.longitude).toFixed(5) + "\\u00b0 W";
    }});

    /* Widgets */
    const home = new Home({{ view }});
    const basemapToggle = new BasemapToggle({{ view, nextBasemap: {basemap_safe} === "hybrid" ? "gray-vector" : "hybrid" }});
    const scaleBar = new ScaleBar({{ view, unit: "dual" }});
    const compass = new Compass({{ view }});
    const fullscreen = new Fullscreen({{ view }});
    const locate = new Locate({{ view }});

    const search = new Search({{
      view, popupEnabled: true, resultGraphicEnabled: true,
      goToOverride: (view, opts) => view.goTo(opts.target, {{ duration: 800, easing: "ease-in-out" }})
    }});
    search.on("select-result", (evt) => {{
      if (evt.result && evt.result.feature && evt.result.feature.geometry) {{
        const geom = evt.result.feature.geometry;
        addAddress(evt.result.name || "", geom.latitude, geom.longitude);
      }}
    }});

    const sketch = new Sketch({{
      view, layer: sketchLayer, creationMode: "single",
      availableCreateTools: ["polygon", "circle", "rectangle"],
      defaultCreateOptions: {{ mode: "freehand" }},
      visibleElements: {{ selectionTools: {{ "lasso-selection": false, "rectangle-selection": false }}, settingsMenu: false, undoRedoMenu: true }},
      defaultUpdateOptions: {{ tool: "reshape" }}
    }});
    const sketchExpand = new Expand({{
      view, content: sketch, expandIconClass: "esri-icon-polygon",
      expandTooltip: "Draw area to collect addresses", group: "tools"
    }});

    /* Layer toggle */
    const layerDiv = document.createElement("div");
    layerDiv.style.cssText = "background:rgba(13,23,36,0.94);border-radius:8px;padding:10px;font-family:'Avenir Next LT Pro',system-ui,sans-serif;font-size:12px;color:rgba(210,225,240,0.90);min-width:160px;";
    layerDiv.innerHTML = '<div style="font-size:9px;text-transform:uppercase;letter-spacing:0.12em;color:rgba(150,175,200,0.65);font-weight:700;margin-bottom:6px;">Reference Layers</div>'
      + '<label style="display:flex;align-items:center;gap:6px;cursor:pointer;padding:3px 0;"><input type="checkbox" id="tfl-draw-toggle-city" style="accent-color:#28b464;"><span>City Boundaries</span></label>'
      + '<label style="display:flex;align-items:center;gap:6px;cursor:pointer;padding:3px 0;"><input type="checkbox" id="tfl-draw-toggle-district" style="accent-color:#c88c3c;"><span>School Districts</span></label>';
    const layerExpand = new Expand({{ view, content: layerDiv, expandIconClass: "esri-icon-layer-list", expandTooltip: "Toggle reference layers", group: "tools" }});

    view.ui.add(home, "top-left");
    view.ui.add(compass, "top-left");
    view.ui.add(fullscreen, "top-left");
    view.ui.add(locate, "top-left");
    view.ui.add(sketchExpand, "top-left");
    view.ui.add(layerExpand, "top-left");
    view.ui.add(search, "top-right");
    view.ui.add(basemapToggle, "top-right");
    view.ui.add(scaleBar, "bottom-left");

    view.when(() => {{
      const cBox = document.getElementById("tfl-draw-toggle-city");
      const dBox = document.getElementById("tfl-draw-toggle-district");
      if (cBox) cBox.addEventListener("change", () => {{ cityLayer.visible = cBox.checked; }});
      if (dBox) dBox.addEventListener("change", () => {{ districtLayer.visible = dBox.checked; }});
    }});

    /* Sketch complete → reverse-geocode the centroid of the drawn area */
    sketch.on("create", (evt) => {{
      if (evt.state !== "complete") return;
      const geom = evt.graphic.geometry;
      const ext = geom.extent;
      if (!ext) return;

      /* Sample grid of points inside the drawn area for reverse geocoding */
      const cx = ext.center.longitude;
      const cy = ext.center.latitude;
      const dx = (ext.xmax - ext.xmin);
      const dy = (ext.ymax - ext.ymin);
      const SAMPLES = 5;
      const promises = [];

      /* Always geocode the centroid */
      reverseGeocode(cy, cx);

      /* Sample a NxN grid within the extent, but only inside the polygon */
      for (let xi = 0; xi < SAMPLES; xi++) {{
        for (let yi = 0; yi < SAMPLES; yi++) {{
          const px = ext.xmin + (dx * (xi + 0.5) / SAMPLES);
          const py = ext.ymin + (dy * (yi + 0.5) / SAMPLES);
          const testPt = {{ type: "point", longitude: px, latitude: py, spatialReference: {{ wkid: 4326 }} }};
          if (geometryEngine.contains(geom, testPt)) {{
            reverseGeocode(py, px);
          }}
        }}
      }}

      /* Update badge */
      const badge = document.getElementById("tfl-draw-badge");
      if (badge) badge.textContent = "Area scanned — see collected addresses \\u2192";

      /* Post area addresses */
      setTimeout(() => {{
        try {{
          window.parent.postMessage({{
            type: "tfl-draw-area-addresses",
            allAddresses: collectedAddresses.slice()
          }}, "*");
        }} catch(e) {{}}
      }}, 3000);
    }});

    /* Copy all button */
    document.getElementById("tfl-draw-copy-btn").addEventListener("click", () => {{
      if (collectedAddresses.length === 0) return;
      const text = collectedAddresses.map(a => a.address).join("\\n");
      navigator.clipboard.writeText(text).then(() => {{
        const btn = document.getElementById("tfl-draw-copy-btn");
        if (btn) {{ btn.textContent = "Copied!"; setTimeout(() => {{ btn.textContent = "Copy All"; }}, 2000); }}
      }}).catch(() => {{}});

      /* Also post to parent */
      try {{
        window.parent.postMessage({{
          type: "tfl-draw-copy-all",
          allAddresses: collectedAddresses.slice(),
          text: text
        }}, "*");
      }} catch(e) {{}}
    }});

    /* Clear button */
    document.getElementById("tfl-draw-clear-btn").addEventListener("click", () => {{
      collectedAddresses.length = 0;
      pinsLayer.removeAll();
      sketchLayer.removeAll();
      updateCollectorUI();
      const badge = document.getElementById("tfl-draw-badge");
      if (badge) badge.textContent = "Click map or search to collect addresses";
    }});

    /* Loading done */
    view.when(() => {{
      const loader = document.getElementById("tfl-draw-loading");
      if (loader) {{ loader.style.opacity = "0"; setTimeout(() => loader.remove(), 600); }}
      if (preMarkers.length > 0) {{
        view.goTo(markersLayer.graphics.toArray(), {{ padding: {{ top:50, right:50, bottom:50, left:50 }}, duration:1000, easing:"ease-in-out" }}).catch(() => {{}});
      }}
    }});
  }});
</script>
"""
    )
    _persistent_html_frame(
        html=arcgis_html,
        signature=draw_map_signature,
        height=int(height) + 8,
        key=f"mp5_draw_area_map_{draw_map_cache_key}_v1",
        default=None,
    )


def render_address_overlap_arcgis_map(
    lon: float,
    lat: float,
    matched_address: str,
    overlap_points: pd.DataFrame,
    height: int = 440,
    basemap: str = "gray-vector",
) -> None:
    try:
        lon_val = float(lon)
        lat_val = float(lat)
    except Exception:
        return

    # PERFORMANCE: Vectorized point_rows builder — avoids per-row itertuples + html.escape loop
    point_rows: list[dict] = []
    legend_types: dict[str, str] = {}
    if isinstance(overlap_points, pd.DataFrame) and not overlap_points.empty:
        _op = overlap_points.copy()
        for col in ("subdivision_type", "subdivision_name", "subdivision_code", "match_method", "source_name"):
            if col in _op.columns:
                _op[col] = _op[col].fillna("").astype(str).str.strip()
            else:
                _op[col] = ""
        _op["lon"] = pd.to_numeric(_op.get("lon", 0.0), errors="coerce").fillna(0.0)
        _op["lat"] = pd.to_numeric(_op.get("lat", 0.0), errors="coerce").fillna(0.0)
        _op["match_count"] = pd.to_numeric(_op.get("match_count", 0), errors="coerce").fillna(0).astype(int)
        _op["high_total"] = pd.to_numeric(_op.get("high_total", 0.0), errors="coerce").fillna(0.0)
        # Pre-compute colors and escape in bulk
        _color_cache: dict[str, list[float]] = {}
        for st_val in _op["subdivision_type"].unique():
            hex_c = _subdivision_color_hex(st_val)
            _color_cache[st_val] = _hex_to_rgba(hex_c)
            if st_val:
                legend_types[html.escape(st_val, quote=True)] = hex_c
        point_rows = [
            {
                "subdivision_type": html.escape(r.subdivision_type, quote=True),
                "subdivision_name": html.escape(r.subdivision_name, quote=True),
                "subdivision_code": html.escape(r.subdivision_code, quote=True),
                "lon": r.lon,
                "lat": r.lat,
                "match_count": r.match_count,
                "high_total": r.high_total,
                "match_method": html.escape(r.match_method, quote=True),
                "source_name": html.escape(r.source_name, quote=True),
                "color": _color_cache.get(r.subdivision_type, [113, 129, 145, 0.88]),
            }
            for r in _op.itertuples(index=False)
        ]
        del _op

    points_json = json.dumps(point_rows, ensure_ascii=True)
    address_json = json.dumps(
        {
            "lon": lon_val,
            "lat": lat_val,
            "matched_address": html.escape(str(matched_address).strip(), quote=True),
        },
        ensure_ascii=True,
    )
    basemap_safe = json.dumps(str(basemap).strip() or "gray-vector")

    legend_json = json.dumps(
        [{"type": t, "color": c} for t, c in legend_types.items()],
        ensure_ascii=True,
    )
    address_map_signature = _stable_json_signature(
        {
            "address": {
                "lon": lon_val,
                "lat": lat_val,
                "matched_address": str(matched_address).strip(),
            },
            "points": point_rows,
            "basemap": str(basemap).strip() or "gray-vector",
            "height": int(height),
        }
    )
    arcgis_html = _session_cached_value(
        "_mp5_address_overlap_html_v2",
        address_map_signature,
        lambda: f"""
<link rel="preload" href="https://js.arcgis.com/4.30/" as="script"/>
<link rel="stylesheet" href="https://js.arcgis.com/4.30/esri/themes/dark/main.css"/>
<style>
  /* -- Dark popup theme -- */
  .esri-popup__main-container {{
    background: rgba(13,23,36,0.96) !important;
    color: rgba(220,230,240,0.95) !important;
    border: 1px solid rgba(100,140,180,0.22) !important;
    border-radius: 10px !important;
    backdrop-filter: blur(10px) !important;
    box-shadow: 0 8px 32px rgba(0,0,0,0.45) !important;
  }}
  .esri-popup__header-title {{ color: rgba(235,242,250,0.97) !important; font-weight: 600 !important; }}
  .esri-popup__content {{ color: rgba(200,215,230,0.92) !important; }}
  .esri-popup__button {{ color: rgba(180,200,220,0.85) !important; }}
  .esri-popup__button:hover {{ color: #fff !important; background: rgba(100,180,255,0.18) !important; }}
  .esri-popup__pointer-direction {{ background: rgba(13,23,36,0.96) !important; }}

  /* -- Sketch toolbar styling -- */
  .esri-sketch {{ background: rgba(13,23,36,0.92) !important; border-radius: 8px !important; border: 1px solid rgba(100,140,180,0.22) !important; }}

  /* -- Legend — bottom-right, compact -- */
  #tfl-addr-legend {{
    position: absolute; bottom: 36px; right: 12px; z-index: 90;
    background: rgba(10,20,32,0.92); border: 1px solid rgba(100,140,180,0.18);
    border-radius: 10px; padding: 6px 10px; max-width: 210px;
    font-family: 'Avenir Next LT Pro', system-ui, sans-serif; font-size: 10.5px;
    color: rgba(210,225,240,0.90); backdrop-filter: blur(8px);
    max-height: 160px; overflow-y: auto;
  }}
  #tfl-addr-legend .leg-title {{
    text-transform: uppercase; letter-spacing: 0.14em; font-size: 8px;
    color: rgba(150,175,200,0.70); margin-bottom: 3px; font-weight: 700;
  }}
  #tfl-addr-legend .leg-row {{ display: flex; align-items: center; gap: 5px; padding: 1.5px 0; }}
  #tfl-addr-legend .leg-chip {{
    width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0;
    border: 1px solid rgba(255,255,255,0.18);
  }}

  /* -- Loading overlay -- */
  @keyframes tfl-pulse {{ 0%,100% {{ transform:scale(1); opacity:0.92; }} 50% {{ transform:scale(1.35); opacity:0.45; }} }}
  #tfl-addr-loading {{
    position:absolute; top:0; left:0; width:100%; height:100%;
    background:rgba(10,16,26,0.92); display:flex; flex-direction:column;
    align-items:center; justify-content:center; gap:10px;
    z-index:100; border-radius:14px; transition:opacity 0.6s ease;
  }}
  #tfl-addr-loading .ld-spinner {{
    width:30px; height:30px; border:2.5px solid rgba(100,140,180,0.18);
    border-top:2.5px solid rgba(100,180,255,0.80); border-radius:50%;
    animation: tfl-ld-spin 0.8s linear infinite;
  }}
  #tfl-addr-loading .ld-label {{
    font-family:'Avenir Next LT Pro',system-ui,sans-serif; font-size:10px;
    color:rgba(160,185,210,0.65); letter-spacing:0.06em;
  }}
  @keyframes tfl-ld-spin {{ 0%{{transform:rotate(0deg)}} 100%{{transform:rotate(360deg)}} }}

  /* -- Coordinate bar -- */
  #tfl-addr-coord {{
    position:absolute; bottom:10px; left:50%; transform:translateX(-50%); z-index:90;
    background:rgba(10,16,26,0.85); border:1px solid rgba(100,140,180,0.15);
    border-radius:6px; padding:2px 10px;
    font-family:'Avenir Next LT Pro',system-ui,sans-serif; font-size:10px;
    color:rgba(180,200,220,0.75); pointer-events:none; backdrop-filter:blur(6px);
    white-space:nowrap; letter-spacing:0.04em;
  }}

  /* -- Lasso/selection feedback -- */
  #tfl-addr-sel-info {{
    position:absolute; bottom:36px; left:12px; z-index:90;
    background:rgba(10,16,26,0.92); border:1px solid rgba(0,180,255,0.25);
    border-radius:8px; padding:6px 12px; backdrop-filter:blur(6px);
    font-family:'Avenir Next LT Pro',system-ui,sans-serif; font-size:11px;
    color:rgba(200,220,240,0.90); display:none; max-width:280px;
  }}
  #tfl-addr-sel-info .sel-title {{
    font-weight:700; color:rgba(100,200,255,0.95); font-size:10px;
    text-transform:uppercase; letter-spacing:0.08em; margin-bottom:3px;
  }}
  #tfl-addr-adv-btn {{
    position:absolute; top:12px; right:12px; z-index:95;
    border:1px solid rgba(100,180,255,0.32);
    background:rgba(10,20,32,0.92);
    color:rgba(190,220,245,0.92);
    border-radius:8px;
    padding:5px 10px;
    font-family:'Avenir Next LT Pro',system-ui,sans-serif;
    font-size:10px;
    letter-spacing:0.04em;
    cursor:pointer;
    backdrop-filter:blur(6px);
    transition:all .2s ease;
  }}
  #tfl-addr-adv-btn:hover {{
    border-color:rgba(100,180,255,0.52);
    background:rgba(16,34,52,0.95);
  }}
  #tfl-addr-adv-btn[disabled] {{
    opacity:0.7;
    cursor:default;
  }}
</style>
<div style="width:100%;height:{height}px;position:relative;">
  <div id="tfl-address-overlap-map" style="width:100%;height:100%;border-radius:14px;overflow:hidden;"></div>
  <div id="tfl-addr-legend"></div>
  <button id="tfl-addr-adv-btn" type="button">Load advanced tools</button>
  <div id="tfl-addr-loading"><div class="ld-spinner"></div><div class="ld-label">Loading map layers&hellip;</div></div>
  <div id="tfl-addr-coord">&ndash;</div>
  <div id="tfl-addr-sel-info"></div>
</div>
<script src="https://js.arcgis.com/4.30/"></script>
<script>
  const overlapPoints = {points_json};
  const addressPoint = {address_json};
  const baseMapId = {basemap_safe};
  const legendEntries = {legend_json};
  const advBtn = document.getElementById("tfl-addr-adv-btn");
  const scheduleAdvancedLoad = (fn) => {{
    if (typeof window.requestIdleCallback === "function") {{
      window.requestIdleCallback(fn, {{ timeout: 2600 }});
    }} else {{
      setTimeout(fn, 1500);
    }}
  }};

  /* Build on-map legend */
  (function() {{
    const el = document.getElementById("tfl-addr-legend");
    if (!el || legendEntries.length === 0) {{ if (el) el.style.display = "none"; return; }}
    let h = '<div class="leg-title">Subdivision Types</div>';
    for (const e of legendEntries) {{
      h += '<div class="leg-row"><span class="leg-chip" style="background:' + e.color + ';"></span><span>' + e.type + '</span></div>';
    }}
    h += '<div class="leg-row" style="margin-top:2px;"><span class="leg-chip" style="background:#c92234;transform:rotate(45deg);border-radius:2px;"></span><span>Queried Address</span></div>';
    el.innerHTML = h;
  }})();

  require([
    "esri/Map",
    "esri/views/MapView",
    "esri/layers/GraphicsLayer",
    "esri/Graphic",
    "esri/widgets/Home",
    "esri/widgets/ScaleBar",
    "esri/widgets/BasemapToggle"
  ], function(Map, MapView, GraphicsLayer, Graphic, Home, ScaleBar, BasemapToggle) {{
    const map = new Map({{ basemap: baseMapId }});

    const overlapLayer = new GraphicsLayer();
    const addressLayer = new GraphicsLayer();
    const sketchLayer = new GraphicsLayer();
    map.add(overlapLayer);
    map.add(addressLayer);
    map.add(sketchLayer);

    const view = new MapView({{
      container: "tfl-address-overlap-map",
      map,
      center: [addressPoint.lon, addressPoint.lat],
      zoom: 11,
      constraints: {{ minZoom: 5 }},
      popup: {{ dockEnabled: true, dockOptions: {{ position: "bottom-right", breakpoint: false }} }},
      ui: {{ padding: {{ top: 10, right: 10, bottom: 30, left: 10 }} }}
    }});

    const formatUsd = (v) => Number(v||0).toLocaleString("en-US",{{style:"currency",currency:"USD",maximumFractionDigits:0}});
    const maxHigh = overlapPoints.reduce((a,r) => Math.max(a, Number(r.high_total||0)), 0);
    const sz = (v) => {{ if(maxHigh<=0) return 10; const n=Math.max(0,Number(v||0)); return Math.max(9,Math.min(28,9+(Math.log10(n+1)/Math.log10(maxHigh+1))*19)); }};
    const badge = (m) => {{
      const l=(m||"").toLowerCase();
      if(l.includes("spatial")||l.includes("boundary")) return '<span style="display:inline-block;padding:1px 6px;border-radius:5px;font-size:9.5px;font-weight:600;background:rgba(0,200,140,0.18);color:#00c88c;">Spatial</span>';
      if(l.includes("name")||l.includes("anchor")) return '<span style="display:inline-block;padding:1px 6px;border-radius:5px;font-size:9.5px;font-weight:600;background:rgba(255,180,40,0.18);color:#ffb428;">Name-anchored</span>';
      return '<span style="display:inline-block;padding:1px 6px;border-radius:5px;font-size:9.5px;font-weight:600;background:rgba(130,145,160,0.18);color:#8291a0;">Unknown</span>';
    }};

    /* -- Render overlap points and address marker immediately (no layer fetch needed) -- */
    for (const row of overlapPoints) {{
      const g = new Graphic({{
        geometry: {{ type: "point", longitude: row.lon, latitude: row.lat }},
        symbol: {{
          type: "simple-marker", size: sz(row.high_total),
          color: row.color || [113,129,145,0.85],
          outline: {{ color: [255,255,255,0.70], width: 1 }}
        }},
        attributes: row,
        popupTemplate: {{
          title: row.subdivision_name || "Overlapping subdivision",
          content: `<div style="font-family:'Avenir Next LT Pro',system-ui,sans-serif;font-size:12px;line-height:1.5;">
            <div style="margin-bottom:5px;">${{badge(row.match_method)}}</div>
            <table style="border-collapse:collapse;width:100%;">
              <tr><td style="color:#7a94ab;padding:2px 6px 2px 0;font-size:11px;">Type</td><td style="font-weight:600;">${{row.subdivision_type||"N/A"}}</td></tr>
              <tr><td style="color:#7a94ab;padding:2px 6px 2px 0;font-size:11px;">Code</td><td>${{row.subdivision_code||"N/A"}}</td></tr>
              <tr><td style="color:#7a94ab;padding:2px 6px 2px 0;font-size:11px;">Matched clients</td><td style="font-weight:600;">${{row.match_count||0}}</td></tr>
              <tr><td style="color:#7a94ab;padding:2px 6px 2px 0;font-size:11px;">TFL high est.</td><td style="font-weight:600;">${{formatUsd(row.high_total)}}</td></tr>
              <tr><td style="color:#7a94ab;padding:2px 6px 2px 0;font-size:11px;">Method</td><td>${{row.match_method||"N/A"}}</td></tr>
              <tr><td style="color:#7a94ab;padding:2px 6px 2px 0;font-size:11px;">Source</td><td>${{row.source_name||"N/A"}}</td></tr>
            </table>
          </div>`
        }}
      }});
      overlapLayer.add(g);
    }}

    /* Address marker with pulse */
    addressLayer.add(new Graphic({{
      geometry: {{ type: "point", longitude: addressPoint.lon, latitude: addressPoint.lat }},
      symbol: {{ type: "simple-marker", style: "circle", size: 24, color: [201,34,52,0.0], outline: {{ color: [201,34,52,0.50], width: 2 }} }}
    }}));
    addressLayer.add(new Graphic({{
      geometry: {{ type: "point", longitude: addressPoint.lon, latitude: addressPoint.lat }},
      symbol: {{ type: "simple-marker", style: "diamond", size: 14, color: [201,34,52,0.95], outline: {{ color: [255,255,255,0.90], width: 1.8 }} }},
      popupTemplate: {{
        title: "Queried Address",
        content: `<div style="font-family:'Avenir Next LT Pro',system-ui,sans-serif;font-size:12px;">
          <div style="font-weight:600;margin-bottom:3px;">${{addressPoint.matched_address||"Address point"}}</div>
          <div style="color:#7a94ab;font-size:10.5px;">Lat ${{Number(addressPoint.lat).toFixed(5)}}, Lon ${{Number(addressPoint.lon).toFixed(5)}}</div>
        </div>`
      }}
    }}));

    /* -- Essential widgets (loaded in initial bundle) -- */
    const home = new Home({{ view }});
    const basemapToggle = new BasemapToggle({{ view, nextBasemap: baseMapId === "hybrid" ? "gray-vector" : "hybrid" }});
    const scaleBar = new ScaleBar({{ view, unit: "dual" }});
    view.ui.add(home, "top-left");
    view.ui.add(basemapToggle, "top-right");
    view.ui.add(scaleBar, "bottom-left");

    /* Coordinate readout */
    view.on("pointer-move", (evt) => {{
      const pt = view.toMap(evt);
      const el = document.getElementById("tfl-addr-coord");
      if (pt && el) el.textContent = pt.latitude.toFixed(5) + "\u00b0 N, " + Math.abs(pt.longitude).toFixed(5) + "\u00b0 W";
    }});

    /* Hover highlight */
    let hoverHL = null;
    view.on("pointer-move", (evt) => {{
      view.hitTest(evt, {{ include: [overlapLayer] }}).then((r) => {{
        const hit = r.results && r.results.find(x => x.graphic);
        document.getElementById("tfl-address-overlap-map").style.cursor = hit ? "pointer" : "default";
        if (hoverHL) {{ overlapLayer.remove(hoverHL); hoverHL = null; }}
        if (hit && hit.graphic && hit.graphic.geometry) {{
          hoverHL = new Graphic({{
            geometry: hit.graphic.geometry,
            symbol: {{ type: "simple-marker", style: "circle", size: 32, color: [255,255,255,0.0], outline: {{ color: [255,255,255,0.55], width: 2 }} }}
          }});
          overlapLayer.add(hoverHL);
        }}
      }});
    }});

    /* -- Phase 1: View ready — dismiss loading overlay and zoom to graphics -- */
    view.when(() => {{
      const loader = document.getElementById("tfl-addr-loading");
      if (loader) {{ loader.style.opacity = "0"; setTimeout(() => loader.remove(), 600); }}
      const all = [...overlapLayer.graphics.toArray(), ...addressLayer.graphics.toArray()];
      if (all.length > 0) {{
        view.goTo(all, {{ padding: {{ top: 50, right: 50, bottom: 50, left: 50 }}, duration: 1000, easing: "ease-in-out" }}).catch(() => {{}});
      }}

      /* -- Phase 2: Deferred load of reference FeatureLayers and secondary widgets -- */
      let advancedLoaded = false;
      const loadAdvanced = () => {{
        if (advancedLoaded) return;
        advancedLoaded = true;
        if (advBtn) {{
          advBtn.textContent = "Loading advanced tools...";
          advBtn.disabled = true;
        }}
        require([
        "esri/layers/FeatureLayer",
        "esri/widgets/Compass",
        "esri/widgets/Fullscreen",
        "esri/widgets/Search",
        "esri/widgets/Locate",
        "esri/widgets/Sketch",
        "esri/widgets/Expand",
        "esri/geometry/geometryEngine"
      ], function(FeatureLayer, Compass, Fullscreen, Search, Locate, Sketch, Expand, geometryEngine) {{

        /* -- Reference boundary layers (deferred — not needed for initial render) -- */
        const countyLayer = new FeatureLayer({{
          url: "{TEA_ARCGIS_COUNTY_LAYER_URL}",
          outFields: ["FENAME", "FIPS"],
          popupEnabled: false, labelsVisible: false,
          minScale: 2000000,
          labelingInfo: [{{
            labelExpressionInfo: {{ expression: "$feature.FENAME + ' County'" }},
            symbol: {{ type: "text", color: [160, 140, 110, 0.75], haloColor: [13, 23, 36, 0.80], haloSize: 0.8,
              font: {{ size: 11, family: "Avenir Next LT Pro", weight: "600" }} }}
          }}],
          renderer: {{ type: "simple", symbol: {{ type: "simple-fill", color: [0,0,0,0], outline: {{ color: [145, 111, 63, 0.22], width: 0.6 }} }} }},
          opacity: 0.35
        }});

        const districtLayer = new FeatureLayer({{
          url: "{TEA_ARCGIS_SCHOOL_DISTRICT_LAYER_URL}",
          outFields: ["FID", "NAME20", "DISTRICT"],
          popupEnabled: false, labelsVisible: false,
          minScale: 500000,
          labelingInfo: [{{
            labelExpressionInfo: {{ expression: "$feature.NAME20" }},
            symbol: {{ type: "text", color: [73, 112, 150, 0.65], haloColor: [13, 23, 36, 0.8], haloSize: 0.6,
              font: {{ size: 8, family: "Avenir Next LT Pro", weight: "normal" }} }}
          }}],
          renderer: {{ type: "simple", symbol: {{ type: "simple-fill", color: [0,0,0,0], outline: {{ color: [30, 144, 255, 0.20], width: 0.5 }} }} }},
          opacity: 0.35
        }});

        const cityLayer = new FeatureLayer({{
          url: "{CENSUS_ARCGIS_TEXAS_CITY_LAYER_URL}",
          outFields: ["NAME", "BASENAME", "GEOID", "STATE"],
          definitionExpression: "STATE = '48'",
          popupEnabled: false, labelsVisible: false,
          minScale: 1000000,
          labelingInfo: [{{
            labelExpressionInfo: {{ expression: "DefaultValue($feature.BASENAME, $feature.NAME)" }},
            symbol: {{ type: "text", color: [165, 100, 105, 0.80], haloColor: [13, 23, 36, 0.76], haloSize: 0.7,
              font: {{ size: 9, family: "Avenir Next LT Pro", weight: "500" }} }}
          }}],
          renderer: {{ type: "simple", symbol: {{ type: "simple-fill", color: [0,0,0,0], outline: {{ color: [158, 42, 43, 0.12], width: 0.4 }} }} }},
          opacity: 0.20
        }});

        const houseLayer = new FeatureLayer({{
          url: "{TEXAS_HOUSE_DISTRICTS_LAYER_URL}",
          outFields: ["DISTRICT"],
          popupEnabled: true,
          popupTemplate: {{ title: "TX House District {{{{DISTRICT}}}}", content: "Texas House of Representatives District {{{{DISTRICT}}}}" }},
          labelsVisible: false,
          minScale: 2000000,
          labelingInfo: [{{
            labelExpressionInfo: {{ expression: "'HD ' + $feature.DISTRICT" }},
            symbol: {{ type: "text", color: [90, 180, 130, 0.70], haloColor: [13, 23, 36, 0.75], haloSize: 0.6,
              font: {{ size: 8, family: "Avenir Next LT Pro", weight: "600" }} }}
          }}],
          renderer: {{ type: "simple", symbol: {{ type: "simple-fill", color: [40, 180, 100, 0.03], outline: {{ color: [40, 180, 100, 0.30], width: 0.8 }} }} }},
          opacity: 0.30, visible: false
        }});

        const senateLayer = new FeatureLayer({{
          url: "{TEXAS_SENATE_DISTRICTS_LAYER_URL}",
          outFields: ["DISTRICT"],
          popupEnabled: true,
          popupTemplate: {{ title: "TX Senate District {{{{DISTRICT}}}}", content: "Texas Senate District {{{{DISTRICT}}}}" }},
          labelsVisible: false,
          minScale: 2000000,
          labelingInfo: [{{
            labelExpressionInfo: {{ expression: "'SD ' + $feature.DISTRICT" }},
            symbol: {{ type: "text", color: [180, 130, 90, 0.70], haloColor: [13, 23, 36, 0.75], haloSize: 0.6,
              font: {{ size: 9, family: "Avenir Next LT Pro", weight: "600" }} }}
          }}],
          renderer: {{ type: "simple", symbol: {{ type: "simple-fill", color: [200, 140, 60, 0.03], outline: {{ color: [200, 140, 60, 0.30], width: 0.8 }} }} }},
          opacity: 0.30, visible: false
        }});

        /* Insert reference layers below overlap graphics */
        map.add(countyLayer, 0);
        map.add(districtLayer, 1);
        map.add(houseLayer, 2);
        map.add(senateLayer, 3);
        map.add(cityLayer, 4);

        /* -- Zoom-dependent label visibility -- */
        const updateLabels = () => {{
          const z = Number(view.zoom || 0);
          countyLayer.labelsVisible = z >= 6;
          cityLayer.labelsVisible = z >= 7;
          districtLayer.labelsVisible = z >= 9;
          houseLayer.labelsVisible = z >= 8;
          senateLayer.labelsVisible = z >= 7;
        }};
        view.watch("zoom", updateLabels);
        updateLabels();

        /* -- Secondary widgets -- */
        const compass = new Compass({{ view }});
        const fullscreen = new Fullscreen({{ view }});
        const locate = new Locate({{ view }});

        const search = new Search({{
          view,
          popupEnabled: true,
          resultGraphicEnabled: true,
          goToOverride: (view, opts) => view.goTo(opts.target, {{ duration: 800, easing: "ease-in-out" }})
        }});
        search.on("select-result", (evt) => {{
          if (evt.result && evt.result.name) {{
            try {{ window.parent.postMessage({{ type: "tfl-map-address-search", address: evt.result.name }}, "*"); }} catch(e) {{}}
          }}
        }});

        const sketch = new Sketch({{
          view,
          layer: sketchLayer,
          creationMode: "single",
          availableCreateTools: ["polygon", "circle", "rectangle"],
          defaultCreateOptions: {{ mode: "freehand" }},
          visibleElements: {{ selectionTools: {{ "lasso-selection": false, "rectangle-selection": false }}, settingsMenu: false, undoRedoMenu: true }},
          defaultUpdateOptions: {{ tool: "reshape" }}
        }});
        const sketchExpand = new Expand({{
          view,
          content: sketch,
          expandIconClass: "esri-icon-polygon",
          expandTooltip: "Draw area for batch analysis",
          group: "tools"
        }});

        const layerDiv = document.createElement("div");
        layerDiv.style.cssText = "background:rgba(13,23,36,0.94);border-radius:8px;padding:10px;font-family:'Avenir Next LT Pro',system-ui,sans-serif;font-size:12px;color:rgba(210,225,240,0.90);min-width:160px;";
        layerDiv.innerHTML = '<div style="font-size:9px;text-transform:uppercase;letter-spacing:0.12em;color:rgba(150,175,200,0.65);font-weight:700;margin-bottom:6px;">Legislative Districts</div>'
          + '<label style="display:flex;align-items:center;gap:6px;cursor:pointer;padding:3px 0;"><input type="checkbox" id="tfl-toggle-house" style="accent-color:#28b464;"><span>TX House Districts</span></label>'
          + '<label style="display:flex;align-items:center;gap:6px;cursor:pointer;padding:3px 0;"><input type="checkbox" id="tfl-toggle-senate" style="accent-color:#c88c3c;"><span>TX Senate Districts</span></label>';
        const layerExpand = new Expand({{
          view,
          content: layerDiv,
          expandIconClass: "esri-icon-layer-list",
          expandTooltip: "Toggle legislative districts",
          group: "tools"
        }});

        view.ui.add(compass, "top-left");
        view.ui.add(fullscreen, "top-left");
        view.ui.add(locate, "top-left");
        view.ui.add(sketchExpand, "top-left");
        view.ui.add(layerExpand, "top-left");
        view.ui.add(search, "top-right");

        /* Wire layer toggles */
        const hBox = document.getElementById("tfl-toggle-house");
        const sBox = document.getElementById("tfl-toggle-senate");
        if (hBox) hBox.addEventListener("change", () => {{ houseLayer.visible = hBox.checked; }});
        if (sBox) sBox.addEventListener("change", () => {{ senateLayer.visible = sBox.checked; }});

        /* Sketch complete → batch analysis info */
        sketch.on("create", (evt) => {{
          if (evt.state !== "complete") return;
          const drawn = evt.graphic.geometry;
          const selInfo = document.getElementById("tfl-addr-sel-info");
          const contained = [];
          overlapLayer.graphics.forEach((g) => {{
            if (g.geometry && geometryEngine.contains(drawn, g.geometry)) {{
              contained.push(g.attributes || {{}});
            }}
          }});
          if (selInfo && contained.length > 0) {{
            const total = contained.reduce((a,r) => a + Number(r.high_total||0), 0);
            const types = [...new Set(contained.map(r => r.subdivision_type).filter(Boolean))];
            selInfo.style.display = "block";
            selInfo.innerHTML = '<div class="sel-title">Area Selection</div>'
              + '<div><strong>' + contained.length + '</strong> subdivision(s) in area</div>'
              + '<div>Combined TFL est.: <strong>' + formatUsd(total) + '</strong></div>'
              + '<div style="font-size:10px;color:rgba(180,200,220,0.65);margin-top:3px;">' + types.join(", ") + '</div>';
            try {{
              const names = contained.map(r => r.subdivision_name).filter(Boolean);
              window.parent.postMessage({{ type: "tfl-map-area-select", count: contained.length, totalHigh: total, names: names, types: types }}, "*");
            }} catch(e) {{}}
          }} else if (selInfo) {{
            selInfo.style.display = "block";
            selInfo.innerHTML = '<div class="sel-title">Area Selection</div><div>No subdivisions in drawn area.</div>';
            setTimeout(() => {{ selInfo.style.display = "none"; }}, 3000);
          }}
        }});
        if (advBtn) {{
          advBtn.textContent = "Advanced tools ready";
          setTimeout(() => {{
            try {{ advBtn.remove(); }} catch (e) {{}}
          }}, 1100);
        }}
      }}); /* end deferred require */
      }};
      if (advBtn) {{
        advBtn.addEventListener("click", () => loadAdvanced(), {{ once: true }});
      }}
      scheduleAdvancedLoad(() => loadAdvanced());
    }}); /* end view.when */
  }});
</script>
"""
    )
    _persistent_html_frame(
        html=arcgis_html,
        signature=address_map_signature,
        height=int(height) + 8,
        key="mp5_address_overlap_map_v2",
        default=None,
    )

def render_tfl_school_district_arcgis_map(matches: pd.DataFrame, height: int = 620, basemap: str = "gray-vector") -> None:
    if matches.empty:
        st.info("No matching school-district clients to plot on the map.")
        return

    payload_rows = []
    for row in matches.itertuples(index=False):
        clients = row.match_clients if isinstance(row.match_clients, list) else []
        safe_clients = [html.escape(str(c), quote=True) for c in clients]
        payload_rows.append(
            {
                "fid": int(row.fid),
                "district_name": html.escape(str(row.district_name), quote=True),
                "district_code": html.escape(str(row.district_code), quote=True),
                "lon": float(row.lon),
                "lat": float(row.lat),
                "match_count": int(row.match_count),
                "high_total": float(getattr(row, "high_total", 0.0) or 0.0),
                "match_clients_preview": html.escape(str(row.match_clients_preview), quote=True),
                "match_clients": safe_clients[:14],
                "extra_count": max(0, len(safe_clients) - 14),
            }
        )
    payload_json = json.dumps(payload_rows, ensure_ascii=True)
    basemap_safe = json.dumps(str(basemap).strip() or "gray-vector")

    total_districts = len(payload_rows)
    total_high = sum(r["high_total"] for r in payload_rows)
    total_high_fmt = f"${total_high:,.0f}"
    arcgis_html = f"""
<link rel="stylesheet" href="https://js.arcgis.com/4.30/esri/themes/dark/main.css"/>
<style>
  /* -- Dark popup theme -- */
  .esri-popup__main-container {{
    background: rgba(13,23,36,0.96) !important;
    color: rgba(220,230,240,0.95) !important;
    border: 1px solid rgba(100,140,180,0.22) !important;
    border-radius: 10px !important;
    backdrop-filter: blur(10px) !important;
    box-shadow: 0 8px 32px rgba(0,0,0,0.45) !important;
  }}
  .esri-popup__header-title {{ color: rgba(235,242,250,0.97) !important; font-weight: 600 !important; }}
  .esri-popup__content {{ color: rgba(200,215,230,0.92) !important; }}
  .esri-popup__button {{ color: rgba(180,200,220,0.85) !important; }}
  .esri-popup__button:hover {{ color: #fff !important; background: rgba(0,224,184,0.18) !important; }}
  .esri-popup__pointer-direction {{ background: rgba(13,23,36,0.96) !important; }}

  .esri-sketch {{ background: rgba(13,23,36,0.92) !important; border-radius: 8px !important; border: 1px solid rgba(100,140,180,0.22) !important; }}

  #tfl-sd-loading {{
    position:absolute; top:0; left:0; width:100%; height:100%;
    background:rgba(10,16,26,0.92); display:flex; flex-direction:column;
    align-items:center; justify-content:center; gap:10px;
    z-index:100; border-radius:14px; transition:opacity 0.6s ease;
  }}
  #tfl-sd-loading .ld-spinner {{
    width:30px; height:30px; border:2.5px solid rgba(100,140,180,0.18);
    border-top:2.5px solid rgba(0,224,184,0.80); border-radius:50%;
    animation: tfl-sd-spin 0.8s linear infinite;
  }}
  #tfl-sd-loading .ld-label {{
    font-family:'Avenir Next LT Pro',system-ui,sans-serif; font-size:10px;
    color:rgba(160,185,210,0.65); letter-spacing:0.06em;
  }}
  @keyframes tfl-sd-spin {{ 0%{{transform:rotate(0deg)}} 100%{{transform:rotate(360deg)}} }}
  #tfl-sd-coord {{
    position:absolute; bottom:10px; left:50%; transform:translateX(-50%); z-index:90;
    background:rgba(10,16,26,0.85); border:1px solid rgba(100,140,180,0.15);
    border-radius:6px; padding:2px 10px;
    font-family:'Avenir Next LT Pro',system-ui,sans-serif; font-size:10px;
    color:rgba(180,200,220,0.75); pointer-events:none; backdrop-filter:blur(6px);
    white-space:nowrap; letter-spacing:0.04em;
  }}
  #tfl-sd-legend {{
    position:absolute; bottom:36px; right:12px; z-index:90;
    background:rgba(10,20,32,0.92); border:1px solid rgba(100,140,180,0.18);
    border-radius:10px; padding:6px 10px; max-width:210px;
    font-family:'Avenir Next LT Pro',system-ui,sans-serif; font-size:10.5px;
    color:rgba(210,225,240,0.90); backdrop-filter:blur(8px);
  }}
  #tfl-sd-legend .leg-title {{
    text-transform:uppercase; letter-spacing:0.14em; font-size:8px;
    color:rgba(150,175,200,0.70); margin-bottom:3px; font-weight:700;
  }}
  #tfl-sd-legend .leg-row {{ display:flex; align-items:center; gap:5px; padding:1.5px 0; }}
  #tfl-sd-legend .leg-chip {{
    width:9px; height:9px; border-radius:50%; flex-shrink:0;
    border:1px solid rgba(255,255,255,0.18);
  }}
  #tfl-sd-sel-info {{
    position:absolute; bottom:36px; left:12px; z-index:90;
    background:rgba(10,16,26,0.92); border:1px solid rgba(0,224,184,0.25);
    border-radius:8px; padding:6px 12px; backdrop-filter:blur(6px);
    font-family:'Avenir Next LT Pro',system-ui,sans-serif; font-size:11px;
    color:rgba(200,220,240,0.90); display:none; max-width:280px;
  }}
  #tfl-sd-sel-info .sel-title {{
    font-weight:700; color:rgba(0,224,184,0.95); font-size:10px;
    text-transform:uppercase; letter-spacing:0.08em; margin-bottom:3px;
  }}
</style>
<div style="width:100%;height:{height}px;position:relative;">
  <div id="tfl-arcgis-map" style="width:100%;height:100%;border-radius:14px;overflow:hidden;"></div>
  <div id="tfl-sd-legend">
    <div class="leg-title">Legend</div>
    <div class="leg-row"><span class="leg-chip" style="background:#00e0b8;"></span><span>School District ({total_districts})</span></div>
    <div class="leg-row"><span class="leg-chip" style="background:rgba(145,111,63,0.5);border-color:rgba(145,111,63,0.6);"></span><span style="font-size:10px;color:rgba(180,195,210,0.70);">County boundary</span></div>
    <div class="leg-row"><span class="leg-chip" style="background:rgba(30,144,255,0.3);border-color:rgba(30,144,255,0.5);"></span><span style="font-size:10px;color:rgba(180,195,210,0.70);">District boundary</span></div>
  </div>
  <div id="tfl-sd-loading"><div class="ld-spinner"></div><div class="ld-label">Loading map layers&hellip;</div></div>
  <div id="tfl-sd-coord">&ndash;</div>
  <div id="tfl-sd-sel-info"></div>
</div>
<script src="https://js.arcgis.com/4.30/"></script>
<script>
  const tflPoints = {payload_json};
  const baseMapId = {basemap_safe};
  require([
    "esri/Map",
    "esri/views/MapView",
    "esri/layers/FeatureLayer",
    "esri/layers/GraphicsLayer",
    "esri/Graphic",
    "esri/widgets/Home",
    "esri/widgets/ScaleBar",
    "esri/widgets/BasemapToggle",
    "esri/widgets/Compass",
    "esri/widgets/Fullscreen",
    "esri/widgets/Search",
    "esri/widgets/Locate",
    "esri/widgets/Sketch",
    "esri/widgets/Expand",
    "esri/geometry/geometryEngine"
  ], function(Map, MapView, FeatureLayer, GraphicsLayer, Graphic, Home, ScaleBar, BasemapToggle, Compass, Fullscreen, Search, Locate, Sketch, Expand, geometryEngine) {{
    const map = new Map({{ basemap: baseMapId }});

    const countyLayer = new FeatureLayer({{
      url: "{TEA_ARCGIS_COUNTY_LAYER_URL}",
      outFields: ["FENAME", "FIPS"],
      popupEnabled: false, labelsVisible: false,
      labelingInfo: [{{
        labelExpressionInfo: {{ expression: "$feature.FENAME + ' County'" }},
        symbol: {{ type: "text", color: [160, 140, 110, 0.75], haloColor: [13, 23, 36, 0.80], haloSize: 0.8,
          font: {{ size: 11, family: "Avenir Next LT Pro", weight: "600" }} }}
      }}],
      renderer: {{ type: "simple", symbol: {{ type: "simple-fill", color: [0,0,0,0], outline: {{ color: [145, 111, 63, 0.22], width: 0.6 }} }} }},
      opacity: 0.35
    }});

    const districtLayer = new FeatureLayer({{
      url: "{TEA_ARCGIS_SCHOOL_DISTRICT_LAYER_URL}",
      outFields: ["FID", "NAME20", "DISTRICT"],
      popupEnabled: false, labelsVisible: false,
      labelingInfo: [{{
        labelExpressionInfo: {{ expression: "$feature.NAME20" }},
        symbol: {{ type: "text", color: [73, 112, 150, 0.65], haloColor: [13, 23, 36, 0.8], haloSize: 0.6,
          font: {{ size: 8, family: "Avenir Next LT Pro", weight: "normal" }} }}
      }}],
      renderer: {{ type: "simple", symbol: {{ type: "simple-fill", color: [0,0,0,0], outline: {{ color: [30, 144, 255, 0.25], width: 0.6 }} }} }},
      opacity: 0.40
    }});

    /* TX House & Senate district boundaries */
    const houseLayer = new FeatureLayer({{
      url: "{TEXAS_HOUSE_DISTRICTS_LAYER_URL}",
      outFields: ["*"], popupEnabled: true,
      popupTemplate: {{ title: "TX House District {{{{DISTRICT}}}}", content: "Texas House of Representatives District {{{{DISTRICT}}}}" }},
      labelsVisible: false,
      labelingInfo: [{{ labelExpressionInfo: {{ expression: "'HD ' + $feature.DISTRICT" }},
        symbol: {{ type: "text", color: [90, 180, 130, 0.70], haloColor: [13, 23, 36, 0.75], haloSize: 0.6,
          font: {{ size: 8, family: "Avenir Next LT Pro", weight: "600" }} }} }}],
      renderer: {{ type: "simple", symbol: {{ type: "simple-fill", color: [40, 180, 100, 0.03], outline: {{ color: [40, 180, 100, 0.30], width: 0.8 }} }} }},
      opacity: 0.30, visible: false
    }});
    const senateLayer = new FeatureLayer({{
      url: "{TEXAS_SENATE_DISTRICTS_LAYER_URL}",
      outFields: ["*"], popupEnabled: true,
      popupTemplate: {{ title: "TX Senate District {{{{DISTRICT}}}}", content: "Texas Senate District {{{{DISTRICT}}}}" }},
      labelsVisible: false,
      labelingInfo: [{{ labelExpressionInfo: {{ expression: "'SD ' + $feature.DISTRICT" }},
        symbol: {{ type: "text", color: [180, 130, 90, 0.70], haloColor: [13, 23, 36, 0.75], haloSize: 0.6,
          font: {{ size: 9, family: "Avenir Next LT Pro", weight: "600" }} }} }}],
      renderer: {{ type: "simple", symbol: {{ type: "simple-fill", color: [200, 140, 60, 0.03], outline: {{ color: [200, 140, 60, 0.30], width: 0.8 }} }} }},
      opacity: 0.30, visible: false
    }});

    map.add(countyLayer);
    map.add(districtLayer);
    map.add(houseLayer);
    map.add(senateLayer);

    const graphics = new GraphicsLayer();
    const sketchLayer = new GraphicsLayer();
    map.add(graphics);
    map.add(sketchLayer);

    const view = new MapView({{
      container: "tfl-arcgis-map",
      map,
      center: [-99.3, 31.1],
      zoom: 5,
      constraints: {{ minZoom: 4 }},
      popup: {{ dockEnabled: true, dockOptions: {{ position: "bottom-right", breakpoint: false }} }},
      ui: {{ padding: {{ top: 10, right: 10, bottom: 30, left: 10 }} }}
    }});

    const formatUsd = (v) => Number(v||0).toLocaleString("en-US",{{style:"currency",currency:"USD",maximumFractionDigits:0}});
    const maxHigh = tflPoints.reduce((a, r) => Math.max(a, Number(r.high_total || 0)), 0);
    const sz = (row) => {{
      if (maxHigh > 0) {{
        const n = Math.max(0, Number(row.high_total || 0));
        return Math.max(8, Math.min(28, 8 + (Math.log10(n+1)/Math.log10(maxHigh+1))*20));
      }}
      return Math.min(26, 8 + Math.log2((row.match_count || 1) + 1) * 5);
    }};

    for (const row of tflPoints) {{
      const clientsHtml = (row.match_clients || []).join(", ");
      const extraHtml = row.extra_count > 0 ? `, +${{row.extra_count}} more` : "";
      const g = new Graphic({{
        geometry: {{ type: "point", longitude: row.lon, latitude: row.lat }},
        symbol: {{
          type: "simple-marker", size: sz(row),
          color: [0, 224, 184, 0.85],
          outline: {{ color: [7, 22, 39, 0.95], width: 1 }}
        }},
        attributes: row,
        popupTemplate: {{
          title: row.district_name || "School District",
          content: `<div style="font-family:'Avenir Next LT Pro',system-ui,sans-serif;font-size:12px;line-height:1.5;">
            <table style="border-collapse:collapse;width:100%;">
              <tr><td style="color:#7a94ab;padding:2px 6px 2px 0;font-size:11px;">District code</td><td style="font-weight:600;">${{row.district_code || "N/A"}}</td></tr>
              <tr><td style="color:#7a94ab;padding:2px 6px 2px 0;font-size:11px;">TFL high est.</td><td style="font-weight:600;">${{formatUsd(row.high_total)}}</td></tr>
              <tr><td style="color:#7a94ab;padding:2px 6px 2px 0;font-size:11px;">Matched clients</td><td style="font-weight:600;">${{row.match_count}}</td></tr>
            </table>
            <div style="margin-top:5px;padding-top:4px;border-top:1px solid rgba(140,160,180,0.20);font-size:11px;">${{clientsHtml}}${{extraHtml}}</div>
          </div>`
        }}
      }});
      graphics.add(g);
    }}

    const updateLabels = () => {{
      const z = Number(view.zoom || 0);
      countyLayer.labelsVisible = z >= 6;
      districtLayer.labelsVisible = z >= 8.5;
      houseLayer.labelsVisible = z >= 8;
      senateLayer.labelsVisible = z >= 7;
    }};
    view.watch("zoom", updateLabels);

    /* -- Widgets -- */
    const home = new Home({{ view }});
    const basemapToggle = new BasemapToggle({{ view, nextBasemap: baseMapId === "hybrid" ? "gray-vector" : "hybrid" }});
    const scaleBar = new ScaleBar({{ view, unit: "dual" }});
    const compass = new Compass({{ view }});
    const fullscreen = new Fullscreen({{ view }});
    const locate = new Locate({{ view }});
    const search = new Search({{
      view, popupEnabled: true, resultGraphicEnabled: true,
      goToOverride: (view, opts) => view.goTo(opts.target, {{ duration: 800, easing: "ease-in-out" }})
    }});

    /* Sketch tool for encircling areas */
    const sketch = new Sketch({{
      view, layer: sketchLayer, creationMode: "single",
      availableCreateTools: ["polygon", "circle", "rectangle"],
      defaultCreateOptions: {{ mode: "freehand" }},
      visibleElements: {{ selectionTools: {{ "lasso-selection": false, "rectangle-selection": false }}, settingsMenu: false, undoRedoMenu: true }},
      defaultUpdateOptions: {{ tool: "reshape" }}
    }});
    const sketchExpand = new Expand({{
      view, content: sketch, expandIconClass: "esri-icon-polygon",
      expandTooltip: "Draw area for batch analysis", group: "tools"
    }});

    /* House/Senate layer toggle */
    const layerDiv = document.createElement("div");
    layerDiv.style.cssText = "background:rgba(13,23,36,0.94);border-radius:8px;padding:10px;font-family:'Avenir Next LT Pro',system-ui,sans-serif;font-size:12px;color:rgba(210,225,240,0.90);min-width:160px;";
    layerDiv.innerHTML = '<div style="font-size:9px;text-transform:uppercase;letter-spacing:0.12em;color:rgba(150,175,200,0.65);font-weight:700;margin-bottom:6px;">Legislative Districts</div>'
      + '<label style="display:flex;align-items:center;gap:6px;cursor:pointer;padding:3px 0;"><input type="checkbox" id="tfl-sd-toggle-house" style="accent-color:#28b464;"><span>TX House Districts</span></label>'
      + '<label style="display:flex;align-items:center;gap:6px;cursor:pointer;padding:3px 0;"><input type="checkbox" id="tfl-sd-toggle-senate" style="accent-color:#c88c3c;"><span>TX Senate Districts</span></label>';
    const layerExpand = new Expand({{
      view, content: layerDiv, expandIconClass: "esri-icon-layer-list",
      expandTooltip: "Toggle legislative districts", group: "tools"
    }});

    view.ui.add(home, "top-left");
    view.ui.add(compass, "top-left");
    view.ui.add(fullscreen, "top-left");
    view.ui.add(locate, "top-left");
    view.ui.add(sketchExpand, "top-left");
    view.ui.add(layerExpand, "top-left");
    view.ui.add(search, "top-right");
    view.ui.add(basemapToggle, "top-right");
    view.ui.add(scaleBar, "bottom-left");

    /* Wire layer toggles */
    view.when(() => {{
      const hBox = document.getElementById("tfl-sd-toggle-house");
      const sBox = document.getElementById("tfl-sd-toggle-senate");
      if (hBox) hBox.addEventListener("change", () => {{ houseLayer.visible = hBox.checked; }});
      if (sBox) sBox.addEventListener("change", () => {{ senateLayer.visible = sBox.checked; }});
    }});

    /* Sketch complete → batch analysis info */
    sketch.on("create", (evt) => {{
      if (evt.state !== "complete") return;
      const drawn = evt.graphic.geometry;
      const selInfo = document.getElementById("tfl-sd-sel-info");
      const contained = [];
      graphics.graphics.forEach((g) => {{
        if (g.geometry && geometryEngine.contains(drawn, g.geometry)) contained.push(g.attributes || {{}});
      }});
      if (selInfo && contained.length > 0) {{
        const total = contained.reduce((a,r) => a + Number(r.high_total||0), 0);
        selInfo.style.display = "block";
        selInfo.innerHTML = '<div class="sel-title">Area Selection</div>'
          + '<div><strong>' + contained.length + '</strong> district(s) in area</div>'
          + '<div>Combined TFL est.: <strong>' + formatUsd(total) + '</strong></div>';
        try {{ window.parent.postMessage({{ type: "tfl-map-area-select", count: contained.length, totalHigh: total }}, "*"); }} catch(e) {{}}
      }} else if (selInfo) {{
        selInfo.style.display = "block";
        selInfo.innerHTML = '<div class="sel-title">Area Selection</div><div>No districts in drawn area.</div>';
        setTimeout(() => {{ selInfo.style.display = "none"; }}, 3000);
      }}
    }});

    /* Coordinate readout */
    view.on("pointer-move", (evt) => {{
      const pt = view.toMap(evt);
      const el = document.getElementById("tfl-sd-coord");
      if (pt && el) el.textContent = pt.latitude.toFixed(5) + "\u00b0 N, " + Math.abs(pt.longitude).toFixed(5) + "\u00b0 W";
    }});

    /* Hover highlight */
    let hoverHL = null;
    view.on("pointer-move", (evt) => {{
      view.hitTest(evt, {{ include: [graphics] }}).then((r) => {{
        const hit = r.results && r.results.find(x => x.graphic);
        document.getElementById("tfl-arcgis-map").style.cursor = hit ? "pointer" : "default";
        if (hoverHL) {{ graphics.remove(hoverHL); hoverHL = null; }}
        if (hit && hit.graphic && hit.graphic.geometry) {{
          hoverHL = new Graphic({{
            geometry: hit.graphic.geometry,
            symbol: {{ type: "simple-marker", style: "circle", size: 30, color: [255,255,255,0.0], outline: {{ color: [0,224,184,0.55], width: 2 }} }}
          }});
          graphics.add(hoverHL);
        }}
      }});
    }});

    view.when(() => {{
      const loader = document.getElementById("tfl-sd-loading");
      if (loader) {{ loader.style.opacity = "0"; setTimeout(() => loader.remove(), 600); }}
      updateLabels();
      if (graphics.graphics.length > 0) {{
        view.goTo(graphics.graphics.toArray(), {{ padding: {{ top: 50, right: 50, bottom: 50, left: 50 }}, duration: 1000, easing: "ease-in-out" }}).catch(() => {{}});
      }}
    }});
  }});
</script>
"""
    components.html(arcgis_html, height=height + 8, scrolling=False)

def render_tfl_subdivision_arcgis_map(
    matches: pd.DataFrame,
    height: int = 640,
    basemap: str = "gray-vector",
) -> None:
    if matches.empty:
        st.info("No matching political-subdivision clients to plot on the map.")
        return

    type_colors = {
        subtype: _hex_to_rgba(color_hex, alpha=0.9)
        for subtype, color_hex in SUBDIVISION_TYPE_COLORS.items()
    }
    type_colors_json = json.dumps(type_colors, ensure_ascii=True)

    # Build hex color map for the on-map legend
    type_hex_colors = {
        subtype: color_hex
        for subtype, color_hex in SUBDIVISION_TYPE_COLORS.items()
    }

    payload_rows = []
    for row in matches.itertuples(index=False):
        clients = row.match_clients if isinstance(row.match_clients, list) else []
        safe_clients = [str(c).strip() for c in clients if str(c).strip()]
        preview = str(getattr(row, "match_clients_preview", "")).strip() or ", ".join(safe_clients[:14])
        payload_rows.append(
            {
                "subdivision_type": html.escape(str(row.subdivision_type), quote=True),
                "subdivision_name": html.escape(str(row.subdivision_name), quote=True),
                "subdivision_code": html.escape(str(row.subdivision_code), quote=True),
                "source_name": html.escape(str(getattr(row, "source_name", "")), quote=True),
                "lon": float(row.lon),
                "lat": float(row.lat),
                "match_count": int(row.match_count),
                "high_total": float(getattr(row, "high_total", 0.0) or 0.0),
                "match_clients_preview": html.escape(preview, quote=True),
                "extra_count": max(0, len(safe_clients) - 14),
            }
        )
    payload_json = json.dumps(payload_rows, ensure_ascii=True)
    basemap_safe = json.dumps(str(basemap).strip() or "gray-vector")

    # Determine which subdivision types are actually present for the legend
    present_types: dict[str, tuple[str, int]] = {}
    for pr in payload_rows:
        st_key = pr["subdivision_type"]
        if st_key:
            if st_key not in present_types:
                present_types[st_key] = (type_hex_colors.get(st_key, "#718191"), 0)
            present_types[st_key] = (present_types[st_key][0], present_types[st_key][1] + 1)
    legend_items_json = json.dumps(
        [{"type": t, "color": c, "count": n} for t, (c, n) in sorted(present_types.items(), key=lambda x: -x[1][1])],
        ensure_ascii=True,
    )

    total_sub = len(payload_rows)
    total_sub_high = sum(r["high_total"] for r in payload_rows)
    total_sub_high_fmt = f"${total_sub_high:,.0f}"
    subdivision_map_signature = _stable_json_signature(
        {
            "renderer_version": 3,
            "points": payload_rows,
            "basemap": str(basemap).strip() or "gray-vector",
            "height": int(height),
        }
    )
    arcgis_html = _session_cached_value(
        "_mp5_subdivision_map_html_v3",
        subdivision_map_signature,
        lambda: f"""
<link rel="stylesheet" href="https://js.arcgis.com/4.30/esri/themes/dark/main.css"/>
<style>
  /* -- Dark popup theme -- */
  .esri-popup__main-container {{
    background: rgba(13,23,36,0.96) !important;
    color: rgba(220,230,240,0.95) !important;
    border: 1px solid rgba(100,140,180,0.22) !important;
    border-radius: 10px !important;
    backdrop-filter: blur(10px) !important;
    box-shadow: 0 8px 32px rgba(0,0,0,0.45) !important;
  }}
  .esri-popup__header-title {{ color: rgba(235,242,250,0.97) !important; font-weight: 600 !important; }}
  .esri-popup__content {{ color: rgba(200,215,230,0.92) !important; }}
  .esri-popup__button {{ color: rgba(180,200,220,0.85) !important; }}
  .esri-popup__button:hover {{ color: #fff !important; background: rgba(100,180,255,0.18) !important; }}
  .esri-popup__pointer-direction {{ background: rgba(13,23,36,0.96) !important; }}

  .esri-sketch {{ background: rgba(13,23,36,0.92) !important; border-radius: 8px !important; border: 1px solid rgba(100,140,180,0.22) !important; }}

  #tfl-sub-legend {{
    position: absolute; bottom: 90px; right: 12px; z-index: 90;
    background: rgba(10,20,32,0.92); border: 1px solid rgba(100,140,180,0.18);
    border-radius: 11px; padding: 0; max-width: 240px; overflow: hidden;
    font-family: 'Avenir Next LT Pro', system-ui, sans-serif; font-size: 10.5px;
    color: rgba(210,225,240,0.90); backdrop-filter: blur(8px);
    transition: max-height 0.3s ease;
  }}
  #tfl-sub-legend .leg-hdr {{
    display: flex; align-items: center; justify-content: space-between;
    padding: 6px 10px 4px 10px; cursor: pointer; user-select: none;
  }}
  #tfl-sub-legend .leg-title {{
    text-transform: uppercase; letter-spacing: 0.14em; font-size: 8px;
    color: rgba(150,175,200,0.70); font-weight: 700;
  }}
  #tfl-sub-legend .leg-toggle {{
    font-size: 12px; color: rgba(150,175,200,0.60); transition: transform 0.25s;
  }}
  #tfl-sub-legend .leg-body {{
    padding: 0 10px 6px 10px; max-height: 180px; overflow-y: auto;
  }}
  #tfl-sub-legend .leg-body::-webkit-scrollbar {{ width:4px; }}
  #tfl-sub-legend .leg-body::-webkit-scrollbar-thumb {{ background:rgba(100,140,180,0.25); border-radius:4px; }}
  #tfl-sub-legend .leg-body::-webkit-scrollbar-track {{ background:transparent; }}
  #tfl-sub-legend .leg-row {{
    display: flex; align-items: center; justify-content: space-between; gap: 5px; padding: 2px 0;
    cursor: pointer; border-radius: 4px; padding-left: 3px; padding-right: 3px;
    transition: background 0.15s, opacity 0.25s;
  }}
  #tfl-sub-legend .leg-row:hover {{ background: rgba(255,255,255,0.06); }}
  #tfl-sub-legend .leg-row.dimmed {{ opacity: 0.28; }}
  #tfl-sub-legend .leg-left {{ display: flex; align-items: center; gap: 5px; min-width: 0; }}
  #tfl-sub-legend .leg-chip {{
    width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0;
    border: 1px solid rgba(255,255,255,0.18);
  }}
  #tfl-sub-legend .leg-label {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  #tfl-sub-legend .leg-count {{ font-weight: 600; flex-shrink: 0; color: rgba(200,215,230,0.75); font-size: 9.5px; }}
  #tfl-sub-legend.collapsed .leg-body {{ display: none; }}
  #tfl-sub-legend.collapsed .leg-toggle {{ transform: rotate(180deg); }}

  #tfl-sub-loading {{
    position:absolute; top:0; left:0; width:100%; height:100%;
    background:rgba(10,16,26,0.92); display:flex; flex-direction:column;
    align-items:center; justify-content:center; gap:10px;
    z-index:100; border-radius:14px; transition:opacity 0.6s ease;
  }}
  #tfl-sub-loading .ld-spinner {{
    width:30px; height:30px; border:2.5px solid rgba(100,140,180,0.18);
    border-top:2.5px solid rgba(100,180,255,0.80); border-radius:50%;
    animation: tfl-sub-spin 0.8s linear infinite;
  }}
  #tfl-sub-loading .ld-label {{
    font-family:'Avenir Next LT Pro',system-ui,sans-serif; font-size:10px;
    color:rgba(160,185,210,0.65); letter-spacing:0.06em;
  }}
  @keyframes tfl-sub-spin {{ 0%{{transform:rotate(0deg)}} 100%{{transform:rotate(360deg)}} }}
  #tfl-sub-coord {{
    position:absolute; bottom:10px; left:50%; transform:translateX(-50%); z-index:90;
    background:rgba(10,16,26,0.85); border:1px solid rgba(100,140,180,0.15);
    border-radius:6px; padding:2px 10px;
    font-family:'Avenir Next LT Pro',system-ui,sans-serif; font-size:10px;
    color:rgba(180,200,220,0.75); pointer-events:none; backdrop-filter:blur(6px);
    white-space:nowrap; letter-spacing:0.04em;
  }}
  #tfl-sub-sel-info {{
    position:absolute; top:52px; right:12px; z-index:90;
    background:rgba(10,16,26,0.92); border:1px solid rgba(0,180,255,0.25);
    border-radius:8px; padding:6px 12px; backdrop-filter:blur(6px);
    font-family:'Avenir Next LT Pro',system-ui,sans-serif; font-size:11px;
    color:rgba(200,220,240,0.90); display:none; max-width:260px;
  }}
  #tfl-sub-sel-info .sel-title {{
    font-weight:700; color:rgba(100,200,255,0.95); font-size:10px;
    text-transform:uppercase; letter-spacing:0.08em; margin-bottom:3px;
  }}

  /* -- Address Collector Panel -- */
  #tfl-sub-collector {{
    position:absolute; bottom:40px; left:12px; z-index:95;
    background:rgba(10,20,32,0.94); border:1px solid rgba(30,144,255,0.22);
    border-radius:12px; padding:10px 12px; min-width:210px; max-width:260px;
    font-family:'Avenir Next LT Pro',system-ui,sans-serif; font-size:11.5px;
    color:rgba(210,225,240,0.90); backdrop-filter:blur(10px);
    max-height:{height - 100}px; overflow-y:auto;
    box-shadow:0 8px 28px rgba(0,0,0,0.40);
    transition: max-height 0.3s ease, opacity 0.3s ease;
  }}
  #tfl-sub-collector::-webkit-scrollbar {{ width:4px; }}
  #tfl-sub-collector::-webkit-scrollbar-thumb {{ background:rgba(30,144,255,0.25); border-radius:4px; }}
  #tfl-sub-collector::-webkit-scrollbar-track {{ background:transparent; }}
  }}
  #tfl-sub-collector.collapsed {{ max-height:32px; overflow:hidden; }}
  #tfl-sub-collector .dc-title {{
    text-transform:uppercase; letter-spacing:0.14em; font-size:8.5px;
    color:rgba(30,144,255,0.82); font-weight:700; margin-bottom:6px;
    display:flex; align-items:center; justify-content:space-between;
    cursor:pointer; user-select:none;
  }}
  #tfl-sub-collector .dc-toggle {{
    font-size:11px; color:rgba(150,175,200,0.60); transition:transform 0.25s;
  }}
  #tfl-sub-collector.collapsed .dc-toggle {{ transform:rotate(180deg); }}
  #tfl-sub-collector .dc-body {{ }}
  #tfl-sub-collector.collapsed .dc-body {{ display:none; }}
  #tfl-sub-collector .dc-item {{
    display:flex; align-items:flex-start; gap:6px; padding:5px 0;
    border-bottom:1px solid rgba(255,255,255,0.06);
  }}
  #tfl-sub-collector .dc-item:last-child {{ border-bottom:none; }}
  #tfl-sub-collector .dc-num {{
    flex-shrink:0; width:18px; height:18px; border-radius:50%;
    background:rgba(30,144,255,0.18); border:1px solid rgba(30,144,255,0.30);
    display:flex; align-items:center; justify-content:center;
    font-size:9px; font-weight:700; color:rgba(30,144,255,0.90);
  }}
  #tfl-sub-collector .dc-addr {{
    font-size:11px; line-height:1.35; color:rgba(210,230,245,0.85);
  }}
  #tfl-sub-collector .dc-coord {{
    font-size:9px; color:rgba(160,185,210,0.55); margin-top:1px;
  }}
  #tfl-sub-collector .dc-empty {{
    text-align:center; padding:10px 0; color:rgba(180,200,220,0.45); font-size:10.5px;
  }}
  #tfl-sub-collector .dc-actions {{
    display:flex; gap:6px; margin-top:6px;
  }}
  #tfl-sub-collector .dc-btn {{
    flex:1; padding:5px 8px; border-radius:8px; border:1px solid rgba(30,144,255,0.25);
    background:rgba(30,144,255,0.10); color:rgba(30,144,255,0.90); cursor:pointer;
    font-size:10px; font-weight:600; text-align:center; transition:all 0.2s;
  }}
  #tfl-sub-collector .dc-btn:hover {{ background:rgba(30,144,255,0.22); border-color:rgba(30,144,255,0.40); }}
  #tfl-sub-collector .dc-btn.clear {{ background:rgba(255,80,80,0.08); border-color:rgba(255,80,80,0.20); color:rgba(255,120,120,0.85); }}
  #tfl-sub-collector .dc-btn.clear:hover {{ background:rgba(255,80,80,0.18); }}
  #tfl-sub-badge {{
    display:none;
  }}

  /* -- Toast Notification System -- */
  #tfl-sub-toast-container {{
    position:absolute; bottom:50px; left:50%; transform:translateX(-50%); z-index:200;
    display:flex; flex-direction:column-reverse; align-items:center; gap:8px;
    pointer-events:none;
  }}
  .tfl-toast {{
    background:rgba(10,20,32,0.95); border:1px solid rgba(30,144,255,0.30);
    border-radius:10px; padding:8px 18px; backdrop-filter:blur(12px);
    font-family:'Avenir Next LT Pro',system-ui,sans-serif; font-size:12px;
    color:rgba(210,230,245,0.95); box-shadow:0 6px 24px rgba(0,0,0,0.45);
    display:flex; align-items:center; gap:8px; white-space:nowrap;
    animation: tfl-toast-in 0.35s ease-out forwards;
    pointer-events:auto;
  }}
  .tfl-toast.success {{ border-color:rgba(40,180,100,0.40); }}
  .tfl-toast.success .toast-icon {{ color:#28b464; }}
  .tfl-toast.info {{ border-color:rgba(30,144,255,0.40); }}
  .tfl-toast.info .toast-icon {{ color:#1e90ff; }}
  .tfl-toast.warn {{ border-color:rgba(255,170,50,0.40); }}
  .tfl-toast.warn .toast-icon {{ color:#ffaa32; }}
  .tfl-toast.out {{ animation: tfl-toast-out 0.3s ease-in forwards; }}
  .toast-icon {{ font-size:15px; }}
  @keyframes tfl-toast-in {{ 0%{{opacity:0;transform:translateY(16px);}} 100%{{opacity:1;transform:translateY(0);}} }}
  @keyframes tfl-toast-out {{ 0%{{opacity:1;transform:translateY(0);}} 100%{{opacity:0;transform:translateY(-12px);}} }}

  /* -- Stats ribbon -- */
  #tfl-sub-stats {{
    position:absolute; top:10px; left:56px; z-index:90;
    background:rgba(10,16,26,0.88); border:1px solid rgba(100,140,180,0.15);
    border-radius:20px; padding:4px 16px; backdrop-filter:blur(8px);
    font-family:'Avenir Next LT Pro',system-ui,sans-serif; font-size:11px;
    color:rgba(200,220,240,0.85); pointer-events:none;
    display:flex; align-items:center; gap:14px; white-space:nowrap;
    animation: tfl-toast-in 0.5s ease-out 1.2s both;
  }}
  #tfl-sub-stats .stat-val {{ font-weight:700; color:rgba(100,200,255,0.95); }}
  #tfl-sub-stats .stat-sep {{ color:rgba(100,140,180,0.30); }}

  /* -- Hover tooltip -- */
  #tfl-sub-tooltip {{
    position:absolute; z-index:110; pointer-events:none;
    background:rgba(10,16,26,0.94); border:1px solid rgba(100,180,255,0.22);
    border-radius:8px; padding:5px 10px; backdrop-filter:blur(8px);
    font-family:'Avenir Next LT Pro',system-ui,sans-serif;
    color:rgba(210,230,245,0.92); display:none;
    box-shadow:0 4px 16px rgba(0,0,0,0.35);
    max-width:240px;
  }}
  #tfl-sub-tooltip .tt-name {{ font-size:11.5px; font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  #tfl-sub-tooltip .tt-val {{ font-size:10px; color:rgba(100,200,255,0.85); margin-top:2px; }}
  #tfl-sub-tooltip .tt-type {{ font-size:9px; color:rgba(150,175,200,0.55); margin-top:1px; }}

  /* -- Address delete button -- */
  #tfl-sub-collector .dc-del {{
    flex-shrink:0; width:16px; height:16px; border-radius:50%; margin-left:auto;
    background:rgba(255,80,80,0.08); border:1px solid rgba(255,80,80,0.20);
    color:rgba(255,120,120,0.70); font-size:10px; line-height:14px;
    text-align:center; cursor:pointer; transition:all 0.2s;
    display:flex; align-items:center; justify-content:center;
  }}
  #tfl-sub-collector .dc-del:hover {{ background:rgba(255,80,80,0.22); color:rgba(255,120,120,1); }}
</style>
<div style="width:100%;height:{height}px;position:relative;">
  <div id="tfl-subdivision-map" style="width:100%;height:100%;border-radius:14px;overflow:hidden;"></div>
  <div id="tfl-sub-legend" class="collapsed">
    <div class="leg-hdr" onclick="this.parentElement.classList.toggle('collapsed')">
      <span class="leg-title">Subdivisions &middot; click to filter</span>
      <span class="leg-toggle">&#9650;</span>
    </div>
    <div class="leg-body" id="tfl-sub-legend-body"></div>
  </div>
  <div id="tfl-sub-loading"><div class="ld-spinner"></div><div class="ld-label">Loading map layers&hellip;</div></div>
  <div id="tfl-sub-coord">&ndash;</div>
  <div id="tfl-sub-sel-info"></div>
  <div id="tfl-sub-badge">Click map or search to collect addresses</div>
  <div id="tfl-sub-toast-container"></div>
  <div id="tfl-sub-stats">
    <span><span class="stat-val" id="tfl-sub-stats-count">{total_sub}</span> subdivisions</span>
    <span class="stat-sep">|</span>
    <span>TFL est. <span class="stat-val" id="tfl-sub-stats-high">{total_sub_high_fmt}</span></span>
  </div>
  <div id="tfl-sub-tooltip"><div class="tt-name"></div><div class="tt-val"></div><div class="tt-type"></div></div>
  <div id="tfl-sub-collector">
    <div class="dc-title" onclick="this.parentElement.classList.toggle('collapsed')">
      <span>&#x1F4CD; Collected Addresses <span id="tfl-sub-addr-count">0</span></span>
      <span class="dc-toggle">&#9650;</span>
    </div>
    <div class="dc-body">
      <div id="tfl-sub-addr-list"><div class="dc-empty">Click on the map, use Search, or draw an area to collect addresses.</div></div>
      <div class="dc-actions">
        <div class="dc-btn" id="tfl-sub-send-forensics-btn">&#x1F50D; Send to Forensics</div>
        <div class="dc-btn" id="tfl-sub-send-batch-btn">&#x1F4E5; Send to Batch</div>
      </div>
      <div class="dc-actions" style="margin-top:4px;">
        <div class="dc-btn clear" id="tfl-sub-clear-btn">Clear</div>
      </div>
    </div>
  </div>
</div>
<script src="https://js.arcgis.com/4.30/"></script>
<script>
  const tflPoints = {payload_json};
  const baseMapId = {basemap_safe};
  const typeColors = {type_colors_json};
  const legendItems = {legend_items_json};

  /* Track hidden types for interactive legend filtering */
  const hiddenTypes = new Set();
  function broadcastAddressPayload(payload) {{
    try {{
      window.parent.postMessage(payload, "*");
    }} catch (_) {{}}
    try {{
      if (window.top && window.top !== window.parent) {{
        window.top.postMessage(payload, "*");
      }}
    }} catch (_) {{}}
    try {{
      const frames = window.parent.frames;
      for (let i = 0; i < frames.length; i++) {{
        try {{ frames[i].postMessage(payload, "*"); }} catch(_) {{}}
      }}
    }} catch (_) {{}}
  }}

  /* Build interactive legend */
  let filterCallback = null;
  (function() {{
    const body = document.getElementById("tfl-sub-legend-body");
    if (!body || legendItems.length === 0) return;
    let h = "";
    for (const e of legendItems) {{
      h += '<div class="leg-row" data-type="' + e.type + '"><div class="leg-left"><span class="leg-chip" style="background:' + e.color + ';"></span><span class="leg-label">' + e.type + '</span></div><span class="leg-count">' + e.count + '</span></div>';
    }}
    body.innerHTML = h;
    body.querySelectorAll(".leg-row").forEach(row => {{
      row.addEventListener("click", () => {{
        const t = row.getAttribute("data-type");
        if (hiddenTypes.has(t)) {{ hiddenTypes.delete(t); row.classList.remove("dimmed"); }}
        else {{ hiddenTypes.add(t); row.classList.add("dimmed"); }}
        if (filterCallback) filterCallback();
      }});
    }});
  }})();

  require([
    "esri/Map",
    "esri/views/MapView",
    "esri/layers/FeatureLayer",
    "esri/layers/GraphicsLayer",
    "esri/Graphic",
    "esri/widgets/Home",
    "esri/widgets/ScaleBar",
    "esri/widgets/BasemapToggle",
    "esri/widgets/Compass",
    "esri/widgets/Fullscreen",
    "esri/widgets/Search",
    "esri/widgets/Locate",
    "esri/widgets/Sketch",
    "esri/widgets/Expand",
    "esri/geometry/geometryEngine"
  ], function(Map, MapView, FeatureLayer, GraphicsLayer, Graphic, Home, ScaleBar, BasemapToggle, Compass, Fullscreen, Search, Locate, Sketch, Expand, geometryEngine) {{
    const map = new Map({{ basemap: baseMapId }});

    /* -- Address collector state -- */
    const collectedAddresses = [];
    const pinsLayer = new GraphicsLayer();
    const geocodeUrl = "{ARCGIS_GEOCODER_URL}";

    const districtLayer = new FeatureLayer({{
      url: "{TEA_ARCGIS_SCHOOL_DISTRICT_LAYER_URL}",
      outFields: ["FID", "NAME20", "DISTRICT"],
      popupEnabled: false, labelsVisible: false,
      labelingInfo: [{{
        labelExpressionInfo: {{ expression: "$feature.NAME20" }},
        symbol: {{ type: "text", color: [73, 112, 150, 0.65], haloColor: [13, 23, 36, 0.80], haloSize: 0.6,
          font: {{ size: 8, family: "Avenir Next LT Pro", weight: "normal" }} }}
      }}],
      renderer: {{ type: "simple", symbol: {{ type: "simple-fill", color: [0,0,0,0], outline: {{ color: [73, 112, 150, 0.25], width: 0.6 }} }} }},
      opacity: 0.40
    }});

    const countyLayer = new FeatureLayer({{
      url: "{TEA_ARCGIS_COUNTY_LAYER_URL}",
      outFields: ["FENAME", "FIPS"],
      popupEnabled: false, labelsVisible: false,
      labelingInfo: [{{
        labelExpressionInfo: {{ expression: "$feature.FENAME + ' County'" }},
        symbol: {{ type: "text", color: [160, 140, 110, 0.80], haloColor: [13, 23, 36, 0.82], haloSize: 0.9,
          font: {{ size: 12, family: "Avenir Next LT Pro", weight: "600" }} }}
      }}],
      renderer: {{ type: "simple", symbol: {{ type: "simple-fill", color: [0,0,0,0], outline: {{ color: [145, 111, 63, 0.22], width: 0.6 }} }} }},
      opacity: 0.35
    }});

    const cityLayer = new FeatureLayer({{
      url: "{CENSUS_ARCGIS_TEXAS_CITY_LAYER_URL}",
      outFields: ["NAME", "BASENAME", "GEOID", "STATE"],
      definitionExpression: "STATE = '48'",
      popupEnabled: false, labelsVisible: false,
      labelingInfo: [{{
        labelExpressionInfo: {{ expression: "DefaultValue($feature.BASENAME, $feature.NAME)" }},
        symbol: {{ type: "text", color: [165, 100, 105, 0.80], haloColor: [13, 23, 36, 0.76], haloSize: 0.7,
          font: {{ size: 9, family: "Avenir Next LT Pro", weight: "500" }} }}
      }}],
      renderer: {{ type: "simple", symbol: {{ type: "simple-fill", color: [0,0,0,0], outline: {{ color: [158, 42, 43, 0.12], width: 0.4 }} }} }},
      opacity: 0.20
    }});

    /* TX House & Senate district boundaries */
    const houseLayer = new FeatureLayer({{
      url: "{TEXAS_HOUSE_DISTRICTS_LAYER_URL}",
      outFields: ["*"], popupEnabled: true,
      popupTemplate: {{ title: "TX House District {{{{DISTRICT}}}}", content: "Texas House of Representatives District {{{{DISTRICT}}}}" }},
      labelsVisible: false,
      labelingInfo: [{{ labelExpressionInfo: {{ expression: "'HD ' + $feature.DISTRICT" }},
        symbol: {{ type: "text", color: [90, 180, 130, 0.70], haloColor: [13, 23, 36, 0.75], haloSize: 0.6,
          font: {{ size: 8, family: "Avenir Next LT Pro", weight: "600" }} }} }}],
      renderer: {{ type: "simple", symbol: {{ type: "simple-fill", color: [40, 180, 100, 0.03], outline: {{ color: [40, 180, 100, 0.30], width: 0.8 }} }} }},
      opacity: 0.30, visible: false
    }});
    const senateLayer = new FeatureLayer({{
      url: "{TEXAS_SENATE_DISTRICTS_LAYER_URL}",
      outFields: ["*"], popupEnabled: true,
      popupTemplate: {{ title: "TX Senate District {{{{DISTRICT}}}}", content: "Texas Senate District {{{{DISTRICT}}}}" }},
      labelsVisible: false,
      labelingInfo: [{{ labelExpressionInfo: {{ expression: "'SD ' + $feature.DISTRICT" }},
        symbol: {{ type: "text", color: [180, 130, 90, 0.70], haloColor: [13, 23, 36, 0.75], haloSize: 0.6,
          font: {{ size: 9, family: "Avenir Next LT Pro", weight: "600" }} }} }}],
      renderer: {{ type: "simple", symbol: {{ type: "simple-fill", color: [200, 140, 60, 0.03], outline: {{ color: [200, 140, 60, 0.30], width: 0.8 }} }} }},
      opacity: 0.30, visible: false
    }});

    map.add(districtLayer);
    map.add(countyLayer);
    map.add(houseLayer);
    map.add(senateLayer);
    map.add(cityLayer);

    const graphics = new GraphicsLayer();
    const sketchLayer = new GraphicsLayer();
    map.add(graphics);
    map.add(sketchLayer);
    map.add(pinsLayer);

    const view = new MapView({{
      container: "tfl-subdivision-map",
      map,
      center: [-99.3, 31.1],
      zoom: 5,
      constraints: {{ minZoom: 5 }},
      popup: {{ dockEnabled: true, dockOptions: {{ position: "bottom-right", breakpoint: false }} }},
      ui: {{ padding: {{ top: 10, right: 10, bottom: 30, left: 10 }} }}
    }});

    /* -- Address collector helper functions -- */
    function updateCollectorUI() {{
      const listEl = document.getElementById("tfl-sub-addr-list");
      const countEl = document.getElementById("tfl-sub-addr-count");
      if (countEl) countEl.textContent = collectedAddresses.length;
      if (!listEl) return;
      if (collectedAddresses.length === 0) {{
        listEl.innerHTML = '<div class="dc-empty">Click on the map, use Search, or draw an area to collect addresses.</div>';
        return;
      }}
      listEl.innerHTML = collectedAddresses.map((a, i) =>
        '<div class="dc-item">'
        + '<div class="dc-num">' + (i + 1) + '</div>'
        + '<div style="flex:1;min-width:0;"><div class="dc-addr">' + (a.address || "Unknown") + '</div>'
        + '<div class="dc-coord">' + Number(a.lat).toFixed(5) + '\u00b0 N, ' + Math.abs(a.lon).toFixed(5) + '\u00b0 W</div>'
        + '</div>'
        + '<div class="dc-del" onclick="window._tflRemoveAddr(' + i + ')" title="Remove">\u00d7</div>'
        + '</div>'
      ).join("");
    }}

    /* Toast notification system */
    function showToast(message, type) {{
      type = type || "info";
      const icons = {{ success: "\u2713", info: "\u2139\uFE0F", warn: "\u26A0\uFE0F" }};
      const container = document.getElementById("tfl-sub-toast-container");
      if (!container) return;
      const toast = document.createElement("div");
      toast.className = "tfl-toast " + type;
      toast.innerHTML = '<span class="toast-icon">' + (icons[type] || "") + '</span><span>' + message + '</span>';
      container.appendChild(toast);
      setTimeout(() => {{ toast.classList.add("out"); setTimeout(() => toast.remove(), 320); }}, 2600);
    }}

    /* Remove individual address by index */
    function removeAddress(idx) {{
      if (idx < 0 || idx >= collectedAddresses.length) return;
      collectedAddresses.splice(idx, 1);
      /* Rebuild pins layer to match */
      pinsLayer.removeAll();
      collectedAddresses.forEach((a) => {{
        pinsLayer.add(new Graphic({{
          geometry: {{ type: "point", longitude: a.lon, latitude: a.lat }},
          symbol: {{ type: "simple-marker", style: "circle", size: 10, color: [30,144,255,0.85], outline: {{ color: [255,255,255,0.80], width: 1.5 }} }},
          attributes: {{ address: a.address, lat: a.lat, lon: a.lon }},
          popupTemplate: {{ title: a.address || "Point", content: "Lat: " + a.lat.toFixed(5) + ", Lon: " + a.lon.toFixed(5) }}
        }}));
      }});
      updateCollectorUI();
      showToast("Address removed", "info");
    }}
    /* Expose removeAddress globally for inline onclick */
    window._tflRemoveAddr = removeAddress;

    function addAddress(address, lat, lon) {{
      const exists = collectedAddresses.some(a =>
        Math.abs(a.lat - lat) < 0.0001 && Math.abs(a.lon - lon) < 0.0001
      );
      if (exists) {{
        showToast("Address already collected", "warn");
        return;
      }}
      collectedAddresses.push({{ address, lat, lon }});
      pinsLayer.add(new Graphic({{
        geometry: {{ type: "point", longitude: lon, latitude: lat }},
        symbol: {{ type: "simple-marker", style: "circle", size: 12, color: [30,144,255,0.85], outline: {{ color: [255,255,255,0.90], width: 2 }} }},
        attributes: {{ address, lat, lon }},
        popupTemplate: {{ title: address || "Point", content: "Lat: " + lat.toFixed(5) + ", Lon: " + lon.toFixed(5) }}
      }}));
      updateCollectorUI();
      showToast((address || "Point").substring(0, 50) + " added", "success");
      /* Fly to the newly added point */
      view.goTo({{ center: [lon, lat], zoom: Math.max(view.zoom || 10, 12) }}, {{ duration: 700, easing: "ease-in-out" }}).catch(() => {{}});
      try {{
        window.parent.postMessage({{
          type: "tfl-draw-address-found",
          address: address, lat: lat, lon: lon,
          allAddresses: collectedAddresses.slice()
        }}, "*");
      }} catch(e) {{}}
    }}

    function reverseGeocode(lat, lon) {{
      const url = geocodeUrl.replace("findAddressCandidates", "reverseGeocode")
        + "?location=" + lon + "," + lat
        + "&outSR=4326&langCode=en&f=json";
      fetch(url).then(r => r.json()).then(data => {{
        const addr = (data.address && data.address.LongLabel) || (data.address && data.address.ShortLabel) || ("Point: " + lat.toFixed(5) + ", " + lon.toFixed(5));
        addAddress(addr, lat, lon);
      }}).catch(() => {{
        addAddress("Point: " + lat.toFixed(5) + ", " + lon.toFixed(5), lat, lon);
      }});
    }}

    const formatUsd = (v) => Number(v||0).toLocaleString("en-US",{{style:"currency",currency:"USD",maximumFractionDigits:0}});
    const maxHigh = tflPoints.reduce((a, r) => Math.max(a, Number(r.high_total || 0)), 0);
    const sz = (v) => {{
      if (maxHigh <= 0) return 9;
      const n = Math.max(0, Number(v || 0));
      return Math.max(8, Math.min(30, 8 + (Math.log10(n+1)/Math.log10(maxHigh+1))*22));
    }};

    for (const row of tflPoints) {{
      const clientsHtml = row.match_clients_preview || "";
      const extraHtml = row.extra_count > 0 ? `, +${{row.extra_count}} more` : "";
      const g = new Graphic({{
        geometry: {{ type: "point", longitude: row.lon, latitude: row.lat }},
        symbol: {{
          type: "simple-marker", size: sz(row.high_total),
          color: typeColors[row.subdivision_type] || [113, 129, 145, 0.9],
          outline: {{ color: [255, 255, 255, 0.70], width: 1 }}
        }},
        attributes: row,
        popupTemplate: {{
          title: row.subdivision_name || "Political Subdivision",
          content: `<div style="font-family:'Avenir Next LT Pro',system-ui,sans-serif;font-size:12px;line-height:1.5;">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid rgba(140,160,180,0.15);">
              <div style="width:10px;height:10px;border-radius:50%;background:${{(Object.values(typeColors).find((_, idx) => Object.keys(typeColors)[idx] === row.subdivision_type) || [113,129,145]).slice(0,3).map(v => typeof v === 'number' ? v : 113).join(',') }};flex-shrink:0;border:1px solid rgba(255,255,255,0.15);"></div>
              <span style="font-size:10px;color:rgba(150,175,200,0.70);text-transform:uppercase;letter-spacing:0.08em;font-weight:600;">${{row.subdivision_type}}</span>
            </div>
            <table style="border-collapse:collapse;width:100%;">
              <tr><td style="color:#7a94ab;padding:3px 8px 3px 0;font-size:11px;">Code</td><td style="font-weight:500;">${{row.subdivision_code || "N/A"}}</td></tr>
              <tr><td style="color:#7a94ab;padding:3px 8px 3px 0;font-size:11px;">TFL high est.</td><td style="font-weight:700;color:rgba(100,200,255,0.95);">${{formatUsd(row.high_total)}}</td></tr>
              <tr><td style="color:#7a94ab;padding:3px 8px 3px 0;font-size:11px;">Source</td><td>${{row.source_name || "N/A"}}</td></tr>
              <tr><td style="color:#7a94ab;padding:3px 8px 3px 0;font-size:11px;">Matched clients</td><td style="font-weight:600;">${{row.match_count}}</td></tr>
            </table>
            <div style="margin-top:6px;padding-top:5px;border-top:1px solid rgba(140,160,180,0.12);font-size:10.5px;line-height:1.6;color:rgba(200,215,230,0.80);">${{clientsHtml}}${{extraHtml}}</div>
          </div>`
        }}
      }});
      graphics.add(g);
    }}

    /* Interactive legend filtering callback */
    filterCallback = () => {{
      let visCount = 0, visHigh = 0;
      graphics.graphics.forEach(g => {{
        if (g.attributes && g.attributes.subdivision_type) {{
          const vis = !hiddenTypes.has(g.attributes.subdivision_type);
          g.visible = vis;
          if (vis) {{ visCount++; visHigh += Number(g.attributes.high_total || 0); }}
        }}
      }});
      /* Update stats ribbon */
      const cEl = document.getElementById("tfl-sub-stats-count");
      const hEl = document.getElementById("tfl-sub-stats-high");
      if (cEl) cEl.textContent = visCount.toLocaleString();
      if (hEl) hEl.textContent = formatUsd(visHigh);
    }};

    const updateLabels = () => {{
      const z = Number(view.zoom || 0);
      countyLayer.labelsVisible = z >= 5;
      cityLayer.labelsVisible = z >= 6.2;
      districtLayer.labelsVisible = z >= 8.5;
      houseLayer.labelsVisible = z >= 8;
      senateLayer.labelsVisible = z >= 7;
    }};
    view.watch("zoom", updateLabels);

    /* -- Widgets -- */
    const home = new Home({{ view }});
    const basemapToggle = new BasemapToggle({{ view, nextBasemap: baseMapId === "hybrid" ? "gray-vector" : "hybrid" }});
    const scaleBar = new ScaleBar({{ view, unit: "dual" }});
    const compass = new Compass({{ view }});
    const fullscreen = new Fullscreen({{ view }});
    const locate = new Locate({{ view }});
    const search = new Search({{
      view, popupEnabled: true, resultGraphicEnabled: true,
      goToOverride: (view, opts) => view.goTo(opts.target, {{ duration: 800, easing: "ease-in-out" }})
    }});
    search.on("select-result", (evt) => {{
      if (evt.result && evt.result.feature && evt.result.feature.geometry) {{
        const geom = evt.result.feature.geometry;
        addAddress(evt.result.name || "", geom.latitude, geom.longitude);
      }}
    }});

    /* Sketch tool for encircling areas */
    const sketch = new Sketch({{
      view, layer: sketchLayer, creationMode: "single",
      availableCreateTools: ["polygon", "circle", "rectangle"],
      defaultCreateOptions: {{ mode: "freehand" }},
      visibleElements: {{ selectionTools: {{ "lasso-selection": false, "rectangle-selection": false }}, settingsMenu: false, undoRedoMenu: true }},
      defaultUpdateOptions: {{ tool: "reshape" }}
    }});
    const sketchExpand = new Expand({{
      view, content: sketch, expandIconClass: "esri-icon-polygon",
      expandTooltip: "Draw area for batch analysis", group: "tools"
    }});

    /* House/Senate layer toggle */
    const layerDiv = document.createElement("div");
    layerDiv.style.cssText = "background:rgba(13,23,36,0.94);border-radius:8px;padding:10px;font-family:'Avenir Next LT Pro',system-ui,sans-serif;font-size:12px;color:rgba(210,225,240,0.90);min-width:160px;";
    layerDiv.innerHTML = '<div style="font-size:9px;text-transform:uppercase;letter-spacing:0.12em;color:rgba(150,175,200,0.65);font-weight:700;margin-bottom:6px;">Legislative Districts</div>'
      + '<label style="display:flex;align-items:center;gap:6px;cursor:pointer;padding:3px 0;"><input type="checkbox" id="tfl-sub-toggle-house" style="accent-color:#28b464;"><span>TX House Districts</span></label>'
      + '<label style="display:flex;align-items:center;gap:6px;cursor:pointer;padding:3px 0;"><input type="checkbox" id="tfl-sub-toggle-senate" style="accent-color:#c88c3c;"><span>TX Senate Districts</span></label>';
    const layerExpand = new Expand({{
      view, content: layerDiv, expandIconClass: "esri-icon-layer-list",
      expandTooltip: "Toggle legislative districts", group: "tools"
    }});

    view.ui.add(home, "top-left");
    view.ui.add(compass, "top-left");
    view.ui.add(fullscreen, "top-left");
    view.ui.add(locate, "top-left");
    view.ui.add(sketchExpand, "top-left");
    view.ui.add(layerExpand, "top-left");
    view.ui.add(search, "top-right");
    view.ui.add(basemapToggle, "top-right");
    view.ui.add(scaleBar, "bottom-left");

    /* Wire layer toggles */
    view.when(() => {{
      const hBox = document.getElementById("tfl-sub-toggle-house");
      const sBox = document.getElementById("tfl-sub-toggle-senate");
      if (hBox) hBox.addEventListener("change", () => {{ houseLayer.visible = hBox.checked; }});
      if (sBox) sBox.addEventListener("change", () => {{ senateLayer.visible = sBox.checked; }});
    }});

    /* Sketch complete → batch analysis info + address scanning */
    sketch.on("create", (evt) => {{
      if (evt.state !== "complete") return;
      const drawn = evt.graphic.geometry;
      const selInfo = document.getElementById("tfl-sub-sel-info");
      const contained = [];
      graphics.graphics.forEach((g) => {{
        if (g.visible !== false && g.geometry && geometryEngine.contains(drawn, g.geometry)) contained.push(g.attributes || {{}});
      }});
      if (selInfo && contained.length > 0) {{
        const total = contained.reduce((a,r) => a + Number(r.high_total||0), 0);
        const types = [...new Set(contained.map(r => r.subdivision_type).filter(Boolean))];
        selInfo.style.display = "block";
        selInfo.innerHTML = '<div class="sel-title">Area Selection</div>'
          + '<div><strong>' + contained.length + '</strong> subdivision(s) in area</div>'
          + '<div>Combined TFL est.: <strong>' + formatUsd(total) + '</strong></div>'
          + '<div style="font-size:10px;color:rgba(180,200,220,0.65);margin-top:3px;">' + types.join(", ") + '</div>';
        try {{ window.parent.postMessage({{ type: "tfl-map-area-select", count: contained.length, totalHigh: total, types: types }}, "*"); }} catch(e) {{}}
      }} else if (selInfo) {{
        selInfo.style.display = "block";
        selInfo.innerHTML = '<div class="sel-title">Area Selection</div><div>No subdivisions in drawn area.</div>';
        setTimeout(() => {{ selInfo.style.display = "none"; }}, 3000);
      }}

      /* Reverse-geocode sampled points within the drawn area */
      const ext = drawn.extent;
      if (ext) {{
        const cx = ext.center.longitude, cy = ext.center.latitude;
        const dx = (ext.xmax - ext.xmin), dy = (ext.ymax - ext.ymin);
        const SAMPLES = 5;
        reverseGeocode(cy, cx);
        for (let xi = 0; xi < SAMPLES; xi++) {{
          for (let yi = 0; yi < SAMPLES; yi++) {{
            const px = ext.xmin + (dx * (xi + 0.5) / SAMPLES);
            const py = ext.ymin + (dy * (yi + 0.5) / SAMPLES);
            const testPt = {{ type: "point", longitude: px, latitude: py, spatialReference: {{ wkid: 4326 }} }};
            if (geometryEngine.contains(drawn, testPt)) {{
              reverseGeocode(py, px);
            }}
          }}
        }}
        const badge = document.getElementById("tfl-sub-badge");
        if (badge) badge.textContent = "Area scanned \u2014 see collected addresses \u2192";
        setTimeout(() => {{
          try {{ window.parent.postMessage({{ type: "tfl-draw-area-addresses", allAddresses: collectedAddresses.slice() }}, "*"); }} catch(e) {{}}
        }}, 3000);
      }}
    }});

    /* Click → reverse geocode for address collection */
    view.on("click", (evt) => {{
      if (evt.mapPoint) {{
        reverseGeocode(evt.mapPoint.latitude, evt.mapPoint.longitude);
      }}
    }});

    /* Coordinate readout */
    view.on("pointer-move", (evt) => {{
      const pt = view.toMap(evt);
      const el = document.getElementById("tfl-sub-coord");
      if (pt && el) el.textContent = pt.latitude.toFixed(5) + "\u00b0 N, " + Math.abs(pt.longitude).toFixed(5) + "\u00b0 W";
    }});

    /* Hover highlight + tooltip */
    let hoverHL = null;
    view.on("pointer-move", (evt) => {{
      const tooltip = document.getElementById("tfl-sub-tooltip");
      view.hitTest(evt, {{ include: [graphics] }}).then((r) => {{
        const hit = r.results && r.results.find(x => x.graphic && x.graphic.attributes && x.graphic.attributes.subdivision_name);
        document.getElementById("tfl-subdivision-map").style.cursor = hit ? "pointer" : "default";
        if (hoverHL) {{ graphics.remove(hoverHL); hoverHL = null; }}
        if (hit && hit.graphic && hit.graphic.geometry) {{
          hoverHL = new Graphic({{
            geometry: hit.graphic.geometry,
            symbol: {{ type: "simple-marker", style: "circle", size: 30, color: [255,255,255,0.0], outline: {{ color: [255,255,255,0.55], width: 2 }} }}
          }});
          graphics.add(hoverHL);
          /* Show tooltip */
          if (tooltip) {{
            const a = hit.graphic.attributes;
            tooltip.querySelector(".tt-name").textContent = a.subdivision_name || "";
            tooltip.querySelector(".tt-val").textContent = formatUsd(a.high_total);
            tooltip.querySelector(".tt-type").textContent = a.subdivision_type || "";
            tooltip.style.display = "block";
            tooltip.style.left = (evt.x + 14) + "px";
            tooltip.style.top = (evt.y - 10) + "px";
          }}
        }} else {{
          if (tooltip) tooltip.style.display = "none";
        }}
      }});
    }});

    /* -- Send to Forensics (first address) -- */
    document.getElementById("tfl-sub-send-forensics-btn").addEventListener("click", () => {{
      if (collectedAddresses.length === 0) {{ showToast("No addresses collected yet", "warn"); return; }}
      const payload = {{
        type: "tfl-send-address",
        action: "forensics",
        address: collectedAddresses[0].address || "",
        addresses: collectedAddresses.map(a => a.address),
        nonce: Date.now()
      }};
      broadcastAddressPayload(payload);
      showToast("Sent to Address Forensics", "success");
    }});

    /* -- Send All to Batch -- */
    document.getElementById("tfl-sub-send-batch-btn").addEventListener("click", () => {{
      if (collectedAddresses.length === 0) {{ showToast("No addresses collected yet", "warn"); return; }}
      const payload = {{
        type: "tfl-send-address",
        action: "batch",
        address: collectedAddresses[0].address || "",
        addresses: collectedAddresses.map(a => a.address),
        nonce: Date.now()
      }};
      broadcastAddressPayload(payload);
      showToast(collectedAddresses.length + " address(es) sent to Batch", "success");
    }});

    /* Clear button */
    document.getElementById("tfl-sub-clear-btn").addEventListener("click", () => {{
      const count = collectedAddresses.length;
      collectedAddresses.length = 0;
      pinsLayer.removeAll();
      sketchLayer.removeAll();
      updateCollectorUI();
      const badge = document.getElementById("tfl-sub-badge");
      if (badge) badge.textContent = "Click map or search to collect addresses";
      const selInfo = document.getElementById("tfl-sub-sel-info");
      if (selInfo) selInfo.style.display = "none";
      if (count > 0) showToast(count + " address(es) cleared", "info");
    }});

    view.when(() => {{
      const loader = document.getElementById("tfl-sub-loading");
      const ldLabel = loader && loader.querySelector(".ld-label");
      if (ldLabel) ldLabel.textContent = "Rendering " + tflPoints.length + " subdivisions\u2026";
      setTimeout(() => {{
        if (ldLabel) ldLabel.textContent = "Almost ready\u2026";
      }}, 600);
      setTimeout(() => {{
        if (loader) {{ loader.style.opacity = "0"; setTimeout(() => loader.remove(), 600); }}
      }}, 900);
      updateLabels();
      if (graphics.graphics.length > 0) {{
        view.goTo(graphics.graphics.toArray(), {{ padding: {{ top: 50, right: 50, bottom: 50, left: 50 }}, duration: 1000, easing: "ease-in-out" }}).catch(() => {{}});
      }}
    }});
  }});
</script>
"""
    )
    _persistent_html_frame(
        html=arcgis_html,
        signature=subdivision_map_signature,
        height=int(height) + 8,
        key="mp5_tfl_subdivision_map_v3",
        default=None,
    )

PRIMARY_PATTERNS = [
    (r"\bmetropolitan transit authority\b", "Transit Authority"),
    (r"\bregional mobility authority\b", "Regional Mobility Authority"),
    (r"\bwater control ?&? improvement district\b", "Water Control & Improvement District"),
    (r"\bmunicipal utility district\b", "Municipal Utility District"),
    (r"\bmud\b", "Municipal Utility District"),
    (r"\bgroundwater conservation district\b", "Groundwater Conservation District"),
    (r"\bhospital district\b", "Hospital District"),
    (r"\bemergency services district\b", "Emergency Services District"),
    (r"\bappraisal district\b", "Appraisal District"),
    (r"\bhousing authority\b", "Housing Authority"),
    (r"\btransit authority\b", "Transit Authority"),
    (r"\bthe league\b|\bleague\b", "League"),
    (r"\briver authority\b", "River Authority"),
    (r"\bnavigation district\b", "Navigation District"),
    (r"\bport authority\b", "Port Authority"),
    (r"\bdrainage district\b", "Drainage District"),
    (r"\b(independent )?school district\b", "Independent School District"),
    (r"\bschool district\b", "Independent School District"),
    (r"(^|\s)isd($|\s|[^a-z])", "Independent School District"),
    (r"\bwcid\b", "Water Control & Improvement District"),
    (r"\bpublic improvement district\b", "Public Improvement District"),
    (r"(^|\s)pid($|\s|[^a-z])", "Public Improvement District"),
    (r"\bmunicipal corporation\b|\blocal government corporation\b|\bcorporation\b", "Local Government Corporation"),
    (r"\bcoalition\b", "Coalition"),
    (r"\bassociation\b", "Association"),
    (r"\bcommittee\b", "Committee"),
    (r"\bfoundation\b", "Foundation"),
    (r"\bcollege\b", "College"),
    (r"\bboard\b", "Board"),
    (r"\bauthority\b", "Authority"),
    (r"\bdistrict\b", "District"),
    (r"\bcity\b", "City"),
    (r"\bcounty\b", "County"),
]

COARSE_CATEGORY = {
    "Independent School District": "Public School Districts",
    "Transit Authority": "Special Districts and Other Authorities",
    "Regional Mobility Authority": "Special Districts and Other Authorities",
    "Water Control & Improvement District": "Special Districts and Other Authorities",
    "Municipal Utility District": "Special Districts and Other Authorities",
    "Groundwater Conservation District": "Special Districts and Other Authorities",
    "Hospital District": "Special Districts and Other Authorities",
    "Emergency Services District": "Special Districts and Other Authorities",
    "Appraisal District": "Special Districts and Other Authorities",
    "Housing Authority": "Special Districts and Other Authorities",
    "River Authority": "Special Districts and Other Authorities",
    "Navigation District": "Special Districts and Other Authorities",
    "Port Authority": "Special Districts and Other Authorities",
    "Drainage District": "Special Districts and Other Authorities",
    "Public Improvement District": "Special Districts and Other Authorities",
    "Local Government Corporation": "Special Districts and Other Authorities",
    "Authority": "Special Districts and Other Authorities",
    "District": "Special Districts and Other Authorities",
    "City": "Cities, Towns, Villages",
    "County": "County",
    "College": "Community and Junior Colleges",
    "Coalition": "Associations",
    "Association": "Associations",
    "Foundation": "Associations",
    "Committee": "Associations",
    "Board": "Associations",
    "League": "Associations",
}

def normalize_entity_name(name: str) -> str:
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return ""
    s = str(name).strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s

def match_entity_type(name: str) -> tuple[str, str]:
    s = normalize_entity_name(name)
    for pattern, canonical in PRIMARY_PATTERNS:
        if re.search(pattern, s, flags=re.IGNORECASE):
            coarse = COARSE_CATEGORY.get(canonical, None)
            if canonical == "Independent School District":
                coarse = "Public School Districts"
            if canonical in ("City",):
                coarse = "Cities, Towns, Villages"
            if canonical in ("County",):
                coarse = "County"
            if not coarse:
                coarse = COARSE_CATEGORY.get(canonical, "Special Districts and Other Authorities")
            return canonical, coarse

    if re.search(r"\bschool\b", s):
        return "Independent School District", "Public School Districts"

    if re.search(r"\bcommunity college\b|\bjunior college\b", s):
        return "College", "Community and Junior Colleges"

    if re.search(r"\bcity\b|\btown\b|\bvillage\b", s):
        return "City", "Cities, Towns, Villages"
    if re.search(r"\bcounty\b", s):
        return "County", "County"
    if re.search(r"\bassociation\b|\bcoalition\b|\bfoundation\b|\bcommittee\b|\bboard\b", s):
        return "Association", "Associations"

    return "Other", "Other"

def filter_filer_rows(
    df: pd.DataFrame,
    session: str | None,
    lobbyshort: str,
    name_to_short: dict,
    lobbyist_norms: set[str],
    filerid_to_short: dict | None,
    filer_ids: set[int] | tuple[int, ...] | None = None,
    loose: bool = False,
) -> pd.DataFrame:
    if df.empty:
        return df

    d = df.copy()
    if session is not None:
        d = d[d["Session"].astype(str).str.strip() == str(session)]
    if d.empty:
        return d

    filerid_map = filerid_to_short or {}
    if "FilerID" in d.columns:
        d["FilerID"] = pd.to_numeric(d["FilerID"], errors="coerce").fillna(-1).astype(int)
    elif "filerIdent" in d.columns:
        d["FilerID"] = pd.to_numeric(d["filerIdent"], errors="coerce").fillna(-1).astype(int)
    else:
        d["FilerID"] = -1

    if filerid_map:
        d["FilerShortFromId"] = d["FilerID"].map(filerid_map)
    else:
        d["FilerShortFromId"] = ""

    filer_name = d.get("filerName", pd.Series([""] * len(d)))
    filer_sort = d.get("filerSort", pd.Series([""] * len(d)))
    if isinstance(filer_name, pd.DataFrame):
        filer_name = filer_name.iloc[:, 0]
    if isinstance(filer_sort, pd.DataFrame):
        filer_sort = filer_sort.iloc[:, 0]
    filer_clean = clean_filer_name_series(filer_name)
    d["FilerNormRaw"] = norm_name_series(filer_name)
    d["FilerNormClean"] = norm_name_series(filer_clean)
    d["FilerSortNorm"] = norm_name_series(filer_sort)

    mapped = d["FilerNormRaw"].map(name_to_short)
    mapped = mapped.where(mapped.notna(), d["FilerNormClean"].map(name_to_short))
    mapped = mapped.where(mapped.notna(), d["FilerSortNorm"].map(name_to_short))
    d["FilerShortMapped"] = mapped

    lobbyshort_norm = norm_name(lobbyshort)
    d["FilerIsShort"] = (
        d["FilerNormClean"].eq(lobbyshort_norm) |
        d["FilerNormRaw"].eq(lobbyshort_norm)
    )

    ok = (
        (d["FilerShortFromId"].astype(str) == str(lobbyshort)) |
        (d["FilerShortMapped"].astype(str) == str(lobbyshort)) |
        (d["FilerNormRaw"].isin(lobbyist_norms) if lobbyist_norms else False) |
        (d["FilerNormClean"].isin(lobbyist_norms) if lobbyist_norms else False) |
        (d["FilerSortNorm"].isin(lobbyist_norms) if lobbyist_norms else False) |
        (d["FilerIsShort"])
    )
    if filer_ids:
        filer_ids_set = set()
        for x in filer_ids:
            try:
                if pd.isna(x):
                    continue
            except Exception:
                pass
            try:
                filer_ids_set.add(int(x))
            except Exception:
                try:
                    filer_ids_set.add(int(float(x)))
                except Exception:
                    continue
        if filer_ids_set:
            filer_match = d["FilerID"].isin(filer_ids_set)
            if filer_match.any():
                ok = filer_match
    if loose and not ok.any():
        loose_ok = pd.Series(False, index=d.index)

        if lobbyshort_norm and len(lobbyshort_norm) >= 4:
            loose_ok |= (
                d["FilerNormRaw"].str.contains(lobbyshort_norm, na=False) |
                d["FilerNormClean"].str.contains(lobbyshort_norm, na=False) |
                d["FilerSortNorm"].str.contains(lobbyshort_norm, na=False)
            )

        if lobbyist_norms:
            for n in lobbyist_norms:
                if n and len(n) >= 4:
                    loose_ok |= (
                        d["FilerNormRaw"].str.contains(n, na=False) |
                        d["FilerNormClean"].str.contains(n, na=False) |
                        d["FilerSortNorm"].str.contains(n, na=False)
                    )

        target_last = last_name_norm_from_text(lobbyshort)
        if target_last:
            last_raw = last_name_norm_series(filer_name)
            last_sort = last_name_norm_series(filer_sort)
            loose_ok |= last_raw.eq(target_last) | last_sort.eq(target_last)

        target_init = _last_first_initial_key(lobbyshort)
        if target_init:
            init_raw = filer_name.fillna("").astype(str).map(_last_first_initial_key)
            init_sort = filer_sort.fillna("").astype(str).map(_last_first_initial_key)
            loose_ok |= init_raw.eq(target_init) | init_sort.eq(target_init)

        ok = loose_ok

    return d.loc[ok]

def filter_filer_rows_multi(
    df: pd.DataFrame,
    session: str | None,
    lobbyshorts: list[str],
    name_to_short: dict,
    lobbyist_norms: set[str],
    filerid_to_short: dict | None,
    loose: bool = False,
) -> pd.DataFrame:
    if df.empty or not lobbyshorts:
        return df.iloc[0:0]

    lobbyshorts_set = {str(s).strip() for s in lobbyshorts if str(s).strip()}
    if not lobbyshorts_set:
        return df.iloc[0:0]

    d = df.copy()
    if session is not None:
        d = d[d["Session"].astype(str).str.strip() == str(session)]
    if d.empty:
        return d

    lobbyshort_norms = {norm_name(s) for s in lobbyshorts_set if s}
    norm_to_short = {norm_name(s): s for s in lobbyshorts_set if s}
    filerid_map = filerid_to_short or {}

    if "filerIdent" in d.columns and filerid_map:
        d["FilerID"] = pd.to_numeric(d["filerIdent"], errors="coerce").fillna(-1).astype(int)
        d["FilerShortFromId"] = d["FilerID"].map(filerid_map)
    else:
        d["FilerShortFromId"] = ""

    filer_name = d.get("filerName", pd.Series([""] * len(d)))
    filer_sort = d.get("filerSort", pd.Series([""] * len(d)))
    if isinstance(filer_name, pd.DataFrame):
        filer_name = filer_name.iloc[:, 0]
    if isinstance(filer_sort, pd.DataFrame):
        filer_sort = filer_sort.iloc[:, 0]
    filer_clean = clean_filer_name_series(filer_name)

    d["FilerNormRaw"] = norm_name_series(filer_name)
    d["FilerNormClean"] = norm_name_series(filer_clean)
    d["FilerSortNorm"] = norm_name_series(filer_sort)

    mapped = d["FilerNormRaw"].map(name_to_short)
    mapped = mapped.where(mapped.notna(), d["FilerNormClean"].map(name_to_short))
    mapped = mapped.where(mapped.notna(), d["FilerSortNorm"].map(name_to_short))
    d["FilerShortMapped"] = mapped

    d["FilerIsShort"] = (
        d["FilerNormClean"].isin(lobbyshort_norms) |
        d["FilerNormRaw"].isin(lobbyshort_norms)
    )

    ok = (
        d["FilerShortFromId"].astype(str).isin(lobbyshorts_set) |
        d["FilerShortMapped"].astype(str).isin(lobbyshorts_set) |
        (d["FilerNormRaw"].isin(lobbyist_norms) if lobbyist_norms else False) |
        (d["FilerNormClean"].isin(lobbyist_norms) if lobbyist_norms else False) |
        (d["FilerSortNorm"].isin(lobbyist_norms) if lobbyist_norms else False) |
        d["FilerIsShort"]
    )

    if loose and not ok.any():
        patterns = [re.escape(n) for n in list(lobbyshort_norms) + list(lobbyist_norms) if n and len(n) >= 4]
        if patterns:
            pat = "|".join(patterns)
            loose_ok = (
                d["FilerNormRaw"].str.contains(pat, na=False) |
                d["FilerNormClean"].str.contains(pat, na=False) |
                d["FilerSortNorm"].str.contains(pat, na=False)
            )
            ok = loose_ok

    d = d.loc[ok]
    if d.empty:
        return d

    matched = d["FilerShortFromId"].where(d["FilerShortFromId"].astype(str).isin(lobbyshorts_set), "")
    mapped_short = d["FilerShortMapped"].where(d["FilerShortMapped"].astype(str).isin(lobbyshorts_set), "")
    matched = matched.where(matched.astype(str).str.strip() != "", mapped_short)
    norm_short = d["FilerNormClean"].map(norm_to_short)
    norm_short = norm_short.where(norm_short.notna(), d["FilerNormRaw"].map(norm_to_short))
    matched = matched.where(matched.astype(str).str.strip() != "", norm_short)
    d["MatchedLobbyShort"] = matched.fillna("")
    return d

def last_name_norm_from_text(text: str) -> str:
    if not text:
        return ""
    s = str(text).replace("\u00A0", " ").strip()
    if not s:
        return ""
    if "," in s:
        last = s.split(",", 1)[0].strip()
    else:
        parts = s.split()
        last = parts[-1] if parts else ""
    return norm_name(last)

def last_name_norm_series(s: pd.Series) -> pd.Series:
    if isinstance(s, pd.DataFrame):
        s = s.iloc[:, 0] if s.shape[1] > 0 else pd.Series([], dtype="string")
    if not isinstance(s, pd.Series):
        s = pd.Series(s)
    s = (
        s.fillna("")
         .astype("string")
         .str.replace("\u00A0", " ", regex=False)
         .str.strip()
    )
    comma_mask = s.str.contains(",", na=False)
    last_from_comma = (
        s.where(comma_mask, "")
         .astype("string")
         .str.split(",", n=1)
         .str[0]
         .astype("string")
         .str.strip()
    )
    last_from_space = (
        s.where(~comma_mask, "")
         .astype("string")
         .str.split()
         .str[-1]
         .fillna("")
         .astype("string")
         .str.strip()
    )
    last = last_from_comma.where(comma_mask, last_from_space).fillna("")
    return norm_name_series(last)

def first_name_norm_series(s: pd.Series) -> pd.Series:
    if isinstance(s, pd.DataFrame):
        s = s.iloc[:, 0] if s.shape[1] > 0 else pd.Series([], dtype="string")
    if not isinstance(s, pd.Series):
        s = pd.Series(s)
    s = (
        s.fillna("")
         .astype("string")
         .str.replace("\u00A0", " ", regex=False)
         .str.strip()
    )
    comma_mask = s.str.contains(",", na=False)
    first_from_comma = (
        s.where(comma_mask, "")
         .astype("string")
         .str.split(",", n=1)
         .str[1]
         .fillna("")
         .astype("string")
         .str.strip()
         .str.split()
         .str[0]
         .fillna("")
         .astype("string")
         .str.strip()
    )
    first_from_space = (
        s.where(~comma_mask, "")
         .astype("string")
         .str.split()
         .str[0]
         .fillna("")
         .astype("string")
         .str.strip()
    )
    first = first_from_comma.where(comma_mask, first_from_space).fillna("")
    return norm_name_series(first)

def _last_first_initial_key(name: str) -> str:
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return ""
    s = str(name).replace("\u00A0", " ").strip()
    if not s:
        return ""
    if "," in s:
        last, rest = [p.strip() for p in s.split(",", 1)]
        first = rest
    else:
        toks = s.split()
        if len(toks) < 2:
            return ""
        first, last = toks[0], toks[-1]
    initial = ""
    for ch in first:
        if ch.isalnum():
            initial = ch
            break
    if not last or not initial:
        return ""
    return norm_name(f"{last} {initial}")

def norm_person_variants(user_text: str) -> set[str]:
    if not user_text:
        return set()
    t = clean_person_name(user_text)
    if not t:
        return set()

    if "," in t:
        parts = [p.strip() for p in t.split(",", 1)]
        last = parts[0]
        rest = parts[1] if len(parts) > 1 else ""
        first = rest.split()[0].strip() if rest else ""
    else:
        toks = t.split()
        if len(toks) == 1:
            first, last = "", toks[0]
        else:
            first, last = toks[0], toks[-1]

    variants = {norm_name(t)}
    raw_norm = norm_name(user_text)
    if raw_norm:
        variants.add(raw_norm)
    if first and last:
        variants |= {
            norm_name(f"{first} {last}"),
            norm_name(f"{last}, {first}"),
            norm_name(f"{last} {first}"),
            norm_name(f"{first}{last}"),
            norm_name(f"{last}{first}"),
        }
    return {v for v in variants if v}

def _nickname_variants(first_norm: str) -> set[str]:
    if not first_norm:
        return set()
    variants = {first_norm}
    if first_norm in _NICKNAME_MAP:
        variants |= _NICKNAME_MAP[first_norm]
    for base, nicknames in _NICKNAME_MAP.items():
        if first_norm in nicknames:
            variants.add(base)
            variants |= nicknames
    return {v for v in variants if v}

def norm_person_variants_with_nicknames(user_text: str) -> set[str]:
    variants = norm_person_variants(user_text)
    if not user_text:
        return variants
    t = clean_person_name(user_text)
    if not t:
        return variants

    def _add_nickname_variants(first_val: str, last_val: str) -> None:
        first_norm = norm_name(first_val)
        last_norm = norm_name(last_val)
        if not first_norm or not last_norm:
            return
        for fn in _nickname_variants(first_norm):
            if fn == first_norm:
                continue
            variants.add(f"{fn}{last_norm}")
            variants.add(f"{last_norm}{fn}")

    if "," in t:
        parts = [p.strip() for p in t.split(",", 1)]
        last = parts[0]
        rest = parts[1] if len(parts) > 1 else ""
        first = rest.split()[0].strip() if rest else ""
        _add_nickname_variants(first, last)
    else:
        toks = t.split()
        if len(toks) < 2:
            return variants
        first, last = toks[0], toks[-1]
        _add_nickname_variants(first, last)
        if len(toks) == 2:
            _add_nickname_variants(last, first)
    return {v for v in variants if v}

def person_display(org, last, first) -> str:
    org = "" if pd.isna(org) else str(org).strip()
    last = "" if pd.isna(last) else str(last).strip()
    first = "" if pd.isna(first) else str(first).strip()
    if org:
        return org
    if last and first:
        return f"{last}, {first}"
    return (last or first or "").strip()

def amount_display(exact, low, high, code=None) -> str:
    if pd.notna(exact) and str(exact).strip():
        return str(exact)
    if pd.notna(low) and str(low).strip():
        if pd.notna(high) and str(high).strip():
            return f"{low}--{high}"
        return str(low)
    if pd.notna(code) and str(code).strip():
        return str(code)
    return ""

def ensure_cols(df: pd.DataFrame, cols_with_defaults: dict) -> pd.DataFrame:
    missing = {c: v for c, v in cols_with_defaults.items() if c not in df.columns}
    if not missing:
        return df  # No copy needed when all columns present
    out = df.copy()
    for c, default in missing.items():
        out[c] = default
    return out

_SESSION_BASE_YEAR = 2023
_SESSION_BASE_NUM = 88

def _session_from_year(year_val) -> str:
    try:
        y = int(year_val)
    except Exception:
        return ""
    # Texas regular sessions map odd/even years to the same session.
    # Examples: 2023/2024 -> 88R, 2025/2026 -> 89R.
    session = _SESSION_BASE_NUM + ((y - _SESSION_BASE_YEAR) // 2)
    return f"{session}R"

def _add_session_from_year(df: pd.DataFrame) -> pd.DataFrame:
    if "Session" in df.columns:
        return df
    out = df.copy()
    year_col = None
    for cand in ["applicableYear", "applicable_year", "ApplicableYear", "year", "Year"]:
        if cand in out.columns:
            year_col = cand
            break
    if year_col:
        years = pd.to_numeric(out[year_col], errors="coerce")
        sessions = years.map(_session_from_year)
        out["Session"] = sessions
    else:
        out["Session"] = ""
    return out

def _build_filerid_map(frames: list[tuple[pd.DataFrame, str, str]]) -> dict[int, str]:
    rows = []
    for df, fid_col, short_col in frames:
        if not isinstance(df, pd.DataFrame) or df.empty:
            continue
        if fid_col not in df.columns or short_col not in df.columns:
            continue
        fid = pd.to_numeric(df[fid_col], errors="coerce")
        if fid.isna().all():
            continue
        short = df[short_col].fillna("").astype(str).str.strip()
        tmp = pd.DataFrame({"FilerID": fid, "LobbyShort": short})
        tmp = tmp.dropna(subset=["FilerID"])
        tmp["FilerID"] = tmp["FilerID"].astype(int)
        tmp = tmp[tmp["LobbyShort"].astype(str).str.strip() != ""]
        if not tmp.empty:
            rows.append(tmp)
    if not rows:
        return {}
    all_rows = pd.concat(rows, ignore_index=True)
    counts = (
        all_rows.groupby(["FilerID", "LobbyShort"])
        .size()
        .reset_index(name="n")
        .sort_values(["FilerID", "n"], ascending=[True, False])
        .drop_duplicates("FilerID")
    )
    return dict(zip(counts["FilerID"], counts["LobbyShort"]))

def _tfl_session_for_filter(session_val: str | None, tfl_sessions: set[str]) -> str | None:
    if session_val is None:
        return None
    s = str(session_val).strip()
    if not s:
        return ""
    # Lobby_TFL_Client_All rolls special sessions into the regular session (e.g., 891 -> 89R).
    if s.isdigit() and len(s) >= 3:
        reg = f"{s[:-1]}R"
        if reg in tfl_sessions:
            return reg
    return s

def fmt_usd(x: float, decimals: int = 0) -> str:
    try:
        return f"${x:,.{decimals}f}"
    except Exception:
        return "$0"

def _shorten_text(value: str, max_len: int = 36) -> str:
    s = str(value or "").strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 3].rstrip() + "..."

def render_pill_list(items: list[str], limit: int = 12, empty_label: str = "--") -> str:
    cleaned = [str(i).strip() for i in (items or []) if str(i).strip()]
    if not cleaned:
        return f'<div class="pill-list"><span class="pill pill-muted">{html.escape(empty_label)}</span></div>'
    seen = []
    for item in cleaned:
        if item not in seen:
            seen.append(item)
    shown = seen[:limit]
    pills = [f'<span class="pill">{html.escape(item)}</span>' for item in shown]
    if len(seen) > limit:
        pills.append(f'<span class="pill pill-muted">+{len(seen) - limit} more</span>')
    return '<div class="pill-list">' + "".join(pills) + "</div>"

def _current_filter_parts(extra: list[str] | None = None) -> list[str]:
    parts = []
    session_val = st.session_state.get("session", None)
    session_label = _session_label(session_val) if session_val is not None else ""
    if session_label:
        parts.append(f"Session: {session_label}")
    scope_label = st.session_state.get("scope", "")
    if scope_label:
        parts.append(f"Scope: {scope_label}")
    lobbyshort = st.session_state.get("lobbyshort", "").strip()
    query = st.session_state.get("search_query", "").strip()
    if lobbyshort:
        parts.append(f"Lobbyist: {_shorten_text(lobbyshort, 28)}")
    elif query:
        parts.append(f"Query: {_shorten_text(query, 28)}")
    if extra:
        parts.extend([p for p in extra if p])
    return parts

def _export_context_label(extra: list[str] | None = None, max_len: int = 72) -> str:
    parts = _current_filter_parts(extra)
    if not parts:
        return ""
    return _shorten_text(", ".join(parts), max_len)

def _export_filename(filename: str, extra: list[str] | None = None) -> str:
    parts = _current_filter_parts(extra)
    if not parts:
        return filename
    stem = Path(filename).stem or "export"
    suffix = Path(filename).suffix or ".csv"
    tokens = []
    for part in parts:
        token = re.sub(r"[^A-Za-z0-9]+", "-", part).strip("-").lower()
        if token:
            tokens.append(token)
    tokens = tokens[:4]
    if not tokens:
        return filename
    return f"{stem}__{'__'.join(tokens)}{suffix}"

def export_dataframe(df: pd.DataFrame, filename: str, label: str = "Download CSV", context: list[str] | str | None = None):
    extra = []
    if isinstance(context, str):
        extra = [context]
    elif isinstance(context, (list, tuple)):
        extra = [str(c) for c in context if c]
    context_label = _export_context_label(extra)
    export_label = f"{label} ({context_label})" if context_label else label
    export_name = _export_filename(filename, extra)
    _ = st.download_button(label=export_label, data=df.to_csv(index=False), file_name=export_name, mime="text/csv")
    if context_label:
        st.markdown(f'<div class="section-caption">CSV includes: {context_label}.</div>', unsafe_allow_html=True)
    return ""


def require_columns(df: pd.DataFrame, required: list[str], label: str, hint: str = "") -> bool:
    missing = [c for c in required if c not in df.columns]
    if not missing:
        return True
    st.warning(f"{label} is missing required columns: {', '.join(missing)}.")
    if hint:
        st.caption(hint)
    return False

def reset_filters(default_session: str) -> None:
    st.session_state.search_query = ""
    st.session_state.lobbyshort = ""
    st.session_state.lobby_filerid = None
    st.session_state.lobby_selected_key = ""
    st.session_state.lobby_all_matches = False
    st.session_state.lobby_merge_keys = []
    st.session_state.lobby_candidate_map = {}
    st.session_state.lobby_match_query = ""
    st.session_state.lobby_match_select = "No match"
    st.session_state.bill_search = ""
    st.session_state.activity_search = ""
    st.session_state.disclosure_search = ""
    st.session_state.lobby_policy_focus = {}
    st.session_state.filter_lobbyshort = ""
    st.session_state.scope = "This Session"
    st.session_state.session = default_session


def _remember_recent_search(query: str) -> None:
    """Track recent lobby lookups for quick reuse."""
    if not query or not query.strip():
        return
    history = st.session_state.get("recent_lobby_searches", [])
    q = query.strip()
    deduped = [h for h in history if h.strip().lower() != q.lower()]
    deduped.insert(0, q)
    st.session_state.recent_lobby_searches = deduped[:6]


def reset_client_filters(default_session: str) -> None:
    st.session_state.client_query = ""
    st.session_state.client_name = ""
    st.session_state.client_bill_search = ""
    st.session_state.client_bill_search_seed = ""
    st.session_state.client_activity_search = ""
    st.session_state.client_disclosure_search = ""
    st.session_state.client_policy_focus = {}
    st.session_state.client_filter = ""
    st.session_state.client_scope = "This Session"
    st.session_state.client_session = default_session
    st.session_state.client_scope_radio = "This Session"
    st.session_state.client_session_select = _session_label(default_session)
    st.session_state.client_suggestions_select = "Select a client..."
    st.session_state.client_query_input = ""
    st.session_state.client_bill_search_input = ""
    st.session_state.client_activity_search_input = ""
    st.session_state.client_disclosure_search_input = ""
    st.session_state.client_filter_input = ""


def reset_member_filters(default_session: str) -> None:
    st.session_state.member_query = ""
    st.session_state.member_name = ""
    st.session_state.member_bill_search = ""
    st.session_state.member_witness_search = ""
    st.session_state.member_activity_search = ""
    st.session_state.member_filter = ""
    st.session_state.member_session = default_session
    st.session_state.member_session_select = _session_label(default_session)
    st.session_state.member_suggestions_select = "Select a legislator..."
    st.session_state.member_query_input = ""
    st.session_state.member_bill_search_input = ""
    st.session_state.member_witness_search_input = ""
    st.session_state.member_activity_search_input = ""
    st.session_state.member_filter_input = ""


def _remember_recent_client_search(query: str) -> None:
    if not query or not query.strip():
        return
    history = st.session_state.get("recent_client_searches", [])
    q = query.strip()
    deduped = [h for h in history if h.strip().lower() != q.lower()]
    deduped.insert(0, q)
    st.session_state.recent_client_searches = deduped[:6]


def _remember_recent_member_search(query: str) -> None:
    if not query or not query.strip():
        return
    history = st.session_state.get("recent_member_searches", [])
    q = query.strip()
    deduped = [h for h in history if h.strip().lower() != q.lower()]
    deduped.insert(0, q)
    st.session_state.recent_member_searches = deduped[:6]


def _ordinal(n: int) -> str:
    if 10 <= (n % 100) <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"

def _session_label(session_val: str) -> str:
    s = str(session_val).strip()
    if not s or s.lower() in {"none", "nan", "null"}:
        return ""
    # Special sessions encoded like 891 -> "89R / 1st Special".
    if s.isdigit():
        if len(s) >= 3:
            base = s[:-1]
            special = s[-1]
            if base.isdigit() and special.isdigit():
                return f"{base}R / {_ordinal(int(special))} Special"
        return _ordinal(int(s))
    return s

def _session_long_label(session_val: str | None) -> str:
    s = str(session_val or "").strip()
    if not s or s.lower() in {"none", "nan", "null"}:
        return ""
    if s.isdigit() and len(s) >= 3:
        base = s[:-1]
        special = s[-1]
        if base.isdigit() and special.isdigit():
            return f"{_ordinal(int(base))} {_ordinal(int(special))} Special Session"
    m = re.match(r"^(\d+)\s*R$", s, flags=re.IGNORECASE)
    if m:
        return f"{_ordinal(int(m.group(1)))} Regular Session"
    if s.isdigit():
        return f"{_ordinal(int(s))} Regular Session"
    m = re.search(r"(\d+).*(\d+)(?:st|nd|rd|th)?\s*Special", s, flags=re.IGNORECASE)
    if m:
        return f"{_ordinal(int(m.group(1)))} {_ordinal(int(m.group(2)))} Special Session"
    return s

def _session_range_label(series: pd.Series) -> str:
    if series is None or series.empty:
        return "All Sessions"
    base_nums = _session_base_number_series(series)
    base_nums = base_nums.dropna().astype(int)
    if base_nums.empty:
        return "All Sessions"
    min_base = int(base_nums.min())
    max_base = int(base_nums.max())
    if min_base == max_base:
        return f"{_ordinal(min_base)} Regular Session"
    return f"{_ordinal(min_base)} to {_ordinal(max_base)} Sessions"

def _session_sort_key(session_val: str) -> tuple[int, int, int]:
    s = str(session_val).strip()
    if not s:
        return (0, 2, 0)
    if s.isdigit():
        base = int(s[:-1]) if len(s) >= 2 else int(s)
        special = int(s[-1]) if len(s) >= 2 else 0
        return (base, 1, special)
    m = re.match(r"^(\d+)\s*R$", s, flags=re.IGNORECASE)
    if m:
        return (int(m.group(1)), 0, 0)
    return (0, 2, 0)

def _default_session_from_list(sessions: list[str]) -> str:
    if not sessions:
        return ""
    if "89R" in sessions:
        return "89R"
    regular = [s for s in sessions if str(s).strip().upper().endswith("R") and str(s).strip()[:-1].isdigit()]
    if regular:
        return sorted(regular, key=_session_sort_key)[-1]
    return sorted(sessions, key=_session_sort_key)[-1]

def _slugify(value: str, default: str = "report") -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", str(value or "")).strip("-").lower()
    return s or default

def _clean_options(options: list[str]) -> list[str]:
    clean = []
    for opt in options:
        s = str(opt).strip()
        if not s or s.lower() in {"none", "nan", "null"}:
            continue
        clean.append(s)
    return clean

def _pdf_safe_text(text: str) -> str:
    if text is None:
        return ""
    return str(text).encode("latin-1", "replace").decode("latin-1")

PDF_CHART_ERROR_KEY = "pdf_chart_error"

PDF_H1_SIZE = 18
PDF_H2_SIZE = 13
PDF_BODY_SIZE = 11
PDF_CAPTION_SIZE = 9
PDF_FOOTNOTE_SIZE = 8
PDF_SECTION_BAR_H = 8
PDF_BODY_LINE_H = 5.2
PDF_FONT_SANS = "Helvetica"
PDF_FONT_SERIF = "Times"
PDF_COLOR_NAVY_DARK = (9, 28, 50)
PDF_COLOR_NAVY = (16, 42, 74)
PDF_COLOR_ACCENT = (34, 96, 146)
PDF_COLOR_TEXT = (33, 45, 60)
PDF_COLOR_MUTED = (92, 106, 124)
PDF_COLOR_PANEL = (244, 248, 253)
PDF_COLOR_PANEL_ALT = (237, 243, 250)
PDF_COLOR_BORDER = (206, 218, 232)
PDF_COLOR_PAGE_BG = (250, 252, 255)

_ROMAN_MAP = (
    (1000, "M"),
    (900, "CM"),
    (500, "D"),
    (400, "CD"),
    (100, "C"),
    (90, "XC"),
    (50, "L"),
    (40, "XL"),
    (10, "X"),
    (9, "IX"),
    (5, "V"),
    (4, "IV"),
    (1, "I"),
)

def _record_pdf_chart_error(message: str) -> None:
    if not message:
        return
    if PDF_CHART_ERROR_KEY not in st.session_state:
        st.session_state[PDF_CHART_ERROR_KEY] = message

def _clear_pdf_chart_error() -> None:
    if PDF_CHART_ERROR_KEY in st.session_state:
        del st.session_state[PDF_CHART_ERROR_KEY]

def _configure_kaleido_scope() -> bool:
    try:
        scope = pio.kaleido.scope
    except Exception as exc:
        _record_pdf_chart_error(f"Kaleido unavailable: {exc}")
        return False
    if scope is None:
        _record_pdf_chart_error("Kaleido scope unavailable. Install the kaleido package.")
        return False
    try:
        scope.mathjax = None
        scope.default_format = "png"
    except Exception:
        pass
    return True

def _wrap_pdf_line(pdf: FPDF, text: str, max_w: float) -> list[str]:
    if text is None:
        return [""]
    safe_text = _pdf_safe_text(text)
    if max_w <= 0:
        return [safe_text]
    words = safe_text.split(" ")
    if not words:
        return [""]

    lines = []
    current = ""
    for word in words:
        if word == "":
            continue
        candidate = word if not current else f"{current} {word}"
        if pdf.get_string_width(candidate) <= max_w:
            current = candidate
            continue

        if current:
            lines.append(current)
            current = ""

        if pdf.get_string_width(word) <= max_w:
            current = word
            continue

        chunk = ""
        for ch in word:
            if not chunk or pdf.get_string_width(chunk + ch) <= max_w:
                chunk += ch
            else:
                lines.append(chunk)
                chunk = ch
        current = chunk

    if current:
        lines.append(current)
    return lines if lines else [safe_text]

def _apply_pdf_chart_layout(fig):
    if fig is None:
        return fig
    fig.update_layout(
        font=dict(family=PDF_FONT_SANS, size=10.5, color="#1f2937"),
        title_font=dict(family=PDF_FONT_SANS, size=13, color="#102843"),
        paper_bgcolor="#f8fbff",
        plot_bgcolor="#ffffff",
        legend=dict(
            font=dict(family=PDF_FONT_SANS, size=9.5, color="#1f2937"),
            bgcolor="rgba(248,251,255,0.9)",
            bordercolor="#d5e0ee",
            borderwidth=1,
        ),
    )
    fig.update_xaxes(
        automargin=True,
        showgrid=True,
        gridcolor="#e3eaf4",
        linecolor="#ccd7e6",
        tickfont=dict(family=PDF_FONT_SANS, color="#3a4a5f", size=9.5),
        title_font=dict(family=PDF_FONT_SANS, color="#2d3f57", size=10),
    )
    fig.update_yaxes(
        automargin=True,
        showgrid=True,
        gridcolor="#e3eaf4",
        linecolor="#ccd7e6",
        tickfont=dict(family=PDF_FONT_SANS, color="#3a4a5f", size=9.5),
        title_font=dict(family=PDF_FONT_SANS, color="#2d3f57", size=10),
    )
    return fig

def _fig_to_png_bytes(fig, width: int = 900, height: int = 500, scale: int = 2) -> bytes | None:
    if fig is None:
        return None
    if not _configure_kaleido_scope():
        return None
    _apply_pdf_chart_layout(fig)
    last_exc = None
    scales = [scale] if scale == 1 else [scale, 1]
    for attempt_scale in scales:
        try:
            return pio.to_image(
                fig,
                format="png",
                width=width,
                height=height,
                scale=attempt_scale,
                engine="kaleido",
            )
        except Exception as exc:
            last_exc = exc
    if last_exc is not None:
        _record_pdf_chart_error(str(last_exc))
    return None

def _coerce_pdf_bytes(data) -> bytes | None:
    if data is None:
        return None
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    if isinstance(data, str):
        return data.encode("latin-1", errors="replace")
    if hasattr(data, "getvalue"):
        try:
            return data.getvalue()
        except Exception:
            return None
    try:
        return bytes(data)
    except Exception:
        return None

def _to_roman(value: int) -> str:
    if value <= 0:
        return str(value)
    out = []
    remaining = int(value)
    for numeral_value, numeral in _ROMAN_MAP:
        while remaining >= numeral_value:
            out.append(numeral)
            remaining -= numeral_value
    return "".join(out)

def _pdf_clean_chart_caption(caption: str) -> str:
    txt = str(caption or "").strip()
    if not txt:
        return "Chart"
    txt = re.sub(r"^(chart|figure)\s*\d+\s*[:.\-]\s*", "", txt, flags=re.IGNORECASE)
    return txt.strip() or "Chart"

def _pdf_add_rule(
    pdf: FPDF,
    *,
    before: float = 0.0,
    after: float = 2.2,
    color: tuple[int, int, int] = PDF_COLOR_BORDER,
) -> None:
    if before > 0:
        pdf.ln(before)
    y = pdf.get_y()
    pdf.set_draw_color(*color)
    pdf.set_line_width(0.22)
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.set_line_width(0.2)
    if after > 0:
        pdf.ln(after)

def _pdf_add_heading(pdf: FPDF, text: str, size: int = PDF_H2_SIZE) -> None:
    pdf.set_font(PDF_FONT_SANS, "B", size)
    pdf.set_text_color(*PDF_COLOR_NAVY_DARK)
    max_w = pdf.w - pdf.l_margin - pdf.r_margin
    line_h = max(5.7, size * 0.41)
    for line in _wrap_pdf_line(pdf, text, max_w):
        pdf.cell(0, line_h, line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(*PDF_COLOR_TEXT)
    pdf.ln(0.9)

def _pdf_add_subheading(pdf: FPDF, text: str, size: int = PDF_H2_SIZE) -> None:
    pdf.set_font(PDF_FONT_SANS, "B", size)
    pdf.set_text_color(*PDF_COLOR_NAVY)
    max_w = pdf.w - pdf.l_margin - pdf.r_margin
    line_h = max(4.8, size * 0.4)
    for line in _wrap_pdf_line(pdf, text, max_w):
        pdf.cell(0, line_h, line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(*PDF_COLOR_TEXT)
    pdf.ln(0.7)

def _pdf_add_paragraph(pdf: FPDF, text: str, size: int = PDF_BODY_SIZE, line_h: float = PDF_BODY_LINE_H) -> None:
    pdf.set_font(PDF_FONT_SERIF, "", size)
    pdf.set_text_color(*PDF_COLOR_TEXT)
    max_w = pdf.w - pdf.l_margin - pdf.r_margin
    for line in _wrap_pdf_line(pdf, text, max_w):
        pdf.cell(0, line_h, line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1.1)

def _pdf_add_bullets(pdf: FPDF, bullets: list[str], size: int = 10, line_h: float = 4.9) -> None:
    if not bullets:
        return
    bullet_x = pdf.l_margin + 1.4
    bullet_size = 1.2
    text_x = bullet_x + bullet_size + 2.2
    max_w = pdf.w - pdf.r_margin - text_x
    for bullet in bullets:
        safe_bullet = _pdf_safe_text(bullet)
        lines = _wrap_pdf_line(pdf, safe_bullet, max_w) if safe_bullet else [""]
        row_h = max(line_h, len(lines) * line_h)
        _pdf_ensure_space(pdf, row_h + 0.9)

        row_y = pdf.get_y()
        pdf.set_fill_color(*PDF_COLOR_ACCENT)
        pdf.set_draw_color(*PDF_COLOR_ACCENT)
        dot_y = row_y + (line_h - bullet_size) * 0.58
        pdf.ellipse(bullet_x, dot_y, bullet_size, bullet_size, "F")

        pdf.set_font(PDF_FONT_SERIF, "", size)
        pdf.set_text_color(*PDF_COLOR_TEXT)
        for idx, line in enumerate(lines):
            if idx == 0:
                pdf.set_xy(text_x, row_y)
            else:
                pdf.set_xy(text_x, row_y + (line_h * idx))
            pdf.cell(0, line_h, line, new_x=XPos.LMARGIN, new_y=YPos.TOP)
        pdf.set_y(row_y + row_h + 0.6)
    pdf.ln(0.6)

def _pdf_add_kpi_table(pdf: FPDF, rows: list[tuple[str, str]], size: int = 10) -> None:
    if not rows:
        return
    table_w = pdf.w - pdf.l_margin - pdf.r_margin
    label_w = min(110.0, table_w * 0.56)
    value_w = table_w - label_w
    body_line_h = 4.5
    for idx, (label, value) in enumerate(rows):
        label_txt = _pdf_safe_text(label)
        value_txt = _pdf_safe_text(value)

        pdf.set_font(PDF_FONT_SANS, "", size)
        label_lines = _wrap_pdf_line(pdf, label_txt, label_w - 4)
        pdf.set_font(PDF_FONT_SANS, "B", size)
        value_lines = _wrap_pdf_line(pdf, value_txt, value_w - 4)

        lines = max(len(label_lines), len(value_lines))
        row_h = max(6.8, lines * body_line_h + 1.8)
        _pdf_ensure_space(pdf, row_h + 0.8)

        row_y = pdf.get_y()
        fill_color = (248, 251, 255) if (idx % 2 == 0) else (243, 248, 253)
        pdf.set_fill_color(*fill_color)
        pdf.set_draw_color(*PDF_COLOR_BORDER)
        pdf.rect(pdf.l_margin, row_y, table_w, row_h, "DF")
        pdf.line(pdf.l_margin + label_w, row_y, pdf.l_margin + label_w, row_y + row_h)

        label_start_y = row_y + max(0.9, (row_h - len(label_lines) * body_line_h) / 2)
        value_start_y = row_y + max(0.9, (row_h - len(value_lines) * body_line_h) / 2)

        pdf.set_text_color(*PDF_COLOR_TEXT)
        pdf.set_font(PDF_FONT_SANS, "", size)
        for line_idx, line in enumerate(label_lines):
            pdf.set_xy(pdf.l_margin + 2.2, label_start_y + line_idx * body_line_h)
            pdf.cell(label_w - 4, body_line_h, line, align="L")

        pdf.set_text_color(*PDF_COLOR_NAVY_DARK)
        pdf.set_font(PDF_FONT_SANS, "B", size)
        for line_idx, line in enumerate(value_lines):
            pdf.set_xy(pdf.l_margin + label_w + 2, value_start_y + line_idx * body_line_h)
            pdf.cell(value_w - 4, body_line_h, line, align="R")

        pdf.set_text_color(*PDF_COLOR_TEXT)
        pdf.set_y(row_y + row_h)
    pdf.ln(1.2)

def _pdf_ensure_space(pdf: FPDF, height_needed: float) -> None:
    if pdf.get_y() + height_needed > pdf.h - pdf.b_margin:
        pdf.add_page()

def _pdf_add_chart(pdf: FPDF, fig, caption: str, width_px: int = 900, height_px: int = 500) -> None:
    png = _fig_to_png_bytes(fig, width=width_px, height=height_px, scale=2)
    base_caption = _pdf_clean_chart_caption(caption)
    figure_no = int(getattr(pdf, "_figure_counter", 0)) + 1
    setattr(pdf, "_figure_counter", figure_no)
    figure_caption = f"Figure {figure_no}. {base_caption}"
    if not png:
        pdf.set_font(PDF_FONT_SANS, "I", PDF_CAPTION_SIZE)
        pdf.set_text_color(*PDF_COLOR_MUTED)
        pdf.cell(0, 5, _pdf_safe_text(f"{figure_caption} (chart unavailable)"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(*PDF_COLOR_TEXT)
        pdf.ln(2)
        return

    block_w = pdf.w - pdf.l_margin - pdf.r_margin
    pad = 2.0
    caption_line_h = 4.0
    caption_pad = 1.2
    img_w = block_w - (pad * 2)
    img_h = img_w * (height_px / width_px)
    pdf.set_font(PDF_FONT_SANS, "", PDF_CAPTION_SIZE)
    caption_lines = _wrap_pdf_line(pdf, figure_caption, img_w)
    caption_h = max(4.8, len(caption_lines) * caption_line_h + caption_pad)
    block_h = caption_h + img_h + (pad * 2)
    _pdf_ensure_space(pdf, block_h + 2.2)

    y = pdf.get_y()
    pdf.set_fill_color(252, 254, 255)
    pdf.set_draw_color(*PDF_COLOR_BORDER)
    pdf.rect(pdf.l_margin, y, block_w, block_h, "DF")
    caption_y = y + 1.0
    pdf.set_font(PDF_FONT_SANS, "", PDF_CAPTION_SIZE)
    pdf.set_text_color(*PDF_COLOR_NAVY)
    y_cursor = caption_y + 1.6
    for line in caption_lines:
        pdf.set_xy(pdf.l_margin + pad, y_cursor)
        pdf.cell(img_w, caption_line_h, _pdf_safe_text(line), align="L")
        y_cursor += caption_line_h

    pdf.set_draw_color(223, 231, 241)
    pdf.line(pdf.l_margin + pad, y + caption_h + 1.1, pdf.w - pdf.r_margin - pad, y + caption_h + 1.1)
    img_y = y + caption_h + pad
    pdf.image(BytesIO(png), x=pdf.l_margin + pad, y=img_y, w=img_w, h=img_h)
    pdf.set_text_color(*PDF_COLOR_TEXT)
    pdf.set_y(y + block_h + 1.6)

def _pdf_add_section_title(pdf: FPDF, text: str, number: str | None = None) -> None:
    if pdf.get_y() > (pdf.t_margin + 4):
        pdf.ln(1.5)
    bar_w = pdf.w - pdf.l_margin - pdf.r_margin
    title = f"{number} {text}".strip() if number else text
    title_w = bar_w
    pdf.set_font(PDF_FONT_SANS, "B", PDF_H2_SIZE - 0.2)
    title_lines = _wrap_pdf_line(pdf, _pdf_safe_text(title), title_w)
    title_line_h = 4.8
    title_h = max(6.0, len(title_lines) * title_line_h)
    _pdf_ensure_space(pdf, title_h + 3.2)
    y = pdf.get_y()
    pdf.set_font(PDF_FONT_SANS, "B", PDF_H2_SIZE - 0.2)
    pdf.set_text_color(*PDF_COLOR_NAVY_DARK)
    y_cursor = y + 0.2
    for line in title_lines:
        pdf.set_xy(pdf.l_margin, y_cursor)
        pdf.cell(title_w, title_line_h, _pdf_safe_text(line), align="L")
        y_cursor += title_line_h
    pdf.set_draw_color(*PDF_COLOR_BORDER)
    pdf.line(pdf.l_margin, y + title_h + 0.4, pdf.w - pdf.r_margin, y + title_h + 0.4)
    pdf.set_text_color(*PDF_COLOR_TEXT)
    pdf.set_y(y + title_h + 1.6)

def _pdf_add_numbered_section_title(pdf: FPDF, number: int, text: str) -> None:
    _pdf_add_section_title(pdf, text, number=f"{_to_roman(number)}.")

def _pdf_add_callout_box(
    pdf: FPDF,
    title: str,
    body: str,
    *,
    accent: tuple[int, int, int] = PDF_COLOR_ACCENT,
) -> None:
    title = _pdf_safe_text(title)
    body = _pdf_safe_text(body)
    if not title and not body:
        return

    inner_pad = 2.8
    title_size = 9.4
    body_size = PDF_BODY_SIZE
    line_h = 4.9
    left_accent_w = 1.6
    box_w = pdf.w - pdf.l_margin - pdf.r_margin
    text_w = box_w - left_accent_w - (inner_pad * 2)

    pdf.set_font(PDF_FONT_SANS, "B", title_size)
    title_lines = _wrap_pdf_line(pdf, title, text_w)
    pdf.set_font(PDF_FONT_SERIF, "", body_size)
    body_lines = _wrap_pdf_line(pdf, body, text_w)

    content_lines = len(title_lines) + len(body_lines)
    box_h = max(13.6, inner_pad * 2 + content_lines * line_h + 0.5)
    _pdf_ensure_space(pdf, box_h + 1.2)
    y = pdf.get_y()

    pdf.set_fill_color(247, 250, 254)
    pdf.set_draw_color(*PDF_COLOR_BORDER)
    pdf.rect(pdf.l_margin, y, box_w, box_h, "DF")
    pdf.set_fill_color(*accent)
    pdf.rect(pdf.l_margin, y, left_accent_w, box_h, "F")

    x_text = pdf.l_margin + left_accent_w + inner_pad
    y_cursor = y + inner_pad
    pdf.set_text_color(*PDF_COLOR_NAVY_DARK)
    pdf.set_font(PDF_FONT_SANS, "B", title_size)
    for line in title_lines:
        pdf.set_xy(x_text, y_cursor)
        pdf.cell(text_w, line_h, line, align="L")
        y_cursor += line_h

    pdf.set_font(PDF_FONT_SERIF, "", body_size)
    pdf.set_text_color(*PDF_COLOR_TEXT)
    for line in body_lines:
        pdf.set_xy(x_text, y_cursor)
        pdf.cell(text_w, line_h, line, align="L")
        y_cursor += line_h

    pdf.set_text_color(*PDF_COLOR_TEXT)
    pdf.set_y(y + box_h + 1.1)

def _pdf_add_focus_highlights(pdf: FPDF, highlights: list[str], *, size: int = 10) -> None:
    clean = [str(h).strip() for h in (highlights or []) if str(h).strip()]
    if not clean:
        return

    block_w = pdf.w - pdf.l_margin - pdf.r_margin
    badge_w = 5.2
    inner_pad = 2.1
    row_gap = 1.0
    line_h = 4.5

    for idx, raw in enumerate(clean, start=1):
        title = raw
        detail = ""
        lead, sep, tail = raw.partition(":")
        if sep and len(lead.strip()) <= 42:
            title = lead.strip()
            detail = tail.strip()

        text_x = pdf.l_margin + badge_w + 2.2
        text_w = block_w - badge_w - 6
        pdf.set_font(PDF_FONT_SANS, "B", size)
        title_lines = _wrap_pdf_line(pdf, title, text_w)
        pdf.set_font(PDF_FONT_SERIF, "", max(9.3, size - 0.2))
        detail_lines = _wrap_pdf_line(pdf, detail, text_w) if detail else []

        row_lines = len(title_lines) + len(detail_lines)
        row_h = max(10.8, (row_lines * line_h) + (inner_pad * 2))
        _pdf_ensure_space(pdf, row_h + row_gap + 1)
        y = pdf.get_y()

        fill = (248, 251, 255) if idx % 2 else (243, 248, 253)
        pdf.set_fill_color(*fill)
        pdf.set_draw_color(*PDF_COLOR_BORDER)
        pdf.rect(pdf.l_margin, y, block_w, row_h, "DF")

        pdf.set_fill_color(225, 236, 248)
        pdf.rect(pdf.l_margin, y, badge_w, row_h, "F")
        pdf.set_fill_color(*PDF_COLOR_NAVY)
        circle_d = 3.3
        circle_x = pdf.l_margin + (badge_w - circle_d) / 2
        circle_y = y + (row_h - circle_d) / 2
        pdf.ellipse(circle_x, circle_y, circle_d, circle_d, "F")
        pdf.set_text_color(236, 243, 250)
        pdf.set_font(PDF_FONT_SANS, "B", 6.7)
        pdf.set_xy(circle_x, circle_y + 0.25)
        pdf.cell(circle_d, 2.8, f"{idx}", align="C")

        pdf.set_text_color(*PDF_COLOR_NAVY_DARK)
        pdf.set_font(PDF_FONT_SANS, "B", size)
        y_cursor = y + inner_pad
        for line in title_lines:
            pdf.set_xy(text_x, y_cursor)
            pdf.cell(text_w, line_h, _pdf_safe_text(line), align="L")
            y_cursor += line_h

        if detail_lines:
            pdf.set_text_color(*PDF_COLOR_TEXT)
            pdf.set_font(PDF_FONT_SERIF, "", max(9.3, size - 0.2))
            for line in detail_lines:
                pdf.set_xy(text_x, y_cursor)
                pdf.cell(text_w, line_h, _pdf_safe_text(line), align="L")
                y_cursor += line_h

        pdf.set_text_color(*PDF_COLOR_TEXT)
        pdf.set_y(y + row_h + row_gap)

def _pdf_add_cover_page(pdf: FPDF, payload: dict) -> None:
    page_w = pdf.w
    page_h = pdf.h

    pdf.set_fill_color(*PDF_COLOR_PAGE_BG)
    pdf.rect(0, 0, page_w, page_h, "F")

    # Minimal page architecture.
    pdf.set_fill_color(244, 249, 255)
    pdf.rect(page_w * 0.86, 0, page_w * 0.14, page_h, "F")
    pdf.set_fill_color(*PDF_COLOR_NAVY_DARK)
    pdf.rect(0, 0, page_w, 27, "F")
    pdf.set_fill_color(*PDF_COLOR_ACCENT)
    pdf.rect(0, 27, page_w, 1.6, "F")

    logo_w = 30
    logo_h = 10
    logo_x = page_w - pdf.r_margin - logo_w
    logo_y = 8.8
    pdf.set_draw_color(187, 205, 226)
    pdf.set_fill_color(23, 55, 90)
    pdf.rect(logo_x, logo_y, logo_w, logo_h, "DF")
    pdf.set_font(PDF_FONT_SANS, "B", 8)
    pdf.set_text_color(236, 243, 250)
    pdf.set_xy(logo_x, logo_y + 2.6)
    pdf.cell(logo_w, 4, "LOGO", align="C")

    header_title = payload.get("report_title", "Lobby Look-Up Report")
    scope_sub = payload.get("scope_session_label") or payload.get("scope_label", "")
    focus_label = payload.get("focus_label", "")

    pdf.set_text_color(236, 243, 250)
    pdf.set_font(PDF_FONT_SANS, "B", 8.5)
    pdf.set_xy(pdf.l_margin, 7.4)
    pdf.cell(page_w - pdf.l_margin - pdf.r_margin - logo_w - 8, 4.8, _pdf_safe_text(header_title))
    pdf.set_font(PDF_FONT_SANS, "", 7)
    pdf.set_xy(pdf.l_margin, 12.5)
    top_sub = f"{scope_sub} | {focus_label}".strip(" |")
    if len(top_sub) > 88:
        top_sub = top_sub[:85].rstrip() + "..."
    pdf.cell(page_w - pdf.l_margin - pdf.r_margin - logo_w - 8, 4.2, _pdf_safe_text(top_sub))

    pdf.set_text_color(*PDF_COLOR_NAVY_DARK)
    pdf.set_y(48)
    _pdf_add_heading(pdf, "TAXPAYER-FUNDED LOBBYING IN TEXAS", size=PDF_H1_SIZE)
    _pdf_add_subheading(pdf, f"Analysis of the {payload['session_label']} Legislative Session", size=12)

    box_x = pdf.l_margin
    box_y = 85
    box_w = page_w - pdf.l_margin - pdf.r_margin - 20
    box_h = 52
    pdf.set_fill_color(255, 255, 255)
    pdf.set_draw_color(*PDF_COLOR_BORDER)
    pdf.rect(box_x, box_y, box_w, box_h, "DF")
    pdf.set_fill_color(*PDF_COLOR_ACCENT)
    pdf.rect(box_x, box_y, 1.8, box_h, "F")

    pdf.set_font(PDF_FONT_SANS, "B", 10)
    pdf.set_text_color(*PDF_COLOR_NAVY_DARK)
    pdf.set_xy(box_x + 5.0, box_y + 3.0)
    pdf.cell(0, 5, "Report Scope")

    pdf.set_text_color(*PDF_COLOR_TEXT)
    pdf.set_font(PDF_FONT_SERIF, "", PDF_BODY_SIZE)
    pdf.set_xy(box_x + 5.0, box_y + 11.0)
    pdf.cell(0, 5.2, _pdf_safe_text(f"Session: {payload['session_label']}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(box_x + 5.0)
    pdf.cell(0, 5.2, _pdf_safe_text(f"Scope: {payload['scope_session_label']}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(box_x + 5.0)
    pdf.cell(0, 5.2, _pdf_safe_text(f"Focus: {payload['focus_label']}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(box_x + 5.0)
    pdf.cell(0, 5.2, _pdf_safe_text(f"Generated: {payload['generated_date']}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_draw_color(205, 218, 234)
    pdf.line(pdf.l_margin, page_h - 25, page_w - pdf.r_margin, page_h - 25)
    pdf.set_y(page_h - 23)
    pdf.set_font(PDF_FONT_SANS, "I", PDF_FOOTNOTE_SIZE)
    pdf.set_text_color(*PDF_COLOR_MUTED)
    pdf.cell(
        0,
        4.5,
        _pdf_safe_text("Prepared by Texas Taxpayer Lobbying Transparency Center"),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.cell(0, 4.5, _pdf_safe_text(payload.get("disclaimer_note", "")), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(*PDF_COLOR_TEXT)

def _pdf_add_contents_page(pdf: FPDF, payload: dict, *, include_focus_snapshot: bool) -> None:
    pdf.add_page()
    page_w = pdf.w
    page_h = pdf.h
    content_top = 20
    pdf.set_fill_color(*PDF_COLOR_PAGE_BG)
    pdf.rect(0, content_top, page_w, page_h - content_top, "F")

    pdf.set_text_color(*PDF_COLOR_NAVY_DARK)
    pdf.set_y(26)
    _pdf_add_heading(pdf, "Contents", size=14)
    _pdf_add_paragraph(
        pdf,
        "Legislative briefing sections included in this report.",
        size=10.5,
        line_h=5.2,
    )

    entries = [
        "Executive Summary",
    ]
    if include_focus_snapshot:
        entries.append("Focus Snapshot")
    entries.extend(
        [
            "I. The Scale of Lobbying",
            "II. What Taxpayer-Funded Lobbying Is - And Why It Matters",
            "III. Legislative Activity Patterns",
            "IV. Bills Most Opposed by Taxpayer-Funded Lobbyists",
            "V. Policy Areas Most Opposed by Taxpayer-Funded Lobbyists",
            "VI. Structural Incentives and the Compulsion Problem",
            "VII. Legal Parity and Statutory Inconsistency",
            "VIII. Policy Solution: A Comprehensive Ban on Taxpayer-Funded Lobbying",
            "IX. Data Sources and Methodology",
            "X. Conclusion",
        ]
    )

    index_w = 11
    text_w = page_w - pdf.l_margin - pdf.r_margin - index_w
    row_h = 5.8
    for idx, label in enumerate(entries, start=1):
        _pdf_ensure_space(pdf, row_h + 1.1)
        y = pdf.get_y()
        number_label = f"{idx:02d}"

        pdf.set_fill_color(250, 252, 255) if idx % 2 else pdf.set_fill_color(245, 249, 254)
        pdf.set_draw_color(*PDF_COLOR_BORDER)
        pdf.rect(pdf.l_margin, y, page_w - pdf.l_margin - pdf.r_margin, row_h, "DF")
        pdf.set_font(PDF_FONT_SANS, "B", 7.8)
        pdf.set_text_color(*PDF_COLOR_NAVY_DARK)
        pdf.set_xy(pdf.l_margin + 2.0, y + 1.1)
        pdf.cell(index_w - 2.0, 3.8, number_label, align="L")

        pdf.set_font(PDF_FONT_SERIF, "", 10)
        pdf.set_text_color(*PDF_COLOR_TEXT)
        pdf.set_xy(pdf.l_margin + index_w, y + 1.0)
        pdf.cell(text_w - 1.0, 4.2, _pdf_safe_text(label), align="L")
        pdf.set_y(y + row_h + 0.5)

    pdf.set_font(PDF_FONT_SANS, "I", PDF_FOOTNOTE_SIZE)
    pdf.set_text_color(*PDF_COLOR_MUTED)
    pdf.set_y(page_h - 18)
    pdf.cell(
        0,
        4.2,
        _pdf_safe_text(f"Generated {payload.get('generated_date', '')}"),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
        align="R",
    )
    pdf.set_text_color(*PDF_COLOR_TEXT)

def _build_focus_chart(chart: dict):
    kind = str(chart.get("kind", "")).strip().lower()
    if kind == "bar":
        df = pd.DataFrame(chart.get("data", []))
        if df.empty or "label" not in df.columns or "value" not in df.columns:
            return None
        orientation = str(chart.get("orientation", "h")).strip().lower()
        if orientation == "v":
            fig = px.bar(
                df,
                x="label",
                y="value",
                text="value",
                color_discrete_sequence=["#4c78a8"],
            )
            fig.update_traces(textposition="outside", cliponaxis=False)
            fig.update_layout(
                template="plotly_white",
                title=chart.get("title", ""),
                xaxis_title="",
                yaxis_title="",
                margin=dict(l=40, r=20, t=50, b=40),
            )
            fig.update_yaxes(tickformat="~s")
        else:
            fig = px.bar(
                df.sort_values("value"),
                x="value",
                y="label",
                orientation="h",
                text="value",
                color_discrete_sequence=["#4c78a8"],
            )
            fig.update_traces(textposition="outside", cliponaxis=False)
            fig.update_layout(
                template="plotly_white",
                title=chart.get("title", ""),
                xaxis_title="",
                yaxis_title="",
                margin=dict(l=40, r=20, t=50, b=30),
            )
            fig.update_xaxes(tickformat="~s")
        return fig

    if kind == "grouped_bar":
        df = pd.DataFrame(chart.get("data", []))
        if df.empty or not {"Position", "Funding", "Count"}.issubset(df.columns):
            return None
        fig = px.bar(
            df,
            x="Position",
            y="Count",
            color="Funding",
            barmode="group",
            text="Count",
            color_discrete_map={"Taxpayer Funded": "#d14b4b", "Private": "#4c78a8"},
        )
        fig.update_traces(textposition="outside", cliponaxis=False)
        fig.update_layout(
            template="plotly_white",
            title=chart.get("title", ""),
            xaxis_title="",
            yaxis_title="",
            margin=dict(l=40, r=20, t=50, b=30),
        )
        fig.update_yaxes(tickformat="~s")
        return fig

    return None

def _calc_share_range(tfl_low: float, tfl_high: float, total_low: float, total_high: float) -> tuple[float, float]:
    if total_low <= 0 or total_high <= 0:
        return 0.0, 0.0
    low = tfl_low / total_high if total_high else 0.0
    high = tfl_high / total_low if total_low else 0.0
    low = min(max(low, 0.0), 1.0)
    high = min(max(high, 0.0), 1.0)
    return low * 100, high * 100

def _chart_lines(rows: list[tuple[str, str]]) -> str:
    return "\n".join([f"{label}: {value}" for label, value in rows if label])

def _build_report_payload(
    *,
    session_val: str | None,
    scope_label: str,
    focus_label: str,
    Lobby_TFL_Client_All: pd.DataFrame,
    Wit_All: pd.DataFrame,
    Bill_Status_All: pd.DataFrame,
    Bill_Sub_All: pd.DataFrame,
    tfl_session_val: str | None,
    focus_context: dict | None = None,
) -> dict:
    session_label = _session_label(session_val) if session_val else "Selected Session"
    generated_dt = datetime.now()
    generated_date = generated_dt.strftime("%B %d, %Y")
    generated_ts = generated_dt.strftime("%Y-%m-%d %H:%M")
    scope_label = scope_label or "Selected Session"
    focus_label = focus_label or "All"

    scope_all = scope_label.strip().lower().startswith("all")
    tfl_session = str(tfl_session_val) if tfl_session_val is not None else str(session_val or "")

    base = ensure_cols(
        Lobby_TFL_Client_All,
        {"IsTFL": 0, "Low_num": 0.0, "High_num": 0.0, "Client": "", "LobbyShort": ""},
    ).copy()
    if "Session" in base.columns:
        base["Session"] = base["Session"].astype(str).str.strip()
        if not scope_all and tfl_session:
            base = base[base["Session"] == tfl_session]

    base["IsTFL"] = pd.to_numeric(base.get("IsTFL", 0), errors="coerce").fillna(0).astype(int)
    base["Low_num"] = pd.to_numeric(base.get("Low_num", 0), errors="coerce").fillna(0.0)
    base["High_num"] = pd.to_numeric(base.get("High_num", 0), errors="coerce").fillna(0.0)

    scope_session_label = ""
    if scope_all:
        if "Session" in base.columns:
            scope_session_label = _session_range_label(base["Session"])
        else:
            scope_session_label = "All Sessions"
    else:
        scope_session_label = _session_long_label(session_val)
    if not scope_session_label:
        scope_session_label = scope_label or "Selected Session"

    report_id = f"LL-{generated_dt.strftime('%Y%m%d-%H%M')}-{_slugify(focus_label, default='scope')[:10]}"
    filter_summary_parts = [f"Scope: {scope_session_label}"]
    if focus_label:
        filter_summary_parts.append(f"Focus: {focus_label}")
    if focus_context and isinstance(focus_context, dict):
        if focus_context.get("type") == "bill":
            bill_id = focus_context.get("bill") or focus_context.get("query", "")
            if bill_id:
                filter_summary_parts.append(f"Bill: {bill_id}")
        if focus_context.get("type") == "lobbyist":
            lobby_name = focus_context.get("display_name", "")
            if lobby_name:
                filter_summary_parts.append(f"Lobbyist: {lobby_name}")
    filter_summary = "; ".join(filter_summary_parts)
    selected_lobbyist = ""
    if focus_context and isinstance(focus_context, dict) and focus_context.get("type") == "lobbyist":
        selected_lobbyist = focus_context.get("display_name") or ""

    total_low = float(base["Low_num"].sum()) if not base.empty else 0.0
    total_high = float(base["High_num"].sum()) if not base.empty else 0.0
    tfl_low = float(base.loc[base["IsTFL"] == 1, "Low_num"].sum()) if not base.empty else 0.0
    tfl_high = float(base.loc[base["IsTFL"] == 1, "High_num"].sum()) if not base.empty else 0.0
    private_low = float(base.loc[base["IsTFL"] == 0, "Low_num"].sum()) if not base.empty else 0.0
    private_high = float(base.loc[base["IsTFL"] == 0, "High_num"].sum()) if not base.empty else 0.0

    tfl_share_low_pct, tfl_share_high_pct = _calc_share_range(tfl_low, tfl_high, total_low, total_high)
    private_share_low_pct, private_share_high_pct = _calc_share_range(
        private_low, private_high, total_low, total_high
    )

    funding_mix = {
        "Taxpayer Funded": (tfl_low + tfl_high) / 2,
        "Private": (private_low + private_high) / 2,
    }

    def _top_clients(df: pd.DataFrame, is_tfl: int, limit: int = 5) -> list[dict]:
        if df.empty or "Client" not in df.columns:
            return []
        subset = df[df["IsTFL"] == is_tfl]
        subset["Client"] = subset["Client"].fillna("").astype(str).str.strip()
        subset = subset[subset["Client"] != ""]
        if subset.empty:
            return []
        grouped = (
            subset.groupby("Client", as_index=False)
            .agg(Low=("Low_num", "sum"), High=("High_num", "sum"))
            .sort_values(["High", "Low"], ascending=False)
            .head(limit)
        )
        return [
            {"Client": row.Client, "Low": float(row.Low), "High": float(row.High)}
            for row in grouped.itertuples(index=False)
        ]

    top_clients_tfl = _top_clients(base, 1, limit=5)
    top_clients_private = _top_clients(base, 0, limit=5)

    def _series_from(df: pd.DataFrame, col: str) -> pd.Series:
        s = df.get(col, pd.Series(dtype=object))
        if isinstance(s, pd.DataFrame):
            s = s.iloc[:, 0]
        return s

    def _unique_count(s: pd.Series) -> int:
        if s is None or s.empty:
            return 0
        v = s.dropna().astype(str).str.strip()
        v = v[(v != "") & (~v.str.lower().isin(["nan", "none", "null"]))]
        return int(v.nunique())

    unique_lobbyists_total = _unique_count(_series_from(base, "LobbyShort"))
    unique_lobbyists_tfl = _unique_count(_series_from(base.loc[base["IsTFL"] == 1], "LobbyShort"))
    unique_clients_total = _unique_count(_series_from(base, "Client"))
    unique_clients_tfl = _unique_count(_series_from(base.loc[base["IsTFL"] == 1], "Client"))

    chart_compensation_bar = _chart_lines(
        [
            ("Taxpayer Funded", f"{fmt_usd(tfl_low)} - {fmt_usd(tfl_high)}"),
            ("Private", f"{fmt_usd(private_low)} - {fmt_usd(private_high)}"),
            ("Total", f"{fmt_usd(total_low)} - {fmt_usd(total_high)}"),
        ]
    )
    chart_share = _chart_lines(
        [
            ("Taxpayer Funded share", f"{tfl_share_low_pct:.1f}% - {tfl_share_high_pct:.1f}%"),
            ("Private share", f"{private_share_low_pct:.1f}% - {private_share_high_pct:.1f}%"),
        ]
    )

    chart_entity_types = "No taxpayer-funded clients found."
    entity_type_counts = []
    tfl_clients = base[base["IsTFL"] == 1]
    if not tfl_clients.empty:
        clients = _series_from(tfl_clients, "Client").dropna().astype(str).str.strip()
        clients = clients[(clients != "") & (~clients.str.lower().isin(["nan", "none", "null"]))].drop_duplicates()
        if not clients.empty:
            type_counts = clients.map(lambda x: match_entity_type(x)[0]).value_counts().head(5)
            chart_entity_types = "\n".join(
                [f"{name}: {count} clients" for name, count in type_counts.items()]
            )
            entity_type_counts = [
                {"type": name, "count": int(count)} for name, count in type_counts.items()
            ]

    tfl_flag = pd.DataFrame(columns=["LobbyShort", "IsTFL"])
    if not base.empty and "LobbyShort" in base.columns:
        tfl_flag = (
            base.groupby("LobbyShort", as_index=False)["IsTFL"]
            .max()
            .rename(columns={"IsTFL": "IsTFL"})
        )

    witness_summary = "No witness-list data available for this scope/session."
    chart_witness_positions = "No witness-list data available."
    witness_counts = {
        "tfl": {"Against": 0, "For": 0, "On": 0},
        "private": {"Against": 0, "For": 0, "On": 0},
    }
    against = pd.DataFrame()

    wit = Wit_All if isinstance(Wit_All, pd.DataFrame) else pd.DataFrame()
    if not wit.empty and "LobbyShort" in wit.columns:
        if session_val is not None and "Session" in wit.columns:
            wit = wit[wit["Session"].astype(str).str.strip() == str(session_val)]
        if not wit.empty:
            pos = bill_position_from_flags(wit)
            if not pos.empty:
                pos = pos.merge(tfl_flag, on="LobbyShort", how="left")
                pos["IsTFL"] = pd.to_numeric(pos.get("IsTFL", 0), errors="coerce").fillna(0).astype(int)

                def _pos_counts(df: pd.DataFrame) -> dict:
                    return {
                        "Against": int(df["Position"].astype(str).str.contains("Against", case=False, na=False).sum()),
                        "For": int(df["Position"].astype(str).str.contains(r"\bFor\b", case=False, na=False).sum()),
                        "On": int(df["Position"].astype(str).str.contains(r"\bOn\b", case=False, na=False).sum()),
                    }

                tfl_counts = _pos_counts(pos[pos["IsTFL"] == 1])
                pri_counts = _pos_counts(pos[pos["IsTFL"] != 1])
                witness_counts = {"tfl": tfl_counts, "private": pri_counts}

                witness_summary = (
                    "Taxpayer-funded lobbyists recorded "
                    f"{tfl_counts['Against']:,} against, {tfl_counts['For']:,} for, "
                    f"and {tfl_counts['On']:,} on positions; private lobbyists recorded "
                    f"{pri_counts['Against']:,} against, {pri_counts['For']:,} for, "
                    f"and {pri_counts['On']:,} on positions."
                )
                chart_witness_positions = _chart_lines(
                    [
                        (
                            "Taxpayer Funded",
                            f"Against {tfl_counts['Against']:,}, For {tfl_counts['For']:,}, On {tfl_counts['On']:,}",
                        ),
                        (
                            "Private",
                            f"Against {pri_counts['Against']:,}, For {pri_counts['For']:,}, On {pri_counts['On']:,}",
                        ),
                    ]
                )
                against = pos[pos["Position"].astype(str).str.contains("Against", case=False, na=False)]

    top_bills = []
    if not against.empty:
        counts = (
            against.groupby(["Bill", "IsTFL"])
            .size()
            .unstack(fill_value=0)
            .reset_index()
        )
        counts["tfl"] = counts.get(1, 0)
        counts["private"] = counts.get(0, 0)
        counts = counts.sort_values(["tfl", "private", "Bill"], ascending=[False, False, True]).head(5)

        bill_info = Bill_Status_All if isinstance(Bill_Status_All, pd.DataFrame) else pd.DataFrame()
        if not bill_info.empty and "Session" in bill_info.columns and session_val is not None:
            bill_info = bill_info[bill_info["Session"].astype(str).str.strip() == str(session_val)]
        keep_cols = [c for c in ["Bill", "Caption", "Status"] if c in bill_info.columns]
        if keep_cols:
            bill_info = bill_info[keep_cols].drop_duplicates(subset=["Bill"])
        counts = counts.merge(bill_info, on="Bill", how="left") if keep_cols else counts

        for row in counts.itertuples(index=False):
            bill_id = str(getattr(row, "Bill", "")).strip() or "-"
            caption = str(getattr(row, "Caption", "")).strip() or "-"
            status = str(getattr(row, "Status", "")).strip()
            summary = f"Status: {status}" if status else "Status: Unknown"
            top_bills.append(
                {
                    "id": bill_id,
                    "caption": caption,
                    "tfl": int(getattr(row, "tfl", 0) or 0),
                    "private": int(getattr(row, "private", 0) or 0),
                    "summary": summary,
                }
            )

    chart_top_bills = (
        "\n".join(
            [
                f"{i + 1}. {b['id']} - TFL {b['tfl']:,}, Private {b['private']:,}"
                for i, b in enumerate(top_bills)
            ]
        )
        if top_bills
        else "No bill-level opposition data available."
    )

    top_subjects = []
    bill_sub = Bill_Sub_All if isinstance(Bill_Sub_All, pd.DataFrame) else pd.DataFrame()
    if not against.empty and not bill_sub.empty and {"Bill", "Subject"}.issubset(bill_sub.columns):
        if "Session" in bill_sub.columns and session_val is not None:
            bill_sub = bill_sub[bill_sub["Session"].astype(str).str.strip() == str(session_val)]
        merged = against[["Bill"]].merge(bill_sub[["Bill", "Subject"]], on="Bill", how="left")
        merged["Subject"] = merged["Subject"].fillna("").astype(str).str.strip()
        merged = merged[merged["Subject"] != ""]
        if not merged.empty:
            subject_counts = (
                merged.groupby("Subject")
                .size()
                .reset_index(name="Oppositions")
                .sort_values("Oppositions", ascending=False)
                .head(5)
            )
            top_subjects = subject_counts.to_dict("records")

    chart_top_subjects = (
        "\n".join(
            [
                f"{i + 1}. {s['Subject']} - {int(s['Oppositions']):,} oppositions"
                for i, s in enumerate(top_subjects)
            ]
        )
        if top_subjects
        else "No subject-level opposition data available."
    )

    scope_note = ""
    if scope_all:
        scope_note = (
            f"Totals reflect all available sessions. Bill-level sections reflect {session_label}."
        )

    existing_law_gap_summary = (
        "Texas law restricts state agencies from hiring lobbyists with public funds, "
        "but political subdivisions are not uniformly covered, creating a parity gap."
    )
    recommended_fix_statute = (
        "Amend Texas Government Code Section 556.005 to include political subdivisions and "
        "prohibit direct or indirect use of public funds for lobbying."
    )
    implementation_notes = (
        "Define political subdivision and public funds clearly, cover dues and assessments, "
        "and provide enforceable remedies for violations."
    )
    data_sources_bullets = "\n".join(
        [
            "- Texas Ethics Commission: lobby registrations, compensation ranges, and activity reports.",
            "- Texas Legislature Online: bill status, witness lists, and subject classifications.",
            "- Lobby Look-Up compiled dataset.",
        ]
    )
    disclaimer_note = (
        "Disclaimer: Figures are based on reported ranges and should be read as conservative estimates."
    )

    focus_section = None
    fc = focus_context or {}
    focus_type = str(fc.get("type", "")).strip().lower()
    tables = fc.get("tables", {}) if isinstance(fc, dict) else {}
    lookups = fc.get("lookups", {}) if isinstance(fc, dict) else {}
    if not isinstance(tables, dict):
        tables = {}
    if not isinstance(lookups, dict):
        lookups = {}

    staff_all = tables.get("Staff_All", pd.DataFrame())
    lobby_sub_all = tables.get("Lobby_Sub_All", pd.DataFrame())
    la_food = tables.get("LaFood", pd.DataFrame())
    la_ent = tables.get("LaEnt", pd.DataFrame())
    la_tran = tables.get("LaTran", pd.DataFrame())
    la_gift = tables.get("LaGift", pd.DataFrame())
    la_evnt = tables.get("LaEvnt", pd.DataFrame())
    la_awrd = tables.get("LaAwrd", pd.DataFrame())
    la_cvr = tables.get("LaCvr", pd.DataFrame())
    la_dock = tables.get("LaDock", pd.DataFrame())
    la_i4e = tables.get("LaI4E", pd.DataFrame())
    la_sub = tables.get("LaSub", pd.DataFrame())

    name_to_short = lookups.get("name_to_short", {})
    short_to_names = lookups.get("short_to_names", {})
    filerid_to_short = lookups.get("filerid_to_short", {})
    if not isinstance(name_to_short, dict):
        name_to_short = {}
    if not isinstance(short_to_names, dict):
        short_to_names = {}
    if not isinstance(filerid_to_short, dict):
        filerid_to_short = {}

    report_title = str(fc.get("report_title", "")).strip()
    if not report_title:
        if focus_type == "client":
            report_title = "Client Report"
        elif focus_type == "legislator":
            report_title = "Legislator Report"
        elif focus_type == "lobbyist":
            report_title = "Lobbyist Report"
        elif focus_type == "bill":
            report_title = "Bill Report"
        else:
            report_title = "Lobby Look-Up Report"

    def _truncate_text(text: str, max_len: int = 80) -> str:
        s = str(text or "").strip()
        if len(s) <= max_len:
            return s
        return s[: max_len - 3].rstrip() + "..."

    def _join_top(items: list[str], fallback: str = "Not available") -> str:
        clean = [s for s in items if str(s).strip()]
        return ", ".join(clean) if clean else fallback

    def _amount_mid_sum(series: pd.Series) -> float:
        if series is None or series.empty:
            return 0.0
        s = series.fillna("").astype(str).str.strip()
        s_clean = s.str.replace("$", "", regex=False).str.replace(",", "", regex=False)
        rng = s_clean.str.extract(_MONEY_RANGE)
        rng_lo = pd.to_numeric(rng[0], errors="coerce")
        rng_hi = pd.to_numeric(rng[1], errors="coerce")
        mid = (rng_lo + rng_hi) / 2
        single = pd.to_numeric(s_clean.str.extract(r"(-?\d+(?:\.\d+)?)")[0], errors="coerce")
        val = mid.where(mid.notna(), single).fillna(0.0)
        return float(val.sum())

    def _top_counts(series: pd.Series, limit: int = 5) -> list[tuple[str, int]]:
        if series is None or series.empty:
            return []
        clean = series.dropna().astype(str).str.strip()
        clean = clean[clean != ""]
        if clean.empty:
            return []
        counts = clean.value_counts().head(limit)
        return [(idx, int(val)) for idx, val in counts.items()]

    lobbyshort_to_name = {}
    if isinstance(short_to_names, dict) and short_to_names:
        lobbyshort_to_name = {k: (v[0] if v else k) for k, v in short_to_names.items()}
    if not lobbyshort_to_name and isinstance(Lobby_TFL_Client_All, pd.DataFrame) and not Lobby_TFL_Client_All.empty:
        tmp = Lobby_TFL_Client_All[["LobbyShort", "Lobby Name"]].dropna()
        tmp["LobbyShort"] = tmp["LobbyShort"].astype(str).str.strip()
        tmp["Lobby Name"] = tmp["Lobby Name"].astype(str).str.strip()
        lobbyshort_to_name = (
            tmp.groupby("LobbyShort")["Lobby Name"]
            .first()
            .to_dict()
        )

    def _pos_counts_from_positions(df: pd.DataFrame) -> dict:
        if df.empty:
            return {"Against": 0, "For": 0, "On": 0}
        return {
            "Against": int(df["Position"].astype(str).str.contains("Against", case=False, na=False).sum()),
            "For": int(df["Position"].astype(str).str.contains(r"\bFor\b", case=False, na=False).sum()),
            "On": int(df["Position"].astype(str).str.contains(r"\bOn\b", case=False, na=False).sum()),
        }

    if focus_type == "client":
        client_name = str(fc.get("name", "")).strip()
        if client_name:
            client_rows = ensure_cols(
                base,
                {"Client": "", "LobbyShort": "", "Low_num": 0.0, "High_num": 0.0, "IsTFL": 0, "Lobby Name": ""},
            ).copy()
            _cr_norms = norm_name_series(client_rows["Client"])
            client_rows = client_rows[_cr_norms == norm_name(client_name)]

            focus_section = {"title": f"Client - {client_name}", "summary": "", "metrics": [], "bullets": [], "charts": []}
            if client_rows.empty:
                focus_section["summary"] = "No client rows were found for the selected scope."
            else:
                client_rows["Mid"] = (client_rows["Low_num"] + client_rows["High_num"]) / 2
                c_total_low = float(client_rows["Low_num"].sum())
                c_total_high = float(client_rows["High_num"].sum())
                c_tfl_low = float(client_rows.loc[client_rows["IsTFL"] == 1, "Low_num"].sum())
                c_tfl_high = float(client_rows.loc[client_rows["IsTFL"] == 1, "High_num"].sum())
                c_pri_low = float(client_rows.loc[client_rows["IsTFL"] == 0, "Low_num"].sum())
                c_pri_high = float(client_rows.loc[client_rows["IsTFL"] == 0, "High_num"].sum())
                lobbyist_count = _unique_count(_series_from(client_rows, "LobbyShort"))
                session_count = _unique_count(_series_from(client_rows, "Session")) if "Session" in client_rows.columns else 0
                is_tfl_client = "Yes" if (client_rows["IsTFL"] == 1).any() else "No"

                focus_section["summary"] = (
                    f"{client_name} is associated with {lobbyist_count:,} lobbyists in this scope "
                    f"and reported compensation ranging from {fmt_usd(c_total_low)} to {fmt_usd(c_total_high)}."
                )
                focus_section["metrics"] = [
                    ("Client", client_name),
                    ("Taxpayer funded", is_tfl_client),
                    ("Lobbyists", f"{lobbyist_count:,}"),
                    ("Total range", f"{fmt_usd(c_total_low)} - {fmt_usd(c_total_high)}"),
                    ("Taxpayer-funded range", f"{fmt_usd(c_tfl_low)} - {fmt_usd(c_tfl_high)}"),
                    ("Private range", f"{fmt_usd(c_pri_low)} - {fmt_usd(c_pri_high)}"),
                ]
                if scope_all and session_count:
                    focus_section["bullets"].append(f"Sessions observed: {session_count:,}")

                lobbyshorts = (
                    client_rows["LobbyShort"].dropna().astype(str).str.strip().unique().tolist()
                )
                lobbyshort_norms = {norm_name(s) for s in lobbyshorts if s}
                lobbyist_names = [
                    lobbyshort_to_name.get(s, s) for s in lobbyshorts
                ]
                lobbyist_norms = set()
                for name in lobbyist_names + lobbyshorts:
                    lobbyist_norms |= norm_person_variants(name)
                    init_key = _last_first_initial_key(name)
                    if init_key:
                        lobbyist_norms.add(init_key)
                lobbyist_norms_tuple = tuple(sorted(lobbyist_norms))

                wit = Wit_All if isinstance(Wit_All, pd.DataFrame) else pd.DataFrame()
                bill_count = 0
                policy_count = 0
                top_bill_lines = []
                top_subject_lines = []
                status_counts = []
                bill_list_all = []
                sub_counts = pd.DataFrame()
                if lobbyshorts and not wit.empty and "LobbyShort" in wit.columns:
                    wit = wit[wit["LobbyShort"].astype(str).str.strip().isin(lobbyshorts)]
                    if session_val is not None and "Session" in wit.columns:
                        wit = wit[wit["Session"].astype(str).str.strip() == str(session_val)]
                    if not wit.empty:
                        pos = bill_position_from_flags(wit)
                        bill_count = int(pos["Bill"].nunique()) if not pos.empty else 0
                        bill_list_all = pos["Bill"].dropna().astype(str).unique().tolist() if not pos.empty else []
                        pos_counts = _pos_counts_from_positions(pos)
                        focus_section["bullets"].append(
                            f"Bills with witness activity (selected session): {bill_count:,}"
                        )
                        focus_section["bullets"].append(
                            f"Witness positions - Against {pos_counts['Against']:,}, For {pos_counts['For']:,}, On {pos_counts['On']:,}."
                        )

                        bs = Bill_Status_All if isinstance(Bill_Status_All, pd.DataFrame) else pd.DataFrame()
                        if not bs.empty and "Session" in bs.columns and session_val is not None:
                            bs = bs[bs["Session"].astype(str).str.strip() == str(session_val)]
                        if bill_list_all and not bs.empty and "Bill" in bs.columns:
                            status_counts = _top_counts(
                                bs[bs["Bill"].astype(str).isin(bill_list_all)].get(
                                    "Status", pd.Series(dtype=object)
                                ),
                                4,
                            )

                        if "Bill" in wit.columns:
                            bill_counts = (
                                wit.groupby("Bill").size().reset_index(name="Witness Rows")
                                .sort_values("Witness Rows", ascending=False)
                                .head(5)
                            )
                            if not bill_counts.empty:
                                if not bs.empty and "Bill" in bs.columns:
                                    bs_short = bs.drop_duplicates(subset=["Bill"])
                                    bill_counts = bill_counts.merge(
                                        bs_short[["Bill", "Caption", "Status"]],
                                        on="Bill",
                                        how="left",
                                    )
                                for row in bill_counts.to_dict("records"):
                                    bill = str(row.get("Bill", "")).strip()
                                    count = int(row.get("Witness Rows", 0) or 0)
                                    caption = _truncate_text(row.get("Caption", ""), 70)
                                    status = str(row.get("Status", "")).strip()
                                    line = f"{bill} ({count:,} witness rows)"
                                    if status:
                                        line += f", {status}"
                                    if caption:
                                        line += f" - {caption}"
                                    top_bill_lines.append(line)

                        bill_sub = Bill_Sub_All if isinstance(Bill_Sub_All, pd.DataFrame) else pd.DataFrame()
                        if bill_list_all and not bill_sub.empty and {"Bill", "Subject"}.issubset(bill_sub.columns):
                            if session_val is not None and "Session" in bill_sub.columns:
                                bill_sub = bill_sub[bill_sub["Session"].astype(str).str.strip() == str(session_val)]
                            sub_counts = (
                                bill_sub[bill_sub["Bill"].astype(str).isin(bill_list_all)]
                                .groupby("Subject")
                                .size()
                                .reset_index(name="Mentions")
                                .sort_values("Mentions", ascending=False)
                                .head(5)
                            )
                            policy_count = int(sub_counts["Subject"].nunique()) if not sub_counts.empty else 0
                            for row in sub_counts.to_dict("records"):
                                subject = _truncate_text(row.get("Subject", ""), 60)
                                mentions = int(row.get("Mentions", 0) or 0)
                                if subject:
                                    top_subject_lines.append(f"{subject} ({mentions:,})")

                if bill_count:
                    focus_section["metrics"].append(("Bills w/ witness activity", f"{bill_count:,}"))
                if policy_count:
                    focus_section["metrics"].append(("Policy areas", f"{policy_count:,}"))
                if top_bill_lines:
                    focus_section["bullets"].append(
                        f"Top bills by witness activity: {_join_top(top_bill_lines)}"
                    )
                if top_subject_lines:
                    focus_section["bullets"].append(
                        f"Top policy areas: {_join_top(top_subject_lines)}"
                    )
                if not sub_counts.empty:
                    focus_section["charts"].append(
                        {
                            "kind": "bar",
                            "orientation": "h",
                            "title": "Top Policy Areas (Witness Bills)",
                            "caption": "Focus Chart. Policy areas tied to client-linked witness activity",
                            "data": [
                                {"label": str(r.Subject), "value": int(r.Mentions)}
                                for r in sub_counts.itertuples()
                            ],
                        }
                    )
                if status_counts:
                    status_summary = ", ".join([f"{k} ({v:,})" for k, v in status_counts])
                    focus_section["bullets"].append(f"Bill outcomes (selected session): {status_summary}")

                if not lobby_sub_all.empty:
                    lobby_sub = lobby_sub_all
                    if "Session" in lobby_sub.columns and session_val is not None:
                        lobby_sub = lobby_sub[lobby_sub["Session"].astype(str).str.strip() == str(session_val)]
                    if "LobbyShortNorm" in lobby_sub.columns:
                        lobby_sub = lobby_sub[lobby_sub["LobbyShortNorm"].isin(lobbyshort_norms)]
                    elif "LobbyShort" in lobby_sub.columns:
                        lobby_sub = lobby_sub[lobby_sub["LobbyShort"].astype(str).str.strip().isin(lobbyshorts)]
                    else:
                        lobby_sub = lobby_sub.iloc[0:0]
                    if not lobby_sub.empty:
                        lobby_sub = lobby_sub.assign(
                            Subject=lobby_sub.get("Subject Matter", "").fillna("").astype(str).str.strip(),
                            Other=lobby_sub.get("Other Subject Matter Description", "").fillna("").astype(str).str.strip(),
                        )
                        for col in ["Subject", "Other"]:
                            series = lobby_sub[col]
                            lobby_sub[col] = series.where(~series.str.lower().isin(["nan", "none"]), "")
                        unnamed0 = lobby_sub.get("Unnamed: 0", lobby_sub.get("Column1", "")).fillna("").astype(str).str.strip()
                        unnamed0 = unnamed0.where(~unnamed0.str.lower().isin(["nan", "none"]), "")
                        topic = lobby_sub["Subject"]
                        topic = topic.where(topic != "", lobby_sub["Other"])
                        topic = topic.where(topic != "", unnamed0)
                        topic = topic.where(topic != "", "Unspecified")
                        lobby_sub["Topic"] = topic
                        topic_counts = _top_counts(lobby_sub["Topic"], 5)
                        if topic_counts:
                            topics = ", ".join([f"{t} ({c:,})" for t, c in topic_counts])
                            focus_section["bullets"].append(f"Reported subject matters: {topics}")

                if not staff_all.empty and lobbyist_norms:
                    staff_df = staff_all
                    staff_session_mask = (
                        staff_df["Session"].astype(str).str.strip() == str(session_val)
                        if "Session" in staff_df.columns and session_val is not None
                        else pd.Series(False, index=staff_df.index)
                    )
                    last_names = {last_name_norm_from_text(n) for n in lobbyist_names if last_name_norm_from_text(n)}
                    init_map = {k: v for k, v in ((_last_first_initial_key(n), n) for n in lobbyist_names) if k}
                    full_map = {norm_name(n): n for n in lobbyist_names if n}
                    last_map = {k: v for k, v in ((last_name_norm_from_text(n), n) for n in lobbyist_names) if k}

                    match_mask = pd.Series(False, index=staff_df.index)
                    match_mask = match_mask | staff_df.get("StaffNameNorm", pd.Series(False, index=staff_df.index)).isin(lobbyist_norms)
                    match_mask = match_mask | staff_df.get("StaffLastInitialNorm", pd.Series(False, index=staff_df.index)).isin(lobbyist_norms)
                    if last_names:
                        match_mask = match_mask | staff_df.get("StaffLastNorm", pd.Series(False, index=staff_df.index)).isin(last_names)
                    if lobbyshort_norms:
                        match_mask = match_mask | staff_df.get("StaffLastInitialNorm", pd.Series(False, index=staff_df.index)).isin(lobbyshort_norms)

                    staff_pick = staff_df[match_mask]
                    staff_pick_session = staff_df[staff_session_mask & match_mask]
                    if not staff_pick.empty:
                        staff_rows = int(len(staff_pick))
                        staff_legs = int(staff_pick.get("Legislator", pd.Series(dtype=object)).nunique()) if "Legislator" in staff_pick.columns else 0
                        focus_section["metrics"].append(("Staff history rows", f"{staff_rows:,}"))
                        if staff_legs:
                            focus_section["metrics"].append(("Legislators w/ staff ties", f"{staff_legs:,}"))
                if lobbyshorts:
                    activities = build_activities_multi(
                        la_food,
                        la_ent,
                        la_tran,
                        la_gift,
                        la_evnt,
                        la_awrd,
                        lobbyshorts=lobbyshorts,
                        session=str(session_val) if session_val is not None else None,
                        name_to_short=name_to_short,
                        lobbyist_norms_tuple=lobbyist_norms_tuple,
                        filerid_to_short=filerid_to_short,
                        lobbyshort_to_name=lobbyshort_to_name,
                    )
                    if not activities.empty:
                        focus_section["metrics"].append(("Activity rows", f"{len(activities):,}"))
                        type_counts = _top_counts(activities.get("Type", pd.Series(dtype=object)), 4)
                        if type_counts:
                            types = ", ".join([f"{t} ({c:,})" for t, c in type_counts])
                            focus_section["bullets"].append(f"Top activity types: {types}")
                        amount_total = _amount_mid_sum(activities.get("Amount", pd.Series(dtype=object)))
                        if amount_total > 0:
                            focus_section["bullets"].append(f"Reported activity amount (midpoint): {fmt_usd(amount_total)}")
                        focus_section["charts"].append(
                            {
                                "kind": "bar",
                                "orientation": "h",
                                "title": "Activity Types (Rows)",
                                "caption": "Focus Chart. Activity types for client-linked lobbyists",
                                "data": [{"label": t, "value": c} for t, c in type_counts],
                            }
                        )

                    disclosures = build_disclosures_multi(
                        la_cvr,
                        la_dock,
                        la_i4e,
                        la_sub,
                        lobbyshorts=lobbyshorts,
                        session=str(session_val) if session_val is not None else None,
                        name_to_short=name_to_short,
                        lobbyist_norms_tuple=lobbyist_norms_tuple,
                        filerid_to_short=filerid_to_short,
                        lobbyshort_to_name=lobbyshort_to_name,
                    )
                    if not disclosures.empty:
                        focus_section["metrics"].append(("Disclosure rows", f"{len(disclosures):,}"))
                        d_counts = _top_counts(disclosures.get("Type", pd.Series(dtype=object)), 4)
                        if d_counts:
                            types = ", ".join([f"{t} ({c:,})" for t, c in d_counts])
                            focus_section["bullets"].append(f"Top disclosure types: {types}")
                        focus_section["charts"].append(
                            {
                                "kind": "bar",
                                "orientation": "h",
                                "title": "Disclosure Types (Rows)",
                                "caption": "Focus Chart. Disclosure types for client-linked lobbyists",
                                "data": [{"label": t, "value": c} for t, c in d_counts],
                            }
                        )
                lobby_group = (
                    client_rows.groupby("LobbyShort", as_index=False)
                    .agg(Mid=("Mid", "sum"), LobbyName=("Lobby Name", lambda s: s.dropna().astype(str).iloc[0] if len(s) else ""))
                )
                lobby_group["Lobbyist"] = lobby_group["LobbyName"].where(
                    lobby_group["LobbyName"].astype(str).str.strip().ne(""),
                    lobby_group["LobbyShort"],
                )
                top_lobby = lobby_group.sort_values("Mid", ascending=False).head(5)
                chart_data = [
                    {"label": str(r.Lobbyist), "value": float(r.Mid)}
                    for r in top_lobby.itertuples()
                    if float(r.Mid) > 0
                ]
                if chart_data:
                    focus_section["charts"].append(
                        {
                            "kind": "bar",
                            "orientation": "h",
                            "title": "Top Lobbyists by Midpoint Compensation",
                            "caption": "Focus Chart. Top lobbyists by midpoint compensation",
                            "data": chart_data,
                        }
                    )

    if focus_type == "lobbyist":
        lobbyshort = str(fc.get("lobbyshort", "")).strip()
        display_name = str(fc.get("display_name", "")).strip() or lobbyshort
        if lobbyshort:
            lobbyist_norms = set()
            for name in [display_name, lobbyshort]:
                if not name:
                    continue
                lobbyist_norms |= norm_person_variants(name)
                init_key = _last_first_initial_key(name)
                if init_key:
                    lobbyist_norms.add(init_key)
            if isinstance(short_to_names, dict) and lobbyshort in short_to_names:
                for name in short_to_names.get(lobbyshort, []):
                    lobbyist_norms |= norm_person_variants(name)
                    init_key = _last_first_initial_key(name)
                    if init_key:
                        lobbyist_norms.add(init_key)
            lobbyist_norms_tuple = tuple(sorted(lobbyist_norms))
            lobbyshort_norm = norm_name(lobbyshort)

            lobby_rows = ensure_cols(
                base,
                {"Client": "", "LobbyShort": "", "Low_num": 0.0, "High_num": 0.0, "IsTFL": 0},
            )
            lobby_rows = lobby_rows[lobby_rows["LobbyShort"].astype(str).str.strip() == lobbyshort]

            focus_section = {"title": f"Lobbyist - {display_name}", "summary": "", "metrics": [], "bullets": [], "charts": []}
            if lobby_rows.empty:
                focus_section["summary"] = "No lobbyist rows were found for the selected scope."
            else:
                lobby_rows["Mid"] = (lobby_rows["Low_num"] + lobby_rows["High_num"]) / 2
                l_tfl_low = float(lobby_rows.loc[lobby_rows["IsTFL"] == 1, "Low_num"].sum())
                l_tfl_high = float(lobby_rows.loc[lobby_rows["IsTFL"] == 1, "High_num"].sum())
                l_pri_low = float(lobby_rows.loc[lobby_rows["IsTFL"] == 0, "Low_num"].sum())
                l_pri_high = float(lobby_rows.loc[lobby_rows["IsTFL"] == 0, "High_num"].sum())
                tfl_clients_count = int(lobby_rows.loc[lobby_rows["IsTFL"] == 1, "Client"].nunique())
                pri_clients_count = int(lobby_rows.loc[lobby_rows["IsTFL"] == 0, "Client"].nunique())

                focus_section["summary"] = (
                    f"{display_name} is tied to {tfl_clients_count + pri_clients_count:,} clients in this scope "
                    f"and reported compensation ranging from {fmt_usd(l_tfl_low + l_pri_low)} to {fmt_usd(l_tfl_high + l_pri_high)}."
                )
                focus_section["metrics"] = [
                    ("Lobbyist", display_name),
                    ("Total clients", f"{tfl_clients_count + pri_clients_count:,}"),
                    ("Taxpayer-funded clients", f"{tfl_clients_count:,}"),
                    ("Private clients", f"{pri_clients_count:,}"),
                    ("Taxpayer-funded range", f"{fmt_usd(l_tfl_low)} - {fmt_usd(l_tfl_high)}"),
                    ("Private range", f"{fmt_usd(l_pri_low)} - {fmt_usd(l_pri_high)}"),
                ]

                bill_count = 0
                policy_count = 0
                top_bill_lines = []
                top_subject_lines = []
                status_counts = []
                bill_list_all = []
                sub_counts = pd.DataFrame()

                wit = Wit_All if isinstance(Wit_All, pd.DataFrame) else pd.DataFrame()
                if not wit.empty and "LobbyShort" in wit.columns:
                    wit = wit[wit["LobbyShort"].astype(str).str.strip() == lobbyshort]
                    if session_val is not None and "Session" in wit.columns:
                        wit = wit[wit["Session"].astype(str).str.strip() == str(session_val)]
                    if not wit.empty:
                        pos = bill_position_from_flags(wit)
                        bill_count = int(pos["Bill"].nunique()) if not pos.empty else 0
                        bill_list_all = pos["Bill"].dropna().astype(str).unique().tolist() if not pos.empty else []
                        pos_counts = _pos_counts_from_positions(pos)
                        focus_section["bullets"].append(
                            f"Bills with witness activity (selected session): {bill_count:,}"
                        )
                        focus_section["bullets"].append(
                            f"Witness positions - Against {pos_counts['Against']:,}, For {pos_counts['For']:,}, On {pos_counts['On']:,}."
                        )

                        bs = Bill_Status_All if isinstance(Bill_Status_All, pd.DataFrame) else pd.DataFrame()
                        if not bs.empty and "Session" in bs.columns and session_val is not None:
                            bs = bs[bs["Session"].astype(str).str.strip() == str(session_val)]
                        if bill_list_all and not bs.empty and "Bill" in bs.columns:
                            status_counts = _top_counts(
                                bs[bs["Bill"].astype(str).isin(bill_list_all)].get(
                                    "Status", pd.Series(dtype=object)
                                ),
                                4,
                            )

                        if "Bill" in wit.columns:
                            bill_counts = (
                                wit.groupby("Bill").size().reset_index(name="Witness Rows")
                                .sort_values("Witness Rows", ascending=False)
                                .head(5)
                            )
                            if not bill_counts.empty:
                                if not bs.empty and "Bill" in bs.columns:
                                    bs_short = bs.drop_duplicates(subset=["Bill"])
                                    bill_counts = bill_counts.merge(
                                        bs_short[["Bill", "Caption", "Status"]],
                                        on="Bill",
                                        how="left",
                                    )
                                for row in bill_counts.to_dict("records"):
                                    bill = str(row.get("Bill", "")).strip()
                                    count = int(row.get("Witness Rows", 0) or 0)
                                    caption = _truncate_text(row.get("Caption", ""), 70)
                                    status = str(row.get("Status", "")).strip()
                                    line = f"{bill} ({count:,} witness rows)"
                                    if status:
                                        line += f", {status}"
                                    if caption:
                                        line += f" - {caption}"
                                    top_bill_lines.append(line)

                        bill_sub = Bill_Sub_All if isinstance(Bill_Sub_All, pd.DataFrame) else pd.DataFrame()
                        if bill_list_all and not bill_sub.empty and {"Bill", "Subject"}.issubset(bill_sub.columns):
                            if session_val is not None and "Session" in bill_sub.columns:
                                bill_sub = bill_sub[bill_sub["Session"].astype(str).str.strip() == str(session_val)]
                            sub_counts = (
                                bill_sub[bill_sub["Bill"].astype(str).isin(bill_list_all)]
                                .groupby("Subject")
                                .size()
                                .reset_index(name="Mentions")
                                .sort_values("Mentions", ascending=False)
                                .head(5)
                            )
                            policy_count = int(sub_counts["Subject"].nunique()) if not sub_counts.empty else 0
                            for row in sub_counts.to_dict("records"):
                                subject = _truncate_text(row.get("Subject", ""), 60)
                                mentions = int(row.get("Mentions", 0) or 0)
                                if subject:
                                    top_subject_lines.append(f"{subject} ({mentions:,})")

                if bill_count:
                    focus_section["metrics"].append(("Bills w/ witness activity", f"{bill_count:,}"))
                if policy_count:
                    focus_section["metrics"].append(("Policy areas", f"{policy_count:,}"))

                client_mid = (
                    lobby_rows.groupby(["Client", "IsTFL"], as_index=False)
                    .agg(Mid=("Mid", "sum"))
                    .sort_values("Mid", ascending=False)
                )
                tfl_top = client_mid[client_mid["IsTFL"] == 1].head(5)
                pri_top = client_mid[client_mid["IsTFL"] == 0].head(5)
                if not tfl_top.empty:
                    top_tfl = [
                        f"{_truncate_text(r.Client, 50)} ({fmt_usd(r.Mid)})"
                        for r in tfl_top.itertuples()
                    ]
                    focus_section["bullets"].append(f"Top taxpayer-funded clients: {_join_top(top_tfl)}")
                if not pri_top.empty:
                    top_pri = [
                        f"{_truncate_text(r.Client, 50)} ({fmt_usd(r.Mid)})"
                        for r in pri_top.itertuples()
                    ]
                    focus_section["bullets"].append(f"Top private clients: {_join_top(top_pri)}")
                if top_bill_lines:
                    focus_section["bullets"].append(
                        f"Top bills by witness activity: {_join_top(top_bill_lines)}"
                    )
                if top_subject_lines:
                    focus_section["bullets"].append(
                        f"Top policy areas: {_join_top(top_subject_lines)}"
                    )
                if not sub_counts.empty:
                    focus_section["charts"].append(
                        {
                            "kind": "bar",
                            "orientation": "h",
                            "title": "Top Policy Areas (Witness Bills)",
                            "caption": "Focus Chart. Policy areas tied to lobbyist witness activity",
                            "data": [
                                {"label": str(r.Subject), "value": int(r.Mentions)}
                                for r in sub_counts.itertuples()
                            ],
                        }
                    )
                if status_counts:
                    status_summary = ", ".join([f"{k} ({v:,})" for k, v in status_counts])
                    focus_section["bullets"].append(f"Bill outcomes (selected session): {status_summary}")

                if not lobby_sub_all.empty:
                    lobby_sub = lobby_sub_all
                    if "Session" in lobby_sub.columns and session_val is not None:
                        lobby_sub = lobby_sub[lobby_sub["Session"].astype(str).str.strip() == str(session_val)]
                    if "LobbyShortNorm" in lobby_sub.columns:
                        lobby_sub = lobby_sub[lobby_sub["LobbyShortNorm"] == lobbyshort_norm]
                    elif "LobbyShort" in lobby_sub.columns:
                        lobby_sub = lobby_sub[lobby_sub["LobbyShort"].astype(str).str.strip() == lobbyshort]
                    else:
                        lobby_sub = lobby_sub.iloc[0:0]
                    if not lobby_sub.empty:
                        lobby_sub = lobby_sub.assign(
                            Subject=lobby_sub.get("Subject Matter", "").fillna("").astype(str).str.strip(),
                            Other=lobby_sub.get("Other Subject Matter Description", "").fillna("").astype(str).str.strip(),
                        )
                        for col in ["Subject", "Other"]:
                            series = lobby_sub[col]
                            lobby_sub[col] = series.where(~series.str.lower().isin(["nan", "none"]), "")
                        unnamed0 = lobby_sub.get("Unnamed: 0", lobby_sub.get("Column1", "")).fillna("").astype(str).str.strip()
                        unnamed0 = unnamed0.where(~unnamed0.str.lower().isin(["nan", "none"]), "")
                        topic = lobby_sub["Subject"]
                        topic = topic.where(topic != "", lobby_sub["Other"])
                        topic = topic.where(topic != "", unnamed0)
                        topic = topic.where(topic != "", "Unspecified")
                        lobby_sub["Topic"] = topic
                        topic_counts = _top_counts(lobby_sub["Topic"], 5)
                        if topic_counts:
                            topics = ", ".join([f"{t} ({c:,})" for t, c in topic_counts])
                            focus_section["bullets"].append(f"Reported subject matters: {topics}")

                if not staff_all.empty and lobbyist_norms:
                    staff_df = staff_all
                    staff_session_mask = (
                        staff_df["Session"].astype(str).str.strip() == str(session_val)
                        if "Session" in staff_df.columns and session_val is not None
                        else pd.Series(False, index=staff_df.index)
                    )
                    last_names = {last_name_norm_from_text(n) for n in [display_name, lobbyshort] if last_name_norm_from_text(n)}

                    match_mask = pd.Series(False, index=staff_df.index)
                    match_mask = match_mask | staff_df.get("StaffNameNorm", pd.Series(False, index=staff_df.index)).isin(lobbyist_norms)
                    match_mask = match_mask | staff_df.get("StaffLastInitialNorm", pd.Series(False, index=staff_df.index)).isin(lobbyist_norms)
                    if last_names:
                        match_mask = match_mask | staff_df.get("StaffLastNorm", pd.Series(False, index=staff_df.index)).isin(last_names)
                    if lobbyshort_norm:
                        match_mask = match_mask | (
                            staff_df.get("StaffLastInitialNorm", pd.Series(False, index=staff_df.index)) == lobbyshort_norm
                        )

                    staff_pick = staff_df[match_mask]
                    staff_pick_session = staff_df[staff_session_mask & match_mask]
                    if not staff_pick.empty:
                        staff_rows = int(len(staff_pick))
                        staff_legs = int(staff_pick.get("Legislator", pd.Series(dtype=object)).nunique()) if "Legislator" in staff_pick.columns else 0
                        focus_section["metrics"].append(("Staff history rows", f"{staff_rows:,}"))
                        if staff_legs:
                            focus_section["metrics"].append(("Legislators w/ staff ties", f"{staff_legs:,}"))
                activities = build_activities(
                    la_food,
                    la_ent,
                    la_tran,
                    la_gift,
                    la_evnt,
                    la_awrd,
                    lobbyshort=lobbyshort,
                    session=str(session_val) if session_val is not None else None,
                    name_to_short=name_to_short,
                    lobbyist_norms_tuple=lobbyist_norms_tuple,
                    filerid_to_short=filerid_to_short,
                )
                if not activities.empty:
                    focus_section["metrics"].append(("Activity rows", f"{len(activities):,}"))
                    type_counts = _top_counts(activities.get("Type", pd.Series(dtype=object)), 4)
                    if type_counts:
                        types = ", ".join([f"{t} ({c:,})" for t, c in type_counts])
                        focus_section["bullets"].append(f"Top activity types: {types}")
                    amount_total = _amount_mid_sum(activities.get("Amount", pd.Series(dtype=object)))
                    if amount_total > 0:
                        focus_section["bullets"].append(f"Reported activity amount (midpoint): {fmt_usd(amount_total)}")
                    focus_section["charts"].append(
                        {
                            "kind": "bar",
                            "orientation": "h",
                            "title": "Activity Types (Rows)",
                            "caption": "Focus Chart. Activity types for the selected lobbyist",
                            "data": [{"label": t, "value": c} for t, c in type_counts],
                        }
                    )

                disclosures = build_disclosures(
                    la_cvr,
                    la_dock,
                    la_i4e,
                    la_sub,
                    lobbyshort=lobbyshort,
                    session=str(session_val) if session_val is not None else None,
                    name_to_short=name_to_short,
                    lobbyist_norms_tuple=lobbyist_norms_tuple,
                    filerid_to_short=filerid_to_short,
                )
                if not disclosures.empty:
                    focus_section["metrics"].append(("Disclosure rows", f"{len(disclosures):,}"))
                    d_counts = _top_counts(disclosures.get("Type", pd.Series(dtype=object)), 4)
                    if d_counts:
                        types = ", ".join([f"{t} ({c:,})" for t, c in d_counts])
                        focus_section["bullets"].append(f"Top disclosure types: {types}")
                    focus_section["charts"].append(
                        {
                            "kind": "bar",
                            "orientation": "h",
                            "title": "Disclosure Types (Rows)",
                            "caption": "Focus Chart. Disclosure types for the selected lobbyist",
                            "data": [{"label": t, "value": c} for t, c in d_counts],
                        }
                    )

                client_group = (
                    lobby_rows.groupby("Client", as_index=False)
                    .agg(Mid=("Mid", "sum"))
                    .sort_values("Mid", ascending=False)
                    .head(5)
                )
                chart_data = [
                    {"label": str(r.Client), "value": float(r.Mid)}
                    for r in client_group.itertuples()
                    if float(r.Mid) > 0
                ]
                if chart_data:
                    focus_section["charts"].append(
                        {
                            "kind": "bar",
                            "orientation": "h",
                            "title": "Top Clients by Midpoint Compensation",
                            "caption": "Focus Chart. Top clients by midpoint compensation",
                            "data": chart_data,
                        }
                    )

    if focus_type == "legislator":
        member_name = str(fc.get("name", "")).strip()
        if member_name:
            focus_section = {"title": f"Legislator - {member_name}", "summary": "", "metrics": [], "bullets": [], "charts": []}
            member_info = parse_member_name(member_name)
            authored_all = build_author_bill_index(Bill_Status_All) if isinstance(Bill_Status_All, pd.DataFrame) else pd.DataFrame()
            if authored_all.empty:
                focus_section["summary"] = "No authored bill data was available for the selected session."
            else:
                authored = authored_all
                authored = authored[authored["AuthorNorm"] == norm_name(member_name)]
                if session_val is not None and "Session" in authored.columns:
                    authored = authored[authored["Session"].astype(str).str.strip() == str(session_val)]

                bill_count = int(authored["Bill"].nunique()) if not authored.empty else 0
                passed = int((authored.get("Status", pd.Series(dtype=object)) == "Passed").sum()) if not authored.empty else 0
                failed = int((authored.get("Status", pd.Series(dtype=object)) == "Failed").sum()) if not authored.empty else 0
                bill_list = authored["Bill"].dropna().astype(str).unique().tolist() if not authored.empty else []

                wit = Wit_All if isinstance(Wit_All, pd.DataFrame) else pd.DataFrame()
                witness = pd.DataFrame()
                if bill_list and not wit.empty:
                    if session_val is not None and "Session" in wit.columns:
                        wit = wit[wit["Session"].astype(str).str.strip() == str(session_val)]
                    wit = wit[wit["Bill"].astype(str).isin(bill_list)] if "Bill" in wit.columns else wit.iloc[0:0]
                    witness = bill_position_from_flags(wit) if not wit.empty else pd.DataFrame()
                    if not witness.empty:
                        witness = witness.merge(tfl_flag, on="LobbyShort", how="left")
                        witness["IsTFL"] = pd.to_numeric(witness.get("IsTFL", 0), errors="coerce").fillna(0).astype(int)

                any_witness = int(witness["Bill"].nunique()) if not witness.empty else 0
                tfl_opposed = 0
                lobbyist_count = int(witness["LobbyShort"].nunique()) if not witness.empty and "LobbyShort" in witness.columns else 0
                tfl_lobbyist_count = int(witness.loc[witness["IsTFL"] == 1, "LobbyShort"].nunique()) if not witness.empty and "LobbyShort" in witness.columns else 0
                if not witness.empty:
                    against_mask = witness["Position"].astype(str).str.contains("Against", case=False, na=False)
                    tfl_mask = witness["IsTFL"] == 1
                    tfl_opposed = int(witness.loc[against_mask & tfl_mask, "Bill"].nunique())

                focus_section["summary"] = (
                    f"{member_name} authored {bill_count:,} bills in the selected session, with "
                    f"{passed:,} passed and {failed:,} failed."
                )
                focus_section["metrics"] = [
                    ("Bills authored", f"{bill_count:,}"),
                    ("Passed / Failed", f"{passed:,} / {failed:,}"),
                    ("Bills with witness activity", f"{any_witness:,}"),
                    ("Bills opposed by TFL lobbyists", f"{tfl_opposed:,}"),
                    ("Unique lobbyists", f"{lobbyist_count:,}"),
                    ("Lobbyists w/ TFL clients", f"{tfl_lobbyist_count:,}"),
                ]

                top_bills_lines = []
                if not authored.empty:
                    authored_unique = authored.drop_duplicates(subset=["Bill"])
                    status_rank = authored_unique.get("Status", pd.Series(dtype=object)).map(
                        {"Passed": 0, "Failed": 1}
                    ).fillna(2)
                    authored_unique = authored_unique.assign(_rank=status_rank)
                    top_authored = authored_unique.sort_values(["_rank", "Bill"]).head(5)
                    for row in top_authored.to_dict("records"):
                        bill = str(row.get("Bill", "")).strip()
                        status = str(row.get("Status", "")).strip()
                        caption = _truncate_text(row.get("Caption", ""), 70)
                        line = bill
                        if status:
                            line += f" ({status})"
                        if caption:
                            line += f" - {caption}"
                        if line.strip():
                            top_bills_lines.append(line)

                policy_count = 0
                top_subject_lines = []
                bill_sub = Bill_Sub_All if isinstance(Bill_Sub_All, pd.DataFrame) else pd.DataFrame()
                if bill_list and not bill_sub.empty and {"Bill", "Subject"}.issubset(bill_sub.columns):
                    if session_val is not None and "Session" in bill_sub.columns:
                        bill_sub = bill_sub[bill_sub["Session"].astype(str).str.strip() == str(session_val)]
                    sub_counts = (
                        bill_sub[bill_sub["Bill"].astype(str).isin(bill_list)]
                        .groupby("Subject")
                        .size()
                        .reset_index(name="Mentions")
                        .sort_values("Mentions", ascending=False)
                        .head(5)
                    )
                    policy_count = int(sub_counts["Subject"].nunique()) if not sub_counts.empty else 0
                    for row in sub_counts.to_dict("records"):
                        subject = _truncate_text(row.get("Subject", ""), 60)
                        mentions = int(row.get("Mentions", 0) or 0)
                        if subject:
                            top_subject_lines.append(f"{subject} ({mentions:,})")

                if top_bills_lines:
                    focus_section["bullets"].append(f"Top authored bills: {_join_top(top_bills_lines)}")
                if top_subject_lines:
                    focus_section["bullets"].append(f"Top policy areas: {_join_top(top_subject_lines)}")
                if policy_count:
                    focus_section["metrics"].append(("Policy areas", f"{policy_count:,}"))

                if not witness.empty:
                    pos_counts = _pos_counts_from_positions(witness)
                    focus_section["bullets"].append(
                        f"Witness positions - Against {pos_counts['Against']:,}, For {pos_counts['For']:,}, On {pos_counts['On']:,}."
                    )
                    if "LobbyShort" in witness.columns:
                        top_lobby = (
                            witness.groupby("LobbyShort")
                            .size()
                            .reset_index(name="Rows")
                            .sort_values("Rows", ascending=False)
                            .head(5)
                        )
                        top_lobby_lines = []
                        top_lobby_chart = []
                        for row in top_lobby.to_dict("records"):
                            short = str(row.get("LobbyShort", "")).strip()
                            rows = int(row.get("Rows", 0) or 0)
                            label = lobbyshort_to_name.get(short, short)
                            if label:
                                top_lobby_lines.append(f"{label} ({rows:,} rows)")
                                top_lobby_chart.append({"label": label, "value": rows})
                        if top_lobby_lines:
                            focus_section["bullets"].append(
                                f"Top lobbyists on witness lists: {_join_top(top_lobby_lines)}"
                            )
                        if top_lobby_chart:
                            focus_section["charts"].append(
                                {
                                    "kind": "bar",
                                    "orientation": "h",
                                    "title": "Top Lobbyists on Witness Lists",
                                    "caption": "Focus Chart. Lobbyists with the most witness-list rows",
                                    "data": top_lobby_chart,
                                }
                            )

                    if "IsTFL" in witness.columns:
                        counts = []
                        for funding_label, mask in [
                            ("Taxpayer Funded", witness["IsTFL"] == 1),
                            ("Private", witness["IsTFL"] != 1),
                        ]:
                            subset = witness[mask]
                            pos_counts = _pos_counts_from_positions(subset)
                            for position in ["Against", "For", "On"]:
                                counts.append(
                                    {
                                        "Position": position,
                                        "Funding": funding_label,
                                        "Count": int(pos_counts.get(position, 0)),
                                    }
                                )
                        if counts:
                            focus_section["charts"].append(
                                {
                                    "kind": "grouped_bar",
                                    "title": "Witness Positions by Funding Type",
                                    "caption": "Focus Chart. Witness positions by funding type",
                                    "data": counts,
                                }
                            )

                activities = build_member_activities(
                    la_food,
                    la_ent,
                    la_tran,
                    la_gift,
                    la_evnt,
                    la_awrd,
                    member_name=member_name,
                    session=str(session_val) if session_val is not None else None,
                    name_to_short=name_to_short,
                    filerid_to_short=filerid_to_short,
                    lobbyshort_to_name=lobbyshort_to_name,
                )
                if not activities.empty:
                    focus_section["metrics"].append(("Activity rows", f"{len(activities):,}"))
                    type_counts = _top_counts(activities.get("Type", pd.Series(dtype=object)), 4)
                    if type_counts:
                        types = ", ".join([f"{t} ({c:,})" for t, c in type_counts])
                        focus_section["bullets"].append(f"Top activity types: {types}")
                    amount_total = _amount_mid_sum(activities.get("Amount", pd.Series(dtype=object)))
                    if amount_total > 0:
                        focus_section["bullets"].append(f"Reported activity amount (midpoint): {fmt_usd(amount_total)}")
                    focus_section["charts"].append(
                        {
                            "kind": "bar",
                            "orientation": "h",
                            "title": "Activity Types (Rows)",
                            "caption": "Focus Chart. Activity types linked to the legislator",
                            "data": [{"label": t, "value": c} for t, c in type_counts],
                        }
                    )

                staff_matches = pd.DataFrame()
                if not staff_all.empty and "Legislator" in staff_all.columns:
                    staff_df = staff_all
                    leg_norm = norm_name_series(staff_df["Legislator"])
                    leg_last_norm = last_name_norm_series(staff_df["Legislator"])
                    leg_init_key = staff_df["Legislator"].fillna("").astype(str).map(_last_first_initial_key)

                    match = pd.Series(False, index=staff_df.index)
                    last_norm = member_info.get("last_norm", "")
                    if last_norm:
                        match = leg_last_norm == last_norm
                        if member_info.get("initial_key"):
                            match = match & (leg_init_key == member_info["initial_key"])

                    full_norm = member_info.get("full_norm", "")
                    if full_norm:
                        match = match | leg_norm.str.contains(full_norm, na=False)

                    staff_matches = staff_df[match]

                if not staff_matches.empty:
                    focus_section["metrics"].append(("Staff history rows", f"{len(staff_matches):,}"))
                    staffer_count = int(staff_matches.get("Staffer", pd.Series(dtype=object)).nunique()) if "Staffer" in staff_matches.columns else 0
                    if staffer_count:
                        focus_section["metrics"].append(("Staffers", f"{staffer_count:,}"))
                    top_staffers = _top_counts(staff_matches.get("Staffer", pd.Series(dtype=object)), 5)
                    if top_staffers:
                        staffer_list = ", ".join([f"{s} ({c:,})" for s, c in top_staffers])
                        focus_section["bullets"].append(f"Top staffers in history: {staffer_list}")

                staff_lobbyists = pd.DataFrame()
                if not staff_matches.empty and "Staffer" in staff_matches.columns:
                    tmp_short = Lobby_TFL_Client_All[["LobbyShort"]].dropna()
                    tmp_short["InitialKey"] = tmp_short["LobbyShort"].map(_last_first_initial_key)
                    init_counts = (
                        tmp_short.groupby(["InitialKey", "LobbyShort"])
                        .size()
                        .reset_index(name="n")
                        .sort_values(["InitialKey", "n"], ascending=[True, False])
                        .drop_duplicates("InitialKey")
                    )
                    initial_to_short = dict(zip(init_counts["InitialKey"], init_counts["LobbyShort"]))

                    def map_staffer(name: str) -> str:
                        if not name:
                            return ""
                        for v in norm_person_variants(name):
                            if v in name_to_short:
                                return str(name_to_short[v])
                        init_key = _last_first_initial_key(name)
                        if init_key and init_key in initial_to_short:
                            return str(initial_to_short[init_key])
                        return ""

                    staff_lobbyists = staff_matches
                    staff_lobbyists["LobbyShort"] = staff_lobbyists["Staffer"].fillna("").astype(str).map(map_staffer)
                    staff_lobbyists = staff_lobbyists[staff_lobbyists["LobbyShort"].astype(str).str.strip() != ""]
                    if not staff_lobbyists.empty:
                        focus_section["metrics"].append(
                            ("Staffers who became lobbyists", f"{staff_lobbyists['Staffer'].nunique():,}")
                        )
                        staff_lobbyists["Lobbyist"] = staff_lobbyists["LobbyShort"].map(lobbyshort_to_name).fillna(staff_lobbyists["LobbyShort"])
                        top_lobbyists = _top_counts(staff_lobbyists.get("Lobbyist", pd.Series(dtype=object)), 5)
                        if top_lobbyists:
                            lobbyist_list = ", ".join([f"{l} ({c:,})" for l, c in top_lobbyists])
                            focus_section["bullets"].append(f"Staff-to-lobbyist matches: {lobbyist_list}")

                chart_data = [
                    {"label": "Bills authored", "value": bill_count},
                    {"label": "Bills with witness activity", "value": any_witness},
                    {"label": "Bills opposed by TFL lobbyists", "value": tfl_opposed},
                ]
                focus_section["charts"].append(
                    {
                        "kind": "bar",
                        "orientation": "v",
                        "title": "Legislator Focus Metrics",
                        "caption": "Focus Chart. Legislator summary metrics",
                        "data": chart_data,
                    }
                )

    if focus_type == "bill":
        bill_id = str(fc.get("bill", "")).strip()
        if bill_id:
            bill_norm = bill_id
            try:
                bill_norm = normalize_bill(bill_id) or bill_id
            except Exception:
                bill_norm = bill_id
            bill_id = bill_norm
            focus_section = {"title": f"Bill - {bill_id}", "summary": "", "metrics": [], "bullets": [], "charts": []}
            bs = Bill_Status_All if isinstance(Bill_Status_All, pd.DataFrame) else pd.DataFrame()
            caption = ""
            status = ""
            author = ""
            if not bs.empty and "Bill" in bs.columns:
                bs = bs.copy()
                if session_val is not None and "Session" in bs.columns:
                    bs = bs[bs["Session"].astype(str).str.strip() == str(session_val)]
                try:
                    bs["BillNorm"] = bs["Bill"].astype(str).map(normalize_bill)
                except Exception:
                    bs["BillNorm"] = bs["Bill"].astype(str).str.strip()
                bs_match = bs[bs["BillNorm"] == bill_id]
                if not bs_match.empty:
                    caption = str(bs_match.get("Caption", pd.Series([""])).iloc[0]).strip()
                    status = str(bs_match.get("Status", pd.Series([""])).iloc[0]).strip()
                    for col in ["Author", "Authors"]:
                        if col in bs_match.columns:
                            author = str(bs_match.get(col, pd.Series([""])).iloc[0]).strip()
                            if author:
                                break

            wit = Wit_All if isinstance(Wit_All, pd.DataFrame) else pd.DataFrame()
            pos = pd.DataFrame()
            if not wit.empty and "Bill" in wit.columns:
                wit = wit.copy()
                if session_val is not None and "Session" in wit.columns:
                    wit = wit[wit["Session"].astype(str).str.strip() == str(session_val)]
                try:
                    wit["Bill"] = wit["Bill"].astype(str).map(normalize_bill)
                except Exception:
                    wit["Bill"] = wit["Bill"].astype(str).str.strip()
                wit = wit[wit["Bill"] == bill_id]
                if not wit.empty:
                    pos = bill_position_from_flags(wit)
                    if not pos.empty:
                        pos = pos.merge(tfl_flag, on="LobbyShort", how="left")
                        pos["IsTFL"] = pd.to_numeric(pos.get("IsTFL", 0), errors="coerce").fillna(0).astype(int)

            unique_lobbyists = int(pos["LobbyShort"].nunique()) if not pos.empty else 0
            org_series = wit.get("org", pd.Series(dtype=object)) if isinstance(wit, pd.DataFrame) else pd.Series(dtype=object)
            org_counts = _top_counts(org_series, 5)
            unique_orgs = int(org_series.dropna().astype(str).str.strip().nunique()) if not org_series.empty else 0

            witness_rows = int(len(wit)) if isinstance(wit, pd.DataFrame) else 0
            tfl_opposed = 0
            top_lobbyist_lines = []
            subject_lines = []
            tfl_witness_rows = 0
            private_witness_rows = 0
            if not pos.empty:
                against_mask = pos["Position"].astype(str).str.contains("Against", case=False, na=False)
                tfl_mask = pos["IsTFL"] == 1
                tfl_opposed = int(pos.loc[against_mask & tfl_mask, "LobbyShort"].nunique())
                tfl_witness_rows = int(pos.loc[tfl_mask, "LobbyShort"].nunique())
                private_witness_rows = int(pos.loc[~tfl_mask, "LobbyShort"].nunique())

                if "LobbyShort" in pos.columns:
                    name_map = {}
                    lt = Lobby_TFL_Client_All if isinstance(Lobby_TFL_Client_All, pd.DataFrame) else pd.DataFrame()
                    if not lt.empty and {"LobbyShort", "Lobby Name"}.issubset(lt.columns):
                        tmp = lt[["LobbyShort", "Lobby Name"]].dropna()
                        tmp["LobbyShort"] = tmp["LobbyShort"].astype(str).str.strip()
                        tmp["Lobby Name"] = tmp["Lobby Name"].astype(str).str.strip()
                        name_map = (
                            tmp.groupby("LobbyShort")["Lobby Name"]
                            .first()
                            .to_dict()
                        )

                    counts = (
                        pos.groupby("LobbyShort")
                        .size()
                        .reset_index(name="Rows")
                        .sort_values("Rows", ascending=False)
                        .head(5)
                    )
                    for row in counts.to_dict("records"):
                        short = str(row.get("LobbyShort", "")).strip()
                        rows = int(row.get("Rows", 0) or 0)
                        name = name_map.get(short, "")
                        label = f"{short}"
                        if name:
                            label = f"{name} ({short})"
                        top_lobbyist_lines.append(f"{label} ({rows:,} rows)")

            focus_section["summary"] = (
                f"{bill_id} has {witness_rows:,} witness-list rows in the selected session."
            )
            focus_section["metrics"] = [
                ("Bill", bill_id),
                ("Status", status or "Unknown"),
                ("Witness rows", f"{witness_rows:,}"),
                ("Unique lobbyists", f"{unique_lobbyists:,}"),
                ("TFL lobbyists opposed", f"{tfl_opposed:,}"),
                ("TFL lobbyists (any position)", f"{tfl_witness_rows:,}"),
                ("Private lobbyists (any position)", f"{private_witness_rows:,}"),
            ]
            if unique_orgs:
                focus_section["metrics"].append(("Organizations", f"{unique_orgs:,}"))
            if caption:
                focus_section["bullets"].append(f"Caption: {caption}")
            if author:
                focus_section["bullets"].append(f"Author: {author}")

            if top_lobbyist_lines:
                focus_section["bullets"].append(
                    f"Top lobbyists by witness rows: {_join_top(top_lobbyist_lines)}"
                )
            if org_counts:
                org_lines = [f"{_truncate_text(n, 60)} ({c:,})" for n, c in org_counts]
                focus_section["bullets"].append(
                    f"Top organizations on witness lists: {_join_top(org_lines)}"
                )
                focus_section["charts"].append(
                    {
                        "kind": "bar",
                        "orientation": "h",
                        "title": "Top Witness Organizations",
                        "caption": "Focus Chart. Organizations with the most witness-list rows",
                        "data": [{"label": n, "value": c} for n, c in org_counts],
                    }
                )

            bill_sub = Bill_Sub_All if isinstance(Bill_Sub_All, pd.DataFrame) else pd.DataFrame()
            if not bill_sub.empty and {"Bill", "Subject"}.issubset(bill_sub.columns):
                if session_val is not None and "Session" in bill_sub.columns:
                    bill_sub = bill_sub[bill_sub["Session"].astype(str).str.strip() == str(session_val)]
                bill_sub = bill_sub.copy()
                bill_sub["BillNorm"] = bill_sub["Bill"].astype(str).map(normalize_bill)
                sub_rows = bill_sub[bill_sub["BillNorm"] == bill_id]
                if not sub_rows.empty:
                    subjects = sub_rows["Subject"].dropna().astype(str).str.strip().unique().tolist()
                    for subject in subjects[:6]:
                        subject_lines.append(_truncate_text(subject, 70))
            if subject_lines:
                focus_section["bullets"].append(f"Subjects: {_join_top(subject_lines)}")

            if not pos.empty:
                counts = []
                for funding_label, mask in [
                    ("Taxpayer Funded", pos["IsTFL"] == 1),
                    ("Private", pos["IsTFL"] != 1),
                ]:
                    subset = pos[mask]
                    pos_counts = _pos_counts_from_positions(subset)
                    for position in ["Against", "For", "On"]:
                        counts.append(
                            {
                                "Position": position,
                                "Funding": funding_label,
                                "Count": int(pos_counts.get(position, 0)),
                            }
                        )
                focus_section["charts"].append(
                    {
                        "kind": "grouped_bar",
                        "title": "Witness Positions by Funding Type",
                        "caption": "Focus Chart. Witness positions by funding type",
                        "data": counts,
                    }
                )

    tfl_mid = (tfl_low + tfl_high) / 2
    private_mid = (private_low + private_high) / 2
    total_mid = tfl_mid + private_mid
    tfl_mid_share_pct = (tfl_mid / total_mid * 100) if total_mid > 0 else 0.0

    if total_mid <= 0:
        conditional_share_sentence = (
            "No reportable lobbying compensation was identified for the selected scope."
        )
        conditional_balance_sentence = ""
    else:
        if tfl_mid_share_pct >= 50:
            conditional_share_sentence = (
                "Midpoint estimates indicate taxpayer-funded entities represent a majority share "
                "of reported lobbying compensation in this scope."
            )
        elif tfl_mid_share_pct >= 35:
            conditional_share_sentence = (
                "Midpoint estimates indicate taxpayer-funded entities represent a substantial "
                "share of reported lobbying compensation in this scope."
            )
        elif tfl_mid_share_pct >= 15:
            conditional_share_sentence = (
                "Midpoint estimates indicate taxpayer-funded entities represent a material, "
                "non-trivial share of reported lobbying compensation in this scope."
            )
        else:
            conditional_share_sentence = (
                "Midpoint estimates indicate taxpayer-funded entities represent a smaller share "
                "of reported lobbying compensation in this scope."
            )

        mix_delta = tfl_mid - private_mid
        if abs(mix_delta) <= (0.10 * total_mid):
            conditional_balance_sentence = (
                "The midpoint funding mix is near parity between taxpayer-funded and private activity."
            )
        elif mix_delta > 0:
            conditional_balance_sentence = (
                "The midpoint funding mix shows taxpayer-funded activity outweighing private activity."
            )
        else:
            conditional_balance_sentence = (
                "The midpoint funding mix shows private activity outweighing taxpayer-funded activity."
            )

    tfl_w = witness_counts.get("tfl", {}) if isinstance(witness_counts, dict) else {}
    pri_w = witness_counts.get("private", {}) if isinstance(witness_counts, dict) else {}
    tfl_against = int(tfl_w.get("Against", 0) or 0)
    tfl_for = int(tfl_w.get("For", 0) or 0)
    tfl_on = int(tfl_w.get("On", 0) or 0)
    pri_against = int(pri_w.get("Against", 0) or 0)
    pri_for = int(pri_w.get("For", 0) or 0)
    pri_on = int(pri_w.get("On", 0) or 0)
    witness_total = tfl_against + tfl_for + tfl_on + pri_against + pri_for + pri_on
    if witness_total <= 0:
        conditional_witness_sentence = (
            "No witness-position activity was available in the selected scope/session."
        )
    else:
        if tfl_against >= max(tfl_for, tfl_on):
            stance_text = "taxpayer-funded testimony skews toward opposition"
        elif tfl_for >= max(tfl_against, tfl_on):
            stance_text = "taxpayer-funded testimony skews toward support"
        else:
            stance_text = "taxpayer-funded testimony is mixed across positions"
        conditional_witness_sentence = (
            f"In witness data, {stance_text} "
            f"({tfl_against:,} Against, {tfl_for:,} For, {tfl_on:,} On)."
        )

    if focus_type == "client":
        conditional_focus_sentence = (
            "Focus findings are client-centered and update as the selected client changes."
        )
        focus_highlights_intro = (
            "Key client-specific findings generated from the current scope and linked lobbyist activity."
        )
    elif focus_type == "lobbyist":
        conditional_focus_sentence = (
            "Focus findings are lobbyist-centered and update as the selected lobbyist changes."
        )
        focus_highlights_intro = (
            "Key lobbyist-specific findings generated from the current scope and linked client activity."
        )
    elif focus_type == "legislator":
        conditional_focus_sentence = (
            "Focus findings are legislator-centered and update as the selected legislator changes."
        )
        focus_highlights_intro = (
            "Key legislator-specific findings generated from authored-bill, witness, and activity data."
        )
    elif focus_type == "bill":
        conditional_focus_sentence = (
            "Focus findings are bill-centered and update as the selected bill changes."
        )
        focus_highlights_intro = (
            "Key bill-specific findings generated from witness, status, and subject-matter records."
        )
    else:
        conditional_focus_sentence = (
            "Focus findings are generated from the current filters and update as inputs change."
        )
        focus_highlights_intro = "Most relevant findings for the selected focus."

    conditional_exec_sentences = [
        s
        for s in [
            conditional_share_sentence,
            conditional_balance_sentence,
            conditional_witness_sentence,
        ]
        if str(s).strip()
    ]

    payload = {
        "session_label": session_label,
        "generated_date": generated_date,
        "generated_ts": generated_ts,
        "report_id": report_id,
        "scope_label": scope_label,
        "focus_label": focus_label,
        "filter_summary": filter_summary,
        "selected_lobbyist": selected_lobbyist,
        "total_low_value": total_low,
        "total_high_value": total_high,
        "tfl_low_value": tfl_low,
        "tfl_high_value": tfl_high,
        "private_low_value": private_low,
        "private_high_value": private_high,
        "total_low": fmt_usd(total_low),
        "total_high": fmt_usd(total_high),
        "tfl_low": fmt_usd(tfl_low),
        "tfl_high": fmt_usd(tfl_high),
        "private_low": fmt_usd(private_low),
        "private_high": fmt_usd(private_high),
        "tfl_share_low_pct": f"{tfl_share_low_pct:.1f}",
        "tfl_share_high_pct": f"{tfl_share_high_pct:.1f}",
        "tfl_share_low_pct_value": tfl_share_low_pct,
        "tfl_share_high_pct_value": tfl_share_high_pct,
        "private_share_low_pct_value": private_share_low_pct,
        "private_share_high_pct_value": private_share_high_pct,
        "funding_mix": funding_mix,
        "unique_lobbyists_total": f"{unique_lobbyists_total:,}",
        "unique_lobbyists_tfl": f"{unique_lobbyists_tfl:,}",
        "unique_clients_total": f"{unique_clients_total:,}",
        "unique_clients_tfl": f"{unique_clients_tfl:,}",
        "top_clients_tfl": top_clients_tfl,
        "top_clients_private": top_clients_private,
        "chart_compensation_bar": chart_compensation_bar,
        "chart_share": chart_share,
        "chart_entity_types": chart_entity_types,
        "chart_entity_types_data": entity_type_counts,
        "witness_activity_summary": witness_summary,
        "chart_witness_positions": chart_witness_positions,
        "witness_counts": witness_counts,
        "chart_top_bills": chart_top_bills,
        "chart_top_subjects": chart_top_subjects,
        "existing_law_gap_summary": existing_law_gap_summary,
        "recommended_fix_statute": recommended_fix_statute,
        "implementation_notes": implementation_notes,
        "data_sources_bullets": data_sources_bullets,
        "disclaimer_note": disclaimer_note,
        "report_title": report_title,
        "scope_session_label": scope_session_label,
        "scope_note": scope_note,
        "has_top_bills": bool(top_bills),
        "has_top_subjects": bool(top_subjects),
        "top_bills": top_bills,
        "top_subjects": top_subjects,
        "focus_section": focus_section,
        "conditional_exec_sentences": conditional_exec_sentences,
        "conditional_focus_sentence": conditional_focus_sentence,
        "focus_highlights_intro": focus_highlights_intro,
        "tfl_mid_share_pct_value": tfl_mid_share_pct,
    }

    for i in range(5):
        if i < len(top_bills):
            b = top_bills[i]
            payload[f"bill_{i + 1}_id"] = b["id"]
            payload[f"bill_{i + 1}_caption"] = b["caption"]
            payload[f"bill_{i + 1}_opp_count"] = f"{b['tfl']:,}"
            payload[f"bill_{i + 1}_private_opp"] = f"{b['private']:,}"
            payload[f"bill_{i + 1}_summary"] = b["summary"]
        else:
            payload[f"bill_{i + 1}_id"] = "-"
            payload[f"bill_{i + 1}_caption"] = "-"
            payload[f"bill_{i + 1}_opp_count"] = "0"
            payload[f"bill_{i + 1}_private_opp"] = "0"
            payload[f"bill_{i + 1}_summary"] = "No summary available."

    for i in range(5):
        if i < len(top_subjects):
            s = top_subjects[i]
            payload[f"subject_{i + 1}"] = s["Subject"]
            payload[f"subject_{i + 1}_opp_count"] = f"{int(s['Oppositions']):,}"
        else:
            payload[f"subject_{i + 1}"] = "-"
            payload[f"subject_{i + 1}_opp_count"] = "0"

    return payload

def _build_report_pdf_bytes(payload: dict) -> bytes:
    payload = dict(payload) if isinstance(payload, dict) else {}

    def _safe_str(value, default: str = "") -> str:
        if value is None:
            return default
        try:
            return str(value)
        except Exception:
            return default

    def _safe_float(value, default: float = 0.0) -> float:
        if value is None:
            return default
        try:
            if isinstance(value, str):
                txt = value.strip().replace(",", "")
                if txt == "":
                    return default
                return float(txt)
            return float(value)
        except Exception:
            return default

    def _safe_bool(value, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return bool(value)
        txt = _safe_str(value).strip().lower()
        if txt in {"true", "1", "yes", "y"}:
            return True
        if txt in {"false", "0", "no", "n"}:
            return False
        return default

    def _safe_list(value) -> list:
        return value if isinstance(value, list) else []

    def _safe_dict(value) -> dict:
        return value if isinstance(value, dict) else {}

    default_payload = {
        "report_title": "Lobby Look-Up Report",
        "session_label": "Selected Session",
        "scope_label": "Selected Session",
        "scope_session_label": "Selected Session",
        "focus_label": "All",
        "generated_date": datetime.now().strftime("%B %d, %Y"),
        "generated_ts": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_low": "$0",
        "total_high": "$0",
        "tfl_low": "$0",
        "tfl_high": "$0",
        "private_low": "$0",
        "private_high": "$0",
        "tfl_share_low_pct": "0.0",
        "tfl_share_high_pct": "0.0",
        "unique_lobbyists_total": "0",
        "unique_lobbyists_tfl": "0",
        "unique_clients_total": "0",
        "unique_clients_tfl": "0",
        "witness_activity_summary": "No witness-list data available for this scope/session.",
        "existing_law_gap_summary": "",
        "recommended_fix_statute": "",
        "implementation_notes": "",
        "data_sources_bullets": "",
        "disclaimer_note": "",
        "scope_note": "",
        "focus_section": {},
        "witness_counts": {},
        "top_bills": [],
        "top_subjects": [],
        "chart_entity_types_data": [],
        "conditional_exec_sentences": [],
        "conditional_focus_sentence": "",
        "focus_highlights_intro": "",
        "focus_snapshot_paragraph": "",
        "has_top_bills": False,
        "has_top_subjects": False,
    }
    for key, value in default_payload.items():
        payload.setdefault(key, value)

    numeric_defaults = {
        "total_low_value": 0.0,
        "total_high_value": 0.0,
        "tfl_low_value": 0.0,
        "tfl_high_value": 0.0,
        "private_low_value": 0.0,
        "private_high_value": 0.0,
        "tfl_share_low_pct_value": 0.0,
        "tfl_share_high_pct_value": 0.0,
        "private_share_low_pct_value": 0.0,
        "private_share_high_pct_value": 0.0,
        "tfl_mid_share_pct_value": 0.0,
    }
    for key, fallback in numeric_defaults.items():
        payload[key] = _safe_float(payload.get(key), fallback)

    string_keys = [
        "report_title",
        "session_label",
        "scope_label",
        "scope_session_label",
        "focus_label",
        "generated_date",
        "generated_ts",
        "total_low",
        "total_high",
        "tfl_low",
        "tfl_high",
        "private_low",
        "private_high",
        "tfl_share_low_pct",
        "tfl_share_high_pct",
        "unique_lobbyists_total",
        "unique_lobbyists_tfl",
        "unique_clients_total",
        "unique_clients_tfl",
        "witness_activity_summary",
        "existing_law_gap_summary",
        "recommended_fix_statute",
        "implementation_notes",
        "data_sources_bullets",
        "disclaimer_note",
        "scope_note",
        "conditional_focus_sentence",
        "focus_highlights_intro",
        "focus_snapshot_paragraph",
    ]
    for key in string_keys:
        payload[key] = _safe_str(payload.get(key), _safe_str(default_payload.get(key, "")))

    payload["focus_section"] = _safe_dict(payload.get("focus_section"))
    payload["witness_counts"] = _safe_dict(payload.get("witness_counts"))
    payload["top_bills"] = [b for b in _safe_list(payload.get("top_bills")) if isinstance(b, dict)]
    payload["top_subjects"] = [s for s in _safe_list(payload.get("top_subjects")) if isinstance(s, dict)]
    payload["chart_entity_types_data"] = [
        r for r in _safe_list(payload.get("chart_entity_types_data")) if isinstance(r, dict)
    ]
    payload["conditional_exec_sentences"] = [
        _safe_str(s).strip()
        for s in _safe_list(payload.get("conditional_exec_sentences"))
        if _safe_str(s).strip()
    ]
    payload["has_top_bills"] = _safe_bool(payload.get("has_top_bills"), False) or bool(payload["top_bills"])
    payload["has_top_subjects"] = _safe_bool(payload.get("has_top_subjects"), False) or bool(payload["top_subjects"])

    if payload["focus_section"]:
        fs = payload["focus_section"]
        fs["title"] = _safe_str(fs.get("title", ""))
        fs["summary"] = _safe_str(fs.get("summary", ""))

        metrics_safe = []
        for item in _safe_list(fs.get("metrics")):
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                metrics_safe.append((_safe_str(item[0]), _safe_str(item[1])))
        fs["metrics"] = metrics_safe

        fs["bullets"] = [
            _safe_str(item).strip()
            for item in _safe_list(fs.get("bullets"))
            if _safe_str(item).strip()
        ]
        fs["charts"] = _safe_list(fs.get("charts"))
        payload["focus_section"] = fs

    if not _safe_str(payload.get("total_low")).strip():
        payload["total_low"] = fmt_usd(payload["total_low_value"])
    if not _safe_str(payload.get("total_high")).strip():
        payload["total_high"] = fmt_usd(payload["total_high_value"])
    if not _safe_str(payload.get("tfl_low")).strip():
        payload["tfl_low"] = fmt_usd(payload["tfl_low_value"])
    if not _safe_str(payload.get("tfl_high")).strip():
        payload["tfl_high"] = fmt_usd(payload["tfl_high_value"])
    if not _safe_str(payload.get("private_low")).strip():
        payload["private_low"] = fmt_usd(payload["private_low_value"])
    if not _safe_str(payload.get("private_high")).strip():
        payload["private_high"] = fmt_usd(payload["private_high_value"])

    if payload["tfl_share_low_pct_value"] == 0.0 and payload["tfl_share_high_pct_value"] == 0.0:
        share_low, share_high = _calc_share_range(
            payload["tfl_low_value"],
            payload["tfl_high_value"],
            payload["total_low_value"],
            payload["total_high_value"],
        )
        payload["tfl_share_low_pct_value"] = share_low
        payload["tfl_share_high_pct_value"] = share_high
    if not _safe_str(payload.get("tfl_share_low_pct")).strip():
        payload["tfl_share_low_pct"] = f"{payload['tfl_share_low_pct_value']:.1f}"
    if not _safe_str(payload.get("tfl_share_high_pct")).strip():
        payload["tfl_share_high_pct"] = f"{payload['tfl_share_high_pct_value']:.1f}"

    top_bills_safe = []
    for bill in payload["top_bills"]:
        top_bills_safe.append(
            {
                "id": _safe_str(bill.get("id"), "-").strip() or "-",
                "tfl": int(_safe_float(bill.get("tfl"), 0.0)),
                "private": int(_safe_float(bill.get("private"), 0.0)),
                "caption": _safe_str(bill.get("caption"), "").strip(),
                "summary": _safe_str(bill.get("summary"), "").strip(),
            }
        )
    payload["top_bills"] = top_bills_safe

    top_subjects_safe = []
    for subject in payload["top_subjects"]:
        top_subjects_safe.append(
            {
                "Subject": _safe_str(subject.get("Subject"), "").strip(),
                "Oppositions": int(_safe_float(subject.get("Oppositions"), 0.0)),
            }
        )
    payload["top_subjects"] = top_subjects_safe

    entity_rows_safe = []
    for row in payload["chart_entity_types_data"]:
        label = _safe_str(row.get("type"), "").strip()
        if not label:
            continue
        entity_rows_safe.append({"type": label, "count": int(_safe_float(row.get("count"), 0.0))})
    payload["chart_entity_types_data"] = entity_rows_safe

    witness_counts_safe = _safe_dict(payload.get("witness_counts"))
    witness_counts_safe["tfl"] = _safe_dict(witness_counts_safe.get("tfl"))
    witness_counts_safe["private"] = _safe_dict(witness_counts_safe.get("private"))
    for bucket in ("tfl", "private"):
        for position in ("Against", "For", "On"):
            witness_counts_safe[bucket][position] = int(
                _safe_float(witness_counts_safe[bucket].get(position), 0.0)
            )
    payload["witness_counts"] = witness_counts_safe

    def _derive_exec_conditionals() -> list[str]:
        total_mid = (payload["total_low_value"] + payload["total_high_value"]) / 2.0
        tfl_mid = (payload["tfl_low_value"] + payload["tfl_high_value"]) / 2.0
        private_mid = (payload["private_low_value"] + payload["private_high_value"]) / 2.0
        out = []

        if total_mid <= 0:
            out.append("No reportable lobbying compensation was identified for the selected scope.")
        else:
            tfl_mid_pct = (tfl_mid / total_mid) * 100.0
            if tfl_mid_pct >= 50:
                out.append(
                    "Midpoint estimates indicate taxpayer-funded entities represent a majority share of reported lobbying compensation in this scope."
                )
            elif tfl_mid_pct >= 35:
                out.append(
                    "Midpoint estimates indicate taxpayer-funded entities represent a substantial share of reported lobbying compensation in this scope."
                )
            elif tfl_mid_pct >= 15:
                out.append(
                    "Midpoint estimates indicate taxpayer-funded entities represent a material, non-trivial share of reported lobbying compensation in this scope."
                )
            else:
                out.append(
                    "Midpoint estimates indicate taxpayer-funded entities represent a smaller share of reported lobbying compensation in this scope."
                )

            delta = tfl_mid - private_mid
            if abs(delta) <= (0.10 * total_mid):
                out.append("The midpoint funding mix is near parity between taxpayer-funded and private activity.")
            elif delta > 0:
                out.append("The midpoint funding mix shows taxpayer-funded activity outweighing private activity.")
            else:
                out.append("The midpoint funding mix shows private activity outweighing taxpayer-funded activity.")

        tfl_counts = payload["witness_counts"].get("tfl", {})
        tfl_against = int(tfl_counts.get("Against", 0))
        tfl_for = int(tfl_counts.get("For", 0))
        tfl_on = int(tfl_counts.get("On", 0))
        if (tfl_against + tfl_for + tfl_on) <= 0:
            out.append("No witness-position activity was available in the selected scope/session.")
        else:
            if tfl_against >= max(tfl_for, tfl_on):
                stance = "taxpayer-funded testimony skews toward opposition"
            elif tfl_for >= max(tfl_against, tfl_on):
                stance = "taxpayer-funded testimony skews toward support"
            else:
                stance = "taxpayer-funded testimony is mixed across positions"
            out.append(
                f"In witness data, {stance} ({tfl_against:,} Against, {tfl_for:,} For, {tfl_on:,} On)."
            )
        return [s for s in out if _safe_str(s).strip()]

    def _derive_focus_context_sentence() -> tuple[str, str]:
        focus_label_txt = _safe_str(payload.get("focus_label")).strip().lower()
        focus_title_txt = _safe_str(payload.get("focus_section", {}).get("title", "")).strip().lower()
        focus_hint = f"{focus_label_txt} {focus_title_txt}".strip()

        if "client" in focus_hint:
            return (
                "This snapshot is client-centered and updates with the selected client and filters.",
                "Client-specific indicators drawn from linked lobbying activity and session-scoped records.",
            )
        if "lobbyist" in focus_hint:
            return (
                "This snapshot is lobbyist-centered and updates with the selected lobbyist and filters.",
                "Lobbyist-specific indicators drawn from linked client relationships and session activity.",
            )
        if "legislator" in focus_hint:
            return (
                "This snapshot is legislator-centered and updates with the selected legislator and filters.",
                "Legislator-specific indicators drawn from authored bills, witness behavior, and related activity.",
            )
        if "bill" in focus_hint:
            return (
                "This snapshot is bill-centered and updates with the selected bill and filters.",
                "Bill-specific indicators drawn from witness records, status history, and subject patterns.",
            )
        return (
            "This snapshot updates from the current filters and focus selection.",
            "Most relevant findings generated for the selected focus.",
        )

    computed_exec_conditionals = _derive_exec_conditionals()
    combined_exec_conditionals = []
    for sentence in payload["conditional_exec_sentences"] + computed_exec_conditionals:
        clean_sentence = _safe_str(sentence).strip()
        if clean_sentence and clean_sentence not in combined_exec_conditionals:
            combined_exec_conditionals.append(clean_sentence)
    payload["conditional_exec_sentences"] = combined_exec_conditionals

    default_focus_sentence, default_focus_intro = _derive_focus_context_sentence()
    if not _safe_str(payload.get("conditional_focus_sentence")).strip():
        payload["conditional_focus_sentence"] = default_focus_sentence
    if not _safe_str(payload.get("focus_highlights_intro")).strip():
        payload["focus_highlights_intro"] = default_focus_intro

    def _derive_focus_snapshot_paragraph() -> str:
        focus_section_local = _safe_dict(payload.get("focus_section"))
        focus_title = _safe_str(focus_section_local.get("title", "")).strip()
        focus_label = _safe_str(payload.get("focus_label"), "This focus").strip() or "This focus"
        focus_subject = focus_title or focus_label
        focus_hint = f"{focus_label.lower()} {focus_title.lower()}".strip()

        if "client" in focus_hint:
            focus_type = "client"
        elif "lobbyist" in focus_hint:
            focus_type = "lobbyist"
        elif "legislator" in focus_hint:
            focus_type = "legislator"
        elif "bill" in focus_hint:
            focus_type = "bill"
        else:
            focus_type = "general"

        metric_map = {}
        for metric in _safe_list(focus_section_local.get("metrics")):
            if not isinstance(metric, (list, tuple)) or len(metric) < 2:
                continue
            label = " ".join(_safe_str(metric[0]).strip().lower().split())
            if label:
                metric_map[label] = _safe_str(metric[1]).strip()

        def _extract_numbers(value) -> list[float]:
            txt = _safe_str(value).replace(",", "").strip()
            if not txt:
                return []
            cleaned = "".join(ch if (ch.isdigit() or ch in ".-") else " " for ch in txt)
            out = []
            for token in cleaned.split():
                try:
                    out.append(float(token))
                except Exception:
                    continue
            return out

        def _first_number(value) -> float:
            nums = _extract_numbers(value)
            return nums[0] if nums else 0.0

        def _range_midpoint(value) -> float:
            nums = _extract_numbers(value)
            if not nums:
                return 0.0
            if len(nums) == 1:
                return nums[0]
            return (nums[0] + nums[1]) / 2.0

        def _metric_value(*labels: str) -> str:
            for label in labels:
                key = " ".join(_safe_str(label).strip().lower().split())
                if key and key in metric_map:
                    val = _safe_str(metric_map.get(key, "")).strip()
                    if val:
                        return val
            return ""

        def _metric_int(*labels: str) -> int:
            val = _metric_value(*labels)
            if not val:
                return 0
            return int(_first_number(val))

        def _first_int_after_keyword(text: str, keyword: str) -> int | None:
            text_norm = _safe_str(text)
            key_norm = _safe_str(keyword).strip().lower()
            idx = text_norm.lower().find(key_norm)
            if idx < 0:
                return None
            tail = text_norm[idx + len(key_norm):]
            cleaned = "".join(ch if ch.isdigit() else " " for ch in tail)
            tokens = [tok for tok in cleaned.split() if tok]
            if not tokens:
                return None
            try:
                return int(tokens[0])
            except Exception:
                return None

        def _sentence_case(text: str) -> str:
            t = _safe_str(text).strip()
            if not t:
                return ""
            return t[0].upper() + t[1:]

        parts = []
        signals_used = 0
        focus_specific_signals = 0

        if focus_type == "client":
            parts.append(f"{focus_subject} functions as a client-centered hub in the advocacy network for this scope.")
        elif focus_type == "lobbyist":
            parts.append(f"{focus_subject} functions as a lobbyist-centered conduit between client portfolios and legislative influence.")
        elif focus_type == "legislator":
            parts.append(f"{focus_subject} is evaluated through authored-bill outcomes and observed witness pressure patterns.")
        elif focus_type == "bill":
            parts.append(f"{focus_subject} functions as a bill-level pressure point where support and opposition activity converge.")
        else:
            parts.append(f"{focus_subject} reflects a concentrated set of relationships in the selected scope.")

        focus_clients_total = 0
        focus_clients_tfl = 0
        client_scope = "none"
        if focus_type == "client":
            # Client focus represents a single selected client; infer TFL status from client metrics.
            focus_clients_total = 1
            client_tfl_flag = _metric_value("taxpayer funded")
            normalized_flag = client_tfl_flag.strip().lower() if client_tfl_flag else ""
            if normalized_flag in {"yes", "true", "1"}:
                focus_clients_tfl = 1
                client_scope = "focus"
            elif normalized_flag in {"no", "false", "0"}:
                focus_clients_tfl = 0
                client_scope = "focus"
            else:
                # If classification is unavailable, suppress this ratio sentence for client focus.
                focus_clients_total = 0
                focus_clients_tfl = 0
        elif focus_type == "lobbyist":
            focus_clients_total = _metric_int("total clients")
            focus_clients_tfl = _metric_int("taxpayer-funded clients", "taxpayer funded clients")
            private_clients = _metric_int("private clients")
            if focus_clients_total <= 0 and (focus_clients_tfl + private_clients) > 0:
                focus_clients_total = focus_clients_tfl + private_clients
            if focus_clients_total <= 0:
                focus_clients_total = int(_safe_float(payload.get("focus_clients_total"), 0.0))
            if focus_clients_tfl <= 0:
                focus_clients_tfl = int(_safe_float(payload.get("focus_clients_tfl"), 0.0))
            if focus_clients_total > 0:
                client_scope = "focus"
        elif focus_type == "general":
            focus_clients_total = int(_safe_float(payload.get("focus_clients_total"), 0.0))
            focus_clients_tfl = int(_safe_float(payload.get("focus_clients_tfl"), 0.0))
            if focus_clients_total > 0:
                client_scope = "focus"
            else:
                focus_clients_total = int(_safe_float(payload.get("unique_clients_total"), 0.0))
                focus_clients_tfl = int(_safe_float(payload.get("unique_clients_tfl"), 0.0))
                if focus_clients_total > 0:
                    client_scope = "scope"

        if focus_clients_total > 0 and focus_clients_tfl > focus_clients_total:
            focus_clients_tfl = focus_clients_total
        if focus_clients_total > 0 and client_scope == "focus":
            focus_specific_signals += 1

        add_client_mix = focus_type in {"lobbyist", "general"}
        if add_client_mix and focus_clients_total > 0:
            signals_used += 1
            client_share_tfl = focus_clients_tfl / focus_clients_total
            prefix = "Across the selected scope, " if client_scope == "scope" else ""
            client_base_noun = "clients in the selected scope" if client_scope == "scope" else "associated clients"
            if client_share_tfl >= 0.60:
                parts.append(
                    f"{prefix}taxpayer-funded entities represent {focus_clients_tfl:,} of {focus_clients_total:,} {client_base_noun} "
                    f"({client_share_tfl:.0%}), indicating a strongly public-sector weighted client base."
                )
            elif client_share_tfl >= 0.30:
                parts.append(
                    f"{prefix}taxpayer-funded entities represent {focus_clients_tfl:,} of {focus_clients_total:,} {client_base_noun} "
                    f"({client_share_tfl:.0%}), indicating mixed but meaningful institutional exposure."
                )
            elif client_share_tfl > 0:
                parts.append(
                    f"{prefix}taxpayer-funded clients are present ({focus_clients_tfl:,} of {focus_clients_total:,} {client_base_noun}) but remain a minority share."
                )
            else:
                parts.append(f"{prefix}no taxpayer-funded clients are visible in the current client set.")

        if focus_type == "client":
            lobbyists_count = _metric_int("lobbyists")
            if lobbyists_count > 0:
                signals_used += 1
                focus_specific_signals += 1
                if lobbyists_count >= 10:
                    parts.append(f"This client is connected to {lobbyists_count:,} lobbyists, indicating broad representation capacity.")
                elif lobbyists_count >= 4:
                    parts.append(f"This client is connected to {lobbyists_count:,} lobbyists, suggesting meaningful representation depth.")
                else:
                    parts.append(f"This client is connected to {lobbyists_count:,} lobbyists in the current scope.")
            tfl_flag = _metric_value("taxpayer funded")
            if tfl_flag:
                signals_used += 1
                focus_specific_signals += 1
                normalized_flag = tfl_flag.strip().lower()
                if normalized_flag in {"yes", "true", "1"}:
                    parts.append("The client is classified as taxpayer-funded in the underlying records.")
                elif normalized_flag in {"no", "false", "0"}:
                    parts.append("The client is not classified as taxpayer-funded in the underlying records.")

        if focus_type == "lobbyist":
            lobby_total_clients = _metric_int("total clients")
            lobby_tfl_clients = _metric_int("taxpayer-funded clients", "taxpayer funded clients")
            if lobby_total_clients > 0:
                signals_used += 1
                focus_specific_signals += 1
                if lobby_tfl_clients > lobby_total_clients:
                    lobby_tfl_clients = lobby_total_clients
                share = (lobby_tfl_clients / lobby_total_clients) if lobby_total_clients > 0 else 0.0
                if share >= 0.60:
                    parts.append(
                        f"At the focus level, this lobbyist's client book is majority taxpayer-funded ({lobby_tfl_clients:,} of {lobby_total_clients:,})."
                    )
                elif share >= 0.30:
                    parts.append(
                        f"At the focus level, taxpayer-funded clients account for {lobby_tfl_clients:,} of {lobby_total_clients:,}, indicating a mixed portfolio."
                    )
                else:
                    parts.append(
                        f"At the focus level, taxpayer-funded clients account for {lobby_tfl_clients:,} of {lobby_total_clients:,}, with private clients dominant."
                    )

        if focus_type == "legislator":
            bills_authored = _metric_int("bills authored")
            bills_opposed_tfl = _metric_int("bills opposed by tfl lobbyists", "tfl lobbyists opposed")
            if bills_authored > 0:
                signals_used += 1
                focus_specific_signals += 1
                if bills_opposed_tfl > bills_authored:
                    bills_opposed_tfl = bills_authored
                if bills_opposed_tfl > 0:
                    oppose_share = bills_opposed_tfl / bills_authored
                    if oppose_share >= 0.50:
                        parts.append(
                            f"A substantial share of authored bills ({bills_opposed_tfl:,} of {bills_authored:,}) drew taxpayer-funded opposition."
                        )
                    elif oppose_share >= 0.25:
                        parts.append(
                            f"A meaningful share of authored bills ({bills_opposed_tfl:,} of {bills_authored:,}) drew taxpayer-funded opposition."
                        )
                    else:
                        parts.append(
                            f"Only a smaller share of authored bills ({bills_opposed_tfl:,} of {bills_authored:,}) drew taxpayer-funded opposition."
                        )
                else:
                    parts.append(f"No authored bills are shown as opposed by taxpayer-funded lobbyists out of {bills_authored:,} authored bills.")

        if focus_type == "bill":
            witness_rows = _metric_int("witness rows")
            tfl_witness = _metric_int("tfl lobbyists (any position)")
            private_witness = _metric_int("private lobbyists (any position)")
            if witness_rows > 0:
                signals_used += 1
                focus_specific_signals += 1
                if witness_rows >= 50:
                    parts.append(f"Witness-list volume is high for this bill ({witness_rows:,} rows), indicating elevated engagement intensity.")
                elif witness_rows >= 20:
                    parts.append(f"Witness-list volume is moderate for this bill ({witness_rows:,} rows).")
                else:
                    parts.append(f"Witness-list volume is limited for this bill ({witness_rows:,} rows).")
            if (tfl_witness + private_witness) > 0:
                signals_used += 1
                focus_specific_signals += 1
                total_w = tfl_witness + private_witness
                tfl_share = tfl_witness / total_w if total_w > 0 else 0.0
                if tfl_share >= 0.60:
                    parts.append(
                        f"Taxpayer-funded participation dominates witness representation ({tfl_witness:,} of {total_w:,} lobbyists recorded by funding class)."
                    )
                elif tfl_share >= 0.40:
                    parts.append(
                        f"Taxpayer-funded and private witness representation are comparatively balanced ({tfl_witness:,} vs {private_witness:,})."
                    )
                else:
                    parts.append(
                        f"Private witness representation exceeds taxpayer-funded participation ({private_witness:,} vs {tfl_witness:,})."
                    )

        focus_tfl_range_value = _metric_value("taxpayer-funded range", "taxpayer funded range")
        focus_private_range_value = _metric_value("private range")
        has_focus_comp_ranges = bool(focus_tfl_range_value or focus_private_range_value)
        tfl_mid = _range_midpoint(focus_tfl_range_value)
        pri_mid = _range_midpoint(focus_private_range_value)
        if has_focus_comp_ranges:
            focus_specific_signals += 1
        if (tfl_mid + pri_mid) <= 0:
            tfl_low = max(_safe_float(payload.get("tfl_low_value"), 0.0), 0.0)
            tfl_high = max(_safe_float(payload.get("tfl_high_value"), 0.0), 0.0)
            pri_low = max(_safe_float(payload.get("private_low_value"), 0.0), 0.0)
            pri_high = max(_safe_float(payload.get("private_high_value"), 0.0), 0.0)
            tfl_mid = (tfl_low + tfl_high) / 2.0 if (tfl_low > 0 or tfl_high > 0) else 0.0
            pri_mid = (pri_low + pri_high) / 2.0 if (pri_low > 0 or pri_high > 0) else 0.0

        funding_mid_total = tfl_mid + pri_mid
        if funding_mid_total > 0:
            signals_used += 1
            funding_delta = tfl_mid - pri_mid
            comp_scope = "within this focus" if has_focus_comp_ranges else "across the selected scope"
            if abs(funding_delta) <= (0.10 * funding_mid_total):
                parts.append(
                    f"Midpoint compensation estimates indicate near parity between taxpayer-funded and private financing {comp_scope}."
                )
            elif funding_delta > 0:
                parts.append(
                    f"Midpoint compensation estimates indicate taxpayer-funded financing exceeds private financing {comp_scope}."
                )
            else:
                parts.append(
                    f"Midpoint compensation estimates indicate private financing exceeds taxpayer-funded financing {comp_scope}."
                )

        tfl_against = 0
        tfl_for = 0
        tfl_on = 0
        witness_scope = "scope"
        for bullet in _safe_list(focus_section_local.get("bullets")):
            bullet_txt = _safe_str(bullet)
            if "witness positions" not in bullet_txt.lower():
                continue
            parsed_against = _first_int_after_keyword(bullet_txt, "Against")
            parsed_for = _first_int_after_keyword(bullet_txt, "For")
            parsed_on = _first_int_after_keyword(bullet_txt, "On")
            if parsed_against is not None:
                tfl_against = parsed_against
            if parsed_for is not None:
                tfl_for = parsed_for
            if parsed_on is not None:
                tfl_on = parsed_on
            witness_scope = "focus"
            focus_specific_signals += 1
            break
        if (tfl_against + tfl_for + tfl_on) <= 0:
            tfl_bucket = _safe_dict(_safe_dict(payload.get("witness_counts", {})).get("tfl", {}))
            tfl_against = int(_safe_float(tfl_bucket.get("Against"), 0.0))
            tfl_for = int(_safe_float(tfl_bucket.get("For"), 0.0))
            tfl_on = int(_safe_float(tfl_bucket.get("On"), 0.0))

        witness_total = tfl_against + tfl_for + tfl_on
        if witness_total > 0:
            signals_used += 1
            witness_prefix = "Across the selected scope, " if witness_scope == "scope" else "At the focus level, "
            if tfl_against > max(tfl_for, tfl_on):
                parts.append(
                    f"{witness_prefix}witness posture skews toward opposition ({tfl_against:,} Against vs {tfl_for:,} For)."
                )
            elif tfl_for > max(tfl_against, tfl_on):
                parts.append(
                    f"{witness_prefix}witness posture skews toward support ({tfl_for:,} For vs {tfl_against:,} Against)."
                )
            else:
                parts.append(
                    f"{witness_prefix}witness posture is mixed ({tfl_against:,} Against, {tfl_for:,} For, {tfl_on:,} On)."
                )

        bill_signal_count = _metric_int("bills opposed by tfl lobbyists", "tfl lobbyists opposed")
        if bill_signal_count > 0 and focus_type != "legislator":
            signals_used += 1
            focus_specific_signals += 1
            if bill_signal_count >= 10:
                parts.append(
                    "Focus-level opposition intensity is high, with double-digit taxpayer-funded opposition tied to at least one measure."
                )
            elif bill_signal_count >= 5:
                parts.append("Focus-level opposition intensity is moderate across selected measures.")
            else:
                parts.append("Focus-level opposition is present but not concentrated at high volume.")
        elif bill_signal_count <= 0:
            top_bill_counts = [
                int(_safe_float(_safe_dict(bill).get("tfl"), 0.0))
                for bill in _safe_list(payload.get("top_bills"))
                if int(_safe_float(_safe_dict(bill).get("tfl"), 0.0)) > 0
            ]
            total_top_bill = sum(top_bill_counts)
            top_bill_opp = max(top_bill_counts) if top_bill_counts else 0
            top_bill_share = (top_bill_opp / total_top_bill) if total_top_bill > 0 else 0.0
            if top_bill_opp > 0:
                signals_used += 1
                if top_bill_opp >= 10 or top_bill_share >= 0.45:
                    parts.append("Scope-level bill data indicates concentrated opposition around a narrow set of proposals.")
                elif top_bill_opp >= 5 or top_bill_share >= 0.30:
                    parts.append("Scope-level bill data indicates moderate concentration in opposition activity.")
                else:
                    parts.append("Scope-level bill data indicates opposition activity is relatively diffuse.")

        if focus_specific_signals >= 3:
            parts.append(
                "Taken together, focus-specific signals indicate a clear and internally consistent advocacy profile within the broader taxpayer-funded lobbying landscape."
            )
        elif signals_used >= 3:
            parts.append(
                "Taken together, the available indicators provide a coherent directional profile for this focus, though portions of the profile rely on scope-level context."
            )
        else:
            parts.append(
                "Available focus-specific indicators are limited, but the observable record still places this focus within the broader taxpayer-funded lobbying landscape."
            )

        clean_parts = [_sentence_case(p.rstrip(".")) + "." for p in parts if _safe_str(p).strip()]
        return " ".join(clean_parts)

    if not _safe_str(payload.get("focus_snapshot_paragraph")).strip():
        payload["focus_snapshot_paragraph"] = _derive_focus_snapshot_paragraph()

    def _derive_section_conditionals() -> dict[str, str]:
        out = {
            "scale": "",
            "activity": "",
            "bills": "",
            "subjects": "",
            "conclusion": "",
        }

        total_clients = int(_safe_float(payload.get("unique_clients_total"), 0.0))
        tfl_clients = int(_safe_float(payload.get("unique_clients_tfl"), 0.0))
        if total_clients > 0:
            tfl_client_share = (tfl_clients / total_clients) * 100.0
            if tfl_client_share >= 50:
                out["scale"] = (
                    "Taxpayer-funded entities make up a majority of unique clients in this scope, indicating broad institutional participation in lobbying activity."
                )
            elif tfl_client_share >= 30:
                out["scale"] = (
                    "Taxpayer-funded entities represent a substantial minority of unique clients in this scope, indicating durable institutional presence in lobbying activity."
                )
            elif tfl_client_share > 0:
                out["scale"] = (
                    "Taxpayer-funded entities represent a smaller but observable share of unique clients in this scope."
                )

        tfl_counts = _safe_dict(payload.get("witness_counts", {})).get("tfl", {})
        pri_counts = _safe_dict(payload.get("witness_counts", {})).get("private", {})
        tfl_against = int(_safe_float(_safe_dict(tfl_counts).get("Against"), 0.0))
        tfl_for = int(_safe_float(_safe_dict(tfl_counts).get("For"), 0.0))
        pri_against = int(_safe_float(_safe_dict(pri_counts).get("Against"), 0.0))
        pri_for = int(_safe_float(_safe_dict(pri_counts).get("For"), 0.0))
        if (tfl_against + tfl_for + pri_against + pri_for) > 0:
            if tfl_against > tfl_for and pri_against > pri_for:
                out["activity"] = (
                    "Both taxpayer-funded and private interests show a net-opposition profile in witness testimony for this scope."
                )
            elif tfl_against > tfl_for and not (pri_against > pri_for):
                out["activity"] = (
                    "Taxpayer-funded witness activity leans more opposition-oriented than private witness activity in this scope."
                )
            elif tfl_for > tfl_against:
                out["activity"] = (
                    "Taxpayer-funded witness activity includes a stronger support component than opposition in this scope."
                )

        top_bills = _safe_list(payload.get("top_bills"))
        if top_bills:
            bill_counts = [int(_safe_float(_safe_dict(row).get("tfl"), 0.0)) for row in top_bills]
            total_bill_opp = sum(bill_counts)
            top_bill_opp = max(bill_counts) if bill_counts else 0
            if total_bill_opp > 0 and top_bill_opp > 0:
                concentration = (top_bill_opp / total_bill_opp) * 100.0
                if concentration >= 40:
                    out["bills"] = (
                        "Opposition is relatively concentrated in the top-ranked bill, suggesting focused taxpayer-funded advocacy around a narrow set of proposals."
                    )
                else:
                    out["bills"] = (
                        "Opposition is distributed across multiple high-priority bills rather than concentrated in a single proposal."
                    )

        top_subjects = _safe_list(payload.get("top_subjects"))
        if top_subjects:
            subject_counts = [
                int(_safe_float(_safe_dict(row).get("Oppositions"), 0.0))
                for row in top_subjects
            ]
            total_subject_opp = sum(subject_counts)
            top_subject_opp = max(subject_counts) if subject_counts else 0
            if total_subject_opp > 0 and top_subject_opp > 0:
                concentration = (top_subject_opp / total_subject_opp) * 100.0
                if concentration >= 45:
                    out["subjects"] = (
                        "Policy-area opposition is concentrated in a leading subject, indicating a tighter taxpayer-funded advocacy focus."
                    )
                else:
                    out["subjects"] = (
                        "Policy-area opposition is spread across several subjects, indicating broader taxpayer-funded issue engagement."
                    )

        tfl_mid_share = _safe_float(payload.get("tfl_mid_share_pct_value"), 0.0)
        if tfl_mid_share >= 50:
            out["conclusion"] = (
                "At midpoint estimates, taxpayer-funded activity constitutes a majority share of reported lobbying compensation in this scope."
            )
        elif tfl_mid_share >= 35:
            out["conclusion"] = (
                "At midpoint estimates, taxpayer-funded activity constitutes a substantial share of reported lobbying compensation in this scope."
            )
        elif tfl_mid_share > 0:
            out["conclusion"] = (
                "At midpoint estimates, taxpayer-funded activity remains an identifiable share of reported lobbying compensation in this scope."
            )
        return out

    section_conditionals = _derive_section_conditionals()

    class ReportPDF(FPDF):
        def __init__(self, header_title: str, header_subtitle: str, generated_date: str):
            super().__init__(orientation="P", unit="mm", format="A4")
            self.header_title = header_title
            self.header_subtitle = header_subtitle
            self.generated_date = generated_date

        def header(self):
            if self.page_no() == 1:
                return
            self.set_y(7.2)
            self.set_text_color(*PDF_COLOR_NAVY_DARK)
            self.set_font(PDF_FONT_SANS, "B", 7.6)
            width = self.w - self.l_margin - self.r_margin
            left_w = width * 0.78
            right_w = width - left_w
            self.cell(left_w, 4.3, _pdf_safe_text(self.header_title), new_x=XPos.RIGHT, new_y=YPos.TOP, align="L")
            self.set_font(PDF_FONT_SANS, "", 6.8)
            self.set_text_color(*PDF_COLOR_MUTED)
            self.cell(right_w, 4.3, _pdf_safe_text("Policy Brief"), new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="R")
            self.set_x(self.l_margin)
            subtitle = str(self.header_subtitle or "")
            if len(subtitle) > 90:
                subtitle = subtitle[:87].rstrip() + "..."
            self.set_font(PDF_FONT_SANS, "", 6.5)
            self.set_text_color(*PDF_COLOR_MUTED)
            self.cell(0, 3.2, _pdf_safe_text(subtitle), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_draw_color(*PDF_COLOR_BORDER)
            self.line(self.l_margin, self.get_y() + 0.4, self.w - self.r_margin, self.get_y() + 0.4)
            self.ln(1.8)
            self.set_text_color(*PDF_COLOR_TEXT)

        def footer(self):
            self.set_y(-12)
            self.set_text_color(*PDF_COLOR_MUTED)
            self.set_font(PDF_FONT_SANS, "", PDF_FOOTNOTE_SIZE)
            w = self.w - self.l_margin - self.r_margin
            self.set_draw_color(*PDF_COLOR_BORDER)
            self.line(self.l_margin, self.get_y() - 1.2, self.w - self.r_margin, self.get_y() - 1.2)
            left_w = w * 0.68
            right_w = w - left_w
            self.cell(left_w, 4, _pdf_safe_text(f"Generated {self.generated_date}"), new_x=XPos.RIGHT, new_y=YPos.TOP, align="L")
            self.set_font(PDF_FONT_SANS, "B", PDF_FOOTNOTE_SIZE)
            self.set_text_color(*PDF_COLOR_NAVY)
            self.cell(right_w, 4, _pdf_safe_text(f"Page {self.page_no()}"), new_x=XPos.RIGHT, new_y=YPos.TOP, align="R")
            self.set_text_color(*PDF_COLOR_TEXT)

    header_title = payload.get("report_title", "Lobby Look-Up Report")
    scope_sub = payload.get("scope_session_label") or payload.get("scope_label", "")
    header_subtitle = f"{scope_sub} | {payload['focus_label']}".strip(" |")
    pdf = ReportPDF(header_title, header_subtitle, payload["generated_date"])
    pdf.set_margins(12, 20, 12)
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.set_title(_pdf_safe_text(header_title))
    pdf.set_author(_pdf_safe_text("Lobby Look-Up"))
    pdf.add_page()
    _pdf_add_cover_page(pdf, payload)
    _pdf_add_contents_page(
        pdf,
        payload,
        include_focus_snapshot=bool(payload.get("focus_section") and isinstance(payload.get("focus_section"), dict)),
    )
    pdf.add_page()
    setattr(pdf, "_figure_counter", 0)

    y0 = pdf.get_y()
    pdf.set_fill_color(*PDF_COLOR_NAVY_DARK)
    pdf.rect(pdf.l_margin, y0, pdf.w - pdf.l_margin - pdf.r_margin, 1.8, "F")
    pdf.ln(2.6)

    _pdf_add_heading(pdf, "TAXPAYER-FUNDED LOBBYING IN TEXAS", size=17)
    _pdf_add_subheading(
        pdf,
        f"Analysis of the {payload['session_label']} Legislative Session",
        size=12,
    )
    pdf.set_font(PDF_FONT_SANS, "", PDF_BODY_SIZE - 0.3)
    pdf.set_text_color(*PDF_COLOR_TEXT)
    pdf.cell(0, 4.8, _pdf_safe_text("Prepared by Texas Taxpayer Lobbying Transparency Center"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 4.8, _pdf_safe_text(f"Generated: {payload['generated_date']}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 4.8, _pdf_safe_text(f"Scope: {payload['scope_session_label']}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 4.8, _pdf_safe_text(f"Focus: {payload['focus_label']}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1.2)
    _pdf_add_rule(pdf)

    _pdf_add_section_title(pdf, "Executive Summary")
    exec_summary = (
        "Texas taxpayers should not be compelled to finance political advocacy through their own government. "
        f"During the {payload['session_label']} Legislative Session, registered lobbying activity reported "
        f"compensation ranges totaling between {payload['total_low']} and {payload['total_high']}. Within that total, "
        f"taxpayer-funded lobbying activity accounted for approximately {payload['tfl_low']} to {payload['tfl_high']}, "
        f"while privately funded lobbying accounted for approximately {payload['private_low']} to {payload['private_high']}. "
        f"Even under conservative assumptions, taxpayer-funded lobbying represented roughly {payload['tfl_share_low_pct']}% "
        f"to {payload['tfl_share_high_pct']}% of all reported lobbying compensation during this scope."
    )
    _pdf_add_paragraph(pdf, exec_summary, size=11)
    if payload.get("scope_note"):
        _pdf_add_paragraph(pdf, payload["scope_note"], size=10)
    exec_summary_2 = (
        "This report explains why taxpayer-funded lobbying is structurally inconsistent with transparent and "
        "accountable government, documents the scale of the practice in "
        f"{payload['session_label']}, and identifies the legislation and policy areas most frequently opposed by "
        "taxpayer-funded lobbyists. The conclusion is straightforward: Texas should abolish taxpayer-funded lobbying "
        "by political subdivisions and close both direct and indirect funding pathways so public money is used to provide "
        "public services, not to finance political advocacy."
    )
    _pdf_add_paragraph(pdf, exec_summary_2, size=11)
    exec_conditional = [
        str(s).strip() for s in payload.get("conditional_exec_sentences", []) if str(s).strip()
    ]
    if exec_conditional:
        _pdf_add_callout_box(pdf, "Data-Driven Context", exec_conditional[0])
        if len(exec_conditional) > 1:
            _pdf_add_bullets(pdf, exec_conditional[1:], size=9.8, line_h=4.8)

    _pdf_add_subheading(pdf, "Key Metrics", size=11)
    metrics = [
        ("Total lobbying range", f"{payload['total_low']} - {payload['total_high']}"),
        ("Taxpayer-funded range", f"{payload['tfl_low']} - {payload['tfl_high']}"),
        ("Private range", f"{payload['private_low']} - {payload['private_high']}"),
        ("Unique lobbyists", payload["unique_lobbyists_total"]),
        ("Lobbyists w/ TFL clients", payload["unique_lobbyists_tfl"]),
        ("Unique clients", payload["unique_clients_total"]),
        ("Taxpayer-funded clients", payload["unique_clients_tfl"]),
    ]
    _pdf_add_kpi_table(pdf, metrics, size=10)

    highlights = [
        f"Taxpayer-funded share: {payload['tfl_share_low_pct']}% - {payload['tfl_share_high_pct']}%",
        f"Taxpayer-funded range: {payload['tfl_low']} - {payload['tfl_high']}",
        f"Private range: {payload['private_low']} - {payload['private_high']}",
    ]
    _pdf_add_subheading(pdf, "Report Highlights", size=10)
    _pdf_add_bullets(pdf, highlights, size=10)
    _pdf_add_callout_box(
        pdf,
        "Key Claim: Taxpayer-Funded Share Range",
        (
            f"Even under conservative assumptions, taxpayer-funded lobbying represented "
            f"{payload['tfl_share_low_pct']}% to {payload['tfl_share_high_pct']}% of all reported "
            "lobbying compensation in this scope."
        ),
    )

    focus_section = payload.get("focus_section")
    if focus_section and isinstance(focus_section, dict):
        title = focus_section.get("title", "").strip()
        summary = focus_section.get("summary", "").strip()
        metrics = focus_section.get("metrics", [])
        bullets = focus_section.get("bullets", [])
        charts = focus_section.get("charts", [])

        if title or summary or metrics or bullets or charts:
            _pdf_add_section_title(pdf, "Focus Snapshot")
            if title:
                _pdf_add_subheading(pdf, title, size=11)
            if summary:
                _pdf_add_paragraph(pdf, summary, size=11)
            focus_dynamic_sentence = str(payload.get("conditional_focus_sentence", "")).strip()
            if focus_dynamic_sentence:
                _pdf_add_callout_box(
                    pdf,
                    "Focus Lens",
                    focus_dynamic_sentence,
                    accent=(34, 96, 74),
                )
            focus_snapshot_paragraph = _safe_str(payload.get("focus_snapshot_paragraph", "")).strip()
            if focus_snapshot_paragraph:
                _pdf_add_paragraph(pdf, focus_snapshot_paragraph, size=10.8, line_h=5.2)
            if bullets:
                _pdf_add_subheading(pdf, "Focus Highlights", size=10)
                _pdf_add_paragraph(
                    pdf,
                    str(payload.get("focus_highlights_intro", "Most relevant findings for the selected focus.")),
                    size=9.8,
                    line_h=5.0,
                )
                _pdf_add_focus_highlights(pdf, bullets, size=10)
            if charts:
                _pdf_add_subheading(pdf, "Focus Charts", size=10)
                for chart in charts:
                    fig = _build_focus_chart(chart if isinstance(chart, dict) else {})
                    if fig:
                        caption = str(chart.get("caption", "Focus Chart")).strip() if isinstance(chart, dict) else "Focus Chart"
                        _pdf_add_chart(pdf, fig, caption)
            _pdf_add_rule(pdf)

    _pdf_add_numbered_section_title(pdf, 1, f"THE SCALE OF LOBBYING IN {payload['session_label']}")
    scale_p1 = (
        "Lobbying in Texas is a major industry, and the compensation ranges reported to the state reflect the scale "
        "at which public policy is contested. For the "
        f"{payload['session_label']} session, the total reported lobbying compensation range across the selected scope "
        f"was {payload['total_low']} to {payload['total_high']}. Taxpayer-funded entities accounted for "
        f"{payload['tfl_low']} to {payload['tfl_high']} of that total, while privately funded entities accounted for "
        f"{payload['private_low']} to {payload['private_high']}. Because compensation is disclosed in ranges rather than "
        "precise amounts, these figures should be understood as conservative estimates of the activity captured in "
        "the underlying registrations and filings."
    )
    _pdf_add_paragraph(pdf, scale_p1, size=11)
    scale_p2 = (
        "The composition of the participating universe underscores why taxpayer-funded lobbying is not a marginal "
        "phenomenon. Across this scope, "
        f"{payload['unique_lobbyists_total']} unique lobbyists were observed, including {payload['unique_lobbyists_tfl']} "
        "who represented at least one taxpayer-funded client. Likewise, "
        f"{payload['unique_clients_total']} clients appeared in the data, including {payload['unique_clients_tfl']} that "
        "qualify as governmental or taxpayer-funded entities. The point is not merely that local governments participate "
        "in the process; it is that they do so at a scale capable of shaping agendas, crowding out citizen influence, "
        "and resisting reforms that would otherwise be evaluated on their merits."
    )
    _pdf_add_paragraph(pdf, scale_p2, size=11)
    if _safe_str(section_conditionals.get("scale")).strip():
        _pdf_add_paragraph(pdf, section_conditionals["scale"], size=10.5)

    comp_df = pd.DataFrame(
        [
            {"Funding": "Taxpayer Funded", "Low": payload["tfl_low_value"], "High": payload["tfl_high_value"]},
            {"Funding": "Private", "Low": payload["private_low_value"], "High": payload["private_high_value"]},
        ]
    )
    comp_long = comp_df.melt(id_vars="Funding", value_vars=["Low", "High"], var_name="Estimate", value_name="Total")
    if not comp_long.empty and comp_long["Total"].sum() > 0:
        fig_comp = px.bar(
            comp_long,
            x="Funding",
            y="Total",
            color="Estimate",
            barmode="group",
            text="Total",
            color_discrete_map={"Low": "#004c6d", "High": "#1f77b4"},
        )
        fig_comp.update_traces(texttemplate="$%{text:,.0f}", textposition="outside", cliponaxis=False)
        fig_comp.update_layout(
            template="plotly_white",
            title="Lobbying Compensation Range by Funding Type",
            yaxis_title="Reported compensation",
            xaxis_title="",
            legend_title="Estimate",
            margin=dict(l=40, r=20, t=50, b=30),
        )
        fig_comp.update_yaxes(tickprefix="$", tickformat="~s")
        _pdf_add_chart(pdf, fig_comp, "Chart 1. Lobbying Compensation Range by Funding Type")

    tfl_mid = (payload["tfl_low_value"] + payload["tfl_high_value"]) / 2
    pri_mid = (payload["private_low_value"] + payload["private_high_value"]) / 2
    if (tfl_mid + pri_mid) > 0:
        share_df = pd.DataFrame(
            {"Funding": ["Taxpayer Funded", "Private"], "Total": [tfl_mid, pri_mid]}
        )
        fig_share = px.pie(
            share_df,
            names="Funding",
            values="Total",
            hole=0.5,
            color="Funding",
            color_discrete_map={"Taxpayer Funded": "#0ea5a4", "Private": "#4c78a8"},
        )
        fig_share.update_layout(
            template="plotly_white",
            title="Share of Total Lobbying (Midpoint)",
            margin=dict(l=20, r=20, t=50, b=20),
        )
        _pdf_add_chart(pdf, fig_share, "Chart 2. Share of Total Lobbying - Taxpayer vs Private", width_px=700, height_px=420)

    _pdf_add_numbered_section_title(pdf, 2, "WHAT TAXPAYER-FUNDED LOBBYING IS - AND WHY IT MATTERS")
    def_p1 = (
        "Taxpayer-funded lobbying occurs when political subdivisions use public funds to employ registered lobbyists, "
        "contract with lobbying firms, or pay dues and assessments to associations that, in turn, employ lobbyists. "
        "In practice, the entities involved often include cities, counties, independent school districts, special "
        "districts, authorities, and intergovernmental associations funded by member governments. The distinctive "
        "feature is not the subject matter they address -- nearly any policy can be lobbied -- but the source of the "
        "money used to do it. When advocacy is financed with tax revenue or statutorily compelled fees, citizens are "
        "required to fund political activity as a condition of living, owning property, or receiving basic public services."
    )
    _pdf_add_paragraph(pdf, def_p1, size=11)
    def_p2 = (
        "That is why taxpayer-funded lobbying is a different category of problem than private-sector lobbying. "
        "Private entities spend their own money and must persuade contributors, shareholders, or members that the "
        "advocacy is worthwhile. Public entities spend money that was collected under compulsion and therefore operate "
        "without meaningful donor consent. This creates an unavoidable mismatch between who pays and who benefits. "
        "It also creates a confidence problem: citizens reasonably conclude that government is using their money to "
        "entrench itself, grow its authority, and resist reforms -- especially reforms aimed at fiscal restraint, "
        "regulatory limits, or transparency."
    )
    _pdf_add_paragraph(pdf, def_p2, size=11)

    entity_counts = payload.get("chart_entity_types_data", [])
    if entity_counts:
        entity_df = pd.DataFrame(entity_counts)
        fig_entities = px.bar(
            entity_df.sort_values("count"),
            x="count",
            y="type",
            orientation="h",
            text="count",
            color_discrete_sequence=["#4c78a8"],
        )
        fig_entities.update_traces(textposition="outside", cliponaxis=False)
        fig_entities.update_layout(
            template="plotly_white",
            title="Taxpayer-Funded Clients by Entity Type",
            xaxis_title="Clients",
            yaxis_title="",
            margin=dict(l=40, r=20, t=50, b=30),
        )
        _pdf_add_chart(pdf, fig_entities, "Chart 3. Taxpayer-Funded Clients by Entity Type")

    _pdf_add_numbered_section_title(pdf, 3, f"LEGISLATIVE ACTIVITY PATTERNS IN {payload['session_label']}")
    act_p1 = (
        "Compensation totals explain scale, but legislative activity signals show how that scale is used. "
        f"Across the {payload['session_label']} session, taxpayer-funded lobbyists appeared repeatedly in committee "
        "processes, filing and testifying in ways that illustrate institutional priorities. The witness-list record "
        "indicates that taxpayer-funded entities did not simply monitor legislation; they frequently intervened in it "
        "-- especially on proposals with direct implications for local discretion, budgets, and oversight."
    )
    _pdf_add_paragraph(pdf, act_p1, size=11)
    act_p2 = (
        "Within this scope, witness positions for taxpayer-funded and privately funded interests can be summarized as follows: "
        f"{payload['witness_activity_summary']} The distribution of positions matters because it is a proxy for the "
        "incentives embedded in taxpayer-funded lobbying."
    )
    _pdf_add_paragraph(pdf, act_p2, size=11)
    if _safe_str(section_conditionals.get("activity")).strip():
        _pdf_add_paragraph(pdf, section_conditionals["activity"], size=10.5)

    w_counts = payload.get("witness_counts", {})
    if w_counts:
        w_rows = []
        for position in ["Against", "For", "On"]:
            w_rows.append(
                {
                    "Position": position,
                    "Taxpayer Funded": int(w_counts.get("tfl", {}).get(position, 0)),
                    "Private": int(w_counts.get("private", {}).get(position, 0)),
                }
            )
        w_df = pd.DataFrame(w_rows)
        if not w_df.empty and w_df[["Taxpayer Funded", "Private"]].sum().sum() > 0:
            w_long = w_df.melt(id_vars="Position", var_name="Funding", value_name="Count")
            fig_wit = px.bar(
                w_long,
                x="Position",
                y="Count",
                color="Funding",
                barmode="group",
                text="Count",
                color_discrete_map={"Taxpayer Funded": "#ff6b6b", "Private": "#4c78a8"},
            )
            fig_wit.update_traces(textposition="outside", cliponaxis=False)
            fig_wit.update_layout(
                template="plotly_white",
                title="Witness Positions by Funding Type",
                yaxis_title="Positions",
                xaxis_title="",
                margin=dict(l=40, r=20, t=50, b=30),
            )
            _pdf_add_chart(pdf, fig_wit, "Chart 4. Witness Positions by Funding Type")

    _pdf_add_numbered_section_title(pdf, 4, "THE BILLS MOST OPPOSED BY TAXPAYER-FUNDED LOBBYISTS")
    if payload.get("has_top_bills"):
        bills_p = (
            "The most direct way to see taxpayer-funded lobbying in action is to identify the bills that generated "
            "concentrated opposition from taxpayer-funded entities. The bills below are ranked by the number of "
            "Against filings by taxpayer-funded lobbyists."
        )
        _pdf_add_paragraph(pdf, bills_p, size=11)
        if _safe_str(section_conditionals.get("bills")).strip():
            _pdf_add_paragraph(pdf, section_conditionals["bills"], size=10.5)
        top_bills = payload.get("top_bills", [])
        if top_bills:
            bill_df = pd.DataFrame(
                [{"Bill": b["id"], "Oppositions": b.get("tfl", 0)} for b in top_bills]
            )
            fig_bills = px.bar(
                bill_df.sort_values("Oppositions"),
                x="Oppositions",
                y="Bill",
                orientation="h",
                text="Oppositions",
                color_discrete_sequence=["#d14b4b"],
            )
            fig_bills.update_traces(textposition="outside", cliponaxis=False)
            fig_bills.update_layout(
                template="plotly_white",
                title="Top Bills Opposed by Taxpayer-Funded Lobbyists",
                xaxis_title="Oppositions",
                yaxis_title="",
                margin=dict(l=40, r=20, t=50, b=30),
            )
            _pdf_add_chart(pdf, fig_bills, "Chart 5. Top 5 Bills Opposed by Taxpayer-Funded Lobbyists")
    else:
        _pdf_add_paragraph(pdf, "No bill-level opposition data was available for the selected scope/session.", size=11)

    _pdf_add_numbered_section_title(pdf, 5, "THE POLICY AREAS MOST OPPOSED BY TAXPAYER-FUNDED LOBBYISTS")
    if payload.get("has_top_subjects"):
        subject_p = (
            "Bills are discrete, but policy areas reveal patterns. When opposition is aggregated by subject matter, "
            "taxpayer-funded lobbying tends to cluster in the places where the Legislature can most directly alter "
            "local fiscal and regulatory authority."
        )
        _pdf_add_paragraph(pdf, subject_p, size=11)
        if _safe_str(section_conditionals.get("subjects")).strip():
            _pdf_add_paragraph(pdf, section_conditionals["subjects"], size=10.5)
        top_subjects = payload.get("top_subjects", [])
        if top_subjects:
            subj_df = pd.DataFrame(
                [{"Subject": s["Subject"], "Oppositions": s.get("Oppositions", 0)} for s in top_subjects]
            )
            fig_subjects = px.bar(
                subj_df.sort_values("Oppositions"),
                x="Oppositions",
                y="Subject",
                orientation="h",
                text="Oppositions",
                color_discrete_sequence=["#7aa6c2"],
            )
            fig_subjects.update_traces(textposition="outside", cliponaxis=False)
            fig_subjects.update_layout(
                template="plotly_white",
                title="Top Policy Areas Opposed by Taxpayer-Funded Lobbyists",
                xaxis_title="Oppositions",
                yaxis_title="",
                margin=dict(l=40, r=20, t=50, b=30),
            )
            _pdf_add_chart(pdf, fig_subjects, "Chart 6. Top 5 Policy Areas Opposed by Taxpayer-Funded Lobbyists")
    else:
        _pdf_add_paragraph(pdf, "No subject-level opposition data was available for the selected scope/session.", size=11)

    _pdf_add_numbered_section_title(pdf, 6, "STRUCTURAL INCENTIVES AND THE COMPULSION PROBLEM")
    _pdf_add_paragraph(
        pdf,
        "Taxpayer-funded lobbying persists because it is rational for institutions. Political subdivisions face "
        "budget pressures, political pressures, and administrative demands, and they naturally seek to preserve the "
        "widest possible discretion to manage those pressures. But rationality for institutions is not the same as "
        "legitimacy for taxpayers. When the money used to lobby is collected under compulsion, the normal disciplining "
        "forces of voluntary association are absent. The cost of advocacy is dispersed across taxpayers, while the "
        "perceived benefits -- expanded authority, preserved revenues, reduced oversight -- accrue to the institution.",
        size=11,
    )
    _pdf_add_paragraph(
        pdf,
        "The result is a misalignment: the payer is not the decision-maker, and the decision-maker has an incentive "
        "to externalize the cost. That is why taxpayer-funded lobbying is not merely politics as usual. It is a "
        "financing structure that undermines accountability and encourages institutional self-protection. Over time, "
        "it becomes a form of self-reinforcing governance: public entities use public funds to defend and expand the "
        "very powers that allow them to collect and deploy public funds.",
        size=11,
    )

    _pdf_add_numbered_section_title(pdf, 7, "LEGAL PARITY AND STATUTORY INCONSISTENCY")
    _pdf_add_paragraph(
        pdf,
        "Texas has already recognized that using public money to hire lobbyists raises concerns. State agencies face "
        "statutory restrictions that prevent them from employing registered lobbyists with public funds. Yet political "
        "subdivisions are not subject to uniform prohibitions, and the result is a parity failure. "
        f"{payload['existing_law_gap_summary']}",
        size=11,
    )
    _pdf_add_paragraph(
        pdf,
        "If the state has concluded that state agencies should not use taxpayer dollars to hire registered lobbyists, "
        "the same logic applies -- often more urgently -- to political subdivisions. Local entities are numerous, "
        "collectively spend vast sums, and frequently coordinate through associations that amplify their influence. "
        "In that environment, the absence of a clear prohibition invites continual expansion of the practice and "
        "continued erosion of public trust.",
        size=11,
    )

    _pdf_add_numbered_section_title(pdf, 8, "POLICY SOLUTION: A COMPREHENSIVE BAN ON TAXPAYER-FUNDED LOBBYING")
    _pdf_add_paragraph(
        pdf,
        "The policy principle is simple: public money should not be used to lobby government. A workable statutory "
        "approach is equally straightforward: Texas should extend the existing state-agency prohibition framework to "
        "political subdivisions and close indirect funding pathways that allow local governments to outsource lobbying "
        "through membership associations.",
        size=11,
    )
    _pdf_add_callout_box(
        pdf,
        "Key Claim: Recommended Statutory Reform",
        f"Recommended statutory reform: {payload['recommended_fix_statute']}",
    )
    _pdf_add_paragraph(
        pdf,
        f"A recommended statutory reform is: {payload['recommended_fix_statute']}. Under this approach, the law should "
        "prohibit political subdivisions from using public funds to employ registered lobbyists directly, contract with "
        "registered lobbyists, or pay membership dues or assessments to organizations that employ registered lobbyists "
        "for the purpose of influencing legislation. The ban must be drafted to address both direct payments and indirect "
        "routing of funds. Otherwise, enforcement will become a game of accounting rather than a real protection for taxpayers.",
        size=11,
    )
    _pdf_add_paragraph(
        pdf,
        "Implementation should include clear definitions of political subdivision, public funds, and lobbying "
        "services, and should make explicit that the prohibition applies regardless of whether the money is labeled "
        "appropriated, fee-based, enterprise, or interlocal. The Legislature should also specify enforceable remedies. "
        f"{payload['implementation_notes']}",
        size=11,
    )

    _pdf_add_numbered_section_title(pdf, 9, "DATA SOURCES AND METHODOLOGY")
    _pdf_add_paragraph(pdf, "This report is based on public information drawn from:", size=11)
    bullets = [
        b.strip().lstrip("- ").strip()
        for b in payload.get("data_sources_bullets", "").splitlines()
        if b.strip()
    ]
    _pdf_add_bullets(pdf, bullets, size=10)
    _pdf_add_paragraph(
        pdf,
        "Compensation figures reflect statutory reporting ranges filed with the Texas Ethics Commission. Totals were "
        "calculated by aggregating minimum and maximum disclosed ranges within the selected scope. Witness list activity "
        "reflects publicly available committee records compiled into the Lobby Look-Up dataset. Because compensation is "
        "reported in ranges rather than exact amounts, the totals presented here should be interpreted as conservative "
        "estimates rather than precise expenditures.",
        size=11,
    )

    _pdf_add_numbered_section_title(pdf, 10, "CONCLUSION")
    _pdf_add_paragraph(
        pdf,
        f"During the {payload['session_label']} Legislative Session, taxpayers indirectly financed lobbying activity "
        f"totaling between {payload['tfl_low']} and {payload['tfl_high']} in reported compensation ranges. This practice "
        "compels political financing, entrenches institutional self-interest, and undermines public confidence that "
        "government is operating transparently and accountably.",
        size=11,
    )
    _pdf_add_paragraph(
        pdf,
        "Texas should abolish taxpayer-funded lobbying by political subdivisions and close both direct and indirect "
        "funding pathways. Public money should be used to provide public services -- not to finance political advocacy.",
        size=11,
    )
    if _safe_str(section_conditionals.get("conclusion")).strip():
        _pdf_add_paragraph(pdf, section_conditionals["conclusion"], size=10.5)
    pdf.ln(2)
    pdf.set_font("Helvetica", "I", PDF_CAPTION_SIZE)
    pdf.cell(0, 5, _pdf_safe_text("Prepared by Texas Taxpayer Lobbying Transparency Center"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "I", PDF_FOOTNOTE_SIZE)
    pdf.cell(0, 5, _pdf_safe_text(payload["disclaimer_note"]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    output = pdf.output()
    return output if isinstance(output, (bytes, bytearray)) else output.encode("latin-1")

def _render_pdf_report_section(
    *,
    key_prefix: str,
    session_val: str | None,
    scope_label: str,
    focus_label: str,
    Lobby_TFL_Client_All: pd.DataFrame,
    Wit_All: pd.DataFrame,
    Bill_Status_All: pd.DataFrame,
    Bill_Sub_All: pd.DataFrame,
    tfl_session_val: str | None,
    focus_context: dict | None = None,
) -> None:
    """Render PDF report generation section in an expander."""
    with st.expander("Custom PDF report", expanded=False):
        st.caption("Generate a PDF report using the current filters and selections.")

        sig_key = f"{key_prefix}_report_sig"
        pdf_key = f"{key_prefix}_report_pdf"
        name_key = f"{key_prefix}_report_name"
        signature = f"{session_val}|{scope_label}|{focus_label}"

        if st.session_state.get(sig_key) != signature:
            st.session_state[sig_key] = signature
            if pdf_key in st.session_state:
                del st.session_state[pdf_key]
            if name_key in st.session_state:
                del st.session_state[name_key]

        generate_clicked = st.button(
            "Generate report",
            key=f"{key_prefix}_report_build",
            width="stretch",
            help="Build a PDF using the current filters and selections.",
        )

        if generate_clicked:
            _clear_pdf_chart_error()
            try:
                with st.status("Generating PDF...", expanded=False):
                    payload = _build_report_payload(
                        session_val=session_val,
                        scope_label=scope_label,
                        focus_label=focus_label,
                        Lobby_TFL_Client_All=Lobby_TFL_Client_All,
                        Wit_All=Wit_All,
                        Bill_Status_All=Bill_Status_All,
                        Bill_Sub_All=Bill_Sub_All,
                        tfl_session_val=tfl_session_val,
                        focus_context=focus_context,
                    )
                    pdf_bytes = _coerce_pdf_bytes(_build_report_pdf_bytes(payload))
                    if pdf_bytes and len(pdf_bytes) > 0:
                        st.session_state[pdf_key] = pdf_bytes
                        st.session_state[name_key] = f"tfl-report-{_slugify(focus_label)}.pdf"
                        st.success("Report generated")
            except Exception as e:
                st.error(f"Report generation failed: {str(e)}")

        if pdf_key in st.session_state and st.session_state.get(PDF_CHART_ERROR_KEY):
            st.warning(
                "PDF rendering encountered an issue (charts). "
                "Common cause: missing Kaleido for Plotly images."
            )
            st.caption(st.session_state[PDF_CHART_ERROR_KEY])

        if pdf_key in st.session_state and isinstance(st.session_state[pdf_key], bytes):
            st.download_button(
                "Download PDF",
                st.session_state[pdf_key],
                st.session_state.get(name_key, "report.pdf"),
                "application/pdf",
                key=f"{key_prefix}_dl",
                width="stretch",
            )

PLOTLY_CONFIG = {
    "displayModeBar": "hover",
    "responsive": True,
    "displaylogo": False,
    "modeBarButtonsToRemove": ["select2d", "lasso2d", "autoScale2d"],
    "modeBarButtonsToAdd": ["toggleSpikelines"],
    "toImageButtonOptions": {
        "format": "png",
        "filename": "tfl-chart-export",
        "height": 600,
        "width": 1000,
        "scale": 2,
    },
}
CHART_COLORS = [
    "#8caed3",
    "#6f92b9",
    "#5e7fa3",
    "#4f6f8e",
    "#4f8871",
    "#7d8fa6",
    "#8d7d96",
    "#7b6f86",
    "#a58a64",
    "#6d7682",
]
FUNDING_COLOR_MAP = {"Taxpayer Funded": "#8caed3", "Private": "#6d7682"}
OPPOSITION_COLOR_MAP = {"Opposed by TFL lobbyist": "#be7b7b", "Not opposed by TFL lobbyist": "#748bb0"}
TREND_COLOR_MAP = {"Low estimate": "#8d7d96", "High estimate": "#8caed3"}

def _session_base_number_series(s: pd.Series) -> pd.Series:
    base = s.fillna("").astype(str).str.strip().str.extract(r"^(\d+)", expand=False)
    base = base.where(base.str.len() <= 2, base.str[:-1])
    return pd.to_numeric(base, errors="coerce")

def _session_base_label(base_val: float | int) -> str:
    if pd.isna(base_val):
        return ""
    return _ordinal(int(base_val))

def _apply_plotly_layout(
    fig,
    *,
    height: int | None = None,
    showlegend: bool = False,
    legend_title: str | None = None,
    margin_top: int = 30,
):
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="IBM Plex Sans", color="rgba(235,245,255,0.92)", size=12),
        margin=dict(l=8, r=8, t=margin_top, b=8),
        showlegend=showlegend,
        legend_title_text=legend_title,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            font=dict(size=11, color="rgba(223,234,247,0.78)"),
        ),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor="rgba(16,27,41,0.96)",
            bordercolor="rgba(255,255,255,0.10)",
            font=dict(color="rgba(237,245,255,0.95)", size=12),
        ),
        transition=dict(duration=300, easing="cubic-in-out"),
    )
    if height:
        fig.update_layout(height=height)
    fig.update_xaxes(
        showgrid=False,
        zeroline=False,
        showline=False,
        ticks="outside",
        tickfont=dict(color="rgba(223,234,247,0.78)"),
        showspikes=True,
        spikecolor="rgba(134,167,198,0.3)",
        spikethickness=1,
        spikedash="dot",
        spikemode="across",
    )
    fig.update_yaxes(
        showgrid=False,
        zeroline=False,
        showline=False,
        ticks="outside",
        tickfont=dict(color="rgba(223,234,247,0.78)"),
        showspikes=True,
        spikecolor="rgba(134,167,198,0.3)",
        spikethickness=1,
        spikedash="dot",
        spikemode="across",
    )
    return fig

def _compact_ratio_bar(value: float, max_value: float, width: int = 10) -> str:
    try:
        v = float(value)
        max_v = float(max_value)
    except Exception:
        return "-" * max(1, int(width))
    if max_v <= 0:
        return "-" * max(1, int(width))
    span = max(1, int(width))
    ratio = max(0.0, min(1.0, v / max_v))
    filled = int(round(ratio * span))
    return ("#" * filled) + ("-" * max(0, span - filled))

def _priority_cell_style(value: str) -> str:
    label = str(value).strip()
    if label == "Tier 1":
        return "background-color: rgba(242,95,92,0.20); font-weight: 700;"
    if label == "Tier 2":
        return "background-color: rgba(247,178,103,0.20); font-weight: 600;"
    if label == "Tier 3":
        return "background-color: rgba(77,157,224,0.20);"
    return ""

def _safe_style(df: pd.DataFrame):
    try:
        return df.style
    except Exception:
        return None

def _numeric_heatmap_style_fn(
    series: pd.Series,
    *,
    rgb_lo: tuple[int, int, int],
    rgb_hi: tuple[int, int, int],
    alpha_lo: float = 0.06,
    alpha_hi: float = 0.34,
):
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().any():
        min_v = float(numeric.min())
        max_v = float(numeric.max())
    else:
        min_v = 0.0
        max_v = 0.0
    span = max(1e-9, max_v - min_v)

    def _style_one(value) -> str:
        try:
            v = float(value)
        except Exception:
            return ""
        ratio = (v - min_v) / span if span > 0 else 0.0
        ratio = max(0.0, min(1.0, ratio))
        r = int(round(rgb_lo[0] + (rgb_hi[0] - rgb_lo[0]) * ratio))
        g = int(round(rgb_lo[1] + (rgb_hi[1] - rgb_lo[1]) * ratio))
        b = int(round(rgb_lo[2] + (rgb_hi[2] - rgb_lo[2]) * ratio))
        a = alpha_lo + (alpha_hi - alpha_lo) * ratio
        return f"background-color: rgba({r},{g},{b},{a:.3f});"

    return _style_one

def _apply_numeric_heatmap(
    styler,
    df: pd.DataFrame,
    *,
    columns: list[str],
    rgb_lo: tuple[int, int, int],
    rgb_hi: tuple[int, int, int],
):
    out = styler
    for col in columns:
        if col not in df.columns:
            continue
        fn = _numeric_heatmap_style_fn(
            df[col],
            rgb_lo=rgb_lo,
            rgb_hi=rgb_hi,
        )
        out = out.map(fn, subset=[col])
    return out















def _split_authors(text: str) -> list[str]:
    if text is None:
        return []
    s = str(text).strip()
    if not s or s.lower() in {"nan", "none"}:
        return []
    parts = [p.strip() for p in s.split("|")]
    return [p for p in parts if p and p.lower() not in {"nan", "none"}]




def parse_member_name(member_name: str) -> dict:
    t = clean_person_name(member_name)
    if not t:
        return {"full_norm": "", "last_norm": "", "first_norm": "", "first_initial": "", "initial_key": ""}

    if "," in t:
        last, rest = [p.strip() for p in t.split(",", 1)]
        first = rest.split()[0].strip() if rest else ""
    else:
        parts = t.split()
        if len(parts) == 1:
            first, last = "", parts[0]
        else:
            first, last = parts[0], parts[-1]

    first_norm = norm_name(first)
    last_norm = norm_name(last)
    first_initial = norm_name(first[0]) if first else ""
    initial_key = _last_first_initial_key(t)
    return {
        "full_norm": norm_name(t),
        "last_norm": last_norm,
        "first_norm": first_norm,
        "first_initial": first_initial,
        "initial_key": initial_key,
    }

def parse_person_name(person_name: str) -> dict:
    return parse_member_name(person_name)


def member_match_mask(df: pd.DataFrame, member_info: dict) -> pd.Series:
    if df.empty:
        return pd.Series([], dtype=bool)

    org = df.get("recipientNameOrganization", pd.Series([""] * len(df))).fillna("").astype(str)
    last = df.get("recipientNameLast", pd.Series([""] * len(df))).fillna("").astype(str)
    first = df.get("recipientNameFirst", pd.Series([""] * len(df))).fillna("").astype(str)

    org_norm = norm_name_series(org)
    last_norm = norm_name_series(last)
    first_norm = norm_name_series(first)

    last_target = member_info.get("last_norm", "")
    first_target = member_info.get("first_norm", "")
    first_initial = member_info.get("first_initial", "")
    full_norm = member_info.get("full_norm", "")

    mask = pd.Series(False, index=df.index)

    if last_target:
        if first_target:
            first_ok = (first_norm == first_target)
            if first_initial:
                first_ok = first_ok | first_norm.str.startswith(first_initial)
            mask = mask | ((last_norm == last_target) & first_ok)
        else:
            mask = mask | (last_norm == last_target)

        if full_norm:
            mask = mask | org_norm.str.contains(full_norm, na=False)
        elif len(last_target) >= 4:
            mask = mask | org_norm.str.contains(last_target, na=False)
    elif full_norm:
        mask = mask | org_norm.str.contains(full_norm, na=False)

    return mask

def map_filer_to_lobbyshort(df: pd.DataFrame, name_to_short: dict, filerid_to_short: dict | None) -> pd.DataFrame:
    if df.empty:
        return df
    d = df.copy()
    filerid_map = filerid_to_short or {}
    short = pd.Series([""] * len(d), index=d.index)

    if "filerIdent" in d.columns and filerid_map:
        fid = pd.to_numeric(d["filerIdent"], errors="coerce").fillna(-1).astype(int)
        short = fid.map(filerid_map).fillna("")

    filer_name = d.get("filerName", pd.Series([""] * len(d)))
    filer_sort = d.get("filerSort", pd.Series([""] * len(d)))
    if isinstance(filer_name, pd.DataFrame):
        filer_name = filer_name.iloc[:, 0]
    if isinstance(filer_sort, pd.DataFrame):
        filer_sort = filer_sort.iloc[:, 0]

    filer_clean = clean_filer_name_series(filer_name)
    norm_raw = norm_name_series(filer_name)
    norm_clean = norm_name_series(filer_clean)
    norm_sort = norm_name_series(filer_sort)

    mapped = norm_raw.map(name_to_short)
    mapped = mapped.where(mapped.notna(), norm_clean.map(name_to_short))
    mapped = mapped.where(mapped.notna(), norm_sort.map(name_to_short))

    short = short.where(short.astype(str).str.strip() != "", mapped)
    d["LobbyShort"] = short.fillna("")
    return d




AppState = _shared_search_state.AppState
NavSearchBundle = _shared_search_state.NavSearchBundle
NavQueryKey = _shared_search_state.NavQueryKey
_candidate_label = _shared_search_state._candidate_label
build_client_index = _shared_search_state.build_client_index
resolve_client_name = _shared_search_state.resolve_client_name
build_author_bill_index = _shared_search_state.build_author_bill_index
build_member_index = _shared_search_state.build_member_index
resolve_member_name = _shared_search_state.resolve_member_name
build_lobbyist_index = _shared_search_state.build_lobbyist_index
resolve_lobbyshort = _shared_search_state.resolve_lobbyshort
resolve_lobbyshort_from_wit = _shared_search_state.resolve_lobbyshort_from_wit
lobbyist_autocomplete_candidates = _shared_search_state.lobbyist_autocomplete_candidates
format_lobbyist_label = _shared_search_state.format_lobbyist_label
lobby_candidate_key = _shared_search_state.lobby_candidate_key
normalize_bill = _shared_search_state.normalize_bill
is_bill_query = _shared_search_state.is_bill_query
build_nav_search_bundle = _shared_search_state.build_nav_search_bundle
build_nav_search_bundle_cached = _shared_search_state.build_nav_search_bundle_cached
can_reuse_nav_search_bundle = _shared_search_state.can_reuse_nav_search_bundle
build_data_health_table = _page_bundles.build_data_health_table
build_timeline_counts = _page_bundles.build_timeline_counts
bill_position_from_flags = _page_bundles.bill_position_from_flags
build_bills_with_status = _page_bundles.build_bills_with_status
build_policy_mentions = _page_bundles.build_policy_mentions
build_lobby_subject_counts = _page_bundles.build_lobby_subject_counts
build_lobbyist_trend = _page_bundles.build_lobbyist_trend
build_top_clients = _page_bundles.build_top_clients
build_member_activities = _page_bundles.build_member_activities
build_activities = _page_bundles.build_activities
build_activities_multi = _page_bundles.build_activities_multi
build_disclosures = _page_bundles.build_disclosures
build_disclosures_multi = _page_bundles.build_disclosures_multi
_build_tfl_trend_data = _page_bundles._build_tfl_trend_data
_build_top5_tfl_clients = _page_bundles._build_top5_tfl_clients
_build_lobby_display_names = _page_bundles._build_lobby_display_names
build_all_lobbyists_overview_fast = _page_bundles.build_all_lobbyists_overview_fast
_build_filtered_atlas_bundle = _map_runtime._build_filtered_atlas_bundle
_build_ranked_forensics_leads = _map_runtime._build_ranked_forensics_leads
_build_filtered_forensics_bundle = _map_runtime._build_filtered_forensics_bundle

def render_bill_search_results(bill_query: str, session_val: str | None, tfl_session_val: str | None,
                               wit_all: pd.DataFrame, bill_status_all: pd.DataFrame,
                               lobby_tfl_client_all: pd.DataFrame, short_to_names: dict):
    q = normalize_bill(bill_query)
    if not q:
        return False

    d = wit_all.copy()
    d["Session"] = d["Session"].astype(str).str.strip()
    if session_val is not None:
        d = d[d["Session"] == str(session_val)]

    d_bill_norm = d["Bill"].astype(str).str.upper().str.replace(r"\s+", " ", regex=True)
    d = d[d_bill_norm == q]
    total_rows = len(d)
    d = d[d["LobbyShort"].notna() & (d["LobbyShort"].astype(str).str.strip() != "")]
    if "LobbyShortNorm" not in d.columns:
        d["LobbyShortNorm"] = norm_name_series(d["LobbyShort"])

    tfl = lobby_tfl_client_all.copy()
    tfl["Session"] = tfl["Session"].astype(str).str.strip()
    if tfl_session_val is not None:
        tfl = tfl[tfl["Session"] == str(tfl_session_val)]
    tfl = ensure_cols(tfl, {"LobbyShort": ""})
    if "LobbyShortNorm" not in tfl.columns:
        tfl["LobbyShortNorm"] = norm_name_series(tfl["LobbyShort"])
    lobbyshort_set = set(tfl["LobbyShortNorm"].dropna().unique().tolist())
    if lobbyshort_set:
        d = d[d["LobbyShortNorm"].isin(lobbyshort_set)]
        if not tfl.empty:
            norm_to_short = (
                tfl[["LobbyShortNorm", "LobbyShort"]]
                .dropna()
                .drop_duplicates()
                .groupby("LobbyShortNorm")["LobbyShort"]
                .first()
                .to_dict()
            )
            d["LobbyShort"] = d["LobbyShortNorm"].map(norm_to_short).fillna(d["LobbyShort"])
    if d.empty:
        if total_rows > 0:
            st.info(
                f"Found {total_rows} witness-list rows for {q}, but none matched a lobbyist in Texas Ethics Commission filings "
                "for the selected session."
            )
        else:
            st.info("No witness-list rows matched that bill search.")
        return True

    pos = bill_position_from_flags(d)
    bs = bill_status_all.copy()
    bs["Session"] = bs["Session"].astype(str).str.strip()
    if session_val is not None:
        bs = bs[bs["Session"] == str(session_val)]

    merged = pos.merge(bs, on=["Session", "Bill"], how="left")
    merged["Lobbyist"] = merged["LobbyShort"].map(lambda s: _candidate_label(str(s), short_to_names))
    tfl = lobby_tfl_client_all.copy()
    tfl["Session"] = tfl["Session"].astype(str).str.strip()
    if tfl_session_val is not None:
        tfl = tfl[tfl["Session"] == str(tfl_session_val)]
    tfl = ensure_cols(tfl, {"LobbyShort": "", "IsTFL": 0})
    tfl_flag = (
        tfl.groupby("LobbyShort", as_index=False)["IsTFL"]
        .max()
        .rename(columns={"IsTFL": "Has TFL Client"})
    )
    merged = merged.merge(tfl_flag, on="LobbyShort", how="left")
    merged["Has TFL Client"] = merged["Has TFL Client"].fillna(0).astype(int).map({1: "Yes", 0: "No"})

    show_cols = ["Session", "Bill", "Lobbyist", "Has TFL Client", "Position", "Author", "Caption", "Status"]
    show_cols = [c for c in show_cols if c in merged.columns]
    merged["_tfl_sort"] = merged["Has TFL Client"].map({"Yes": 1, "No": 0}).fillna(0)
    view = merged[show_cols + ["_tfl_sort"]].sort_values(
        ["_tfl_sort", "Session", "Bill", "Lobbyist"],
        ascending=[False, True, True, True],
    )
    view = view.drop(columns=["_tfl_sort"])
    st.dataframe(view, width="stretch", height=520, hide_index=True)
    _ = export_dataframe(view, "bill_lobbyists.csv")
    return True

# =========================================================
# FAST MONEY PARSING (vectorized) for Lobby_TFL_Client_All
# =========================================================
_MONEY_RANGE = re.compile(r"(-?\d[\d,]*\.?\d*)\s*(?:-|to)\s*(-?\d[\d,]*\.?\d*)", re.IGNORECASE)

def _to_num_series(s: pd.Series) -> pd.Series:
    """Vectorized $/comma/paren cleanup -> float; blanks->0"""
    s = s.fillna("").astype(str).str.strip()
    neg = s.str.startswith("(") & s.str.endswith(")")
    s = s.str.replace(r"^\(|\)$", "", regex=True)
    s = s.str.replace("$", "", regex=False).str.replace(",", "", regex=False)
    out = pd.to_numeric(s, errors="coerce").fillna(0.0)
    out = out.where(~neg, -out)
    return out

def add_low_high_numeric(df: pd.DataFrame) -> pd.DataFrame:
    """
    Produces Low_num/High_num with minimal Python-level loops.
    Priority:
      1) Low/High columns if present and nonzero
      2) Parse Amount range "1000-5000"
      3) Parse Amount single value
      4) Mirror one side if only one exists
    """
    d = ensure_cols(df, {"Low": 0, "High": 0, "Amount": ""}).copy()

    low = _to_num_series(d["Low"])
    high = _to_num_series(d["High"])

    amt = d["Amount"].fillna("").astype(str).str.strip()
    amt_clean = (
        amt.str.replace("$", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.replace("\u2013", "-", regex=False)
    )

    # range capture
    rng = amt_clean.str.extract(_MONEY_RANGE)
    rng_lo = pd.to_numeric(rng[0], errors="coerce").fillna(0.0)
    rng_hi = pd.to_numeric(rng[1], errors="coerce").fillna(0.0)

    # single numeric fallback
    single = pd.to_numeric(amt_clean.str.extract(r"(-?\d+(?:\.\d+)?)")[0], errors="coerce").fillna(0.0)

    # If both low/high are zero, use range; else keep existing
    both_zero = (low == 0) & (high == 0)
    low = low.where(~both_zero, rng_lo.where(rng_lo != 0, single))
    high = high.where(~both_zero, rng_hi.where(rng_hi != 0, single))

    # Mirror
    high = high.where(high != 0, low)
    low = low.where(low != 0, high)

    d["Low_num"] = low
    d["High_num"] = high
    return d

# =========================================================
# LOAD WORKBOOK (open once -> much faster)
# =========================================================
def safe_read_excel_xf(xf: pd.ExcelFile, sheet_name: str, cols: list[str]) -> pd.DataFrame:
    try:
        return xf.parse(sheet_name=sheet_name, usecols=cols)
    except Exception:
        try:
            df = xf.parse(sheet_name=sheet_name)
            keep = [c for c in cols if c in df.columns]
            return df[keep]
        except Exception:
            return pd.DataFrame(columns=cols)

@st.cache_data(show_spinner=False)
def _empty_df(cols: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=cols)

def read_parquet_cols(path: Path, cols: list[str]) -> pd.DataFrame:
    """PERFORMANCE: read only requested columns via PyArrow, using pf.read()
    directly so we don't re-open the file a second time."""
    try:
        import pyarrow.parquet as pq
        pf = pq.ParquetFile(path)
        available = set(pf.schema.names)
        use_cols = [c for c in cols if c in available]
        tbl = pf.read(columns=use_cols) if use_cols else pf.read()
        return tbl.to_pandas()
    except Exception:
        try:
            df = pd.read_parquet(path)
            keep = [c for c in cols if c in df.columns]
            return df[keep] if keep else df
        except Exception:
            return pd.DataFrame(columns=cols)

@st.cache_resource(show_spinner=False, ttl=3600, max_entries=2)
def load_workbook(path: str) -> dict:
    cfg = {
        "Wit_All": ["session", "bill", "position", "LobbyShort", "name", "org"],
        "Bill_Status_All": ["Session", "Bill", "Authors", "Author", "Caption", "Status"],
        "Fiscal_Impact": ["Session", "Bill", "Version", "EstimatedTwoYearNetImpactGR"],
        "Bill_Sub_All": ["Session", "Bill", "Subject"],
        "Lobby_Sub_All": [
            "Session",
            "legislative_session",
            "Subject Matter",
            "Other Subject Matter Description",
            "Primary Business",
            "FilerID",
            "LobbyShort",
            "lobbyshort",
            "Lobby Name",
            "Unnamed: 0",
        ],
        "Lobbyist_Pol_Funds": [],
        "Lobby_TFL_Client_All": ["Session", "Client", "Lobby Name", "LobbyShort", "IsTFL", "Low", "High", "Amount", "Mid", "FilerID"],
        "Staff_All": ["Session", "session", "Legislator", "member_or_committee", "legislator_name", "Title", "role",
                      "Staffer", "name", "staff_name_last_initial", "lobby name", "source"],
        "LaFood": ["Session", "applicableYear", "filerIdent", "filerName", "filerSort", "recipientNameOrganization", "recipientNameLast", "recipientNameFirst",
                   "restaurantName", "activityDate", "periodStartDt", "activityExactAmount", "activityAmountRangeLow", "activityAmountRangeHigh", "activityAmountCd"],
        "LaEnt": ["Session", "applicableYear", "filerIdent", "filerName", "filerSort", "recipientNameOrganization", "recipientNameLast", "recipientNameFirst",
                  "entertainmentName", "activityDate", "periodStartDt", "activityExactAmount", "activityAmountRangeLow", "activityAmountRangeHigh", "activityAmountCd"],
        "LaTran": ["Session", "applicableYear", "filerIdent", "filerName", "filerSort", "recipientNameOrganization", "recipientNameLast", "recipientNameFirst",
                   "travelPurpose", "transportationTypeDescr", "departureCity", "arrivalCity", "checkInDt", "checkOutDt", "departureDt", "periodStartDt"],
        "LaGift": ["Session", "applicableYear", "filerIdent", "filerName", "filerSort", "recipientNameOrganization", "recipientNameLast", "recipientNameFirst",
                   "activityDescription", "periodStartDt", "activityExactAmount", "activityAmountRangeLow", "activityAmountRangeHigh", "activityAmountCd"],
        "LaEvnt": ["Session", "applicableYear", "filerIdent", "filerName", "filerSort", "recipientNameOrganization", "recipientNameLast", "recipientNameFirst",
                   "activityDescription", "activityDate", "periodStartDt"],
        "LaAwrd": ["Session", "applicableYear", "filerIdent", "filerName", "filerSort", "recipientNameOrganization", "recipientNameLast", "recipientNameFirst",
                   "activityDescription", "periodStartDt", "activityExactAmount", "activityAmountRangeLow", "activityAmountRangeHigh", "activityAmountCd"],
        "LaCvr": ["Session", "filerIdent", "filerName", "filerSort", "filedDt", "periodStartDt", "sourceCategoryCd",
                  "subjectMatterMemo", "docketsMemo", "filerNameOrganization"],
        "LaDock": ["Session", "filerIdent", "filerName", "filerSort", "receivedDt", "periodStartDt", "designationText", "agencyName"],
        "LaI4E": ["Session", "filerIdent", "filerName", "filerSort", "periodStartDt", "onbehalfName",
                  "onbehalfMailingCity", "onbehalfPrimaryPhoneNumber"],
        "LaSub": ["Session", "filerIdent", "filerName", "filerSort", "periodStartDt", "subjectMatterCodeValue", "subjectMatterDescr"],
    }

    base = Path(path)
    if not base.exists():
        return {k: _empty_df(v) for k, v in cfg.items()}
    if base.is_dir():
        parquet_map = {
        "Wit_All": ["Witness_Lists.parquet", "Witness List.parquet", "Witness_List.parquet", "witnesslist.parquet"],
            "Bill_Status_All": "Bill_Status.parquet",
            "Fiscal_Impact": "Fiscal_Notes.parquet",
            "Bill_Sub_All": "Bill_Sub_All.parquet",
            "Lobby_Sub_All": "Lobby.Sub.parquet",
            "Lobbyist_Pol_Funds": "Lobbyist.Pol.Funds.parquet",
            "Lobby_TFL_Client_All": "Lobby_TFL_Client_All.parquet",
            "Staff_All": ["Staff.parquet", "staff.parquet"],
            "LaFood": "LaFood.parquet",
            "LaEnt": "LaEnt.parquet",
            "LaTran": "LaTran.parquet",
            "LaGift": "LaGift.parquet",
            "LaEvnt": "LaEvnt.parquet",
            "LaAwrd": "LaAwrd.parquet",
            "LaCvr": "LaCvr.parquet",
            "LaDock": "LaDock.parquet",
            "LaI4E": "LaI4E.parquet",
            "LaSub": "LaSub.parquet",
        }
        # PERFORMANCE: resolve paths first, then read all parquet files
        # in parallel with ThreadPoolExecutor (was sequential).
        def _resolve_path(key_: str):
            fname = parquet_map.get(key_)
            if not fname:
                return None
            if isinstance(fname, (list, tuple)):
                if key_ == "Wit_All":
                    return [base / c for c in fname if (base / c).exists()] or None
                for c in fname:
                    if (base / c).exists():
                        return base / c
                return None
            cand = base / fname
            return cand if cand.exists() else None

        resolved = {k: _resolve_path(k) for k in cfg}

        def _read_one(key_: str, fpath_, cols_: list[str]) -> tuple[str, pd.DataFrame]:
            if fpath_ is None:
                return (key_, _empty_df(cols_))
            if isinstance(fpath_, list):  # Wit_All multi-file
                frames = []
                for p in fpath_:
                    try:
                        frames.append(read_parquet_cols(p, cols_))
                    except Exception:
                        continue
                if frames:
                    return (key_, pd.concat(frames, ignore_index=True).drop_duplicates())
                return (key_, _empty_df(cols_))
            try:
                return (key_, read_parquet_cols(fpath_, cols_))
            except Exception:
                return (key_, _empty_df(cols_))

        data = {}
        with ThreadPoolExecutor(max_workers=min(len(cfg), 8)) as pool:
            futs = {
                pool.submit(_read_one, k, resolved[k], v): k
                for k, v in cfg.items()
            }
            for fut in as_completed(futs):
                try:
                    k_, df_ = fut.result()
                    data[k_] = df_
                except Exception:
                    k_ = futs[fut]
                    data[k_] = _empty_df(cfg.get(k_, []))
    else:
        xf = pd.ExcelFile(path, engine="openpyxl")  # OPEN ONCE
        data = {k: safe_read_excel_xf(xf, k, v) for k, v in cfg.items()}

    # Normalize parquet schema differences
    wit = data.get("Wit_All")
    if isinstance(wit, pd.DataFrame):
        wit = wit
        if "session" in wit.columns and "Session" not in wit.columns:
            wit = wit.rename(columns={"session": "Session"})
        if "bill" in wit.columns and "Bill" not in wit.columns:
            wit = wit.rename(columns={"bill": "Bill"})
        if "position" in wit.columns:
            pos = wit["position"].fillna("").astype(str).str.upper()
            if "IsFor" not in wit.columns:
                wit["IsFor"] = pos.str.contains(r"\bFOR\b").astype(int)
            if "IsAgainst" not in wit.columns:
                wit["IsAgainst"] = pos.str.contains(r"\bAGAINST\b").astype(int)
            if "IsOn" not in wit.columns:
                wit["IsOn"] = pos.str.contains(r"\bON\b").astype(int)
        if "LobbyShort" not in wit.columns:
            wit["LobbyShort"] = ""
        unnamed = [c for c in wit.columns if str(c).startswith("Unnamed:")]
        if unnamed:
            wit = wit.drop(columns=unnamed)
        data["Wit_All"] = wit

    bs = data.get("Bill_Status_All")
    if isinstance(bs, pd.DataFrame):
        bs = bs
        if "Authors" in bs.columns and "Author" not in bs.columns:
            bs["Author"] = bs["Authors"]
        data["Bill_Status_All"] = bs

    fi = data.get("Fiscal_Impact")
    if isinstance(fi, pd.DataFrame):
        fi = fi
        data["Fiscal_Impact"] = fi

    lt = data.get("Lobby_TFL_Client_All")
    if isinstance(lt, pd.DataFrame):
        lt = lt
        if "IsTFL" not in lt.columns and "TFL?" in lt.columns:
            lt["IsTFL"] = lt["TFL?"].astype(str).str.upper().isin(["Y", "YES", "TRUE", "1"]).astype(int)
        if "IsTFL" in lt.columns:
            lt["IsTFL"] = pd.to_numeric(lt["IsTFL"], errors="coerce").fillna(0).astype(int)
        data["Lobby_TFL_Client_All"] = lt

    staff = data.get("Staff_All")
    if isinstance(staff, pd.DataFrame) and not staff.empty:
        staff = staff
        # Rename session column if needed
        if "session" in staff.columns and "Session" not in staff.columns:
            staff = staff.rename(columns={"session": "Session"})
        # Map staff parquet schema to expected columns
        if "Legislator" not in staff.columns:
            if "legislator_name" in staff.columns:
                leg = staff["legislator_name"].fillna("").astype(str).str.strip()
                if "member_or_committee" in staff.columns:
                    fallback = staff["member_or_committee"].fillna("").astype(str).str.strip()
                    staff["Legislator"] = leg.where(leg != "", fallback)
                else:
                    staff["Legislator"] = leg
            elif "member_or_committee" in staff.columns:
                staff["Legislator"] = staff["member_or_committee"]
            else:
                staff["Legislator"] = ""
        if "Title" not in staff.columns:
            staff["Title"] = staff.get("role", "")
        if "Staffer" not in staff.columns:
            staff["Staffer"] = staff.get("name", staff.get("staff_name_last_initial", ""))
        if "lobby name" not in staff.columns:
            staff["lobby name"] = staff.get("staff_name_last_initial", staff.get("name", ""))
        # Normalized staff name helpers for matching
        staff["StaffNameNorm"] = norm_name_series(staff.get("name", pd.Series(dtype=object)))
        staff["StaffLastInitialNorm"] = norm_name_series(
            staff.get("staff_name_last_initial", staff.get("name", pd.Series(dtype=object)))
        )
        staff["StaffLastNorm"] = last_name_norm_series(
            staff.get("name", staff.get("staff_name_last_initial", pd.Series(dtype=object)))
        )
        # Normalize Session to match app sessions (e.g., 89 -> 89R)
        if "Session" in staff.columns:
            sess = staff["Session"].astype(str).str.strip()
            staff["Session"] = sess.where(~sess.str.fullmatch(r"\d+"), sess + "R")
        data["Staff_All"] = staff

    ls = data.get("Lobby_Sub_All")
    if isinstance(ls, pd.DataFrame):
        ls = ls
        if "Session" not in ls.columns:
            if "legislative_session" in ls.columns:
                ls = ls.rename(columns={"legislative_session": "Session"})
            elif "session" in ls.columns:
                ls = ls.rename(columns={"session": "Session"})
        if "LobbyShort" not in ls.columns:
            if "lobbyshort" in ls.columns:
                ls = ls.rename(columns={"lobbyshort": "LobbyShort"})
            elif "lobby_short" in ls.columns:
                ls = ls.rename(columns={"lobby_short": "LobbyShort"})
        data["Lobby_Sub_All"] = ls

    pf = data.get("Lobbyist_Pol_Funds")
    if isinstance(pf, pd.DataFrame):
        pf = pf
        if "Session" not in pf.columns and "legislative_session" in pf.columns:
            pf = pf.rename(columns={"legislative_session": "Session"})
        if "LobbyShort" not in pf.columns:
            if "lobbyshort" in pf.columns:
                pf = pf.rename(columns={"lobbyshort": "LobbyShort"})
            elif "lobby_short" in pf.columns:
                pf = pf.rename(columns={"lobby_short": "LobbyShort"})
        data["Lobbyist_Pol_Funds"] = pf

    for key in ["LaFood", "LaEnt", "LaTran", "LaGift", "LaEvnt", "LaAwrd", "LaCvr", "LaDock", "LaI4E", "LaSub"]:
        df = data.get(key)
        if isinstance(df, pd.DataFrame):
            data[key] = _add_session_from_year(df)

    # Normalize Session everywhere
    for df in data.values():
        if isinstance(df, pd.DataFrame) and "Session" in df.columns:
            df["Session"] = df["Session"].astype(str).str.strip()

    # Precompute Low_num/High_num once (speed for overview + per-lobbyist)
    if isinstance(data.get("Lobby_TFL_Client_All"), pd.DataFrame) and not data["Lobby_TFL_Client_All"].empty:
        data["Lobby_TFL_Client_All"] = add_low_high_numeric(data["Lobby_TFL_Client_All"])

    # Build mapping from Lobby Name -> LobbyShort (across all sessions)
    lobby_name_rows = []

    def _append_lobby_names(df: pd.DataFrame, name_col: str, short_col: str, fid_col: str) -> None:
        if not isinstance(df, pd.DataFrame) or df.empty:
            return
        if name_col not in df.columns or short_col not in df.columns:
            return
        tmp = df[[name_col, short_col]]
        tmp = tmp.rename(columns={name_col: "Lobby Name", short_col: "LobbyShort"})
        tmp["FilerID"] = df[fid_col] if fid_col in df.columns else pd.NA
        lobby_name_rows.append(tmp)

    _append_lobby_names(data.get("Lobby_TFL_Client_All"), "Lobby Name", "LobbyShort", "FilerID")
    _append_lobby_names(data.get("Lobby_Sub_All"), "Lobby Name", "LobbyShort", "FilerID")
    _append_lobby_names(data.get("Lobbyist_Pol_Funds"), "Lobbyist", "LobbyShort", "FilerID")

    if lobby_name_rows:
        lobby_names = pd.concat(lobby_name_rows, ignore_index=True)
        lobby_names["LobbyShort"] = lobby_names["LobbyShort"].astype(str).str.strip()
        lobby_names["Lobby Name"] = lobby_names["Lobby Name"].astype(str).str.strip()
        lobby_names = lobby_names[(lobby_names["LobbyShort"] != "") & (lobby_names["Lobby Name"] != "")]
        lobby_names = lobby_names.drop_duplicates()
    else:
        lobby_names = pd.DataFrame(columns=["LobbyShort", "Lobby Name", "FilerID"])

    lobbyist_index = build_lobbyist_index(lobby_names)
    lobby_index = lobbyist_index.copy()
    name_to_short = {}
    short_to_names = {}
    known_shorts = set()
    initial_to_short = {}

    if not lobbyist_index.empty:
        known_shorts = set(
            lobbyist_index["LobbyShort"]
            .dropna()
            .astype(str)
            .str.strip()
            .unique()
            .tolist()
        )

        tmp = lobbyist_index[["LobbyShort", "Lobby Name"]].dropna()
        tmp["LobbyShort"] = tmp["LobbyShort"].astype(str)
        short_to_names = (
            tmp.groupby("LobbyShort")["Lobby Name"]
            .agg(lambda s: sorted(set(map(str, s)))[:6])
            .to_dict()
        )

        key_frames = []
        for col in ["LobbyNameNorm", "LobbyNameCleanNorm", "LastFirstNorm", "FirstLastNorm", "LastFirstInitialNorm"]:
            if col in lobbyist_index.columns:
                key_frames.append(lobbyist_index[[col, "LobbyShort"]].rename(columns={col: "Key"}))
        if key_frames:
            all_keys = pd.concat(key_frames, ignore_index=True)
            all_keys["Key"] = all_keys["Key"].fillna("").astype(str).str.strip()
            all_keys = all_keys[all_keys["Key"] != ""]
            counts = (
                all_keys.groupby(["Key", "LobbyShort"])
                .size()
                .reset_index(name="n")
                .sort_values(["Key", "n"], ascending=[True, False])
                .drop_duplicates("Key")
            )
            name_to_short = dict(zip(counts["Key"], counts["LobbyShort"]))

        # Map last name + first initial to LobbyShort (helps when names don't match exactly)
        tmp_short = lobbyist_index[["LobbyShort"]].dropna()
        tmp_short["InitialKey"] = tmp_short["LobbyShort"].map(_last_first_initial_key)
        tmp_short = tmp_short[tmp_short["InitialKey"].astype(str).str.strip() != ""]
        if not tmp_short.empty:
            init_counts = (
                tmp_short.groupby(["InitialKey", "LobbyShort"])
                .size()
                .reset_index(name="n")
                .sort_values(["InitialKey", "n"], ascending=[True, False])
                .drop_duplicates("InitialKey")
            )
            initial_to_short = dict(zip(init_counts["InitialKey"], init_counts["LobbyShort"]))

    # Map FilerID -> LobbyShort (used for activity matching)
    filerid_to_short = _build_filerid_map([
        (data.get("Lobby_TFL_Client_All"), "FilerID", "LobbyShort"),
        (data.get("Lobby_Sub_All"), "FilerID", "LobbyShort"),
        (data.get("Lobbyist_Pol_Funds"), "FilerID", "LobbyShort"),
    ])

    # Map witness list names/orgs to LobbyShort where possible
    wit = data.get("Wit_All")
    if isinstance(wit, pd.DataFrame) and not wit.empty:
        wit = wit
        if "LobbyShort" not in wit.columns:
            wit["LobbyShort"] = ""
        name_series = wit.get("name", pd.Series([""] * len(wit))).fillna("").astype(str)
        if "name" in wit.columns:
            wit["NameNorm"] = norm_name_series(name_series)
            wit["NameLastNorm"] = last_name_norm_series(name_series)
            wit["NameFirstNorm"] = first_name_norm_series(name_series)
            wit["NameFirstInitialNorm"] = wit["NameFirstNorm"].str.slice(0, 1)
        if name_to_short:
            name_norm = wit.get("NameNorm", name_series.map(norm_name))
            mapped = name_norm.map(name_to_short)
            if initial_to_short:
                init_key = name_series.map(_last_first_initial_key)
                mapped_init = init_key.map(initial_to_short)
                mapped = mapped.where(mapped.notna() & mapped.astype(str).str.strip().ne(""), mapped_init)
            if "org" in wit.columns:
                org_series = wit.get("org", pd.Series([""] * len(wit))).fillna("").astype(str)
                org_norm = norm_name_series(org_series)
                mapped = mapped.where(mapped.notna() & mapped.astype(str).str.strip().ne(""), org_norm.map(name_to_short))
            blank = wit["LobbyShort"].isna() | (wit["LobbyShort"].astype(str).str.strip() == "")
            wit.loc[blank, "LobbyShort"] = mapped[blank].fillna("")
        data["Wit_All"] = wit

    # Normalize LobbyShort for robust matching (hyphens/case/spacing).
    for key in ["Wit_All", "Lobby_TFL_Client_All", "Lobby_Sub_All"]:
        df = data.get(key)
        if isinstance(df, pd.DataFrame) and "LobbyShort" in df.columns:
            df["LobbyShortNorm"] = norm_name_series(df["LobbyShort"])

    data["name_to_short"] = name_to_short
    data["short_to_names"] = short_to_names
    data["lobby_index"] = lobby_index
    data["lobbyist_index"] = lobbyist_index
    data["known_shorts"] = known_shorts
    data["filerid_to_short"] = filerid_to_short

    # Fill Lobby_Sub_All LobbyShort from FilerID when missing
    ls = data.get("Lobby_Sub_All")
    if isinstance(ls, pd.DataFrame) and not ls.empty and filerid_to_short:
        if "FilerID" in ls.columns and "LobbyShort" in ls.columns:
            ls = ls
            fid = pd.to_numeric(ls["FilerID"], errors="coerce").fillna(-1).astype(int)
            missing = ls["LobbyShort"].isna() | ls["LobbyShort"].astype(str).str.strip().eq("")
            ls.loc[missing, "LobbyShort"] = fid.map(filerid_to_short)
            data["Lobby_Sub_All"] = ls
    gc.collect()
    return data

@st.cache_resource(show_spinner=False, ttl=3600, max_entries=2)
def get_app_state(path: str) -> AppState:
    return _shared_search_state.build_app_state(path, load_workbook(path))


@st.cache_resource(show_spinner=False, ttl=3600, max_entries=2)
def get_map_state(path: str) -> _map_page_state.MapState:
    def _fetch_reference_tables() -> dict[str, pd.DataFrame]:
        return {
            "school_districts": fetch_tea_school_district_centroids(),
            "counties": fetch_tea_county_centroids(),
            "cities": fetch_texas_city_centroids(),
            "water_districts": fetch_tceq_water_district_centroids(),
            "groundwater_districts": fetch_tceq_groundwater_district_centroids(),
            "regional_mobility_authorities": fetch_texas_rma_centroids(),
            "junior_colleges": fetch_texas_junior_college_centroids(),
            "navigation_districts": fetch_texas_navigation_district_centroids(),
            "transit_providers": fetch_nctcog_transit_provider_centroids(),
            "seaports": fetch_txdot_seaport_centroids(),
        }

    def _build_client_matches(
        tfl_client_names: tuple[str, ...],
        _reference_tables: dict[str, pd.DataFrame],
    ) -> pd.DataFrame:
        return build_tfl_political_subdivision_matches(tfl_client_names)

    return _map_page_state.build_map_state_from_sources(
        path,
        load_workbook(path),
        classify_entity_type=classify_requested_entity_type,
        fetch_reference_tables=_fetch_reference_tables,
        build_client_matches=_build_client_matches,
    )


def require_app_state(path: str, *, missing_path_message: str, missing_file_message: str) -> AppState:
    if not path:
        st.error(missing_path_message)
        st.stop()
    if not _is_url(path) and not os.path.exists(path):
        st.error(missing_file_message)
        st.stop()
    return get_app_state(path)


def require_map_state(path: str, *, missing_path_message: str, missing_file_message: str) -> _map_page_state.MapState:
    if not path:
        st.error(missing_path_message)
        st.stop()
    if not _is_url(path) and not os.path.exists(path):
        st.error(missing_file_message)
        st.stop()
    return get_map_state(path)


@st.cache_resource(show_spinner=False, ttl=3600, max_entries=16)
def get_map_atlas_bundle(
    path: str,
    scope: str,
    session_for_filter: str | None,
) -> _map_page_state.AtlasBundle:
    return _map_page_state.build_atlas_bundle(
        get_map_state(path),
        scope=scope,
        session_for_filter=session_for_filter,
        prepare_overlap_pool=_prepare_subdivision_match_pool,
    )


@st.cache_data(show_spinner=False, ttl=300, max_entries=16)
def get_client_scope_bundle(path: str, scope: str, session_val: str | None) -> _page_bundles.ClientScopeBundle:
    app_state = get_app_state(path)
    return _page_bundles.build_client_scope_bundle(
        app_state.data["Lobby_TFL_Client_All"],
        session_val,
        scope,
        match_entity_type=match_entity_type,
        build_category_chart_data=_build_category_chart_data,
    )


@st.cache_data(show_spinner=False, ttl=300, max_entries=16)
def get_lobby_scope_bundle(path: str, scope: str, session_val: str | None) -> _page_bundles.LobbyScopeBundle:
    app_state = get_app_state(path)
    return _page_bundles.build_lobby_scope_bundle(
        app_state.data["Lobby_TFL_Client_All"],
        session_val,
        scope,
    )


@st.cache_data(show_spinner=False, ttl=300, max_entries=16)
def get_member_session_bundle(path: str, session_val: str | None) -> _page_bundles.MemberSessionBundle:
    app_state = get_app_state(path)
    return _page_bundles.build_member_session_bundle(
        app_state.author_bills_all,
        app_state.data["Wit_All"],
        str(session_val or ""),
    )


@st.cache_data(show_spinner=False, ttl=300, max_entries=16)
def get_map_forensics_bundle(
    path: str,
    scope: str,
    session_for_filter: str | None,
    selected_subdivision_signature: str,
) -> _map_runtime.MapForensicsBundle:
    atlas_bundle = get_map_atlas_bundle(path, scope, session_for_filter)
    return _map_runtime.build_map_forensics_bundle(
        atlas_bundle,
        selected_subdivision_signature=selected_subdivision_signature,
    )


_PAGE_FRAGMENT_HELPER_KEYS = (
    "CHART_COLORS",
    "FUNDING_COLOR_MAP",
    "OPPOSITION_COLOR_MAP",
    "PLOTLY_CONFIG",
    "TEA_ARCGIS_WEBAPP_URL",
    "TREND_COLOR_MAP",
    "_apply_plotly_layout",
    "_clean_options",
    "_client_page",
    "_last_first_initial_key",
    "_lobby_page",
    "_map_page",
    "_member_page",
    "_session_base_label",
    "_session_label",
    "_shorten_text",
    "_solutions_page",
    "bill_position_from_flags",
    "build_activities",
    "build_activities_multi",
    "build_bills_with_status",
    "build_disclosures",
    "build_disclosures_multi",
    "build_lobby_subject_counts",
    "build_lobbyist_trend",
    "build_member_activities",
    "build_policy_mentions",
    "build_timeline_counts",
    "build_top_clients",
    "ensure_cols",
    "export_dataframe",
    "first_name_norm_series",
    "fmt_usd",
    "last_name_norm_from_text",
    "last_name_norm_series",
    "norm_name",
    "norm_name_series",
    "norm_person_variants",
    "norm_person_variants_with_nicknames",
    "parse_member_name",
    "parse_person_name",
    "pd",
    "px",
    "render_pill_list",
    "require_columns",
)
_MAP_FRAGMENT_HELPER_KEYS = (
    "MAP_BASEMAP_OPTIONS",
    "ThreadPoolExecutor",
    "_atlas_bridge",
    "_build_filtered_atlas_bundle",
    "_build_filtered_forensics_bundle",
    "_mp5_confidence_weight",
    "_mp5_geocode_badge",
    "_mp5_method_weight",
    "_mp5_miles",
    "_session_cached_value",
    "_stable_json_signature",
    "as_completed",
    "build_address_overlap_spending_rows",
    "build_overlap_map_points",
    "classify_requested_entity_type",
    "export_dataframe",
    "fmt_usd",
    "geocode_address_arcgis",
    "pd",
    "px",
    "query_texas_subdivisions_for_point",
    "render_address_overlap_arcgis_map",
    "render_draw_area_search_map",
    "render_subdivision_map_legend",
    "render_tfl_subdivision_arcgis_map",
)
_CLIENT_WORKSPACE_CTX_KEYS = (
    "Bill_Status_All",
    "Bill_Sub_All",
    "Fiscal_Impact",
    "LaCvr",
    "LaDock",
    "LaI4E",
    "LaSub",
    "Lobby_Sub_All",
    "Lobby_TFL_Client_All",
    "Staff_All",
    "Wit_All",
    "all_clients",
    "all_stats",
    "client_scope_bundle",
    "data",
    "name_to_short",
    "tfl_session_val",
)
_MEMBER_WORKSPACE_CTX_KEYS = (
    "Lobby_TFL_Client_All",
    "Staff_All",
    "Wit_All",
    "all_leg_stats",
    "all_legislators",
    "author_bills_all",
    "data",
    "name_to_short",
    "short_to_names",
    "tfl_session_val",
)
_MAP_WORKSPACE_CTX_KEYS = (
    "_atlas_label",
    "_docket_label",
    "_forensics_label",
    "_open_client",
    "_render_cross_context_banner",
    "atlas_bundle",
    "subdivision_matches",
    "tfl_spend",
    "total_high",
)


def _build_fragment_ctx(keys: tuple[str, ...], values: dict[str, object]) -> dict[str, object]:
    return {key: values[key] for key in keys if key in values}


def _subset_globals(keys: tuple[str, ...]) -> dict[str, object]:
    scope = globals()
    return {key: scope[key] for key in keys if key in scope}

@functools.lru_cache(maxsize=None)
def _page_renderer_module(module_name: str):
    return importlib.import_module(module_name)


def _run_page_renderer(module_name: str, ctx: dict[str, object] | None = None) -> None:
    module = _page_renderer_module(module_name)
    helper_keys = tuple(getattr(module, "HELPER_KEYS", ()))
    if helper_keys:
        module.configure_helpers(**_subset_globals(helper_keys))
    module.render_page(ctx or {})


def _page_fragment_helpers() -> dict[str, object]:
    return _subset_globals(_PAGE_FRAGMENT_HELPER_KEYS)


def _map_fragment_helpers() -> dict[str, object]:
    return _subset_globals(_MAP_FRAGMENT_HELPER_KEYS)


_page_fragments.configure_page_fragment_helpers(**_page_fragment_helpers())
_map_fragments.configure_map_fragment_helpers(**_map_fragment_helpers())


_NAV_SEARCH_BUNDLE_KEY = "_nav_search_bundle_v1"
_NAV_SEARCH_QUERY_KEY = "_nav_search_bundle_query_v1"


def _remember_nav_search_bundle(bundle: NavSearchBundle) -> None:
    st.session_state[_NAV_SEARCH_BUNDLE_KEY] = bundle
    st.session_state[_NAV_SEARCH_QUERY_KEY] = bundle.normalized_query


def _cached_nav_search_bundle(query: str) -> NavSearchBundle | None:
    bundle = st.session_state.get(_NAV_SEARCH_BUNDLE_KEY)
    if can_reuse_nav_search_bundle(query, bundle):
        return bundle
    return None


DATA_SOURCE_LABELS = {
    "Wit_All": "Texas Legislature Online (Witness lists)",
    "Bill_Status_All": "Texas Legislature Online (Bill status)",
    "Fiscal_Impact": "Texas Legislature Online (Fiscal notes)",
    "Bill_Sub_All": "Texas Legislature Online (Bill subjects)",
    "Lobby_Sub_All": "Texas Ethics Commission (Subject matter filings)",
    "Lobby_TFL_Client_All": "Texas Ethics Commission (Lobbyist filings and compensation)",
    "Staff_All": "House Research Organization (Legislative staff lists)",
    "LaFood": "Texas Ethics Commission (Activity: Food)",
    "LaEnt": "Texas Ethics Commission (Activity: Entertainment)",
    "LaTran": "Texas Ethics Commission (Activity: Travel)",
    "LaGift": "Texas Ethics Commission (Activity: Gifts)",
    "LaEvnt": "Texas Ethics Commission (Activity: Events)",
    "LaAwrd": "Texas Ethics Commission (Activity: Awards)",
    "LaCvr": "Texas Ethics Commission (Disclosure: Coverage)",
    "LaDock": "Texas Ethics Commission (Disclosure: Docket)",
    "LaI4E": "Texas Ethics Commission (Disclosure: On Behalf)",
    "LaSub": "Texas Ethics Commission (Disclosure: Subject Matter)",
}

def _source_label(key: str) -> str:
    return DATA_SOURCE_LABELS.get(key, key)

@st.cache_data(show_spinner=False, ttl=3600, hash_funcs={dict: id})
def data_health_table(data: dict) -> pd.DataFrame:
    order = [
        "Wit_All",
        "Bill_Status_All",
        "Fiscal_Impact",
        "Bill_Sub_All",
        "Lobby_Sub_All",
        "Lobby_TFL_Client_All",
        "Staff_All",
        "LaFood",
        "LaEnt",
        "LaTran",
        "LaGift",
        "LaEvnt",
        "LaAwrd",
        "LaCvr",
        "LaDock",
        "LaI4E",
        "LaSub",
    ]
    rows = []
    for key in order:
        df = data.get(key)
        label = _source_label(key)
        if isinstance(df, pd.DataFrame):
            sess_count = int(df["Session"].dropna().astype(str).nunique()) if "Session" in df.columns else 0
            lobby_count = int(df["LobbyShort"].dropna().astype(str).nunique()) if "LobbyShort" in df.columns else 0
            rows.append({
                "Source": label,
                "Rows": int(len(df)),
                "Cols": int(len(df.columns)),
                "Has Session": "Yes" if "Session" in df.columns else "No",
                "Empty": "Yes" if df.empty else "No",
                "Sessions": sess_count,
                "Last name + first initial": lobby_count,
            })
        else:
            rows.append({
                "Source": label,
                "Rows": 0,
                "Cols": 0,
                "Has Session": "No",
                "Empty": "Yes",
                "Sessions": 0,
                "Last name + first initial": 0,
            })
    return pd.DataFrame(rows)

# =========================================================
# ACTIVITIES (unchanged logic, still cached)
# =========================================================




nav_bundle = None
if nav_query and len(nav_query) >= 2 and PATH and (_is_url(PATH) or os.path.exists(PATH)):
    nav_bundle = build_nav_search_bundle_cached(NavQueryKey(nav_query), get_app_state(PATH))
    _remember_nav_search_bundle(nav_bundle)

nav_suggestions = list(nav_bundle.nav_suggestions) if nav_bundle else []
nav_suggestion_map = dict(nav_bundle.nav_suggestion_map) if nav_bundle else {}

if nav_suggestions:
    nav_pick = nav_suggest_slot.selectbox(
        "Nav suggestions",
        ["Select a match..."] + nav_suggestions,
        index=0,
        key="nav_suggestions_select",
        label_visibility="collapsed",
    )
    if nav_pick in nav_suggestion_map:
        nav_skip_submit = True
        target, value = nav_suggestion_map[nav_pick]
        nav_value = value if isinstance(value, str) else (value.get("name", "") or value.get("lobbyshort", ""))
        st.session_state.nav_search_query = nav_value
        st.session_state.nav_search_last = nav_value
        if target == "client":
            st.session_state.client_query = value
            st.session_state.client_query_input = value
            if _active_page != _client_page:
                st.switch_page(_client_page)
                st.stop()
        elif target == "member":
            st.session_state.member_query = value
            st.session_state.member_query_input = value
            if _active_page != _member_page:
                st.switch_page(_member_page)
                st.stop()
        else:
            sel = value if isinstance(value, dict) else {"lobbyshort": value, "name": value, "label": value, "filerid": None}
            sel_name = sel.get("name", "") or sel.get("lobbyshort", "")
            st.session_state.search_query = sel_name
            st.session_state.lobby_match_query = sel_name
            if sel.get("label"):
                st.session_state.lobby_match_select = sel.get("label")
            if sel.get("filerid") is not None:
                try:
                    st.session_state.lobby_filerid = int(sel.get("filerid"))
                except Exception:
                    st.session_state.lobby_filerid = sel.get("filerid")
            if sel.get("lobbyshort"):
                st.session_state.lobbyshort = sel.get("lobbyshort")
            if _active_page != _lobby_page:
                st.switch_page(_lobby_page)
                st.stop()
else:
    nav_suggest_slot.empty()

if nav_search_submitted and not nav_skip_submit:
    if nav_query:
        nav_bundle = _cached_nav_search_bundle(nav_query)
        if nav_bundle is None:
            nav_bundle = build_nav_search_bundle_cached(
                NavQueryKey(nav_query),
                require_app_state(
                    PATH,
                    missing_path_message="Data path not configured. Set the DATA_PATH environment variable.",
                    missing_file_message="Data path not found. Set DATA_PATH or place the parquet file in ./data.",
                ),
            )
            _remember_nav_search_bundle(nav_bundle)

        if nav_bundle.bill_query:
            st.session_state.search_query = nav_bundle.bill_query
            st.session_state.lobbyshort = ""
            if _active_page != _lobby_page:
                st.switch_page(_lobby_page)
                st.stop()
        else:
            resolved_client = nav_bundle.resolved_client
            client_suggestions = list(nav_bundle.client_suggestions)
            resolved_member = nav_bundle.resolved_member
            member_suggestions = list(nav_bundle.member_suggestions)
            lobby_candidates = list(nav_bundle.lobby_candidates)
            resolved_lobby = nav_bundle.resolved_lobby
            resolved_lobby_filer = nav_bundle.resolved_lobby_filer
            resolved_lobby_name = nav_bundle.resolved_lobby_name
            lobby_suggestions = list(nav_bundle.lobby_suggestions)

            target_page = _lobby_page
            if resolved_client:
                target_page = _client_page
                st.session_state.client_query = resolved_client
                st.session_state.client_query_input = resolved_client
            elif resolved_member:
                target_page = _member_page
                st.session_state.member_query = resolved_member
                st.session_state.member_query_input = resolved_member
            elif resolved_lobby:
                target_page = _lobby_page
                st.session_state.search_query = resolved_lobby_name or nav_query
                if resolved_lobby_filer is not None:
                    st.session_state.lobby_filerid = resolved_lobby_filer
                if lobby_candidates:
                    st.session_state.lobby_match_query = st.session_state.search_query
                    st.session_state.lobby_match_select = lobby_candidates[0].get("label", "")
            else:
                if "," in nav_query and member_suggestions:
                    target_page = _member_page
                elif client_suggestions and not member_suggestions:
                    target_page = _client_page
                elif member_suggestions and not client_suggestions:
                    target_page = _member_page
                elif client_suggestions:
                    target_page = _client_page
                elif member_suggestions:
                    target_page = _member_page
                elif lobby_suggestions:
                    target_page = _lobby_page

                if target_page == _client_page:
                    st.session_state.client_query = nav_query
                    st.session_state.client_query_input = nav_query
                elif target_page == _member_page:
                    st.session_state.member_query = nav_query
                    st.session_state.member_query_input = nav_query
                else:
                    st.session_state.search_query = nav_query

            if target_page != _active_page:
                st.switch_page(target_page)
                st.stop()

# Render the active page after nav-search routing completes.
_active_page.run()
st.stop()
