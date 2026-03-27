from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

import tfl_app.data.app_runtime as app_runtime


def test_postprocess_witness_table_precomputes_search_columns_and_session_key() -> None:
    witness = pd.DataFrame(
        [
            {"Session": "89R", "LobbyShort": "SMITHJ", "name": "Smith, John", "org": "City of Austin"},
        ]
    )

    processed = app_runtime._postprocess_table_for_state("Wit_All", witness)

    assert "SessionKey" in processed.columns
    assert "LobbyShort" in processed.columns
    assert "LobbyShortNorm" in processed.columns
    assert processed.iloc[0]["NameNorm"] == "SMITHJOHN"
    assert processed.iloc[0]["NameFirstNorm"] == "JOHN"
    assert processed.iloc[0]["NameLastNorm"] == "SMITH"


def test_get_app_table_supports_copy_and_no_copy(monkeypatch) -> None:
    frame = pd.DataFrame([{"Session": "89R", "Client": "City of Austin"}])

    monkeypatch.setattr(app_runtime, "_load_table_resource", lambda path, table_key, data_version: frame)
    monkeypatch.setattr(app_runtime, "get_dataset_version", lambda path: "v1")

    copied = app_runtime.get_app_table("demo.parquet", "Lobby_TFL_Client_All")
    shared = app_runtime.get_app_table("demo.parquet", "Lobby_TFL_Client_All", copy=False)

    assert shared is frame
    assert copied is not frame
    assert copied.equals(frame)

    copied.loc[0, "Client"] = "Changed"
    assert frame.loc[0, "Client"] == "City of Austin"


def test_readonly_table_helpers_reuse_shared_frames(monkeypatch) -> None:
    frames = {
        "Lobby_TFL_Client_All": pd.DataFrame([{"Session": "89R", "Client": "City of Austin"}]),
        "Staff_All": pd.DataFrame([{"Session": "89R", "Legislator": "Bell, Keith"}]),
    }

    monkeypatch.setattr(app_runtime, "_load_table_resource", lambda path, table_key, data_version: frames[table_key])
    monkeypatch.setattr(app_runtime, "get_dataset_version", lambda path: "v1")

    shared = app_runtime.get_app_table_readonly("demo.parquet", "Lobby_TFL_Client_All")
    grouped = app_runtime.get_app_tables_readonly("demo.parquet", ("Lobby_TFL_Client_All", "Staff_All"))

    assert shared is frames["Lobby_TFL_Client_All"]
    assert grouped["Lobby_TFL_Client_All"] is frames["Lobby_TFL_Client_All"]
    assert grouped["Staff_All"] is frames["Staff_All"]


def test_session_overlay_bundle_routes_specialized_session_tables(monkeypatch) -> None:
    if hasattr(app_runtime._get_session_overlay_bundle, "clear"):
        app_runtime._get_session_overlay_bundle.clear()

    calls: list[tuple[str, object]] = []
    witness_rows = pd.DataFrame([{"Session": "89R", "LobbyShort": "SMITHJ"}])
    lobby_sub_rows = pd.DataFrame([{"Session": "89R", "LobbyShort": "SMITHJ"}])
    filer_rows = pd.DataFrame([{"Session": "89R", "FilerID": 101}])
    bill_status = pd.DataFrame([{"Session": "89R", "Bill": "HB 1"}])

    monkeypatch.setattr(
        app_runtime,
        "_get_witness_rows_for_session",
        lambda path, data_version, session_val, include_name_columns=False: calls.append(
            ("witness", (path, data_version, session_val, include_name_columns))
        ) or witness_rows,
    )
    monkeypatch.setattr(
        app_runtime,
        "_get_lobby_sub_rows_for_session",
        lambda path, data_version, session_val: calls.append(("lobby_sub", (path, data_version, session_val))) or lobby_sub_rows,
    )
    monkeypatch.setattr(
        app_runtime,
        "_get_filer_rows_for_session",
        lambda path, table_key, data_version, session_val: calls.append(("filer", (path, table_key, data_version, session_val))) or filer_rows,
    )
    monkeypatch.setattr(
        app_runtime,
        "get_app_table_readonly",
        lambda path, table_key: calls.append(("table", (path, table_key))) or bill_status,
    )
    monkeypatch.setattr(
        app_runtime,
        "_filter_table_by_session",
        lambda df, session_val, copy=True: calls.append(("filter", (session_val, copy))) or df,
    )

    overlay_bundle = app_runtime._get_session_overlay_bundle(
        "demo.parquet",
        "v1",
        "89R",
    )

    assert set(overlay_bundle.tables) >= {"Wit_All", "Lobby_Sub_All", "LaCvr", "Bill_Status_All"}
    assert ("witness", ("demo.parquet", "v1", "89R", False)) in calls
    assert ("witness", ("demo.parquet", "v1", "89R", True)) in calls
    assert ("lobby_sub", ("demo.parquet", "v1", "89R")) in calls
    assert ("filer", ("demo.parquet", "LaCvr", "v1", "89R")) in calls
    assert ("table", ("demo.parquet", "Bill_Status_All")) in calls
    assert ("filter", ("89R", True)) in calls


