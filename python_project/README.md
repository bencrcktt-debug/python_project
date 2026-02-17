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

## Highlights

- Global filters (session, scope, search) are summarized in the Active filters bar with a Clear filters button.
- CSV exports include active filter context in the label and filename.
- PDF reports include a cover, contents, executive summary, and sectioned tables/charts.
- Custom PDF export now offers an HTML/WeasyPrint (beta) option for richer layout alongside the legacy FPDF path.
- PDFs can optionally be saved to `./reports` with a JSON metadata sidecar (report ID, renderer, filters).

## Architecture scaffold (in progress)

The redesign toward a Bloomberg-grade reporting experience is modularized under `app/`:

- `config.py` centralizes defaults for data paths, output folders, and Plotly config.
- `context.py` defines `FilterState` and `ReportContext` objects that carry provenance through data, charts, narrative, and PDF layers.
- `data_loader.py` resolves data paths, creates a cached DuckDB connection, and exposes a place to register materialized views.
- `metrics.py` houses reusable analytics (taxpayer dependency, stance efficacy, policy concentration) returning structured results.
- `narrative.py` wraps Jinja2 templates for exec summaries, reform arguments, and methodology text.
- `pdf.py` converts HTML to PDF (WeasyPrint) and saves to `./reports`.
- `html_report.py` renders the Jinja HTML template (`templates/report.html`) that powers the HTML/WeasyPrint PDF path.
- `report_queue.py` provides a threaded queue for asynchronous PDF generation.
- `report_store.py` saves generated PDFs (FPDF or HTML/WeasyPrint) and a JSON metadata sidecar under `./reports`.
- `report_presets.py` standardizes report types (lobbyist, client, session, aggregate) and their section stacks.
- `charts.py` centralizes Plotly layout helpers and sparklines for consistent visuals.
- `layout.py` offers a shared filter bar that returns a `FilterState` for both explore and report-builder views.

These modules are scaffolding only; wire them into `main.py` incrementally by routing data access through `data_loader`, driving views from `ReportContext`, and rendering HTML-to-PDF via `narrative` + `pdf`.

## Deployment (Streamlit Community Cloud)

1. Push this repo to GitHub.
2. In Streamlit Cloud, set the app file to `main.py`.
3. Provide data in one of two ways:
   - Commit the dataset under `./data/TFL Webstite books - combined.parquet` in the repo (best for Cloud).
   - Or set `DATA_PATH` to a path inside the repo (Cloud cannot access your local machine paths).
4. The Python runtime is pinned via `runtime.txt`, and dependencies are listed in `requirements.txt`.
