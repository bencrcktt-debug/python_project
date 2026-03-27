from __future__ import annotations

import pandas as pd

import tfl_app.ui.renderers.map_workspace as map_workspace_renderer


def test_build_overlap_probe_cached_reuses_equivalent_dataframe_inputs(monkeypatch) -> None:
    if hasattr(map_workspace_renderer._build_overlap_probe_cached, "clear"):
        map_workspace_renderer._build_overlap_probe_cached.clear()

    calls = {"query": 0, "points": 0, "spend": 0}
    overlap_subdivisions = pd.DataFrame(
        [{"subdivision_type": "City", "subdivision_name": "Austin", "subdivision_code": "001"}]
    )
    overlap_points = pd.DataFrame(
        [{"subdivision_type": "City", "subdivision_name": "Austin", "subdivision_code": "001", "lat": 30.2672, "lon": -97.7431}]
    )
    overlap_spend = pd.DataFrame(
        [{"TFL Entity": "City of Austin", "Subdivision Type": "City", "Subdivision": "Austin", "Code": "001", "High": 200.0}]
    )

    def fake_query(lon: float, lat: float) -> pd.DataFrame:
        calls["query"] += 1
        return overlap_subdivisions

    def fake_points(**kwargs) -> pd.DataFrame:
        calls["points"] += 1
        return overlap_points

    def fake_spend(**kwargs) -> pd.DataFrame:
        calls["spend"] += 1
        return overlap_spend

    monkeypatch.setattr(map_workspace_renderer, "query_texas_subdivisions_for_point", fake_query)
    monkeypatch.setattr(map_workspace_renderer, "build_overlap_map_points", fake_points)
    monkeypatch.setattr(map_workspace_renderer, "build_address_overlap_spending_rows", fake_spend)

    subdivision_matches = pd.DataFrame([{"subdivision_name": "Austin"}])
    tfl_spend = pd.DataFrame([{"TFL Entity": "City of Austin", "High": 200.0}])
    prepared_overlap_pools = {"City": pd.DataFrame([{"subdivision_name": "Austin"}])}
    spend_lookup = {"City of Austin": {"EntityType": "City", "High": 200.0}}

    first_points, first_spend = map_workspace_renderer._build_overlap_probe_cached(
        "atlas-sig",
        30.2672,
        -97.7431,
        subdivision_matches,
        tfl_spend,
        prepared_overlap_pools,
        spend_lookup,
    )
    second_points, second_spend = map_workspace_renderer._build_overlap_probe_cached(
        "atlas-sig",
        30.2672,
        -97.7431,
        subdivision_matches.copy(),
        tfl_spend.copy(),
        {"City": prepared_overlap_pools["City"].copy()},
        {"City of Austin": dict(spend_lookup["City of Austin"])},
    )

    assert calls == {"query": 1, "points": 1, "spend": 1}
    assert first_points.equals(second_points)
    assert first_spend.equals(second_spend)


def test_build_overlap_evidence_rows_cached_reuses_equivalent_dataframe_inputs(monkeypatch) -> None:
    if hasattr(map_workspace_renderer._build_overlap_evidence_rows_cached, "clear"):
        map_workspace_renderer._build_overlap_evidence_rows_cached.clear()

    classify_calls: list[str] = []

    def fake_classify(name: str) -> str:
        classify_calls.append(name)
        return "City"

    monkeypatch.setattr(map_workspace_renderer, "classify_requested_entity_type", fake_classify)

    overlap_points = pd.DataFrame(
        [{"subdivision_type": "City", "subdivision_name": "Austin", "subdivision_code": "001", "lat": 30.2672, "lon": -97.7431}]
    )
    overlap_spend = pd.DataFrame(
        [
            {
                "TFL Entity": "City of Austin",
                "Entity Type": "",
                "Low": "100",
                "High": "200",
                "Mid": "150",
                "Match Method": "Spatial Boundary",
                "Match Confidence": "High",
                "Subdivision Type": "City",
                "Subdivision": "Austin",
                "Code": "001",
            }
        ]
    )

    first = map_workspace_renderer._build_overlap_evidence_rows_cached(
        "atlas-sig",
        30.2672,
        -97.7431,
        overlap_points,
        overlap_spend,
    )
    second = map_workspace_renderer._build_overlap_evidence_rows_cached(
        "atlas-sig",
        30.2672,
        -97.7431,
        overlap_points.copy(),
        overlap_spend.copy(),
    )

    assert classify_calls == ["City of Austin"]
    assert list(first["Entity Type"]) == ["City"]
    assert "Distance Miles" in first.columns
    assert "Row Signal" in first.columns
    assert first.equals(second)

