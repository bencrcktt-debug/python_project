import hashlib
import os
import re
import difflib
import functools
import importlib
import html
import json
import math
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from io import BytesIO
import pandas as pd
pd.options.mode.copy_on_write = True  # PERFORMANCE: deferred copy Ã¢â‚¬â€ makes .copy() nearly free
import streamlit as st
from tfl_app.config.map_sources import (
    ARCGIS_GEOCODER_URL,
    CENSUS_ARCGIS_TEXAS_CITY_LAYER_URL,
    MAP_BASEMAP_OPTIONS,
    MAP_DATA_SOURCES,
    NCTCOG_TRANSIT_PROVIDERS_LAYER_URL,
    TCEQ_GROUNDWATER_DISTRICTS_LAYER_URL,
    TCEQ_WATER_DISTRICTS_LAYER_URL,
    TEA_ARCGIS_COUNTY_LAYER_URL,
    TEA_ARCGIS_SCHOOL_DISTRICT_LAYER_URL,
    TEA_ARCGIS_WEBAPP_URL,
    TEXAS_HOUSE_DISTRICTS_LAYER_URL,
    TEXAS_JUNIOR_COLLEGE_LAYER_URL,
    TEXAS_NAVIGATION_DISTRICT_LAYER_URL,
    TEXAS_RMA_LAYER_URL,
    TEXAS_SENATE_DISTRICTS_LAYER_URL,
    TXDOT_SEAPORTS_LAYER_URL,
)
from tfl_app.config.paths import resolve_data_path
import tfl_app.map.state as _map_page_state
import tfl_app.data.loaders as _loaders
import tfl_app.data.state_store as _state_store
import tfl_app.data.workspace_bundles as _workspace_bundles
import tfl_app.charts.runtime as _chart_runtime
import tfl_app.ui.components.runtime as _map_component_runtime
import tfl_app.map.geo_runtime as _map_geo_runtime
import tfl_app.map.runtime as _map_runtime
import tfl_app.map.reference_runtime as _map_reference_runtime
import tfl_app.ui.fragments.map_workspace_fragments as _map_fragments
import tfl_app.map.page_helpers as _map_page_helpers
import tfl_app.bundles.page_bundles as _page_bundles
import tfl_app.bundles.page_detail_bundles as _page_detail_bundles
import tfl_app.ui.fragments.workspace_fragments as _page_fragments
import tfl_app.ui.runtime_exports as _ui_runtime_exports
import tfl_app.ui.runtime_filters as _ui_runtime_filters
import tfl_app.ui.runtime_labels as _ui_runtime_labels
import tfl_app.ui.runtime_pdf as _ui_runtime_pdf
import tfl_app.ui.runtime_plotly as _ui_runtime_plotly
import tfl_app.entrypoints.bootstrap as _entry_bootstrap
import tfl_app.entrypoints.chrome as _entry_chrome
import tfl_app.entrypoints.nav_search as _entry_nav_search
import tfl_app.entrypoints.navigation as _entry_navigation
import tfl_app.entrypoints.page_registry as _entry_page_registry
import tfl_app.entrypoints.service_registry as _entry_service_registry
from tfl_app.services import AppServices, MapServices, WorkspaceServices
from tfl_app.ui.fragments.bound import BoundMapFragments, BoundPageFragments
from tfl_app.ui.page_state import ensure_nav_state
from tfl_app.shared.sessions import add_session_from_year as _add_session_from_year
from tfl_app.shared.sessions import session_from_year as _session_from_year
from tfl_app.shared.sessions import tfl_session_for_filter as _tfl_session_for_filter
from tfl_app.search.indexes import AppState, build_author_bill_index, build_client_index, build_lobbyist_index, build_member_index
from tfl_app.search.resolve import (
    _candidate_label,
    build_nav_search_bundle_cached,
    format_lobbyist_label,
    is_bill_query,
    lobby_candidate_key,
    lobbyist_autocomplete_candidates,
    normalize_bill,
    resolve_client_name,
    resolve_lobbyshort_from_wit,
    resolve_member_name,
)

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
    """Vectorized version of person_display Ã¢â‚¬â€ avoids row-by-row .apply()."""
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
    """Vectorized version of amount_display Ã¢â‚¬â€ avoids row-by-row .apply()."""
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


