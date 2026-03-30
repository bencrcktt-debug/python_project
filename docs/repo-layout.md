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
- `tfl_app/data/`, `tfl_app/search/`, `tfl_app/map/`, and `tfl_app/ui/` contain the canonical runtime modules used by the app.
- `tfl_app/entrypoints/` contains the composition root plus bootstrap/page-config assets, page-registry, navigation, nav-search, chrome, and service-registry wiring.
- `tfl_app/map/` is split between remote reference fetchers, snapshot/version helpers, geo query helpers, geo matching/overlap helpers, and higher-level map runtime façades.
- `tfl_app/ui/chrome/` owns shared intros, guardrails, and workspace guide blocks.
- `tfl_app/ui/fragments/` owns selector persistence plus prepared-context caching and rehydration.
- `tfl_app/ui/pdf/` owns internal PDF/report builders, document shells, page helpers, section-signal helpers, chart helpers, layout primitives, runtime helpers, session-state helpers, and export utilities behind the stable `tfl_app.ui.pdf_runtime` facade.
- `tfl_app/ui/renderers/` owns workspace-specific rendering plus shared renderer helpers.
- `requirements.txt` stays runtime-only; `requirements-dev.txt` holds local test dependencies.
