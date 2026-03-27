from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "tfl_app").exists())
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tfl_app.map.reference_runtime import (
    REFERENCE_SNAPSHOT_DIR,
    list_reference_snapshot_paths,
    refresh_all_reference_snapshots,
    refresh_reference_snapshot,
)


def _parse_args() -> argparse.Namespace:
    snapshot_keys = sorted(list_reference_snapshot_paths().keys())
    parser = argparse.ArgumentParser(description="Refresh local map reference snapshot parquet files.")
    parser.add_argument(
        "--snapshot",
        choices=snapshot_keys,
        help="Refresh only one snapshot instead of the full set.",
    )
    parser.add_argument(
        "--snapshot-dir",
        default=str(REFERENCE_SNAPSHOT_DIR),
        help="Directory to write snapshot parquet files into.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    snapshot_dir = Path(args.snapshot_dir).resolve()

    if args.snapshot:
        written = {
            args.snapshot: refresh_reference_snapshot(args.snapshot, snapshot_dir=snapshot_dir),
        }
    else:
        written = refresh_all_reference_snapshots(snapshot_dir=snapshot_dir)

    for key, path in written.items():
        print(f"{key}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


