from __future__ import annotations

import re
from typing import Any, Mapping

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

import tfl_app.map.runtime as _map_runtime
from tfl_app.shared.sessions import session_base_label as _session_base_label
from tfl_app.shared.sessions import session_base_number_series as _session_base_number_series
from tfl_app.shared.signatures import hash_dataframe_for_cache, stable_json_signature


PRIMARY_PATTERNS = [
    (r"\bindependent school district\b|\bisd\b|\bcisd\b", "Independent School District"),
    (r"\bcity of\b|\bcity\b|\btown of\b|\btown\b|\bvillage\b", "City"),
    (r"\bcounty\b|\bcommissioners court\b", "County"),
    (r"\bcollege\b|\bcommunity college\b|\bjunior college\b", "College"),
    (r"\bmunicipal utility district\b|\bmud\b", "Municipal Utility District"),
    (r"\bwater control(?: and)? improvement district\b|\bwcid\b", "Water Control & Improvement District"),
    (r"\bwater improvement district\b|\bwid\b", "Water Improvement District"),
    (r"\bgroundwater conservation district\b|\bgcd\b", "Groundwater Conservation District"),
    (r"\bdrainage district\b", "Drainage District"),
    (r"\birrigation district\b", "Irrigation District"),
    (r"\blevee improvement district\b|\blid\b", "Levee Improvement District"),
    (r"\bmunicipal management district\b|\bmmd\b", "Municipal Management District"),
    (r"\bregional mobility authority\b|\brma\b", "Regional Mobility Authority"),
    (r"\bnavigation district\b", "Navigation District"),
    (r"\btransit authority\b|\btransportation authority\b|\barea rapid transit\b|\bdart\b", "Transit Authority"),
    (r"\bport authority\b|\bseaport\b", "Port Authority"),
    (r"\bhospital district\b", "Hospital District"),
    (r"\bemergency services district\b|\besd\b", "Emergency Services District"),
    (r"\bappraisal district\b|\bcad\b", "Appraisal District"),
    (r"\blocal government corporation\b|\bdevelopment corporation\b", "Local Government Corporation"),
    (r"\bassociation\b|\bcoalition\b|\bfoundation\b|\bcommittee\b|\bboard\b|\bleague\b", "Association"),
]

