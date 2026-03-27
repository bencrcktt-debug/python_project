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
- `tfl_app/`: application package.
- `assets/components/`: custom Streamlit component assets.
- `data/`: primary parquet dataset plus reference snapshots.
- `tests/`: grouped unit and smoke tests.
- `scripts/`: benchmarks, data maintenance, and refactor helpers.
- `docs/`: architecture and layout notes.
