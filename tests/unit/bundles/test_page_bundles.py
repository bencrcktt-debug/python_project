from __future__ import annotations

import pandas as pd

import tfl_app.bundles.page_bundles as page_bundles


def _match_entity_type(name: str) -> tuple[str, str]:
    value = str(name).lower()
    if "city" in value:
        return "City", "Cities"
    if "county" in value:
        return "County", "Counties"
    return "Other", "Other"


def _build_category_chart_data(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "rows": int(len(df)),
                "unique_clients": int(df.get("Client", pd.Series(dtype=object)).nunique()),
            }
        ]
    )


def test_build_client_scope_bundle_filters_to_selected_session() -> None:
    df = pd.DataFrame(
        [
            {"Session": "88R", "Client": "City of Austin", "Low_num": 10.0, "High_num": 20.0, "LobbyShort": "ALPHA", "IsTFL": 1},
            {"Session": "89R", "Client": "City of Austin", "Low_num": 30.0, "High_num": 50.0, "LobbyShort": "ALPHA", "IsTFL": 1},
            {"Session": "89R", "Client": "County of Travis", "Low_num": 40.0, "High_num": 80.0, "LobbyShort": "BETA", "IsTFL": 1},
            {"Session": "89R", "Client": "Private Widget Co", "Low_num": 5.0, "High_num": 15.0, "LobbyShort": "GAMMA", "IsTFL": 0},
        ]
    )

    bundle = page_bundles.build_client_scope_bundle(
        df,
        session_val="89R",
        scope_val="This Session",
        match_entity_type=_match_entity_type,
        build_category_chart_data=_build_category_chart_data,
    )

    assert set(bundle.overview["Client"]) == {"City of Austin", "County of Travis", "Private Widget Co"}
    assert bundle.stats["total_clients"] == 3
    assert bundle.stats["tfl_clients"] == 2
    assert bundle.stats["private_clients"] == 1
    assert bundle.stats["tfl_high_total"] == 130.0
    assert bundle.overview.loc[bundle.overview["Client"] == "City of Austin", "Category"].iloc[0] == "Cities"
    assert bundle.category_chart_data.iloc[0]["rows"] == 4


def test_build_lobby_scope_bundle_returns_expected_rankings() -> None:
    df = pd.DataFrame(
        [
            {"Session": "88R", "LobbyShort": "ALPHA", "Lobby Name": "Abbott, Chris", "Client": "City of Austin", "IsTFL": 1, "Low_num": 100.0, "High_num": 200.0},
            {"Session": "89R", "LobbyShort": "ALPHA", "Lobby Name": "Abbott, Chris", "Client": "County of Travis", "IsTFL": 1, "Low_num": 50.0, "High_num": 150.0},
            {"Session": "89R", "LobbyShort": "BETA", "Lobby Name": "Jane Bell", "Client": "Private Widget Co", "IsTFL": 0, "Low_num": 75.0, "High_num": 125.0},
        ]
    )

    bundle = page_bundles.build_lobby_scope_bundle(df, session_val="89R", scope_val="This Session")

    assert bundle.all_stats["total_lobbyists"] == 2
    assert bundle.all_stats["has_tfl"] == 1
    assert bundle.all_stats["mixed"] == 0
    assert bundle.top_clients.iloc[0]["Client"] == "County of Travis"
    assert bundle.lobby_display.loc[bundle.lobby_display["LobbyShort"] == "ALPHA", "LobbyNameDisplay"].iloc[0] == "Chris Abbott"
    assert set(bundle.trend_group["SessionLabel"]) == {"88th", "89th"}


