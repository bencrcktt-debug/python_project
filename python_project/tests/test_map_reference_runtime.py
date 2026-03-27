from __future__ import annotations

from pathlib import Path

import pandas as pd

import src.map_reference_runtime as map_reference_runtime


def _clear_reference_fetch_caches() -> None:
    for name in (
        "fetch_tea_school_district_centroids",
        "fetch_tea_county_centroids",
        "fetch_texas_city_centroids",
        "fetch_tceq_water_district_centroids",
        "fetch_tceq_groundwater_district_centroids",
        "fetch_texas_rma_centroids",
        "fetch_texas_junior_college_centroids",
        "fetch_texas_navigation_district_centroids",
        "fetch_nctcog_transit_provider_centroids",
        "fetch_txdot_seaport_centroids",
    ):
        func = getattr(map_reference_runtime, name, None)
        if callable(func) and hasattr(func, "clear"):
            func.clear()


def test_fetch_reference_prefers_local_snapshot(monkeypatch, tmp_path: Path) -> None:
    snapshot = pd.DataFrame(
        [
            {
                "fid": 1,
                "name": "Austin ISD",
                "name2": "Austin",
                "name20": "Austin Independent School District",
                "district_code": "227901",
                "district_code_compact": "227901",
                "lon": -97.74,
                "lat": 30.27,
            }
        ]
    )
    map_reference_runtime.write_reference_snapshot(
        "tea_school_district_centroids",
        snapshot,
        snapshot_dir=tmp_path,
    )
    original_load = map_reference_runtime.load_reference_snapshot

    _clear_reference_fetch_caches()
    monkeypatch.setattr(
        map_reference_runtime,
        "load_reference_snapshot",
        lambda snapshot_key: original_load(snapshot_key, snapshot_dir=tmp_path),
    )
    monkeypatch.setattr(
        map_reference_runtime,
        "_fetch_tea_school_district_centroids_remote",
        lambda: (_ for _ in ()).throw(AssertionError("remote fetch should not run when snapshot exists")),
    )

    result = map_reference_runtime.fetch_tea_school_district_centroids()

    assert result.equals(snapshot)


def test_fetch_reference_falls_back_to_remote_when_snapshot_missing(monkeypatch, tmp_path: Path) -> None:
    original_load = map_reference_runtime.load_reference_snapshot
    calls: list[str] = []

    _clear_reference_fetch_caches()
    monkeypatch.setattr(
        map_reference_runtime,
        "load_reference_snapshot",
        lambda snapshot_key: original_load(snapshot_key, snapshot_dir=tmp_path),
    )
    monkeypatch.setattr(
        map_reference_runtime,
        "_fetch_tea_county_centroids_remote",
        lambda: calls.append("remote")
        or pd.DataFrame(
            [
                {
                    "objectid": 1,
                    "name": "Travis",
                    "fips": "453",
                    "cntykey": "453",
                    "lon": -97.74,
                    "lat": 30.27,
                }
            ]
        ),
    )

    result = map_reference_runtime.fetch_tea_county_centroids()

    assert calls == ["remote"]
    assert list(result.columns) == ["objectid", "name", "fips", "cntykey", "lon", "lat"]
    assert result.iloc[0]["name"] == "Travis"


def test_refresh_reference_snapshot_writes_normalized_columns(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        map_reference_runtime,
        "_fetch_texas_city_centroids_remote",
        lambda: pd.DataFrame(
            [
                {
                    "objectid": 7,
                    "name": "Austin",
                    "basename": "Austin",
                    "geoid": "4805000",
                    "lon": -97.74,
                    "lat": 30.27,
                    "ignored": "value",
                }
            ]
        ),
    )

    written = map_reference_runtime.refresh_reference_snapshot(
        "texas_city_centroids",
        snapshot_dir=tmp_path,
    )
    loaded = map_reference_runtime.load_reference_snapshot(
        "texas_city_centroids",
        snapshot_dir=tmp_path,
    )

    assert written == tmp_path / "texas_city_centroids.parquet"
    assert written.exists()
    assert list(loaded.columns) == ["objectid", "name", "basename", "geoid", "lon", "lat"]
    assert loaded.iloc[0]["name"] == "Austin"
