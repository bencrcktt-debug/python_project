from __future__ import annotations

from copy import deepcopy

import pandas as pd
import pytest

import tfl_app.search.indexes as search_indexes
import tfl_app.search.resolve as search_resolve
from tfl_app.search.models import AppState, NavQueryKey, NavSearchBundle
from tfl_app.shared.names import _last_first_initial_key, norm_name


@pytest.fixture
def sample_workbook() -> dict[str, object]:
    lobby_names = pd.DataFrame(
        [
            {"LobbyShort": "ABBOTT C", "Lobby Name": "Charles Abbott", "FilerID": 101},
            {"LobbyShort": "ABBOTT C", "Lobby Name": "Chuck Abbott", "FilerID": 101},
            {"LobbyShort": "BELL J", "Lobby Name": "Jane Bell", "FilerID": 202},
        ]
    )
    lobbyist_index = search_indexes.build_lobbyist_index(lobby_names)
    return {
        "Wit_All": pd.DataFrame(
            [
                {"Session": "89R", "Bill": "HB 4", "position": "FOR", "LobbyShort": "ABBOTT C", "name": "Charles Abbott", "org": ""},
                {"Session": "88R", "Bill": "SB 7", "position": "AGAINST", "LobbyShort": "BELL J", "name": "Jane Bell", "org": ""},
            ]
        ),
        "Bill_Status_All": pd.DataFrame(
            [
                {"Session": "89R", "Bill": "HB 4", "Authors": "Bell, Keith|Smith, Jane", "Status": "Filed", "Caption": "Example bill"},
                {"Session": "88R", "Bill": "SB 7", "Authors": "Doe, John", "Status": "Passed", "Caption": "Prior bill"},
            ]
        ),
        "Lobby_TFL_Client_All": pd.DataFrame(
            [
                {"Session": "89R", "Client": "City of Austin", "Lobby Name": "Charles Abbott", "LobbyShort": "ABBOTT C", "IsTFL": 1, "Low_num": 100.0, "High_num": 200.0, "FilerID": 101},
                {"Session": "89R", "Client": "City of Dallas", "Lobby Name": "Jane Bell", "LobbyShort": "BELL J", "IsTFL": 1, "Low_num": 300.0, "High_num": 500.0, "FilerID": 202},
                {"Session": "88R", "Client": "Town of Bell", "Lobby Name": "Chuck Abbott", "LobbyShort": "ABBOTT C", "IsTFL": 0, "Low_num": 50.0, "High_num": 75.0, "FilerID": 101},
            ]
        ),
        "Staff_All": pd.DataFrame(
            [
                {"Session": "89R", "Legislator": "Bell, Keith", "Staffer": "Alex Smith"},
                {"Session": "88R", "Legislator": "Doe, John", "Staffer": "Taylor Jones"},
            ]
        ),
        "Fiscal_Impact": pd.DataFrame(),
        "Bill_Sub_All": pd.DataFrame(),
        "Lobby_Sub_All": pd.DataFrame(),
        "Lobbyist_Pol_Funds": pd.DataFrame(),
        "LaFood": pd.DataFrame(),
        "LaEnt": pd.DataFrame(),
        "LaTran": pd.DataFrame(),
        "LaGift": pd.DataFrame(),
        "LaEvnt": pd.DataFrame(),
        "LaAwrd": pd.DataFrame(),
        "LaCvr": pd.DataFrame(),
        "LaDock": pd.DataFrame(),
        "LaI4E": pd.DataFrame(),
        "LaSub": pd.DataFrame(),
        "lobby_index": lobbyist_index.copy(),
        "lobbyist_index": lobbyist_index.copy(),
        "name_to_short": {
            norm_name("Charles Abbott"): "ABBOTT C",
            norm_name("Chuck Abbott"): "ABBOTT C",
            norm_name("Jane Bell"): "BELL J",
            norm_name("Bell, Jane"): "BELL J",
        },
        "short_to_names": {
            "ABBOTT C": ["Charles Abbott", "Chuck Abbott"],
            "BELL J": ["Jane Bell"],
        },
        "known_shorts": {"ABBOTT C", "BELL J"},
        "filerid_to_short": {101: "ABBOTT C", 202: "BELL J"},
    }


@pytest.fixture
def app_state(sample_workbook: dict[str, object]) -> AppState:
    return search_indexes.build_app_state("memory://sample", sample_workbook)


def test_build_app_state_materializes_shared_indices(app_state: AppState) -> None:
    assert set(app_state.client_index["Client"]) == {"City of Austin", "City of Dallas", "Town of Bell"}
    assert set(app_state.member_index["Member"]) == {"Bell, Keith", "Smith, Jane", "Doe, John"}
    assert set(app_state.data).issuperset(
        {
            "Wit_All",
            "Bill_Status_All",
            "Lobby_TFL_Client_All",
            "Lobby_Sub_All",
            "Lobbyist_Pol_Funds",
            "client_index",
            "author_bills_all",
            "member_index",
        }
    )
    assert "LobbyShortNorm" not in app_state.data["Wit_All"].columns
    assert "NameNorm" not in app_state.data["Wit_All"].columns
    assert "Staff_All" not in app_state.data
    assert app_state.shared_sessions == ("88R", "89R")
    assert app_state.default_shared_session == "89R"
    assert app_state.map_sessions == ("88R", "89R")
    assert app_state.default_map_session == "89R"
    assert app_state.lobbyshort_to_name["ABBOTT C"] in {"Charles Abbott", "Chuck Abbott"}
    assert app_state.initial_to_short[_last_first_initial_key("Charles Abbott")] == "ABBOTT C"
    assert not app_state.client_scope_overview_all.empty
    assert not app_state.client_scope_overview_by_session.empty
    assert not app_state.client_category_chart_data.empty
    assert not app_state.lobby_scope_pivot_all.empty
    assert not app_state.lobby_scope_pivot_by_session.empty
    assert not app_state.lobby_scope_trend_group.empty
    assert not app_state.lobby_scope_top_clients_all.empty
    assert not app_state.lobby_scope_top_clients_by_session.empty
    assert not app_state.lobby_display.empty


