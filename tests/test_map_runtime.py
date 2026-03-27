from __future__ import annotations

import pandas as pd

import tfl_app.map.state as map_state
import tfl_app.map.runtime as map_runtime


def _classify_entity_type(name: str) -> str:
    value = str(name).strip().lower()
    if "city" in value:
        return "City"
    if "port" in value:
        return "Port Authority"
    return "Other"


def _reference_tables() -> dict[str, pd.DataFrame]:
    return {"cities": pd.DataFrame(), "counties": pd.DataFrame()}


def _client_matches(_names: tuple[str, ...], _refs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "subdivision_type": "City",
                "subdivision_name": "Austin City",
                "subdivision_code": "001",
                "lon": -97.7431,
                "lat": 30.2672,
                "match_count": 1,
                "match_clients": ["City of Austin"],
                "match_clients_preview": "City of Austin",
                "source_name": "Texas Cities",
                "source_url": "https://example.com/cities",
            },
            {
                "subdivision_type": "Port Authority",
                "subdivision_name": "Port of Houston Authority",
                "subdivision_code": "PHA",
                "lon": -95.0,
                "lat": 29.73,
                "match_count": 1,
                "match_clients": ["Port of Houston Authority"],
                "match_clients_preview": "Port of Houston Authority",
                "source_name": "Texas Ports",
                "source_url": "https://example.com/ports",
            },
        ]
    )


def test_build_map_forensics_bundle_matches_atlas_summary() -> None:
    workbook = {
        "Lobby_TFL_Client_All": pd.DataFrame(
            [
                {"Session": "89R", "Client": "City of Austin", "LobbyShort": "ALPHA", "IsTFL": 1, "Low_num": 150.0, "High_num": 250.0},
                {"Session": "89R", "Client": "Port of Houston Authority", "LobbyShort": "BETA", "IsTFL": 1, "Low_num": 60.0, "High_num": 120.0},
                {"Session": "89R", "Client": "Private Widget Co", "LobbyShort": "GAMMA", "IsTFL": 0, "Low_num": 25.0, "High_num": 50.0},
            ]
        )
    }
    state = map_state.build_map_state_from_sources(
        "memory://map",
        workbook,
        classify_entity_type=_classify_entity_type,
        fetch_reference_tables=_reference_tables,
        build_client_matches=_client_matches,
    )
    atlas_bundle = map_state.build_atlas_bundle(state, scope="This Session", session_for_filter="89R")

    runtime_bundle = map_runtime.build_map_forensics_bundle(
        atlas_bundle,
        selected_subdivision_signature="sig-1",
    )

    assert runtime_bundle.total_tfl == atlas_bundle.total_tfl
    assert runtime_bundle.total_high == atlas_bundle.total_high
    assert runtime_bundle.mapped_high == atlas_bundle.mapped_high
    assert runtime_bundle.hotspot_label == "City - Austin City"
    assert runtime_bundle.hotspot_high == 250.0
    assert runtime_bundle.selected_subdivision_signature == "sig-1"


def test_filtered_atlas_and_forensics_leads_remain_stable() -> None:
    subdivision_matches = pd.DataFrame(
        [
            {
                "subdivision_type": "City",
                "subdivision_name": "Austin City",
                "match_count": 2,
                "match_clients_preview": "City of Austin, County of Travis",
                "match_clients": ["City of Austin", "County of Travis"],
                "low_total": 200.0,
                "high_total": 400.0,
            },
            {
                "subdivision_type": "County",
                "subdivision_name": "Travis County",
                "match_count": 1,
                "match_clients_preview": "County of Travis",
                "match_clients": ["County of Travis"],
                "low_total": 50.0,
                "high_total": 100.0,
            },
        ]
    )
    atlas_filtered = map_runtime._build_filtered_atlas_bundle(
        subdivision_matches,
        selected_types=["City", "County"],
        min_match_count=1,
        query="Austin",
        sort_mode="Highest High",
    )
    assert list(atlas_filtered["filtered_cov"]["subdivision_name"]) == ["Austin City"]
    assert atlas_filtered["cov_total_high_filtered"] == 400.0

    overlap_rows = pd.DataFrame(
        [
            {
                "TFL Entity": "City of Austin",
                "Entity Type": "City",
                "Low": 100.0,
                "High": 200.0,
                "Mid": 150.0,
                "Match Confidence": "High",
                "Boundary Match": True,
                "Distance Miles": 1.0,
                "Row Signal": 90.0,
                "Match Method": "Spatial",
                "Subdivision Type": "City",
                "Subdivision": "Austin City",
            },
            {
                "TFL Entity": "City of Austin",
                "Entity Type": "City",
                "Low": 50.0,
                "High": 100.0,
                "Mid": 75.0,
                "Match Confidence": "Medium",
                "Boundary Match": False,
                "Distance Miles": 8.0,
                "Row Signal": 40.0,
                "Match Method": "Spatial",
                "Subdivision Type": "City",
                "Subdivision": "Austin City",
            },
        ]
    )
    forensics = map_runtime._build_filtered_forensics_bundle(
        overlap_rows,
        confidence_filters=["High", "Medium"],
        method_filters=["Spatial"],
        entity_query="Austin",
        min_high=0.0,
        dist_cap=25.0,
        focus_selected_subdivision=True,
        selected_type="City",
        selected_name="Austin City",
        focus_selected_clients=False,
        selected_clients=[],
        sort_mode="Highest High",
    )
    leads = forensics["leads"]
    assert list(forensics["filtered"]["TFL Entity"].unique()) == ["City of Austin"]
    assert leads.iloc[0]["Priority"] == "Tier 1"
    assert leads.iloc[0]["OverlapRows"] == 2

