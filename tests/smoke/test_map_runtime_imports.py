from __future__ import annotations

import importlib


def test_reference_split_imports() -> None:
    fetchers = importlib.import_module("tfl_app.map.reference_fetchers")
    snapshots = importlib.import_module("tfl_app.map.reference_snapshots")
    runtime = importlib.import_module("tfl_app.map.reference_runtime")
    assert hasattr(fetchers, "arcgis_get_json")
    assert hasattr(snapshots, "get_reference_snapshot_version")
    assert hasattr(runtime, "fetch_tea_school_district_centroids")


def test_geo_query_imports() -> None:
    module = importlib.import_module("tfl_app.map.geo_queries")
    assert hasattr(module, "geocode_address_arcgis")
    assert hasattr(module, "query_texas_subdivisions_for_point")