def test_get_witness_name_match_table_enriches_only_filtered_session(monkeypatch) -> None:
    witness = pd.DataFrame(
        [
            {"Session": "89R", "LobbyShort": "SMITHJ", "NameNorm": "SMITHJOHN", "NameLastNorm": "SMITH", "NameFirstNorm": "JOHN", "NameFirstInitialNorm": "J"},
        ]
    )

    if hasattr(app_runtime.get_witness_name_match_table, "clear"):
        app_runtime.get_witness_name_match_table.clear()

    monkeypatch.setattr(
        app_runtime,
        "_get_session_overlay_bundle",
        lambda path, data_version, session_val: app_runtime.SessionOverlayBundle(
            session=session_val,
            tables={"Wit_All": pd.DataFrame()},
            witness_search=witness,
        ),
    )
    monkeypatch.setattr(app_runtime, "get_dataset_version", lambda path: "v1")

    enriched = app_runtime.get_witness_name_match_table("demo.parquet", "89R")

    assert list(enriched["Session"]) == ["89R"]
    assert {"NameNorm", "NameLastNorm", "NameFirstNorm", "NameFirstInitialNorm"}.issubset(enriched.columns)
    assert enriched.iloc[0]["NameNorm"] == "SMITHJOHN"


def test_member_detail_loader_uses_member_specific_workspace_keys(monkeypatch) -> None:
    if hasattr(app_runtime.get_member_workspace_detail_bundle, "clear"):
        app_runtime.get_member_workspace_detail_bundle.clear()

    lobby_tfl = pd.DataFrame([{"Session": "89R", "Client": "City of Austin"}])
    staff_all = pd.DataFrame([{"Session": "88R", "Legislator": "Bell, Keith"}])
    overlays = {
        "Wit_All": pd.DataFrame([{"Session": "89R", "Bill": "HB 1"}]),
        "LaFood": pd.DataFrame([{"Session": "89R", "filerName": "Smith, John"}]),
    }
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        app_runtime,
        "_get_app_state_cached",
        lambda path, data_version: SimpleNamespace(
            data={},
            data_version=data_version,
            author_bills_all=pd.DataFrame([{"Session": "89R", "Bill": "HB 1", "Author": "Bell, Keith"}]),
            name_to_short={"SMITHJOHN": "SMITHJ"},
            short_to_names={"SMITHJ": ["Smith, John"]},
            filerid_to_short={101: "SMITHJ"},
            initial_to_short={"SMITHJ": "SMITHJ"},
        ),
    )
    monkeypatch.setattr(app_runtime, "get_dataset_version", lambda path: "v1")
    monkeypatch.setattr(
        app_runtime,
        "get_app_table_readonly",
        lambda path, key: lobby_tfl if key == "Lobby_TFL_Client_All" else staff_all,
    )

    def fake_overlays(path: str, data_version: str, session_val: str | None, keys: tuple[str, ...]) -> dict[str, pd.DataFrame]:
        captured["keys"] = keys
        captured["data_version"] = data_version
        return overlays

    def fake_build(data: dict[str, object], **kwargs):
        captured["data"] = data
        captured["kwargs"] = kwargs
        return "member-bundle"

    monkeypatch.setattr(app_runtime, "_get_workspace_table_overlays_for_keys", fake_overlays)
    monkeypatch.setattr(app_runtime._page_detail_bundles, "build_member_workspace_detail_bundle", fake_build)

    result = app_runtime.get_member_workspace_detail_bundle("demo.parquet", "89R", "89R", "Bell, Keith")

    assert result == "member-bundle"
    assert captured["keys"] == app_runtime.MEMBER_DETAIL_TABLE_KEYS
    assert captured["data_version"] == "v1"
    data = captured["data"]
    assert data["Lobby_TFL_Client_All"] is lobby_tfl
    assert data["Staff_All"] is staff_all
    assert "LaCvr" not in data
    assert "LaFood" in data
    assert captured["kwargs"]["initial_to_short"] == {"SMITHJ": "SMITHJ"}


