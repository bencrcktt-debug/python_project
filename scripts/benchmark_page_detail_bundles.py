from __future__ import annotations

from pathlib import Path
import statistics
import sys
import time

import pandas as pd


ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "tfl_app").exists())
sys.path.insert(0, str(ROOT))

import tfl_app.search.state as search_state
import tfl_app.bundles.page_detail_bundles as detail_bundles


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


def _fixture() -> tuple[dict, pd.DataFrame, dict[str, str], dict[str, list[str]]]:
    name_to_short = {
        search_state.norm_name("Smith, John"): "SMITHJ",
        search_state.norm_name("Doe, Jane"): "DOEJ",
    }
    short_to_names = {"SMITHJ": ["Smith, John"], "DOEJ": ["Doe, Jane"]}
    empty = pd.DataFrame()
    bill_status = pd.DataFrame(
        [
            {"Session": "89R", "Bill": "HB 1", "Author": "Bell, Keith", "Caption": "School funding", "Status": "Passed"},
            {"Session": "89R", "Bill": "HB 2", "Author": "Bell, Keith", "Caption": "Hospital funding", "Status": "Failed"},
        ]
    )
    author_bills_all = bill_status.assign(AuthorNorm=search_state.norm_name_series(bill_status["Author"]))
    data = {
        "Lobby_TFL_Client_All": pd.DataFrame(
            [
                {"Session": "89R", "Client": "City of Austin", "LobbyShort": "SMITHJ", "Lobby Name": "Smith, John", "IsTFL": 1, "Low_num": 100.0, "High_num": 200.0, "FilerID": 101},
                {"Session": "89R", "Client": "City of Austin", "LobbyShort": "DOEJ", "Lobby Name": "Doe, Jane", "IsTFL": 0, "Low_num": 50.0, "High_num": 80.0, "FilerID": 202},
            ]
        ),
        "Wit_All": pd.DataFrame(
            [
                {"Session": "89R", "Bill": "HB 1", "LobbyShort": "SMITHJ", "LobbyShortNorm": search_state.norm_name("SMITHJ"), "IsFor": 1, "IsAgainst": 0, "IsOn": 0, "org": "City of Austin", "name": "Smith, John", "NameNorm": search_state.norm_name("Smith, John"), "NameFirstNorm": search_state.norm_name("John"), "NameLastNorm": search_state.norm_name("Smith"), "NameFirstInitialNorm": "j"},
                {"Session": "89R", "Bill": "HB 2", "LobbyShort": "DOEJ", "LobbyShortNorm": search_state.norm_name("DOEJ"), "IsFor": 0, "IsAgainst": 1, "IsOn": 0, "org": "City of Austin", "name": "Doe, Jane", "NameNorm": search_state.norm_name("Doe, Jane"), "NameFirstNorm": search_state.norm_name("Jane"), "NameLastNorm": search_state.norm_name("Doe"), "NameFirstInitialNorm": "j"},
            ]
        ),
        "Bill_Status_All": bill_status,
        "Bill_Sub_All": pd.DataFrame(
            [
                {"Session": "89R", "Bill": "HB 1", "Subject": "Education"},
                {"Session": "89R", "Bill": "HB 2", "Subject": "Health"},
            ]
        ),
        "Fiscal_Impact": pd.DataFrame(
            [
                {"Session": "89R", "Bill": "HB 1", "Version": "H", "EstimatedTwoYearNetImpactGR": 1200},
            ]
        ),
        "Lobby_Sub_All": pd.DataFrame(
            [
                {"Session": "89R", "LobbyShort": "SMITHJ", "LobbyShortNorm": search_state.norm_name("SMITHJ"), "FilerID": 101, "Subject Matter": "Education", "Other Subject Matter Description": ""},
            ]
        ),
        "Staff_All": pd.DataFrame(
            [
                {
                    "Session": "89R",
                    "Legislator": "Bell, Keith",
                    "Title": "Chief of Staff",
                    "Staffer": "Smith, John",
                    "StaffNameNorm": search_state.norm_name("Smith, John"),
                    "StaffLastInitialNorm": search_state._last_first_initial_key("Smith, John"),
                    "StaffLastNorm": _last_name_norm("Smith, John"),
                    "LegislatorNorm": search_state.norm_name("Bell, Keith"),
                    "LegislatorLastNorm": _last_name_norm("Bell, Keith"),
                    "LegislatorInitKey": search_state._last_first_initial_key("Bell, Keith"),
                }
            ]
        ),
        "LaFood": pd.DataFrame(
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
        ),
        "LaEnt": empty,
        "LaTran": empty,
        "LaGift": empty,
        "LaEvnt": empty,
        "LaAwrd": empty,
        "LaCvr": pd.DataFrame(
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
        ),
        "LaDock": empty,
        "LaI4E": empty,
        "LaSub": empty,
        "filerid_to_short": {101: "SMITHJ", 202: "DOEJ"},
    }
    return data, author_bills_all, name_to_short, short_to_names


def _time_call(fn, runs: int = 10) -> tuple[float, float, float]:
    samples: list[float] = []
    for _ in range(runs):
        start = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - start)
    return statistics.mean(samples), min(samples), max(samples)


if __name__ == "__main__":
    data, author_bills_all, name_to_short, short_to_names = _fixture()

    targets = {
        "client_detail_bundle": lambda: detail_bundles.build_client_workspace_detail_bundle(
            data,
            name_to_short=name_to_short,
            session="89R",
            tfl_session_val="89R",
            client_name="City of Austin",
        ),
        "member_detail_bundle": lambda: detail_bundles.build_member_workspace_detail_bundle(
            data,
            author_bills_all=author_bills_all,
            name_to_short=name_to_short,
            short_to_names=short_to_names,
            session="89R",
            tfl_session_val="89R",
            member_name="Bell, Keith",
        ),
        "lobby_detail_bundle": lambda: detail_bundles.build_lobby_workspace_detail_bundle(
            data,
            name_to_short=name_to_short,
            short_to_names=short_to_names,
            session="89R",
            tfl_session_val="89R",
            lobbyshort="SMITHJ",
            typed_norms_tuple=tuple(sorted(search_state.norm_person_variants_with_nicknames("Smith, John"))),
            selected_names=("Smith, John",),
            selected_filer_ids=(101,),
        ),
    }

    for name, fn in targets.items():
        mean_s, min_s, max_s = _time_call(fn)
        print(f"{name}: runs=10 mean={mean_s:.6f} min={min_s:.6f} max={max_s:.6f}")


