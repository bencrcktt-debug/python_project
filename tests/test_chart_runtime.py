from __future__ import annotations

import pandas as pd

import tfl_app.charts.runtime as chart_runtime


def test_client_overview_chart_payload_preserves_mix_and_order() -> None:
    category_chart = pd.DataFrame(
        [
            {"SessionBase": 88, "SessionLabel": "88th", "Category": "County", "Total": 50.0},
            {"SessionBase": 89, "SessionLabel": "89th", "Category": "County", "Total": 80.0},
            {"SessionBase": 89, "SessionLabel": "89th", "Category": "Cities", "Total": 120.0},
        ]
    )

    payload = chart_runtime.build_client_overview_chart_payload(
        "sig-a",
        category_chart,
        {
            "tfl_low_total": 100.0,
            "tfl_high_total": 300.0,
            "pri_low_total": 50.0,
            "pri_high_total": 150.0,
        },
    )

    assert list(payload["mix_df"]["Funding"]) == ["Taxpayer Funded", "Private"]
    assert list(payload["mix_df"]["Total"]) == [200.0, 100.0]
    assert payload["session_labels"] == ["88th", "89th"]
    assert payload["category_order"] == ["Cities", "County"]


def test_map_atlas_chart_payload_filters_zero_high_rows() -> None:
    filtered_cov = pd.DataFrame(
        [
            {"subdivision_type": "City", "subdivision_name": "Austin", "high_total": 250.0, "match_count": 3},
            {"subdivision_type": "County", "subdivision_name": "Travis", "high_total": 0.0, "match_count": 1},
            {"subdivision_type": "City", "subdivision_name": "Dallas", "high_total": 120.0, "match_count": 2},
        ]
    )

    payload = chart_runtime.build_map_atlas_chart_payload("sig-b", filtered_cov)

    assert list(payload["tree_df"]["_name"]) == ["Austin", "Dallas"]
    assert list(payload["hist_vals"]) == [3, 1, 2]


def test_map_forensics_chart_payload_builds_chart_frames() -> None:
    filtered = pd.DataFrame(
        [
            {
                "TFL Entity": "City of Austin",
                "Entity Type": "City",
                "Low": 100.0,
                "High": 150.0,
                "Match Confidence": "High",
                "Match Method": "Spatial boundary (name)",
                "Row Signal": 95.0,
                "Distance Miles": 1.2,
            },
            {
                "TFL Entity": "County of Travis",
                "Entity Type": "County",
                "Low": 50.0,
                "High": 80.0,
                "Match Confidence": "Medium",
                "Match Method": "Name anchored",
                "Row Signal": 40.0,
                "Distance Miles": 8.4,
            },
        ]
    )
    leads = pd.DataFrame(
        [
            {"TFL Entity": "City of Austin", "LeadScore": 90.0, "Priority": "Tier 1"},
            {"TFL Entity": "County of Travis", "LeadScore": 50.0, "Priority": "Tier 2"},
        ]
    )

    payload = chart_runtime.build_map_forensics_chart_payload("sig-c", filtered, leads)

    assert list(payload["chart_df"]["Confidence"]) == ["High", "Medium"]
    assert set(payload["heat_pivot"].index.tolist()) == {"High", "Medium"}
    assert set(payload["etype_melt"]["Entity Type"].tolist()) == {"City", "County"}
    assert list(payload["chart_leads"]["Entity"]) == ["City of Austin", "County of Travis"]

