from __future__ import annotations

from pathlib import Path
from typing import Callable

import pandas as pd
from tfl_app.config.map_sources import (
    ARCGIS_GEOCODER_URL,
    CENSUS_ARCGIS_TEXAS_CITY_LAYER_URL,
    MAP_BASEMAP_OPTIONS,
    NCTCOG_TRANSIT_PROVIDERS_LAYER_URL,
    TCEQ_GROUNDWATER_DISTRICTS_LAYER_URL,
    TCEQ_WATER_DISTRICTS_LAYER_URL,
    TEA_ARCGIS_COUNTY_LAYER_URL,
    TEA_ARCGIS_SCHOOL_DISTRICT_LAYER_URL,
    TEA_ARCGIS_WEBAPP_URL,
    TEXAS_HOUSE_DISTRICTS_LAYER_URL,
    TEXAS_JUNIOR_COLLEGE_LAYER_URL,
    TEXAS_NAVIGATION_DISTRICT_LAYER_URL,
    TEXAS_RMA_LAYER_URL,
    TEXAS_SENATE_DISTRICTS_LAYER_URL,
    TXDOT_SEAPORTS_LAYER_URL,
)
from tfl_app.map.reference_fetchers import (
    arcgis_get_json,
    fetch_nctcog_transit_provider_centroids as _fetch_nctcog_transit_provider_centroids_remote,  # noqa: F401 - used via globals()
    fetch_tceq_groundwater_district_centroids as _fetch_tceq_groundwater_district_centroids_remote,  # noqa: F401
    fetch_tceq_water_district_centroids as _fetch_tceq_water_district_centroids_remote,  # noqa: F401
    fetch_tea_county_centroids as _fetch_tea_county_centroids_remote,  # noqa: F401
    fetch_tea_school_district_centroids as _fetch_tea_school_district_centroids_remote,  # noqa: F401
    fetch_texas_city_centroids as _fetch_texas_city_centroids_remote,  # noqa: F401
    fetch_texas_junior_college_centroids as _fetch_texas_junior_college_centroids_remote,  # noqa: F401
    fetch_texas_navigation_district_centroids as _fetch_texas_navigation_district_centroids_remote,  # noqa: F401
    fetch_texas_rma_centroids as _fetch_texas_rma_centroids_remote,  # noqa: F401
    fetch_txdot_seaport_centroids as _fetch_txdot_seaport_centroids_remote,  # noqa: F401
)
from tfl_app.map.reference_snapshots import (
    REFERENCE_SNAPSHOT_DIR,
    _REFERENCE_SNAPSHOT_COLUMNS,
    get_reference_snapshot_version,
    list_reference_snapshot_paths,
    load_reference_snapshot,
    normalize_reference_frame as _normalize_reference_frame,
    write_reference_snapshot,
)

try:
    import streamlit as st
except ModuleNotFoundError:  # pragma: no cover - import smoke fallback
    class _CacheStub:
        def __call__(self, *decorator_args, **decorator_kwargs):
            if decorator_args and callable(decorator_args[0]) and len(decorator_args) == 1 and not decorator_kwargs:
                func = decorator_args[0]
                func.clear = lambda: None
                return func

            def decorator(func):
                func.clear = lambda: None
                return func

            return decorator

    class _StreamlitStub:
        cache_data = _CacheStub()

    st = _StreamlitStub()


_REFERENCE_REMOTE_FETCHER_NAMES: dict[str, str] = {
    'tea_school_district_centroids': '_fetch_tea_school_district_centroids_remote',
    'tea_county_centroids': '_fetch_tea_county_centroids_remote',
    'texas_city_centroids': '_fetch_texas_city_centroids_remote',
    'tceq_water_district_centroids': '_fetch_tceq_water_district_centroids_remote',
    'tceq_groundwater_district_centroids': '_fetch_tceq_groundwater_district_centroids_remote',
    'texas_rma_centroids': '_fetch_texas_rma_centroids_remote',
    'texas_junior_college_centroids': '_fetch_texas_junior_college_centroids_remote',
    'texas_navigation_district_centroids': '_fetch_texas_navigation_district_centroids_remote',
    'nctcog_transit_provider_centroids': '_fetch_nctcog_transit_provider_centroids_remote',
    'txdot_seaport_centroids': '_fetch_txdot_seaport_centroids_remote',
}


def _get_reference_remote_fetcher(snapshot_key: str) -> Callable[[], pd.DataFrame]:
    fetcher_name = _REFERENCE_REMOTE_FETCHER_NAMES[snapshot_key]
    fetcher = globals().get(fetcher_name)
    if not callable(fetcher):
        raise TypeError(f'Reference fetcher is not callable: {fetcher_name}')
    return fetcher


def _load_or_fetch_reference_snapshot(
    snapshot_key: str,
    snapshot_version: str,
) -> pd.DataFrame:
    del snapshot_version
    cached = load_reference_snapshot(snapshot_key)
    if not cached.empty:
        return cached
    return _normalize_reference_frame(
        _get_reference_remote_fetcher(snapshot_key)(),
        _REFERENCE_SNAPSHOT_COLUMNS[snapshot_key],
    )