def test_lobby_detail_loader_uses_enriched_witness_rows_only_for_exact_name_matches(monkeypatch) -> None:
    if hasattr(app_runtime.get_lobby_workspace_detail_bundle, "clear"):
        app_runtime.get_lobby_workspace_detail_bundle.clear()

    lobby_tfl = pd.DataFrame([{"Session": "89R", "Client": "City of Austin"}])
    staff_all = pd.DataFrame([{"Session": "88R", "Legislator": "Bell, Keith"}])
    base_wit = pd.DataFrame([{"Session": "89R", "LobbyShort": "SMITHJ"}])
    enriched_wit = pd.DataFrame([{"Session": "89R", "LobbyShort": "SMITHJ", "NameNorm": "SMITHJOHN"}])
    captured: list[dict[str, object]] = []

    monkeypatch.setattr(
        app_runtime,
        "_get_app_state_cached",
        lambda path, data_version: SimpleNamespace(
            data={},
            data_version=data_version,
            name_to_short={"SMITHJOHN": "SMITHJ"},
            short_to_names={"SMITHJ": ["Smith, John"]},
            filerid_to_short={101: "SMITHJ"},
        ),
    )
    monkeypatch.setattr(app_runtime, "get_dataset_version", lambda path: "v1")
    monkeypatch.setattr(
        app_runtime,
        "get_app_table_readonly",
        lambda path, key: lobby_tfl if key == "Lobby_TFL_Client_All" else staff_all,
    )
    monkeypatch.setattr(
        app_runtime,
        "_get_workspace_table_overlays_for_keys",
        lambda path, data_version, session_val, keys: {
            "Wit_All": base_wit,
            "Bill_Status_All": pd.DataFrame(),
            "Lobby_Sub_All": pd.DataFrame(),
            "Fiscal_Impact": pd.DataFrame(),
            "Bill_Sub_All": pd.DataFrame(),
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
        },
    )
    monkeypatch.setattr(app_runtime, "get_witness_name_match_table", lambda path, session_val: enriched_wit)
    monkeypatch.setattr(
        app_runtime._page_detail_bundles,
        "build_lobby_workspace_detail_bundle",
        lambda data, **kwargs: captured.append(data) or data,
    )

    plain = app_runtime.get_lobby_workspace_detail_bundle(
        "demo.parquet",
        "89R",
        "89R",
        "SMITHJ",
        tuple(),
        tuple(),
        tuple(),
    )
    named = app_runtime.get_lobby_workspace_detail_bundle(
        "demo.parquet",
        "89R",
        "89R",
        "SMITHJ",
        tuple(),
        ("Smith, John",),
        (101,),
    )

    assert plain["Wit_All"] is base_wit
    assert named["Wit_All"] is enriched_wit
    assert captured[0]["Staff_All"] is staff_all
    assert captured[1]["Staff_All"] is staff_all

