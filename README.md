# Python Project

Streamlit app for exploring the TPPF lobby data.

## Setup

1. Create a virtual environment:
   ```bash
   python -m venv venv
   ```

2. Activate the virtual environment:
   - Windows: `venv\Scripts\activate`
   - macOS/Linux: `source venv/bin/activate`

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Data configuration

The app expects a parquet dataset named `TFL Webstite books - combined.parquet`
(this is a directory when exported as parquet, and a single file when exported as an Excel workbook).

Provide the file using one of these options:
1. Set `DATA_PATH` to an absolute path (recommended for local dev).
2. Place the dataset at `./data/TFL Webstite books - combined.parquet` in the repo
   (current default location).

Note: This project does not use `.streamlit/secrets.toml`.

## Running the app

```bash
streamlit run main.py
```

## Deployment (Streamlit Community Cloud)

1. Push this repo to GitHub.
2. In Streamlit Cloud, set the app file to `main.py`.
3. Provide data in one of two ways:
   - Commit the dataset under `./data/TFL Webstite books - combined.parquet` in the repo (best for Cloud).
   - Or set `DATA_PATH` to a path inside the repo (Cloud cannot access your local machine paths).
4. The Python runtime is pinned via `runtime.txt`, and dependencies are listed in `requirements.txt`.
