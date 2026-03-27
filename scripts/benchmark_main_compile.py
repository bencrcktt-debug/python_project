from __future__ import annotations

from pathlib import Path
import statistics
import time


def benchmark_compile(path: Path, runs: int = 5) -> dict[str, float | int]:
    source = path.read_text(encoding="utf-8")
    samples: list[float] = []
    for _ in range(runs):
        start = time.perf_counter()
        compile(source, str(path), "exec")
        samples.append(time.perf_counter() - start)
    return {
        "runs": runs,
        "lines": source.count("\n") + 1,
        "mean_seconds": statistics.mean(samples),
        "min_seconds": min(samples),
        "max_seconds": max(samples),
    }


if __name__ == "__main__":
    result = benchmark_compile(Path("main.py"))
    for key, value in result.items():
        print(f"{key}={value}")
