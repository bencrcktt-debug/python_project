# Python Project

Streamlit app for exploring the TPPF lobby data.

## Setup

1. Create a virtual environment:
   ```bash
   python -m venv .venv
   ```
2. Activate the virtual environment.
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
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
- `python_project/main.py`: compatibility bootstrap that delegates to `main.py`.
- `tfl_app/`: application package.
  - `tfl_app/entrypoints/`: bootstrap shell, navigation helpers, page chrome, and service-registry assembly.
  - `tfl_app/data/`: public `app_runtime` facade plus split catalog, loader, cached-state, and bundle-access modules.
  - `tfl_app/search/`: public `state` facade plus shared models, index builders, and resolution helpers.
  - `tfl_app/shared/`: cross-cutting normalization, session, series, workspace, and session-state utilities.
  - `tfl_app/ui/`: pages, fragments, renderers, page-state defaults, and grouped runtime helper facades.
- `assets/components/`: custom Streamlit component assets.
- `data/`: primary parquet dataset plus reference snapshots.
- `tests/unit/` and `tests/smoke/`: canonical test locations.
- `scripts/benchmarks/`, `scripts/data/`, `scripts/maintenance/`: canonical utility script locations.
- `docs/`: architecture and layout notes.

## Verification

- Test suite: `.venv-reorg\Scripts\python.exe -m pytest -q`
- Import and bundle benchmarks: `scripts/benchmarks/`
