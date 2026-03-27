from __future__ import annotations

import pandas as pd
import pytest

import tfl_app.map.state as map_state


@pytest.fixture
def sample_workbook() -> dict[str, object]:
    return {
        "Lobby_TFL_Client_All": pd.DataFrame(
            [
                {"Session": "88R", "Client": "City of Austin", "LobbyShort": "ALPHA", "IsTFL": 1, "Low_num": 100.0, "High_num": 200.0},
                {"Session": "89R", "Client": "City of Austin", "LobbyShort": "ALPHA", "IsTFL": 1, "Low_num": 150.0, "High_num": 250.0},
                {"Session": "89R", "Client": "Port of Houston Authority", "LobbyShort": "BETA", "IsTFL": 1, "Low_num": 60.0, "High_num": 120.0},
                {"Session": "89R", "Client": "Private Widget Co", "LobbyShort": "GAMMA", "IsTFL": 0, "Low_num": 25.0, "High_num": 50.0},
            ]
        )
    }


def _classify_entity_type(name: str) -> str:
    value = str(name).strip().lower()
    if "city" in value:
        return "City"
    if "port" in value:
        return "Port Authority"
    return "Other"


def _reference_tables() -> dict[str, pd.DataFrame]:
    return {
        "counties": pd.DataFrame([{"name": "Travis County"}]),
        "cities": pd.DataFrame([{"name": "Austin"}]),
    }


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
                "subdivision_type": "County",
                "subdivision_name": "Travis County",
                "subdivision_code": "453",
                "lon": -97.7431,
                "lat": 30.2672,
                "match_count": 1,
                "match_clients": ["City of Austin"],
                "match_clients_preview": "City of Austin",
                "source_name": "Texas Counties",
                "source_url": "https://example.com/counties",
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


def test_build_map_state_materializes_sessions_and_reference_tables(sample_workbook: dict[str, object]) -> None:
    state = map_state.build_map_state_from_sources(
        "memory://map",
        sample_workbook,
        classify_entity_type=_classify_entity_type,
        fetch_reference_tables=_reference_tables,
    )

    assert state.map_sessions == ("88R", "89R")
    assert state.default_map_session == "89R"
    assert state.all_client_names == ("City of Austin", "Port of Houston Authority")
    assert state.client_names_by_session["89R"] == ("City of Austin", "Port of Houston Authority")
    assert state.client_names_by_session["88R"] == ("City of Austin",)
    assert state.entity_type_by_client["City of Austin"] == "City"
    assert state.entity_type_by_client["Port of Houston Authority"] == "Port Authority"
    assert "ClientNorm" in state.lobby_tfl_client_all.columns
    assert "Entity Type" in state.lobby_tfl_client_all.columns
    assert set(state.reference_tables) == {"cities", "counties"}
    assert list(state.reference_tables["cities"]["name"]) == ["Austin"]


def test_build_atlas_bundle_defers_overlap_pool_prep_for_this_session(sample_workbook: dict[str, object]) -> None:
    state = map_state.build_map_state_from_sources(
        "memory://map",
        sample_workbook,
        classify_entity_type=_classify_entity_type,
        fetch_reference_tables=_reference_tables,
    )
    client_matches = _client_matches(state.all_client_names, state.reference_tables)
    client_edges = map_state.build_client_subdivision_edges(client_matches)
    prepared_calls: list[str] = []

    def prepare_overlap_pool(df: pd.DataFrame, subdivision_type: str) -> pd.DataFrame:
        prepared_calls.append(subdivision_type)
        return df.assign(prepared=subdivision_type)

    bundle = map_state.build_atlas_bundle(
        state,
        scope="This Session",
        session_for_filter="89R",
        client_subdivision_edges_all=client_edges,
        prepare_overlap_pool=prepare_overlap_pool,
    )

    assert set(bundle.tfl_spend["Client"]) == {"City of Austin", "Port of Houston Authority"}
    assert bundle.total_tfl == 2
    assert bundle.total_high == pytest.approx(370.0)
    assert bundle.mapped_high == pytest.approx(370.0)
    assert bundle.mapped_rate == pytest.approx(1.0)
    assert bundle.unmapped_count == 0
    assert set(bundle.matched_clients) == {"City of Austin", "Port of Houston Authority"}
    assert set(bundle.subdivision_matches["subdivision_name"]) == {
        "Austin City",
        "Travis County",
        "Port of Houston Authority",
    }
    assert bundle.spend_lookup["City of Austin"]["EntityType"] == "City"
    assert bundle.spend_lookup["Port of Houston Authority"]["EntityType"] == "Port Authority"
    assert bundle.prepared_overlap_pools == {}
    assert prepared_calls == []
    assert bundle.hotspot_label == "City - Austin City"
    assert bundle.hotspot_high == pytest.approx(250.0)


def test_build_atlas_bundle_includes_all_sessions_when_requested(sample_workbook: dict[str, object]) -> None:
    state = map_state.build_map_state_from_sources(
        "memory://map",
        sample_workbook,
        classify_entity_type=_classify_entity_type,
        fetch_reference_tables=_reference_tables,
    )
    client_matches = _client_matches(state.all_client_names, state.reference_tables)
    client_edges = map_state.build_client_subdivision_edges(client_matches)

    bundle = map_state.build_atlas_bundle(
        state,
        scope="All Sessions",
        session_for_filter=None,
        client_subdivision_edges_all=client_edges,
    )

    austin_city = bundle.subdivision_matches.loc[
        bundle.subdivision_matches["subdivision_name"] == "Austin City"
    ].iloc[0]
    assert austin_city["high_total"] == pytest.approx(450.0)
    assert bundle.total_high == pytest.approx(570.0)


def test_compact_payload_uses_preview_text_and_extra_count() -> None:
    payload = map_state.build_compact_map_payload(
        pd.DataFrame(
            [
                {
                    "subdivision_type": "City",
                    "subdivision_name": "Austin City",
                    "subdivision_code": "001",
                    "lon": -97.7431,
                    "lat": 30.2672,
                    "match_count": 3,
                    "match_clients": ["Alpha", "Beta", "Gamma"],
                    "high_total": 999.99,
                    "source_name": "Texas Cities",
                }
            ]
        ),
        client_preview_limit=2,
    )

    assert payload == (
        {
            "subdivision_type": "City",
            "subdivision_name": "Austin City",
            "subdivision_code": "001",
            "source_name": "Texas Cities",
            "lon": -97.7431,
            "lat": 30.2672,
            "match_count": 3,
            "high_total": 999.99,
            "match_clients_preview": "Alpha, Beta",
            "extra_count": 1,
        },
    )


def test_payload_signature_is_stable_for_identical_payloads() -> None:
    payload = (
        {
            "subdivision_type": "City",
            "subdivision_name": "Austin City",
            "subdivision_code": "001",
            "source_name": "Texas Cities",
            "lon": -97.7431,
            "lat": 30.2672,
            "match_count": 1,
            "high_total": 250.0,
            "match_clients_preview": "City of Austin",
            "extra_count": 0,
        },
    )

    signature_a = map_state.build_payload_signature(payload)
    signature_b = map_state.build_payload_signature(list(payload))

    assert signature_a == signature_b

