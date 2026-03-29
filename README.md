# Python Project

Streamlit app for exploring the TPPF lobby data.

## Setup

1. Create a virtual environment:
   ```bash
   python -m venv .venv
   ```
2. Activate the virtual environment.
3. Install runtime dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Install dev/test dependencies when needed:
   ```bash
   pip install -r requirements-dev.txt
   ```

## Data Configuration

The app expects a parquet dataset named `TFL Webstite books - combined.parquet`.

Provide the file using one of these options:
1. Set `DATA_PATH` to an absolute path.
2. Place the dataset at `./data/TFL Webstite books - combined.parquet`.

Reference snapshots for map lookup tables live under `./data/reference_snapshots/`.

## Running The App

```bash
streamlit run main.py
```

## Repository Layout

- `main.py`: thin Streamlit bootstrap.
- `tfl_app/`: application package.
  - `tfl_app/entrypoints/`: stable Streamlit composition root plus bootstrap/page-config assets, page-registry, nav-search, navigation, chrome, and service-registry helpers.
  - `tfl_app/data/`: catalog, loader, cached-state, and workspace-bundle modules.
  - `tfl_app/search/`: shared models plus canonical index and resolution helpers.
  - `tfl_app/map/`: reference fetchers/snapshots, split geo-query helpers, geospatial matching, and atlas/forensics helpers.
  - `tfl_app/shared/`: cross-cutting normalization, session, series, workspace, and session-state utilities.
  - `tfl_app/ui/chrome/`: shared page chrome and copy blocks.
  - `tfl_app/ui/fragments/`: selector-only fragment state plus prepared-context caches and rehydrators.
  - `tfl_app/ui/renderers/`: workspace renderers and shared renderer helpers.
  - `tfl_app/ui/contexts.py`: typed prepared-context models used between fragments and renderers.
- `assets/components/`: custom Streamlit component assets.
- `data/`: primary parquet dataset plus reference snapshots.
- `tests/unit/` and `tests/smoke/`: canonical test locations.
- `scripts/benchmarks/`, `scripts/data/`, `scripts/maintenance/`: canonical utility script locations.
- `docs/`: architecture and layout notes.

## Verification

- Test suite: `py -3.12 -m pytest -q`
- Import and bundle benchmarks: `scripts/benchmarks/`