COARSE_CATEGORY = {
    "Independent School District": "Public School Districts",
    "Municipal Utility District": "Special Districts and Other Authorities",
    "Water Control & Improvement District": "Special Districts and Other Authorities",
    "Water Improvement District": "Special Districts and Other Authorities",
    "Groundwater Conservation District": "Special Districts and Other Authorities",
    "Drainage District": "Special Districts and Other Authorities",
    "Irrigation District": "Special Districts and Other Authorities",
    "Levee Improvement District": "Special Districts and Other Authorities",
    "Municipal Management District": "Special Districts and Other Authorities",
    "Regional Mobility Authority": "Special Districts and Other Authorities",
    "Navigation District": "Special Districts and Other Authorities",
    "Transit Authority": "Special Districts and Other Authorities",
    "Port Authority": "Special Districts and Other Authorities",
    "Hospital District": "Special Districts and Other Authorities",
    "Emergency Services District": "Special Districts and Other Authorities",
    "Appraisal District": "Special Districts and Other Authorities",
    "Local Government Corporation": "Special Districts and Other Authorities",
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

_SESSION_BASE_YEAR = 2023
_SESSION_BASE_NUM = 88
def normalize_entity_name(name: str) -> str:
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return ""
    normalized = str(name).strip().lower()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def match_entity_type(name: str) -> tuple[str, str]:
    normalized = normalize_entity_name(name)
    for pattern, canonical in PRIMARY_PATTERNS:
        if re.search(pattern, normalized, flags=re.IGNORECASE):
            coarse = COARSE_CATEGORY.get(canonical)
            if canonical == "Independent School District":
                coarse = "Public School Districts"
            if canonical == "City":
                coarse = "Cities, Towns, Villages"
            if canonical == "County":
                coarse = "County"
            if not coarse:
                coarse = COARSE_CATEGORY.get(canonical, "Special Districts and Other Authorities")
            return canonical, coarse

    if re.search(r"\bschool\b", normalized):
        return "Independent School District", "Public School Districts"
    if re.search(r"\bcommunity college\b|\bjunior college\b", normalized):
        return "College", "Community and Junior Colleges"
    if re.search(r"\bcity\b|\btown\b|\bvillage\b", normalized):
        return "City", "Cities, Towns, Villages"
    if re.search(r"\bcounty\b", normalized):
        return "County", "County"
    if re.search(r"\bassociation\b|\bcoalition\b|\bfoundation\b|\bcommittee\b|\bboard\b", normalized):
        return "Association", "Associations"
    return "Other", "Other"
@st.cache_data(
    show_spinner=False,
    ttl=300,
    max_entries=64,
    hash_funcs={pd.DataFrame: hash_dataframe_for_cache},
)
def build_category_chart_data(df: pd.DataFrame) -> pd.DataFrame:
    cat_base = df.copy()
    cat_base["Session"] = cat_base["Session"].astype(str).str.strip()
    for column, default in {"Client": "", "Low_num": 0.0, "High_num": 0.0, "IsTFL": 0}.items():
        if column not in cat_base.columns:
            cat_base[column] = default
    cat_base["IsTFL"] = pd.to_numeric(cat_base["IsTFL"], errors="coerce").fillna(0)
    cat_base = cat_base[cat_base["IsTFL"] == 1]
    cat_base["SessionBase"] = _session_base_number_series(cat_base["Session"])
    cat_base = cat_base[cat_base["SessionBase"].between(85, 89)]
    cat_base = cat_base[cat_base["Client"].fillna("").astype(str).str.strip() != ""]
    if cat_base.empty:
        return pd.DataFrame(columns=["SessionBase", "Category", "Total", "SessionLabel"])
    cat_base["Category"] = cat_base["Client"].map(lambda value: match_entity_type(value)[1])
    cat_base["Low_num"] = pd.to_numeric(cat_base["Low_num"], errors="coerce").fillna(0)
    cat_base["High_num"] = pd.to_numeric(cat_base["High_num"], errors="coerce").fillna(0)
    cat_base["Total"] = (cat_base["Low_num"] + cat_base["High_num"]) / 2
    cat_group = (
        cat_base.groupby(["SessionBase", "Category"], as_index=False)["Total"]
        .sum()
    )
    cat_group["SessionLabel"] = cat_group["SessionBase"].map(_session_base_label)
    return cat_group


@st.cache_data(
    show_spinner=False,
    ttl=300,
    max_entries=64,
    hash_funcs={pd.DataFrame: hash_dataframe_for_cache},
)
def build_client_overview_chart_payload(
    selector_signature: str,
    category_chart_data: pd.DataFrame,
    all_stats: Mapping[str, Any],
) -> dict[str, Any]:
    del selector_signature
    tfl_mid = (float(all_stats.get("tfl_low_total", 0.0) or 0.0) + float(all_stats.get("tfl_high_total", 0.0) or 0.0)) / 2
    pri_mid = (float(all_stats.get("pri_low_total", 0.0) or 0.0) + float(all_stats.get("pri_high_total", 0.0) or 0.0)) / 2
    mix_df = pd.DataFrame(
        {
            "Funding": ["Taxpayer Funded", "Private"],
            "Total": [tfl_mid, pri_mid],
        }
    )
    cat_group = category_chart_data.copy()
    if cat_group.empty:
        return {"mix_df": mix_df, "cat_group": cat_group, "session_labels": [], "category_order": []}
    session_order = sorted(cat_group["SessionBase"].dropna().unique().tolist())
    category_order = sorted(
        {
            str(category).strip()
            for category in cat_group["Category"].dropna().tolist()
            if str(category).strip()
        }
    )
    session_labels = [_session_base_label(base) for base in session_order]
    return {
        "mix_df": mix_df,
        "cat_group": cat_group,
        "session_labels": session_labels,
        "category_order": category_order,
    }


@st.cache_data(
    show_spinner=False,
    ttl=300,
    max_entries=64,
    hash_funcs={pd.DataFrame: hash_dataframe_for_cache},
)
def build_lobby_scope_chart_payload(
    selector_signature: str,
    trend_group: pd.DataFrame,
    all_stats: Mapping[str, Any],
) -> dict[str, Any]:
    del selector_signature
    tfl_mid = (float(all_stats.get("tfl_low_total", 0.0) or 0.0) + float(all_stats.get("tfl_high_total", 0.0) or 0.0)) / 2
    pri_mid = (float(all_stats.get("pri_low_total", 0.0) or 0.0) + float(all_stats.get("pri_high_total", 0.0) or 0.0)) / 2
    mix_df = pd.DataFrame(
        {
            "Funding": ["Taxpayer Funded", "Private"],
            "Total": [tfl_mid, pri_mid],
        }
    )
    trend_long = pd.DataFrame(columns=["SessionBase", "SessionLabel", "Estimate", "Total"])
    session_labels: list[str] = []
    if not trend_group.empty:
        trend_long = trend_group.melt(
            id_vars=["SessionBase", "SessionLabel"],
            value_vars=["Low", "High"],
            var_name="Estimate",
            value_name="Total",
        )
        trend_long["Estimate"] = trend_long["Estimate"].map({"Low": "Low estimate", "High": "High estimate"})
        session_order = sorted(trend_group["SessionBase"].dropna().unique().tolist())
        session_labels = [_session_base_label(base) for base in session_order]
    return {
        "mix_df": mix_df,
        "trend_long": trend_long,
        "session_labels": session_labels,
    }


@st.cache_data(
    show_spinner=False,
    ttl=120,
    max_entries=64,
    hash_funcs={pd.DataFrame: hash_dataframe_for_cache},
)
def build_filtered_atlas_bundle(
    selector_signature: str,
    subdivision_matches: pd.DataFrame,
    *,
    selected_types: list[str],
    min_match_count: int,
    query: str,
    sort_mode: str,
) -> dict[str, Any]:
    del selector_signature
    return _map_runtime._build_filtered_atlas_bundle(
        subdivision_matches,
        selected_types=selected_types,
        min_match_count=min_match_count,
        query=query,
        sort_mode=sort_mode,
    )


@st.cache_data(
    show_spinner=False,
    ttl=120,
    max_entries=64,
    hash_funcs={pd.DataFrame: hash_dataframe_for_cache},
)
def build_filtered_forensics_bundle(
    selector_signature: str,
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
) -> dict[str, Any]:
    del selector_signature
    return _map_runtime._build_filtered_forensics_bundle(
        rows,
        confidence_filters=confidence_filters,
        method_filters=method_filters,
        entity_query=entity_query,
        min_high=min_high,
        dist_cap=dist_cap,
        focus_selected_subdivision=focus_selected_subdivision,
        selected_type=selected_type,
        selected_name=selected_name,
        focus_selected_clients=focus_selected_clients,
        selected_clients=selected_clients,
        sort_mode=sort_mode,
    )


@st.cache_data(
    show_spinner=False,
    ttl=120,
    max_entries=64,
    hash_funcs={pd.DataFrame: hash_dataframe_for_cache},
)
def build_map_atlas_chart_payload(selector_signature: str, filtered_cov: pd.DataFrame) -> dict[str, Any]:
    del selector_signature
    tree_df = pd.DataFrame()
    hist_vals = pd.Series(dtype="float64")
    if not filtered_cov.empty:
        tree_df = filtered_cov.copy()
        tree_df["_type"] = tree_df["subdivision_type"].astype(str).str.strip()
        tree_df["_name"] = tree_df["subdivision_name"].astype(str).str.strip()
        tree_df["high_total"] = pd.to_numeric(tree_df["high_total"], errors="coerce").fillna(0.0)
        tree_df = tree_df[tree_df["high_total"] > 0].head(200)
        hist_vals = pd.to_numeric(filtered_cov["match_count"], errors="coerce").dropna()
    return {"tree_df": tree_df, "hist_vals": hist_vals}


@st.cache_data(
    show_spinner=False,
    ttl=120,
    max_entries=64,
    hash_funcs={pd.DataFrame: hash_dataframe_for_cache},
)
def build_map_forensics_chart_payload(
    selector_signature: str,
    filtered: pd.DataFrame,
    leads: pd.DataFrame,
) -> dict[str, Any]:
    del selector_signature
    chart_df = pd.DataFrame()
    heat_pivot = pd.DataFrame()
    etype_melt = pd.DataFrame()
    chart_leads = pd.DataFrame()

    if not filtered.empty:
        chart_df = filtered.copy()
        chart_df["Confidence"] = chart_df["Match Confidence"].astype(str)

        heat_df = (
            filtered.groupby(
                [filtered["Match Confidence"].astype(str), filtered["Match Method"].astype(str)],
            )
            .size()
            .reset_index(name="Count")
        )
        if not heat_df.empty:
            heat_df = heat_df.set_axis(["Confidence", "Method", "Count"], axis=1)
            heat_pivot = heat_df.pivot_table(
                index="Confidence",
                columns="Method",
                values="Count",
                fill_value=0,
            )

        etype_df = (
            filtered.groupby(filtered["Entity Type"].astype(str).str.strip())
            .agg(Low=("Low", "sum"), High=("High", "sum"))
            .reset_index()
        )
        etype_df = etype_df.set_axis(["Entity Type", "Low", "High"], axis=1)
        etype_df = etype_df[etype_df["Entity Type"] != ""].sort_values("High", ascending=False).head(15)
        if not etype_df.empty:
            etype_melt = etype_df.melt(
                id_vars="Entity Type",
                value_vars=["Low", "High"],
                var_name="Estimate",
                value_name="Amount",
            )

    if not leads.empty:
        chart_leads = leads.head(20).copy()
        chart_leads["Entity"] = chart_leads["TFL Entity"].astype(str).str[:40]

    return {
        "chart_df": chart_df,
        "heat_pivot": heat_pivot,
        "etype_melt": etype_melt,
        "chart_leads": chart_leads,
    }


__all__ = [
    "build_category_chart_data",
    "build_client_overview_chart_payload",
    "build_filtered_atlas_bundle",
    "build_filtered_forensics_bundle",
    "build_lobby_scope_chart_payload",
    "build_map_atlas_chart_payload",
    "build_map_forensics_chart_payload",
    "hash_dataframe_for_cache",
    "match_entity_type",
    "normalize_entity_name",
    "stable_json_signature",
]

