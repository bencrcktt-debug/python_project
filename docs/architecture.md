# Architecture

The runtime is organized around the `tfl_app/` package.

- `tfl_app.entrypoints`: stable Streamlit bootstrap plus split navigation, chrome, and service-registry helpers.
- `tfl_app.config`: app paths, component locations, and map source constants.
- `tfl_app.data`: public `app_runtime` facade over table catalog, dataset loaders, cached state stores, and workspace bundle accessors.
- `tfl_app.search`: public `state` facade over shared search models, lookup indexes, and navigation/query resolution helpers.
- `tfl_app.map`: reference snapshot IO, geospatial matching, map state, and forensics helpers.
- `tfl_app.bundles`: reusable overview/detail dataframe builders.
- `tfl_app.shared`: cross-cutting normalization, session, vectorized-series, workspace, and session-state helpers.
- `tfl_app.ui`: page shells, fragments, renderers, page-state defaults, grouped runtime helper facades, and shared UI helpers.
- `tfl_app.reports`: report/export accessors layered over the UI runtime.

The application entry flow is:

1. `main.py`
2. `tfl_app.entrypoints.streamlit_app`
3. `tfl_app.ui.pages.*`
4. `tfl_app.ui.fragments.*`
5. `tfl_app.ui.renderers.*`

Compatibility is preserved by keeping the historic facades in place:

- `tfl_app.entrypoints.streamlit_app` remains the stable import target.
- `tfl_app.data.app_runtime` remains the public data/runtime facade.
- `tfl_app.search.state` remains the public search/runtime facade.
- `tfl_app.ui.runtime` remains the public UI helper facade while grouped modules expose focused internal slices.
