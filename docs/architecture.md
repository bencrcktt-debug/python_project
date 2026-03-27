# Architecture

The runtime is organized around the `tfl_app/` package.

- `tfl_app.entrypoints`: Streamlit bootstrap and top-level page registration.
- `tfl_app.config`: app paths, component locations, and map source constants.
- `tfl_app.data`: dataset loading, caching, manifest generation, and app/map state access.
- `tfl_app.search`: name normalization, lookup indexes, and navigation search bundles.
- `tfl_app.map`: reference snapshot IO, geospatial matching, map state, and forensics helpers.
- `tfl_app.bundles`: reusable overview/detail dataframe builders.
- `tfl_app.ui`: page shells, fragments, renderers, component runtime, and shared UI helpers.
- `tfl_app.reports`: report/export accessors layered over the UI runtime.

The application entry flow is:

1. `main.py`
2. `tfl_app.entrypoints.streamlit_app`
3. `tfl_app.ui.pages.*`
4. `tfl_app.ui.fragments.*`
5. `tfl_app.ui.renderers.*`
