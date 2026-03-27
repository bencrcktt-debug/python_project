from __future__ import annotations

from importlib import import_module
from pathlib import Path
import statistics
import sys
import time


ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "tfl_app").exists())
sys.path.insert(0, str(ROOT))


def benchmark_import(module_name: str, runs: int = 5, *, preload_streamlit: bool = True) -> dict[str, float | int | str]:
    if preload_streamlit:
        import_module("streamlit")
    samples: list[float] = []
    for _ in range(runs):
        sys.modules.pop(module_name, None)
        start = time.perf_counter()
        import_module(module_name)
        samples.append(time.perf_counter() - start)
    return {
        "module": module_name,
        "runs": runs,
        "mean_seconds": statistics.mean(samples),
        "min_seconds": min(samples),
        "max_seconds": max(samples),
    }


if __name__ == "__main__":
    targets = [
        "tfl_app.ui.fragments.page_fragments",
        "tfl_app.ui.fragments.map_fragments",
        "tfl_app.ui.renderers",
        "tfl_app.ui.renderers.map_workspace",
        "tfl_app.ui.pages.clients",
        "tfl_app.ui.pages.legislators",
        "tfl_app.ui.pages.lobbyists",
        "tfl_app.ui.pages.map_address",
    ]
    for target in targets:
        result = benchmark_import(target)
        print(
            f"{result['module']}: runs={result['runs']} mean={result['mean_seconds']:.6f} "
            f"min={result['min_seconds']:.6f} max={result['max_seconds']:.6f}"
        )