@st.cache_data(show_spinner=False, max_entries=16)
def _fetch_reference_snapshot_cached(snapshot_key: str, snapshot_version: str) -> pd.DataFrame:
    return _load_or_fetch_reference_snapshot(
        snapshot_key,
        snapshot_version,
    )


def fetch_tea_school_district_centroids() -> pd.DataFrame:
    return _fetch_reference_snapshot_cached('tea_school_district_centroids', get_reference_snapshot_version())


def fetch_tea_county_centroids() -> pd.DataFrame:
    return _fetch_reference_snapshot_cached('tea_county_centroids', get_reference_snapshot_version())


def fetch_texas_city_centroids() -> pd.DataFrame:
    return _fetch_reference_snapshot_cached('texas_city_centroids', get_reference_snapshot_version())


def fetch_tceq_water_district_centroids() -> pd.DataFrame:
    return _fetch_reference_snapshot_cached('tceq_water_district_centroids', get_reference_snapshot_version())


def fetch_tceq_groundwater_district_centroids() -> pd.DataFrame:
    return _fetch_reference_snapshot_cached('tceq_groundwater_district_centroids', get_reference_snapshot_version())


def fetch_texas_rma_centroids() -> pd.DataFrame:
    return _fetch_reference_snapshot_cached('texas_rma_centroids', get_reference_snapshot_version())


def fetch_texas_junior_college_centroids() -> pd.DataFrame:
    return _fetch_reference_snapshot_cached('texas_junior_college_centroids', get_reference_snapshot_version())


def fetch_texas_navigation_district_centroids() -> pd.DataFrame:
    return _fetch_reference_snapshot_cached('texas_navigation_district_centroids', get_reference_snapshot_version())


def fetch_nctcog_transit_provider_centroids() -> pd.DataFrame:
    return _fetch_reference_snapshot_cached('nctcog_transit_provider_centroids', get_reference_snapshot_version())


def fetch_txdot_seaport_centroids() -> pd.DataFrame:
    return _fetch_reference_snapshot_cached('txdot_seaport_centroids', get_reference_snapshot_version())


for _public_fetch in (
    fetch_tea_school_district_centroids,
    fetch_tea_county_centroids,
    fetch_texas_city_centroids,
    fetch_tceq_water_district_centroids,
    fetch_tceq_groundwater_district_centroids,
    fetch_texas_rma_centroids,
    fetch_texas_junior_college_centroids,
    fetch_texas_navigation_district_centroids,
    fetch_nctcog_transit_provider_centroids,
    fetch_txdot_seaport_centroids,
):
    _public_fetch.clear = _fetch_reference_snapshot_cached.clear


def refresh_reference_snapshot(
    snapshot_key: str,
    *,
    snapshot_dir: str | Path | None = None,
) -> Path:
    frame = _normalize_reference_frame(
        _get_reference_remote_fetcher(snapshot_key)(),
        _REFERENCE_SNAPSHOT_COLUMNS[snapshot_key],
    )
    return write_reference_snapshot(snapshot_key, frame, snapshot_dir=snapshot_dir)


def refresh_all_reference_snapshots(snapshot_dir: str | Path | None = None) -> dict[str, Path]:
    written: dict[str, Path] = {}
    for snapshot_key in _REFERENCE_SNAPSHOT_COLUMNS:
        written[snapshot_key] = refresh_reference_snapshot(snapshot_key, snapshot_dir=snapshot_dir)
    return written


__all__ = [
    'ARCGIS_GEOCODER_URL',
    'CENSUS_ARCGIS_TEXAS_CITY_LAYER_URL',
    'MAP_BASEMAP_OPTIONS',
    'NCTCOG_TRANSIT_PROVIDERS_LAYER_URL',
    'REFERENCE_SNAPSHOT_DIR',
    'TCEQ_GROUNDWATER_DISTRICTS_LAYER_URL',
    'TCEQ_WATER_DISTRICTS_LAYER_URL',
    'TEA_ARCGIS_COUNTY_LAYER_URL',
    'TEA_ARCGIS_SCHOOL_DISTRICT_LAYER_URL',
    'TEA_ARCGIS_WEBAPP_URL',
    'TEXAS_HOUSE_DISTRICTS_LAYER_URL',
    'TEXAS_JUNIOR_COLLEGE_LAYER_URL',
    'TEXAS_NAVIGATION_DISTRICT_LAYER_URL',
    'TEXAS_RMA_LAYER_URL',
    'TEXAS_SENATE_DISTRICTS_LAYER_URL',
    'TXDOT_SEAPORTS_LAYER_URL',
    'arcgis_get_json',
    'fetch_nctcog_transit_provider_centroids',
    'fetch_tceq_groundwater_district_centroids',
    'fetch_tceq_water_district_centroids',
    'fetch_tea_county_centroids',
    'fetch_tea_school_district_centroids',
    'fetch_texas_city_centroids',
    'fetch_texas_junior_college_centroids',
    'fetch_texas_navigation_district_centroids',
    'fetch_texas_rma_centroids',
    'fetch_txdot_seaport_centroids',
    'get_reference_snapshot_version',
    'list_reference_snapshot_paths',
    'load_reference_snapshot',
    'refresh_all_reference_snapshots',
    'refresh_reference_snapshot',
    'write_reference_snapshot',
]