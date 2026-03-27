# Data Notes

- Main dataset path: `data/TFL Webstite books - combined.parquet`
- Optional override: `DATA_PATH`
- Map reference snapshot path: `data/reference_snapshots`
- Optional override for snapshots: `MAP_REFERENCE_SNAPSHOT_DIR`

The app resolves data in this order:

1. `DATA_PATH`
2. repo root dataset
3. `data/` dataset
4. legacy `python_project/` fallbacks retained for migration safety