# Reuse the shared bundle implementations so the app entrypoint does not own
# a separate display-helper code path.
_vectorized_person_display = _page_bundles._vectorized_person_display
_vectorized_amount_display = _page_bundles._vectorized_amount_display


def _session_base_number_series(s: pd.Series) -> pd.Series:
    base = s.fillna("").astype(str).str.strip().str.extract(r"^(\d+)", expand=False)
    base = base.where(base.str.len() <= 2, base.str[:-1])
    return pd.to_numeric(base, errors="coerce")

# =========================================================
# CONFIG
# =========================================================
def _is_url(path: str) -> bool:
    return path.startswith("http://") or path.startswith("https://")


PATH = resolve_data_path()

_entry_bootstrap.configure_page()

# =========================================================
# STYLE (unchanged)
# =========================================================
_entry_bootstrap.render_global_styles()

# =========================================================
# GLOBAL UX ENHANCEMENTS
# =========================================================
_entry_bootstrap.render_global_ux()


_mp5_miles = _map_page_helpers._mp5_miles
_mp5_method_weight = _map_page_helpers._mp5_method_weight
_mp5_confidence_weight = _map_page_helpers._mp5_confidence_weight
_mp5_priority_from_score = _map_page_helpers._mp5_priority_from_score
_mp5_geocode_badge = _map_page_helpers._mp5_geocode_badge
_build_mp5_css = _map_page_helpers._build_mp5_css

def _same_page(left: object, right: object) -> bool:
    return _entry_navigation.same_page(left, right)


def _journey_steps() -> list[tuple[str, str, str, object]]:
    return _entry_chrome.journey_steps()

def _render_page_intro(kicker: str, title: str, subtitle: str, pills: list[str] | None = None) -> None:
    _entry_chrome.render_page_intro(kicker, title, subtitle, pills)

def _is_guided_mode() -> bool:
    return _entry_chrome.is_guided_mode()

def _render_journey(current_key: str) -> None:
    return _entry_chrome.render_journey(current_key)

def _render_workspace_guide(
    question: str,
    steps: list[str] | None = None,
    method_note: str | None = None,
) -> None:
    return _entry_chrome.render_workspace_guide(question, steps, method_note)

def _render_quickstart(
    page_key: str,
    steps: list[str],
    note: str | None = None,
) -> None:
    return _entry_chrome.render_quickstart(page_key, steps, note)

def _render_evidence_guardrails(
    can_answer: list[str] | None = None,
    cannot_answer: list[str] | None = None,
    next_checks: list[str] | None = None,
) -> None:
    return _entry_chrome.render_evidence_guardrails(can_answer, cannot_answer, next_checks)

def _render_workspace_links(
    key_prefix: str,
    actions: list[tuple[str, object, str]],
) -> None:
    return _entry_chrome.render_workspace_links(key_prefix, actions)

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

# PERFORMANCE: shared urllib3 connection pool Ã¢â‚¬â€ keeps TCP connections alive
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


# Reuse the shared runtime implementations for session helpers and no-op
# column hydration so page modules do not bounce between duplicate logic.
ensure_cols = _page_bundles.ensure_cols



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

get_app_table = _state_store.get_app_table
get_app_tables = _state_store.get_app_tables
get_app_table_readonly = _state_store.get_app_table_readonly
get_app_tables_readonly = _state_store.get_app_tables_readonly
get_workspace_table_overlays = _state_store.get_workspace_table_overlays
get_table_manifest = _loaders.get_table_manifest
load_workbook = _loaders.load_workbook
get_app_state = _state_store.get_app_state
get_map_state = _state_store.get_map_state
require_app_state = _state_store.require_app_state
require_map_state = _state_store.require_map_state
get_map_atlas_bundle = _workspace_bundles.get_map_atlas_bundle
get_client_scope_bundle = _workspace_bundles.get_client_scope_bundle
get_lobby_scope_bundle = _workspace_bundles.get_lobby_scope_bundle
get_member_session_bundle = _workspace_bundles.get_member_session_bundle
get_client_workspace_detail_bundle = _workspace_bundles.get_client_workspace_detail_bundle
get_member_workspace_detail_bundle = _workspace_bundles.get_member_workspace_detail_bundle
get_lobby_workspace_detail_bundle = _workspace_bundles.get_lobby_workspace_detail_bundle
get_map_forensics_bundle = _workspace_bundles.get_map_forensics_bundle

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
_ui_runtime_pdf.configure_helpers(**_UI_RUNTIME_HELPERS)

