from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any, Mapping

import pandas as pd


def _mp5_priority_from_score(score: float) -> str:
    value = float(score or 0.0)
    if value >= 78:
        return "Tier 1"
    if value >= 58:
        return "Tier 2"
    return "Tier 3"


def build_selected_subdivision_signature(selected_context: Mapping[str, Any] | None) -> str:
    payload = dict(selected_context or {})
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha1(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MapForensicsBundle:
    totals: pd.DataFrame
    tfl_spend: pd.DataFrame
    subdivision_matches: pd.DataFrame
    matched_clients: frozenset[str]
    total_tfl: int
    total_high: float
    mapped_high: float
    mapped_rate: float
    unmapped_count: int
    hotspot_label: str
    hotspot_high: float
    selected_subdivision_signature: str


def build_map_forensics_bundle(atlas_bundle, *, selected_subdivision_signature: str) -> MapForensicsBundle:
    totals = atlas_bundle.totals
    tfl_spend = atlas_bundle.tfl_spend
    subdivision_matches = atlas_bundle.subdivision_matches
    matched_clients = frozenset(atlas_bundle.matched_clients)
    total_tfl = int(atlas_bundle.total_tfl or 0)
    total_high = float(atlas_bundle.total_high or 0.0)
    mapped_high = float(atlas_bundle.mapped_high or 0.0)
    mapped_rate = float(atlas_bundle.mapped_rate or 0.0)
    unmapped_count = int(atlas_bundle.unmapped_count or 0)

    return MapForensicsBundle(
        totals=totals,
        tfl_spend=tfl_spend,
        subdivision_matches=subdivision_matches,
        matched_clients=matched_clients,
        total_tfl=total_tfl,
        total_high=total_high,
        mapped_high=mapped_high,
        mapped_rate=mapped_rate,
        unmapped_count=unmapped_count,
        hotspot_label=str(getattr(atlas_bundle, "hotspot_label", "--") or "--"),
        hotspot_high=float(getattr(atlas_bundle, "hotspot_high", 0.0) or 0.0),
        selected_subdivision_signature=str(selected_subdivision_signature or "").strip(),
    )

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
