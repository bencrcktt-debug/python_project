# Repository Layout

```text
/
  main.py
  requirements.txt
  runtime.txt
  .streamlit/
  assets/components/
  data/
  docs/
  scripts/
  tests/
  tfl_app/
```

- `assets/components/` contains the custom Streamlit component bundles and their unchanged `index.html` files.
- `data/` contains the primary dataset and supporting reference snapshot parquet files.
- `scripts/benchmarks/` contains local profiling scripts.
- `scripts/data/` contains data maintenance scripts.
- `scripts/maintenance/` contains one-off refactor helpers.
- `tests/unit/` is grouped by subsystem; `tests/smoke/` contains import/bootstrap checks.
- Root-level duplicate tests and scripts are intentionally removed so the namespaced locations above are the canonical sources.
- `tfl_app/data/`, `tfl_app/search/`, and `tfl_app/ui/` contain the canonical runtime modules used by the app.
