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
pd.options.mode.copy_on_write = True  # PERFORMANCE: deferred copy â€” makes .copy() nearly free
import streamlit as st
import map_page_state as _map_page_state
import shared_search_state as _shared_search_state
import src.app_runtime as _app_runtime
import src.chart_runtime as _chart_runtime
import src.map_component_runtime as _map_component_runtime
import src.map_geo_runtime as _map_geo_runtime
import src.map_runtime as _map_runtime
import src.map_reference_runtime as _map_reference_runtime
import src.map_fragments as _map_fragments
import src.map_page_helpers as _map_page_helpers
import src.page_bundles as _page_bundles
import src.page_detail_bundles as _page_detail_bundles
import src.page_fragments as _page_fragments
import src.ui_runtime as _ui_runtime

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
    """Vectorized version of person_display â€” avoids row-by-row .apply()."""
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
    """Vectorized version of amount_display â€” avoids row-by-row .apply()."""
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


def _session_base_number_series(s: pd.Series) -> pd.Series:
    base = s.fillna("").astype(str).str.strip().str.extract(r"^(\d+)", expand=False)
    base = base.where(base.str.len() <= 2, base.str[:-1])
    return pd.to_numeric(base, errors="coerce")

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

# -- Atlas â†’ Forensics / Batch bridge (invisible component relay) --






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

@_safe_page('Clients')
def _page_client_lookup():
    _run_page_renderer("src.pages.clients")


@_safe_page('Legislators')
def _page_member_lookup():
    _run_page_renderer("src.pages.legislators")


_mp5_miles = _map_page_helpers._mp5_miles
_mp5_method_weight = _map_page_helpers._mp5_method_weight
_mp5_confidence_weight = _map_page_helpers._mp5_confidence_weight
_mp5_priority_from_score = _map_page_helpers._mp5_priority_from_score
_mp5_geocode_badge = _map_page_helpers._mp5_geocode_badge
_build_mp5_css = _map_page_helpers._build_mp5_css


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

# PERFORMANCE: shared urllib3 connection pool â€” keeps TCP connections alive
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




@functools.lru_cache(maxsize=2048)



@functools.lru_cache(maxsize=512)


@functools.lru_cache(maxsize=4096)


@functools.lru_cache(maxsize=2048)

@functools.lru_cache(maxsize=512)



@functools.lru_cache(maxsize=2048)






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

@st.cache_data(show_spinner=False, ttl=43200, max_entries=2)

@st.cache_data(show_spinner=False, ttl=43200, max_entries=2)


@st.cache_data(show_spinner=False, ttl=43200, max_entries=2)

@st.cache_data(show_spinner=False, ttl=43200, max_entries=2)

@st.cache_data(show_spinner=False, ttl=43200, max_entries=2)

@st.cache_data(show_spinner=False, ttl=43200, max_entries=2)

@st.cache_data(show_spinner=False, ttl=43200, max_entries=2)

@st.cache_data(show_spinner=False, ttl=43200, max_entries=2)

@st.cache_data(show_spinner=False, ttl=43200, max_entries=2)

@st.cache_data(show_spinner=False, ttl=3600, max_entries=8)

@st.cache_data(show_spinner=False, ttl=3600, max_entries=8)

@st.cache_data(show_spinner=False, ttl=3600, max_entries=8)

@st.cache_data(show_spinner=False, ttl=3600, max_entries=8)

@st.cache_data(show_spinner=False, ttl=3600, max_entries=8)

@st.cache_data(show_spinner=False, ttl=3600, max_entries=8)

@st.cache_data(show_spinner=False, ttl=3600, max_entries=8)

@st.cache_data(show_spinner=False, ttl=3600, max_entries=8)

@st.cache_data(show_spinner=False, ttl=3600, max_entries=8)

@st.cache_data(show_spinner=False, ttl=3600, max_entries=8)

@st.cache_data(show_spinner=False, ttl=3600, max_entries=8)


@st.cache_data(show_spinner=False, ttl=3600, max_entries=8)

@st.cache_data(show_spinner=False, ttl=86400, max_entries=256)

@st.cache_data(show_spinner=False, ttl=604800, max_entries=4096)

