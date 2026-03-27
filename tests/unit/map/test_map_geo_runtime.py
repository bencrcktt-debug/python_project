from __future__ import annotations

import pandas as pd

import tfl_app.map.geo_runtime as map_geo_runtime


def test_build_tfl_name_anchored_special_matches_prefers_local_anchor(monkeypatch) -> None:
    counties = pd.DataFrame(
        [
            {"name": "Travis", "fips": "453", "lon": -97.75, "lat": 30.28},
        ]
    )
    cities = pd.DataFrame(
        [
            {"name": "Austin", "basename": "Austin", "geoid": "4805000", "lon": -97.74, "lat": 30.27},
        ]
    )

    monkeypatch.setattr(map_geo_runtime, "fetch_tea_county_centroids", lambda: counties)
    monkeypatch.setattr(map_geo_runtime, "fetch_texas_city_centroids", lambda: cities)
    monkeypatch.setattr(
        map_geo_runtime,
        "geocode_texas_entity_arcgis",
        lambda entity_name: (_ for _ in ()).throw(AssertionError("geocode should not run for local anchor matches")),
    )

    result = map_geo_runtime.build_tfl_name_anchored_special_matches(("Travis County Appraisal District",))

    assert len(result) == 1
    row = result.iloc[0]
    assert row["subdivision_type"] == "Appraisal District"
    assert row["subdivision_name"] == "Travis County Appraisal District"
    assert row["source_name"] == "Name-anchored county centroid proxy"
    assert row["subdivision_code"] == "453"


def test_build_tfl_name_anchored_special_matches_falls_back_to_geocode(monkeypatch) -> None:
    monkeypatch.setattr(map_geo_runtime, "fetch_tea_county_centroids", lambda: pd.DataFrame())
    monkeypatch.setattr(map_geo_runtime, "fetch_texas_city_centroids", lambda: pd.DataFrame([{"name": "Austin", "basename": "Austin", "geoid": "4805000", "lon": -97.74, "lat": 30.27}]))
    monkeypatch.setattr(
        map_geo_runtime,
        "geocode_texas_entity_arcgis",
        lambda entity_name: {
            "score": 92.0,
            "postal": "78701",
            "lon": -97.7431,
            "lat": 30.2672,
        },
    )

    result = map_geo_runtime.build_tfl_name_anchored_special_matches(("Mystery Transit Authority",))

    assert len(result) == 1
    row = result.iloc[0]
    assert row["subdivision_type"] == "Transit Authority"
    assert row["subdivision_name"] == "Mystery Transit Authority"
    assert row["source_name"] == "ArcGIS geocoded entity centroid (Texas)"
    assert row["subdivision_code"] == "78701"

