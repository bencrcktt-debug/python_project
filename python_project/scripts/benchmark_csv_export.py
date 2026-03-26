from __future__ import annotations

from pathlib import Path
import statistics
import sys
import time

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import src.ui_runtime as ui_runtime


def _fixture(rows: int = 6000) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Client": [f"Entity {idx % 250}" for idx in range(rows)],
            "LobbyShort": [f"SHORT{idx % 73:02d}" for idx in range(rows)],
            "Low": [(idx % 17) * 1000.0 for idx in range(rows)],
            "High": [(idx % 19) * 1250.0 for idx in range(rows)],
            "IsTFL": [1 if idx % 3 == 0 else 0 for idx in range(rows)],
        }
    )


def _time_call(fn, runs: int = 10) -> tuple[float, float, float]:
    samples: list[float] = []
    for _ in range(runs):
        start = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - start)
    return statistics.mean(samples), min(samples), max(samples)


if __name__ == "__main__":
    frame = _fixture()

    raw_mean, raw_min, raw_max = _time_call(lambda: frame.to_csv(index=False).encode("utf-8"))

    def _cold_cached() -> bytes:
        ui_runtime._dataframe_csv_bytes.clear()
        return ui_runtime._dataframe_csv_bytes(frame)

    cold_mean, cold_min, cold_max = _time_call(_cold_cached, runs=5)

    ui_runtime._dataframe_csv_bytes.clear()
    ui_runtime._dataframe_csv_bytes(frame)
    warm_mean, warm_min, warm_max = _time_call(lambda: ui_runtime._dataframe_csv_bytes(frame))

    print(f"raw_csv_bytes: runs=10 mean={raw_mean:.6f} min={raw_min:.6f} max={raw_max:.6f}")
    print(f"cached_csv_cold: runs=5 mean={cold_mean:.6f} min={cold_min:.6f} max={cold_max:.6f}")
    print(f"cached_csv_warm: runs=10 mean={warm_mean:.6f} min={warm_min:.6f} max={warm_max:.6f}")