@st.cache_data(show_spinner=False, ttl=604800, max_entries=8192)

@st.cache_data(show_spinner=False, ttl=86400, max_entries=512)

@functools.lru_cache(maxsize=4096)












# =================================================================
# DRAW AREA & SEARCH ADDRESS MAP COMPONENT
# =================================================================







def normalize_entity_name(name: str) -> str:
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return ""
    s = str(name).strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


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
match_entity_type = _chart_runtime.match_entity_type

build_address_overlap_spending_rows = _map_geo_runtime.build_address_overlap_spending_rows
build_overlap_map_points = _map_geo_runtime.build_overlap_map_points
build_tfl_political_subdivision_matches = _map_geo_runtime.build_tfl_political_subdivision_matches
classify_requested_entity_type = _map_geo_runtime.classify_requested_entity_type
geocode_address_arcgis = _map_geo_runtime.geocode_address_arcgis
query_texas_subdivisions_for_point = _map_geo_runtime.query_texas_subdivisions_for_point
render_subdivision_map_legend = _map_geo_runtime.render_subdivision_map_legend
_prepare_subdivision_match_pool = _map_geo_runtime.prepare_subdivision_match_pool

fetch_nctcog_transit_provider_centroids = _map_reference_runtime.fetch_nctcog_transit_provider_centroids
fetch_tceq_groundwater_district_centroids = _map_reference_runtime.fetch_tceq_groundwater_district_centroids
fetch_tceq_water_district_centroids = _map_reference_runtime.fetch_tceq_water_district_centroids
fetch_tea_county_centroids = _map_reference_runtime.fetch_tea_county_centroids
fetch_tea_school_district_centroids = _map_reference_runtime.fetch_tea_school_district_centroids
fetch_texas_city_centroids = _map_reference_runtime.fetch_texas_city_centroids
fetch_texas_junior_college_centroids = _map_reference_runtime.fetch_texas_junior_college_centroids
fetch_texas_navigation_district_centroids = _map_reference_runtime.fetch_texas_navigation_district_centroids
fetch_texas_rma_centroids = _map_reference_runtime.fetch_texas_rma_centroids
fetch_txdot_seaport_centroids = _map_reference_runtime.fetch_txdot_seaport_centroids

_atlas_bridge = _map_component_runtime._atlas_bridge
render_address_overlap_arcgis_map = _map_component_runtime.render_address_overlap_arcgis_map
render_draw_area_search_map = _map_component_runtime.render_draw_area_search_map
render_tfl_school_district_arcgis_map = _map_component_runtime.render_tfl_school_district_arcgis_map
render_tfl_subdivision_arcgis_map = _map_component_runtime.render_tfl_subdivision_arcgis_map

get_app_table = _app_runtime.get_app_table
get_app_tables = _app_runtime.get_app_tables
get_workspace_table_overlays = _app_runtime.get_workspace_table_overlays
get_table_manifest = _app_runtime.get_table_manifest
load_workbook = _app_runtime.load_workbook
get_app_state = _app_runtime.get_app_state
get_map_state = _app_runtime.get_map_state
require_app_state = _app_runtime.require_app_state
require_map_state = _app_runtime.require_map_state
get_map_atlas_bundle = _app_runtime.get_map_atlas_bundle
get_client_scope_bundle = _app_runtime.get_client_scope_bundle
get_lobby_scope_bundle = _app_runtime.get_lobby_scope_bundle
get_member_session_bundle = _app_runtime.get_member_session_bundle
get_client_workspace_detail_bundle = _app_runtime.get_client_workspace_detail_bundle
get_member_workspace_detail_bundle = _app_runtime.get_member_workspace_detail_bundle
get_lobby_workspace_detail_bundle = _app_runtime.get_lobby_workspace_detail_bundle
get_map_forensics_bundle = _app_runtime.get_map_forensics_bundle

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