fmt_usd = _ui_runtime_labels.fmt_usd
_shorten_text = _ui_runtime_labels._shorten_text
render_pill_list = _ui_runtime_labels.render_pill_list
_current_filter_parts = _ui_runtime_filters._current_filter_parts
_export_context_label = _ui_runtime_exports._export_context_label
_export_filename = _ui_runtime_exports._export_filename
export_dataframe = _ui_runtime_exports.export_dataframe
require_columns = _ui_runtime_exports.require_columns
reset_filters = _ui_runtime_filters.reset_filters
_remember_recent_search = _ui_runtime_filters._remember_recent_search
reset_client_filters = _ui_runtime_filters.reset_client_filters
reset_member_filters = _ui_runtime_filters.reset_member_filters
_remember_recent_client_search = _ui_runtime_filters._remember_recent_client_search
_remember_recent_member_search = _ui_runtime_filters._remember_recent_member_search
_ordinal = _ui_runtime_labels._ordinal
_session_base_label = _ui_runtime_plotly._session_base_label
_session_label = _ui_runtime_labels._session_label
_session_long_label = _ui_runtime_labels._session_long_label
_session_range_label = _ui_runtime_labels._session_range_label
_default_session_from_list = _ui_runtime_labels._default_session_from_list
_slugify = _ui_runtime_labels._slugify
_clean_options = _ui_runtime_labels._clean_options
PDF_CHART_ERROR_KEY = _ui_runtime_pdf.PDF_CHART_ERROR_KEY
PLOTLY_CONFIG = _ui_runtime_plotly.PLOTLY_CONFIG
CHART_COLORS = _ui_runtime_plotly.CHART_COLORS
FUNDING_COLOR_MAP = _ui_runtime_plotly.FUNDING_COLOR_MAP
OPPOSITION_COLOR_MAP = _ui_runtime_plotly.OPPOSITION_COLOR_MAP
TREND_COLOR_MAP = _ui_runtime_plotly.TREND_COLOR_MAP
_apply_plotly_layout = _ui_runtime_plotly._apply_plotly_layout
_render_pdf_report_section = _ui_runtime_pdf._render_pdf_report_section


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


@functools.lru_cache(maxsize=None)
def _page_renderer_module(module_name: str):
    return importlib.import_module(module_name)


def _run_page_renderer(module_name: str, ctx: dict[str, object] | None = None) -> None:
    module = _page_renderer_module(module_name)
    module.render_page(services=_APP_SERVICES, ctx=ctx or {})


_PAGE_REGISTRY = _entry_page_registry.build_page_registry(_run_page_renderer)
_about_page = _PAGE_REGISTRY.about_page
_lobby_page = _PAGE_REGISTRY.lobby_page
_client_page = _PAGE_REGISTRY.client_page
_map_page = _PAGE_REGISTRY.map_page
_member_page = _PAGE_REGISTRY.member_page
_solutions_page = _PAGE_REGISTRY.solutions_page
_tap_page = _PAGE_REGISTRY.tap_page
_pages = list(_PAGE_REGISTRY.pages)


