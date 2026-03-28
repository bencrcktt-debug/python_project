# Data Notes

- Main dataset path: `data/TFL Webstite books - combined.parquet`
- Optional override: `DATA_PATH`
- Map reference snapshot path: `data/reference_snapshots`
- Optional override for snapshots: `MAP_REFERENCE_SNAPSHOT_DIR`

The app resolves data in this order:

1. `DATA_PATH`
2. repo root dataset
3. `data/` dataset

Data/runtime responsibilities are split under `tfl_app/data/`:

- `catalog.py`: table specs, parquet filename map, and grouped table-key constants.
- `loaders.py`: parquet/excel reads, normalization, dataset versioning, and manifest probes.
- `state_store.py`: cached table and app/map state accessors.
- `workspace_bundles.py`: cached session overlay and workspace bundle accessors.
