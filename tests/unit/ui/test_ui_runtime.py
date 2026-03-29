from __future__ import annotations

import pandas as pd

import tfl_app.bundles.page_bundles as page_bundles
import tfl_app.ui.runtime_exports as ui_runtime_exports


def test_dataframe_csv_bytes_matches_pandas_to_csv() -> None:
    df = pd.DataFrame(
        [
            {"Client": "City of Austin", "Low": 100.0, "High": 200.0},
            {"Client": "County of Travis", "Low": 50.0, "High": 80.0},
        ]
    )

    ui_runtime_exports._dataframe_csv_bytes.clear()
    expected = df.to_csv(index=False).encode("utf-8")

    assert ui_runtime_exports._dataframe_csv_bytes(df) == expected


def test_build_data_health_table_supports_manifest_metadata() -> None:
    health = page_bundles.build_data_health_table(
        {
            "LaFood": {
                "rows": 7,
                "cols": 3,
                "has_session": True,
                "empty": False,
                "sessions": 2,
                "lobby_count": 1,
            }
        },
        {"LaFood": "Food"},
    )

    row = health.loc[health["Source"] == "Food"].iloc[0]
    assert int(row["Rows"]) == 7
    assert int(row["Cols"]) == 3
    assert row["Has Session"] == "Yes"
    assert row["Empty"] == "No"


def test_ensure_cols_avoids_copy_when_all_columns_are_present() -> None:
    df = pd.DataFrame([{"Client": "City of Austin", "Low": 100.0}])

    same = page_bundles.ensure_cols(df, {"Client": "", "Low": 0.0})
    expanded = page_bundles.ensure_cols(df, {"Client": "", "Low": 0.0, "High": 0.0})

    assert same is df
    assert expanded is not df
    assert "High" not in df.columns
    assert list(expanded["High"]) == [0.0]