_PAGE_RUNTIME_HELPERS = {
    "CHART_COLORS": CHART_COLORS,
    "FUNDING_COLOR_MAP": FUNDING_COLOR_MAP,
    "MAP_BASEMAP_OPTIONS": MAP_BASEMAP_OPTIONS,
    "OPPOSITION_COLOR_MAP": OPPOSITION_COLOR_MAP,
    "PATH": PATH,
    "PDF_CHART_ERROR_KEY": PDF_CHART_ERROR_KEY,
    "PLOTLY_CONFIG": PLOTLY_CONFIG,
    "TEA_ARCGIS_WEBAPP_URL": TEA_ARCGIS_WEBAPP_URL,
    "TREND_COLOR_MAP": TREND_COLOR_MAP,
    "_apply_plotly_layout": _apply_plotly_layout,
    "_atlas_bridge": _atlas_bridge,
    "_build_mp5_css": _build_mp5_css,
    "_clean_options": _clean_options,
    "_client_page": _client_page,
    "_current_filter_parts": _current_filter_parts,
    "_default_session_from_list": _default_session_from_list,
    "_last_first_initial_key": _last_first_initial_key,
    "_lobby_page": _lobby_page,
    "_map_fragments": _map_fragments,
    "_map_page": _map_page,
    "_map_runtime": _map_runtime,
    "_member_page": _member_page,
    "_mp5_confidence_weight": _mp5_confidence_weight,
    "_mp5_geocode_badge": _mp5_geocode_badge,
    "_mp5_method_weight": _mp5_method_weight,
    "_mp5_miles": _mp5_miles,
    "_page_fragments": _page_fragments,
    "_remember_recent_client_search": _remember_recent_client_search,
    "_remember_recent_member_search": _remember_recent_member_search,
    "_remember_recent_search": _remember_recent_search,
    "_render_evidence_guardrails": _render_evidence_guardrails,
    "_render_journey": _render_journey,
    "_render_page_intro": _render_page_intro,
    "_render_pdf_report_section": _render_pdf_report_section,
    "_render_quickstart": _render_quickstart,
    "_render_workspace_guide": _render_workspace_guide,
    "_render_workspace_links": _render_workspace_links,
    "_session_base_label": _session_base_label,
    "_session_label": _session_label,
    "_shorten_text": _shorten_text,
    "_solutions_page": _solutions_page,
    "_tfl_session_for_filter": _tfl_session_for_filter,
    "bill_position_from_flags": bill_position_from_flags,
    "build_activities": build_activities,
    "build_activities_multi": build_activities_multi,
    "build_address_overlap_spending_rows": build_address_overlap_spending_rows,
    "build_bills_with_status": build_bills_with_status,
    "build_disclosures": build_disclosures,
    "build_disclosures_multi": build_disclosures_multi,
    "build_lobby_subject_counts": build_lobby_subject_counts,
    "build_lobbyist_trend": build_lobbyist_trend,
    "build_member_activities": build_member_activities,
    "build_overlap_map_points": build_overlap_map_points,
    "build_policy_mentions": build_policy_mentions,
    "build_timeline_counts": build_timeline_counts,
    "build_top_clients": build_top_clients,
    "classify_requested_entity_type": classify_requested_entity_type,
    "data_health_table": lambda path: data_health_table(path),
    "ensure_cols": ensure_cols,
    "export_dataframe": export_dataframe,
    "first_name_norm_series": first_name_norm_series,
    "fmt_usd": fmt_usd,
    "format_lobbyist_label": format_lobbyist_label,
    "geocode_address_arcgis": geocode_address_arcgis,
    "get_app_state": get_app_state,
    "get_app_table": get_app_table,
    "get_app_tables": get_app_tables,
    "get_app_table_readonly": get_app_table_readonly,
    "get_app_tables_readonly": get_app_tables_readonly,
    "get_client_scope_bundle": get_client_scope_bundle,
    "get_client_workspace_detail_bundle": get_client_workspace_detail_bundle,
    "get_lobby_scope_bundle": get_lobby_scope_bundle,
    "get_lobby_workspace_detail_bundle": get_lobby_workspace_detail_bundle,
    "get_map_atlas_bundle": get_map_atlas_bundle,
    "get_map_forensics_bundle": get_map_forensics_bundle,
    "get_map_state": get_map_state,
    "get_member_session_bundle": get_member_session_bundle,
    "get_member_workspace_detail_bundle": get_member_workspace_detail_bundle,
    "get_table_manifest": get_table_manifest,
    "html": html,
    "is_bill_query": is_bill_query,
    "last_name_norm_from_text": last_name_norm_from_text,
    "last_name_norm_series": last_name_norm_series,
    "lobby_candidate_key": lobby_candidate_key,
    "lobbyist_autocomplete_candidates": lobbyist_autocomplete_candidates,
    "norm_name": norm_name,
    "norm_name_series": norm_name_series,
    "norm_person_variants": norm_person_variants,
    "norm_person_variants_with_nicknames": norm_person_variants_with_nicknames,
    "normalize_bill": normalize_bill,
    "parse_member_name": parse_member_name,
    "parse_person_name": parse_person_name,
    "query_texas_subdivisions_for_point": query_texas_subdivisions_for_point,
    "render_address_overlap_arcgis_map": render_address_overlap_arcgis_map,
    "render_bill_search_results": render_bill_search_results,
    "render_draw_area_search_map": render_draw_area_search_map,
    "render_pill_list": render_pill_list,
    "render_subdivision_map_legend": render_subdivision_map_legend,
    "render_tfl_subdivision_arcgis_map": render_tfl_subdivision_arcgis_map,
    "require_app_state": require_app_state,
    "require_columns": require_columns,
    "require_map_state": require_map_state,
    "reset_client_filters": reset_client_filters,
    "reset_filters": reset_filters,
    "reset_member_filters": reset_member_filters,
    "resolve_client_name": resolve_client_name,
    "resolve_lobbyshort_from_wit": resolve_lobbyshort_from_wit,
    "resolve_member_name": resolve_member_name,
}


