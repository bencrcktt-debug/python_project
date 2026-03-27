from __future__ import annotations

from typing import Any, Mapping

import pandas as pd


def ensure_cols(df: pd.DataFrame, cols_with_defaults: Mapping[str, Any]) -> pd.DataFrame:
    missing = {col: default for col, default in cols_with_defaults.items() if col not in df.columns}
    if not missing:
        return df
    out = df.copy()
    for col, default in missing.items():
        out[col] = default
    return out