def test_build_member_session_bundle_accumulates_witness_counts() -> None:
    author_bills = pd.DataFrame(
        [
            {"Session": "89R", "Author": "Bell, Keith", "Bill": "HB 1", "Status": "Passed"},
            {"Session": "89R", "Author": "Bell, Keith", "Bill": "HB 2", "Status": "Failed"},
            {"Session": "89R", "Author": "Smith, Jane", "Bill": "SB 3", "Status": "Passed"},
        ]
    )
    wit_all = pd.DataFrame(
        [
            {"Session": "89R", "Bill": "HB 1", "LobbyShort": "ALPHA"},
            {"Session": "89R", "Bill": "HB 1", "LobbyShort": "BETA"},
            {"Session": "89R", "Bill": "HB 2", "LobbyShort": "ALPHA"},
            {"Session": "88R", "Bill": "HB 1", "LobbyShort": "OLD"},
        ]
    )

    bundle = page_bundles.build_member_session_bundle(author_bills, wit_all, "89R")

    bell = bundle.all_legislators.loc[bundle.all_legislators["Legislator"] == "Bell, Keith"].iloc[0]
    assert bundle.stats["total_legislators"] == 2
    assert bundle.stats["witness_rows"] == 3
    assert bell["Bills"] == 2
    assert bell["WitnessRows"] == 3
    assert bell["WitnessLobbyists"] == 2
    assert bell["WitnessBills"] == 2


def test_build_member_session_bundle_collapses_witness_aliases_to_canonical_lobbyist_id() -> None:
    author_bills = pd.DataFrame(
        [
            {"Session": "89R", "Author": "Bell, Keith", "Bill": "HB 1", "Status": "Passed"},
            {"Session": "89R", "Author": "Bell, Keith", "Bill": "HB 2", "Status": "Failed"},
        ]
    )
    wit_all = pd.DataFrame(
        [
            {"Session": "89R", "Bill": "HB 1", "LobbyShort": "ABBOTTC", "name": "Abbott, Chris"},
            {"Session": "89R", "Bill": "HB 2", "LobbyShort": "ALPHA", "name": "Abbott, Chris"},
            {"Session": "89R", "Bill": "HB 2", "LobbyShort": "BETA", "name": "Bell, Jane"},
        ]
    )

    bundle = page_bundles.build_member_session_bundle(
        author_bills,
        wit_all,
        "89R",
        name_to_short={
            page_bundles.norm_name("Abbott, Chris"): "ALPHA",
            page_bundles.norm_name("Bell, Jane"): "BETA",
        },
    )

    bell = bundle.all_legislators.loc[bundle.all_legislators["Legislator"] == "Bell, Keith"].iloc[0]
    assert bundle.stats["witness_rows"] == 3
    assert bundle.stats["witness_lobbyists"] == 2
    assert bundle.stats["session_lobbyists"] == 2
    assert bell["WitnessRows"] == 3
    assert bell["WitnessLobbyists"] == 2


def test_build_member_session_bundle_counts_only_session_registered_lobbyist_ids() -> None:
    author_bills = pd.DataFrame(
        [
            {"Session": "89R", "Author": "Bell, Keith", "Bill": "HB 1", "Status": "Passed"},
            {"Session": "89R", "Author": "Bell, Keith", "Bill": "HB 2", "Status": "Failed"},
        ]
    )
    wit_all = pd.DataFrame(
        [
            {"Session": "89R", "Bill": "HB 1", "LobbyShort": "ALPHA"},
            {"Session": "89R", "Bill": "HB 1", "LobbyShort": "OLDSHORT"},
            {"Session": "89R", "Bill": "HB 2", "LobbyShort": "BETA"},
        ]
    )

    bundle = page_bundles.build_member_session_bundle(
        author_bills,
        wit_all,
        "89R",
        registered_lobbyshorts={"ALPHA", "BETA"},
    )

    bell = bundle.all_legislators.loc[bundle.all_legislators["Legislator"] == "Bell, Keith"].iloc[0]
    assert bundle.stats["witness_rows"] == 3
    assert bundle.stats["witness_lobbyists"] == 2
    assert bundle.stats["session_lobbyists"] == 2
    assert bell["WitnessRows"] == 3
    assert bell["WitnessLobbyists"] == 2

