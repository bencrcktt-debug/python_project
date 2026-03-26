from __future__ import annotations

import pandas as pd

import src.page_bundles as page_bundles
import src.ui_runtime as ui_runtime


def test_dataframe_csv_bytes_matches_pandas_to_csv() -> None:
    df = pd.DataFrame(
        [
            {"Client": "City of Austin", "Low": 100.0, "High": 200.0},
            {"Client": "County of Travis", "Low": 50.0, "High": 80.0},
        ]
    )

    ui_runtime._dataframe_csv_bytes.clear()
    expected = df.to_csv(index=False).encode("utf-8")

    assert ui_runtime._dataframe_csv_bytes(df) == expected


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