_UI_RUNTIME_HELPERS = {
    "_last_first_initial_key": _last_first_initial_key,
    "bill_position_from_flags": bill_position_from_flags,
    "build_activities": build_activities,
    "build_activities_multi": build_activities_multi,
    "build_author_bill_index": build_author_bill_index,
    "build_disclosures": build_disclosures,
    "build_disclosures_multi": build_disclosures_multi,
    "build_member_activities": build_member_activities,
    "ensure_cols": ensure_cols,
    "last_name_norm_from_text": last_name_norm_from_text,
    "last_name_norm_series": last_name_norm_series,
    "match_entity_type": match_entity_type,
    "norm_name": norm_name,
    "norm_name_series": norm_name_series,
    "norm_person_variants": norm_person_variants,
    "normalize_bill": normalize_bill,
    "parse_member_name": parse_member_name,
}
_ui_runtime.configure_helpers(**_UI_RUNTIME_HELPERS)

fmt_usd = _ui_runtime.fmt_usd
_shorten_text = _ui_runtime._shorten_text
render_pill_list = _ui_runtime.render_pill_list
_current_filter_parts = _ui_runtime._current_filter_parts
_export_context_label = _ui_runtime._export_context_label
_export_filename = _ui_runtime._export_filename
export_dataframe = _ui_runtime.export_dataframe
require_columns = _ui_runtime.require_columns
reset_filters = _ui_runtime.reset_filters
_remember_recent_search = _ui_runtime._remember_recent_search
reset_client_filters = _ui_runtime.reset_client_filters
reset_member_filters = _ui_runtime.reset_member_filters
_remember_recent_client_search = _ui_runtime._remember_recent_client_search
_remember_recent_member_search = _ui_runtime._remember_recent_member_search
_ordinal = _ui_runtime._ordinal
_session_base_label = _ui_runtime._session_base_label
_session_label = _ui_runtime._session_label
_session_long_label = _ui_runtime._session_long_label
_session_range_label = _ui_runtime._session_range_label
_default_session_from_list = _ui_runtime._default_session_from_list
_slugify = _ui_runtime._slugify
_clean_options = _ui_runtime._clean_options
PDF_CHART_ERROR_KEY = _ui_runtime.PDF_CHART_ERROR_KEY
PLOTLY_CONFIG = _ui_runtime.PLOTLY_CONFIG
CHART_COLORS = _ui_runtime.CHART_COLORS
FUNDING_COLOR_MAP = _ui_runtime.FUNDING_COLOR_MAP
OPPOSITION_COLOR_MAP = _ui_runtime.OPPOSITION_COLOR_MAP
TREND_COLOR_MAP = _ui_runtime.TREND_COLOR_MAP
_apply_plotly_layout = _ui_runtime._apply_plotly_layout
_render_pdf_report_section = _ui_runtime._render_pdf_report_section


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
    "get_app_state",
    "get_app_table",
    "get_app_tables",
    "get_client_scope_bundle",
    "get_client_workspace_detail_bundle",
    "get_lobby_scope_bundle",
    "get_lobby_workspace_detail_bundle",
    "get_member_session_bundle",
    "get_member_workspace_detail_bundle",
    "last_name_norm_from_text",
    "last_name_norm_series",
    "norm_name",
    "norm_name_series",
    "norm_person_variants",
    "norm_person_variants_with_nicknames",
    "parse_member_name",
    "parse_person_name",
    "render_pill_list",
    "require_columns",
)
_MAP_FRAGMENT_HELPER_KEYS = (
    "MAP_BASEMAP_OPTIONS",
    "PATH",
    "_atlas_bridge",
    "_map_runtime",
    "_mp5_confidence_weight",
    "_mp5_geocode_badge",
    "_mp5_method_weight",
    "_mp5_miles",
    "_tfl_session_for_filter",
    "build_address_overlap_spending_rows",
    "build_overlap_map_points",
    "classify_requested_entity_type",
    "export_dataframe",
    "fmt_usd",
    "geocode_address_arcgis",
    "get_map_atlas_bundle",
    "get_map_forensics_bundle",
    "get_map_state",
    "query_texas_subdivisions_for_point",
    "render_address_overlap_arcgis_map",
    "render_draw_area_search_map",
    "render_subdivision_map_legend",
    "render_tfl_subdivision_arcgis_map",
)


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
    return _page_bundles.build_data_health_table(data or {}, DATA_SOURCE_LABELS)

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