def test_nav_search_bundle_routes_bill_queries(app_state: AppState) -> None:
    bundle = search_resolve.build_nav_search_bundle("hb4", app_state)
    assert bundle.bill_query == "HB 4"
    assert bundle.nav_suggestions == ()


def test_nav_search_bundle_resolves_exact_client(app_state: AppState) -> None:
    bundle = search_resolve.build_nav_search_bundle("City of Austin", app_state)
    assert bundle.resolved_client == "City of Austin"
    assert bundle.client_suggestions == ()


def test_nav_search_bundle_resolves_exact_member(app_state: AppState) -> None:
    bundle = search_resolve.build_nav_search_bundle("Bell, Keith", app_state)
    assert bundle.resolved_member == "Bell, Keith"
    assert all(not label.startswith("Client:") for label in bundle.nav_suggestions)


def test_nav_search_bundle_prefers_lobby_autocomplete(app_state: AppState) -> None:
    bundle = search_resolve.build_nav_search_bundle("Charles Abbott", app_state)
    assert bundle.resolved_lobby == "ABBOTT C"
    assert bundle.resolved_lobby_filer == 101
    assert any(label.startswith("Lobbyist: Charles Abbott") for label in bundle.nav_suggestions)


def test_nav_search_bundle_falls_back_to_lobbyshort_resolution(sample_workbook: dict[str, object]) -> None:
    workbook = deepcopy(sample_workbook)
    workbook["lobbyist_index"] = pd.DataFrame()
    workbook["lobby_index"] = sample_workbook["lobby_index"]
    state = search_indexes.build_app_state("memory://fallback", workbook)

    bundle = search_resolve.build_nav_search_bundle("Chuck Abbott", state)

    assert bundle.resolved_lobby == "ABBOTT C"
    assert bundle.lobby_candidates == ()


def test_nav_search_bundle_can_be_reused_for_unchanged_query(app_state: AppState) -> None:
    bundle = search_resolve.build_nav_search_bundle("Charles Abbott", app_state)
    assert search_resolve.can_reuse_nav_search_bundle(" Charles   Abbott ", bundle)
    assert not search_resolve.can_reuse_nav_search_bundle("Jane Bell", bundle)


def test_nav_search_bundle_cached_reuses_normalized_query(app_state: AppState, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}
    original = search_resolve._build_nav_search_bundle_uncached

    def wrapped(query: str, state: AppState) -> NavSearchBundle:
        calls["count"] += 1
        return original(query, state)

    search_resolve.build_nav_search_bundle_cached.clear()
    monkeypatch.setattr(search_resolve, "_build_nav_search_bundle_uncached", wrapped)

    first = search_resolve.build_nav_search_bundle_cached(NavQueryKey("Charles Abbott"), app_state)
    second = search_resolve.build_nav_search_bundle_cached(NavQueryKey(" charles   abbott "), app_state)

    assert calls["count"] == 1
    assert first.resolved_lobby == "ABBOTT C"
    assert second.resolved_lobby == "ABBOTT C"


def test_lobbyist_autocomplete_candidates_preserve_ranked_matches(app_state: AppState) -> None:
    candidates = search_resolve.lobbyist_autocomplete_candidates("Abbott", app_state.lobbyist_index)
    assert candidates
    assert candidates[0]["lobbyshort"] == "ABBOTT C"
    assert "FilerID 101" in candidates[0]["label"]


def test_build_app_state_rebuilds_lobby_lookup_state_from_raw_tables(sample_workbook: dict[str, object]) -> None:
    workbook = deepcopy(sample_workbook)
    for key in ("lobby_index", "lobbyist_index", "name_to_short", "short_to_names", "known_shorts", "filerid_to_short"):
        workbook.pop(key, None)

    state = search_indexes.build_app_state("memory://derived", workbook)

    assert not state.lobbyist_index.empty
    assert state.name_to_short[norm_name("Charles Abbott")] == "ABBOTT C"
    assert state.short_to_names["ABBOTT C"][0] in {"Charles Abbott", "Chuck Abbott"}
    candidates = search_resolve.lobbyist_autocomplete_candidates("Abbott", state.lobbyist_index)
    assert candidates
    assert candidates[0]["lobbyshort"] == "ABBOTT C"


def test_resolve_member_name_prefers_exact_normalized_match(app_state: AppState) -> None:
    resolved, suggestions = search_resolve.resolve_member_name("Keith Bell", app_state.member_index)
    assert resolved == "Bell, Keith"
    assert suggestions == []


def test_resolve_lobbyshort_from_wit_honors_session_scope(sample_workbook: dict[str, object]) -> None:
    resolved, suggestions = search_resolve.resolve_lobbyshort_from_wit("Abbott", sample_workbook["Wit_All"], "89R")
    assert resolved == "ABBOTT C"
    assert suggestions == []

