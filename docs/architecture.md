# Architecture

The runtime is organized around the `tfl_app/` package.

- `tfl_app.entrypoints`: stable Streamlit bootstrap plus split page-config/bootstrap assets, page-registry, nav-search, navigation, chrome, and service-registry helpers.
- `tfl_app.config`: app paths, component locations, and map source constants.
- `tfl_app.data`: table catalog, dataset loaders, cached state stores, and workspace bundle accessors.
- `tfl_app.search`: shared models plus canonical `indexes` and `resolve` runtime modules.
- `tfl_app.map`: reference fetchers, reference snapshot IO, split geo-query helpers, geospatial matching, overlap helpers, map state, and forensics helpers.
- `tfl_app.bundles`: reusable overview/detail dataframe builders.
- `tfl_app.shared`: cross-cutting normalization, session, vectorized-series, workspace, and session-state helpers.
- `tfl_app.ui`: page shells, shared chrome, typed prepared contexts, fragments, renderers, page-state defaults, grouped runtime helpers, PDF/report helper packages, and shared UI helpers.
- `tfl_app.reports`: report/export accessors layered over the UI helper modules.

The application entry flow is:

1. `main.py`
2. `tfl_app.entrypoints.streamlit_app`
3. `tfl_app.ui.pages.*`
4. `tfl_app.ui.fragments.*`
5. `tfl_app.ui.renderers.*`

- `tfl_app.entrypoints.streamlit_app` remains the stable import target.
- Canonical runtime modules live under `tfl_app.data.{catalog,loaders,state_store,workspace_bundles}`, `tfl_app.search.{models,indexes,resolve}`, `tfl_app.map.{reference_fetchers,reference_snapshots,reference_runtime,geo_queries,geo_matching,geo_overlap,geo_runtime}`, `tfl_app.ui.chrome`, `tfl_app.ui.contexts`, `tfl_app.ui.fragments.{workspace_fragments,map_workspace_fragments,prepared_cache}`, `tfl_app.ui.pdf.{builders,charts,document,layout,pages,runtime_helpers,section_conditionals,session_state,export_utils}`, and `tfl_app.ui.runtime_*`.
