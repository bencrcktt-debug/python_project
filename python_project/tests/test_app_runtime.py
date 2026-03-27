from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

import src.app_runtime as app_runtime


def test_postprocess_witness_table_keeps_session_key_without_eager_name_columns() -> None:
    witness = pd.DataFrame(
        [
            {"Session": "89R", "LobbyShort": "SMITHJ", "name": "Smith, John", "org": "City of Austin"},
        ]
    )

    processed = app_runtime._postprocess_table_for_state("Wit_All", witness)

    assert "SessionKey" in processed.columns
    assert "LobbyShort" in processed.columns
    assert "NameNorm" not in processed.columns
    assert "NameFirstNorm" not in processed.columns
    assert "NameLastNorm" not in processed.columns


def test_get_app_table_supports_copy_and_no_copy(monkeypatch) -> None:
    frame = pd.DataFrame([{"Session": "89R", "Client": "City of Austin"}])

    monkeypatch.setattr(app_runtime, "_load_table_resource", lambda path, table_key: frame)

    copied = app_runtime.get_app_table("demo.parquet", "Lobby_TFL_Client_All")
    shared = app_runtime.get_app_table("demo.parquet", "Lobby_TFL_Client_All", copy=False)

    assert shared is frame
    assert copied is not frame
    assert copied.equals(frame)

    copied.loc[0, "Client"] = "Changed"
    assert frame.loc[0, "Client"] == "City of Austin"


def test_get_witness_name_match_table_enriches_only_filtered_session(monkeypatch) -> None:
    witness = pd.DataFrame(
        [
            {"Session": "89R", "LobbyShort": "SMITHJ", "name": "Smith, John", "org": "City of Austin"},
            {"Session": "88R", "LobbyShort": "DOEJ", "name": "Doe, Jane", "org": "County of Travis"},
        ]
    )

    if hasattr(app_runtime.get_witness_name_match_table, "clear"):
        app_runtime.get_witness_name_match_table.clear()

    monkeypatch.setattr(app_runtime, "get_app_table", lambda path, key, copy=False: witness)

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
        "get_app_state",
        lambda path: SimpleNamespace(
            data={"Lobby_TFL_Client_All": lobby_tfl, "Staff_All": staff_all},
            author_bills_all=pd.DataFrame([{"Session": "89R", "Bill": "HB 1", "Author": "Bell, Keith"}]),
            name_to_short={"SMITHJOHN": "SMITHJ"},
            short_to_names={"SMITHJ": ["Smith, John"]},
        ),
    )

    def fake_overlays(path: str, session_val: str | None, keys: tuple[str, ...]) -> dict[str, pd.DataFrame]:
        captured["keys"] = keys
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
    data = captured["data"]
    assert data["Lobby_TFL_Client_All"] is lobby_tfl
    assert data["Staff_All"] is staff_all
    assert "LaCvr" not in data
    assert "LaFood" in data


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
        "get_app_state",
        lambda path: SimpleNamespace(
            data={"Lobby_TFL_Client_All": lobby_tfl, "Staff_All": staff_all},
            name_to_short={"SMITHJOHN": "SMITHJ"},
            short_to_names={"SMITHJ": ["Smith, John"]},
        ),
    )
    monkeypatch.setattr(
        app_runtime,
        "_get_workspace_table_overlays_for_keys",
        lambda path, session_val, keys: {
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
