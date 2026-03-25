from __future__ import annotations

from importlib import import_module
from pathlib import Path
import statistics
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
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
        "src.page_fragments",
        "src.map_fragments",
        "src.page_workspace_renderers",
        "src.map_workspace_renderer",
        "src.pages.clients",
        "src.pages.legislators",
        "src.pages.lobbyists",
        "src.pages.map_address",
    ]
    for target in targets:
        result = benchmark_import(target)
        print(
            f"{result['module']}: runs={result['runs']} mean={result['mean_seconds']:.6f} "
            f"min={result['min_seconds']:.6f} max={result['max_seconds']:.6f}"
        )