def _select_helpers(registry: dict[str, object], keys: tuple[str, ...]) -> dict[str, object]:
    return {key: registry[key] for key in keys if key in registry}

def _page_fragment_helpers() -> dict[str, object]:
    return _select_helpers(_PAGE_RUNTIME_HELPERS, _PAGE_FRAGMENT_HELPER_KEYS)


def _map_fragment_helpers() -> dict[str, object]:
    return _select_helpers(_PAGE_RUNTIME_HELPERS, _MAP_FRAGMENT_HELPER_KEYS)


_WORKSPACE_SERVICES, _MAP_SERVICES, _APP_SERVICES = _entry_service_registry.build_services(_PAGE_RUNTIME_HELPERS)


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

@st.cache_data(show_spinner=False, ttl=3600, max_entries=16)
def data_health_table(path: str) -> pd.DataFrame:
    manifest = get_table_manifest(str(path or ""))
    return _page_bundles.build_data_health_table(manifest or {}, DATA_SOURCE_LABELS)

# =========================================================
# ACTIVITIES (unchanged logic, still cached)
# =========================================================

def render_app() -> None:
    _active_page, nav_query, nav_search_submitted, nav_suggest_slot = _entry_navigation.render_navigation_shell(_pages)
    nav_bundle = _entry_nav_search.prefetch_nav_search_bundle(
        nav_query,
        path=PATH,
        path_available=bool(PATH and (_is_url(PATH) or os.path.exists(PATH))),
        build_cached=build_nav_search_bundle_cached,
        get_app_state=get_app_state,
    )
    nav_skip_submit = _entry_nav_search.render_nav_suggestions(
        nav_bundle,
        nav_suggest_slot,
        active_page=_active_page,
        client_page=_client_page,
        member_page=_member_page,
        lobby_page=_lobby_page,
        same_page=_same_page,
    )
    _entry_nav_search.handle_nav_search_submission(
        nav_query=nav_query,
        nav_search_submitted=nav_search_submitted,
        nav_skip_submit=nav_skip_submit,
        active_page=_active_page,
        client_page=_client_page,
        member_page=_member_page,
        lobby_page=_lobby_page,
        same_page=_same_page,
        path=PATH,
        build_cached=build_nav_search_bundle_cached,
        require_app_state=require_app_state,
    )

    _active_page.run()
    st.stop()


