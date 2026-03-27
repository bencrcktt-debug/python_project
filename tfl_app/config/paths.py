from __future__ import annotations

import os
from pathlib import Path

DEFAULT_DATA_FILENAME = "TFL Webstite books - combined.parquet"
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
ASSETS_DIR = REPO_ROOT / "assets"
COMPONENTS_DIR = ASSETS_DIR / "components"
REFERENCE_SNAPSHOT_DIR = Path(
    os.getenv(
        "MAP_REFERENCE_SNAPSHOT_DIR",
        DATA_DIR / "reference_snapshots",
    )
)


def resolve_data_path() -> str:
    env_path = os.getenv("DATA_PATH", "").strip()
    if env_path:
        return env_path

    candidates = (
        REPO_ROOT / DEFAULT_DATA_FILENAME,
        DATA_DIR / DEFAULT_DATA_FILENAME,
        REPO_ROOT / "python_project" / DEFAULT_DATA_FILENAME,
        REPO_ROOT / "python_project" / "data" / DEFAULT_DATA_FILENAME,
    )
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return ""
