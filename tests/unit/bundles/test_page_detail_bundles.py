from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

import tfl_app.search.state as search_state
import tfl_app.bundles.page_detail_bundles as detail_bundles
import tfl_app.ui.fragments.page_fragments as page_fragments


def _last_name_norm(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    if "," in value:
        value = value.split(",", 1)[0].strip()
    else:
        parts = value.split()
        value = parts[-1] if parts else ""
    return search_state.norm_name(value)


def _name_to_short(*pairs: tuple[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for name, short in pairs:
        out[search_state.norm_name(name)] = short
    return out


def _empty_activity_df() -> pd.DataFrame:
    return pd.DataFrame()


def _base_detail_fixture() -> dict[str, Any]:
    name_to_short = _name_to_short(("Smith, John", "SMITHJ"), ("Doe, Jane", "DOEJ"))
    short_to_names = {
        "SMITHJ": ["Smith, John"],
        "DOEJ": ["Doe, Jane"],
    }
    filerid_to_short = {101: "SMITHJ", 202: "DOEJ"}

    lobby_tfl = pd.DataFrame(
        [
            {
                "Session": "89R",
                "Client": "City of Austin",
                "LobbyShort": "SMITHJ",
                "Lobby Name": "Smith, John",
                "IsTFL": 1,
                "Low_num": 100.0,
                "High_num": 200.0,
                "FilerID": 101,
            },
            {
                "Session": "89R",
                "Client": "City of Austin",
                "LobbyShort": "DOEJ",
                "Lobby Name": "Doe, Jane",
                "IsTFL": 0,
                "Low_num": 50.0,
                "High_num": 80.0,
                "FilerID": 202,
            },
            {
                "Session": "89R",
                "Client": "County of Travis",
                "LobbyShort": "SMITHJ",
                "Lobby Name": "Smith, John",
                "IsTFL": 1,
                "Low_num": 70.0,
                "High_num": 140.0,
                "FilerID": 101,
            },
        ]
    )

    wit = pd.DataFrame(
        [
            {
                "Session": "89R",
                "Bill": "HB 1",
                "LobbyShort": "SMITHJ",
                "LobbyShortNorm": search_state.norm_name("SMITHJ"),
                "IsFor": 1,
                "IsAgainst": 0,
                "IsOn": 0,
                "org": "City of Austin",
                "name": "Smith, John",
                "NameNorm": search_state.norm_name("Smith, John"),
                "NameFirstNorm": search_state.norm_name("John"),
                "NameLastNorm": search_state.norm_name("Smith"),
                "NameFirstInitialNorm": "j",
            },
            {
                "Session": "89R",
                "Bill": "HB 2",
                "LobbyShort": "DOEJ",
                "LobbyShortNorm": search_state.norm_name("DOEJ"),
                "IsFor": 0,
                "IsAgainst": 1,
                "IsOn": 0,
                "org": "City of Austin",
                "name": "Doe, Jane",
                "NameNorm": search_state.norm_name("Doe, Jane"),
                "NameFirstNorm": search_state.norm_name("Jane"),
                "NameLastNorm": search_state.norm_name("Doe"),
                "NameFirstInitialNorm": "j",
            },
            {
                "Session": "89R",
                "Bill": "HB 3",
                "LobbyShort": "SMITHJ",
                "LobbyShortNorm": search_state.norm_name("SMITHJ"),
                "IsFor": 0,
                "IsAgainst": 1,
                "IsOn": 0,
                "org": "County of Travis",
                "name": "Smith, John",
                "NameNorm": search_state.norm_name("Smith, John"),
                "NameFirstNorm": search_state.norm_name("John"),
                "NameLastNorm": search_state.norm_name("Smith"),
                "NameFirstInitialNorm": "j",
            },
        ]
    )

    bill_status = pd.DataFrame(
        [
            {"Session": "89R", "Bill": "HB 1", "Author": "Bell, Keith", "Caption": "School funding", "Status": "Passed", "Link": "https://example.com/hb1"},
            {"Session": "89R", "Bill": "HB 2", "Author": "Bell, Keith", "Caption": "Hospital funding", "Status": "Failed", "Link": "https://example.com/hb2"},
            {"Session": "89R", "Bill": "HB 3", "Author": "Bell, Keith", "Caption": "Transit funding", "Status": "Failed", "Link": "https://example.com/hb3"},
        ]
    )
    author_bills_all = bill_status.assign(AuthorNorm=search_state.norm_name_series(bill_status["Author"]))

    fiscal_impact = pd.DataFrame(
        [
            {"Session": "89R", "Bill": "HB 1", "Version": "H", "EstimatedTwoYearNetImpactGR": 1200},
            {"Session": "89R", "Bill": "HB 3", "Version": "S", "EstimatedTwoYearNetImpactGR": -300},
        ]
    )

    bill_subjects = pd.DataFrame(
        [
            {"Session": "89R", "Bill": "HB 1", "Subject": "Education"},
            {"Session": "89R", "Bill": "HB 2", "Subject": "Health"},
            {"Session": "89R", "Bill": "HB 3", "Subject": "Transportation"},
        ]
    )

    lobby_subjects = pd.DataFrame(
        [
            {
                "Session": "89R",
                "LobbyShort": "SMITHJ",
                "LobbyShortNorm": search_state.norm_name("SMITHJ"),
                "FilerID": 101,
                "Subject Matter": "Education",
                "Other Subject Matter Description": "",
            },
            {
                "Session": "89R",
                "LobbyShort": "SMITHJ",
                "LobbyShortNorm": search_state.norm_name("SMITHJ"),
                "FilerID": 101,
                "Subject Matter": "",
                "Other Subject Matter Description": "School finance",
            },
            {
                "Session": "89R",
                "LobbyShort": "DOEJ",
                "LobbyShortNorm": search_state.norm_name("DOEJ"),
                "FilerID": 202,
                "Subject Matter": "Health",
                "Other Subject Matter Description": "",
            },
        ]
    )

    staff = pd.DataFrame(
        [
            {
                "Session": "89R",
                "Legislator": "Bell, Keith",
                "Title": "Chief of Staff",
                "Staffer": "Smith, John",
                "source": "HRO",
                "StaffNameNorm": search_state.norm_name("Smith, John"),
                "StaffLastInitialNorm": search_state._last_first_initial_key("Smith, John"),
                "StaffLastNorm": _last_name_norm("Smith, John"),
                "LegislatorNorm": search_state.norm_name("Bell, Keith"),
                "LegislatorLastNorm": _last_name_norm("Bell, Keith"),
                "LegislatorInitKey": search_state._last_first_initial_key("Bell, Keith"),
            }
        ]
    )

    food = pd.DataFrame(
        [
            {
                "Session": "89R",
                "FilerID": 101,
                "filerName": "Smith, John",
                "activityDate": "2025-01-10",
                "recipientNameLast": "Bell",
                "recipientNameFirst": "Keith",
                "restaurantName": "Capitol Grill",
                "activityExactAmount": "45",
            }
        ]
    )

    coverage = pd.DataFrame(
        [
            {
                "Session": "89R",
                "FilerID": 101,
                "filerName": "Smith, John",
                "filedDt": "2025-01-12",
                "subjectMatterMemo": "Education funding",
                "filerNameOrganization": "City of Austin",
            }
        ]
    )

    empty = pd.DataFrame()
    return {
        "data": {
            "Lobby_TFL_Client_All": lobby_tfl,
            "Wit_All": wit,
            "Bill_Status_All": bill_status,
            "Bill_Sub_All": bill_subjects,
            "Fiscal_Impact": fiscal_impact,
            "Lobby_Sub_All": lobby_subjects,
            "Staff_All": staff,
            "LaFood": food,
            "LaEnt": empty,
            "LaTran": empty,
            "LaGift": empty,
            "LaEvnt": empty,
            "LaAwrd": empty,
            "LaCvr": coverage,
            "LaDock": empty,
            "LaI4E": empty,
            "LaSub": empty,
            "filerid_to_short": filerid_to_short,
        },
        "author_bills_all": author_bills_all,
        "name_to_short": name_to_short,
        "short_to_names": short_to_names,
    }


def test_build_client_workspace_detail_bundle_precomputes_rollups() -> None:
    fixture = _base_detail_fixture()
    bundle = detail_bundles.build_client_workspace_detail_bundle(
        fixture["data"],
        name_to_short=fixture["name_to_short"],
        session="89R",
        tfl_session_val="89R",
        client_name="City of Austin",
    )

    assert bundle.has_rows is True
    assert bundle.context["top_lobbyist_short"] == "SMITHJ"
    assert set(bundle.context["bills"]["Bill"]) == {"HB 1", "HB 2", "HB 3"}
    assert set(bundle.context["mentions"]["Subject"]) == {"Education", "Health", "Transportation"}
    assert set(bundle.context["lobby_sub_counts"]["Topic"]) == {"Education", "Health", "School finance"}
    assert bundle.context["activities"]["Lobbyist"].tolist() == ["Smith, John"]
    assert bundle.context["disclosures"]["Type"].tolist() == ["Coverage"]
    assert bundle.context["staff_stats"].iloc[0]["Legislator"] == "Bell, Keith"


def test_build_member_workspace_detail_bundle_precomputes_witness_and_activity_views() -> None:
    fixture = _base_detail_fixture()
    bundle = detail_bundles.build_member_workspace_detail_bundle(
        fixture["data"],
        author_bills_all=fixture["author_bills_all"],
        name_to_short=fixture["name_to_short"],
        short_to_names=fixture["short_to_names"],
        session="89R",
        tfl_session_val="89R",
        member_name="Bell, Keith",
    )

    assert bundle.has_rows is True
    assert set(bundle.context["authored"]["Bill"]) == {"HB 1", "HB 2", "HB 3"}
    assert set(bundle.context["witness"]["Lobbyist"]) == {"Smith, John", "Doe, Jane"}
    assert bundle.context["activities"].iloc[0]["Has TFL Client"] == "Yes"
    assert bundle.context["staff_lobbyists"].iloc[0]["Lobbyist"] == "Smith, John"


def test_build_lobby_workspace_detail_bundle_precomputes_match_specific_views() -> None:
    fixture = _base_detail_fixture()
    typed_norms = tuple(sorted(search_state.norm_person_variants_with_nicknames("Smith, John")))
    bundle = detail_bundles.build_lobby_workspace_detail_bundle(
        fixture["data"],
        name_to_short=fixture["name_to_short"],
        short_to_names=fixture["short_to_names"],
        session="89R",
        tfl_session_val="89R",
        lobbyshort="SMITHJ",
        typed_norms_tuple=typed_norms,
        selected_names=("Smith, John",),
        selected_filer_ids=(101,),
    )

    assert bundle.context["lobbyist_label"] == "Smith, John"
    assert bundle.context["witness_match_note"] == "Witness list filtered to the selected name."
    assert set(bundle.context["bills"]["Bill"]) == {"HB 1", "HB 3"}
    assert bundle.context["tfl_clients"] == ["City of Austin", "County of Travis"]
    assert bundle.context["private_clients"] == []
    assert bundle.context["subject_non_empty"] > 0
    assert bundle.context["activities"]["Type"].tolist() == ["Food"]
    assert bundle.context["disclosures"]["Type"].tolist() == ["Coverage"]


@dataclass(frozen=True)
class _ScopeBundle:
    overview: pd.DataFrame | None = None
    stats: dict[str, Any] | None = None
    all_legislators: pd.DataFrame | None = None
    all_stats: dict[str, Any] | None = None
    top_clients: pd.DataFrame | None = None
    lobby_display: pd.DataFrame | None = None
    trend_group: pd.DataFrame | None = None


@dataclass(frozen=True)
class _DetailBundle:
    context: dict[str, Any]


def test_fragment_rehydration_rebuilds_client_context_from_selectors() -> None:
    fixture = _base_detail_fixture()
    page_fragments.configure_page_fragment_helpers(
        get_client_scope_bundle=lambda path, scope, tfl: _ScopeBundle(
            overview=pd.DataFrame([{"Client": "City of Austin"}]),
            stats={"total_clients": 1},
        ),
        get_client_workspace_detail_bundle=lambda path, session, tfl, client_name: _DetailBundle(
            {
                "client_has_rows": True,
                "lobbyist_totals": pd.DataFrame([{"Lobbyist": "Smith, John"}]),
                "activities": pd.DataFrame([{"Type": "Food"}]),
            }
        ),
        get_member_session_bundle=lambda *args: _ScopeBundle(),
        get_member_workspace_detail_bundle=lambda *args: _DetailBundle({}),
        get_lobby_scope_bundle=lambda *args: _ScopeBundle(),
        get_lobby_workspace_detail_bundle=lambda *args: _DetailBundle({}),
    )

    ctx = page_fragments._rehydrate_fragment_ctx(
        "_client_workspace_ctx",
        {
            "PATH": "demo.parquet",
            "client_scope": "This Session",
            "client_session": "89R",
            "client_name": "City of Austin",
            "tfl_session_val": "89R",
        },
    )

    assert ctx["_prepared_client_workspace"] is True
    assert ctx["all_stats"]["total_clients"] == 1
    assert ctx["lobbyist_totals"].iloc[0]["Lobbyist"] == "Smith, John"

