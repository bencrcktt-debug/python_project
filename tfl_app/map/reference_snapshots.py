from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import pandas as pd
from tfl_app.config.paths import REFERENCE_SNAPSHOT_DIR

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


_REFERENCE_SNAPSHOT_COLUMNS: dict[str, list[str]] = {
    "tea_school_district_centroids": ["fid", "name", "name2", "name20", "district_code", "district_code_compact", "lon", "lat"],
    "tea_county_centroids": ["objectid", "name", "fips", "cntykey", "lon", "lat"],
    "texas_city_centroids": ["objectid", "name", "basename", "geoid", "lon", "lat"],
    "tceq_water_district_centroids": ["district_name", "district_code", "type_code", "type_desc", "lon", "lat"],
    "tceq_groundwater_district_centroids": ["district_name", "district_code", "lon", "lat"],
    "texas_rma_centroids": ["district_name", "district_code", "lon", "lat"],
    "texas_junior_college_centroids": ["district_name", "district_code", "name2", "lon", "lat"],
    "texas_navigation_district_centroids": ["district_name", "district_code", "lon", "lat"],
    "nctcog_transit_provider_centroids": ["provider_name", "classification", "district_code", "lon", "lat"],
    "txdot_seaport_centroids": ["port_name", "port_type", "port_code", "lon", "lat"],
}
_REFERENCE_SNAPSHOT_FILENAMES = {
    key: f"{key}.parquet"
    for key in _REFERENCE_SNAPSHOT_COLUMNS
}


def _reference_snapshot_dir(snapshot_dir: str | Path | None = None) -> Path:
    base = Path(snapshot_dir) if snapshot_dir is not None else REFERENCE_SNAPSHOT_DIR
    return base.resolve()


@st.cache_data(show_spinner=False, max_entries=8)
def get_reference_snapshot_version(snapshot_dir: str | Path | None = None) -> str:
    base = _reference_snapshot_dir(snapshot_dir)
    digest = hashlib.sha1(str(base).encode("utf-8"))
    try:
        paths = [path for path in list_reference_snapshot_paths(base).values() if path.exists()]
    except Exception:
        paths = []
    for path in sorted(paths, key=lambda item: str(item)):
        try:
            stat = path.stat()
            payload = f"{path}|{int(stat.st_size)}|{int(getattr(stat, 'st_mtime_ns', int(stat.st_mtime * 1_000_000_000)))}"
        except Exception:
            payload = str(path)
        digest.update(payload.encode("utf-8"))
    return digest.hexdigest()


def list_reference_snapshot_paths(snapshot_dir: str | Path | None = None) -> dict[str, Path]:
    base = _reference_snapshot_dir(snapshot_dir)
    return {
        key: base / filename
        for key, filename in _REFERENCE_SNAPSHOT_FILENAMES.items()
    }


def normalize_reference_frame(df: pd.DataFrame | None, columns: list[str]) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame(columns=columns)
    out = df.copy()
    for column in columns:
        if column not in out.columns:
            out[column] = pd.NA
    return out[columns]


@st.cache_data(show_spinner=False, max_entries=32)
def _load_reference_snapshot_cached(
    snapshot_key: str,
    snapshot_version: str,
    snapshot_dir_resolved: str,
) -> pd.DataFrame:
    del snapshot_version
    columns = _REFERENCE_SNAPSHOT_COLUMNS[snapshot_key]
    snapshot_path = list_reference_snapshot_paths(snapshot_dir_resolved)[snapshot_key]
    if not snapshot_path.exists():
        return pd.DataFrame(columns=columns)
    try:
        return normalize_reference_frame(pd.read_parquet(snapshot_path), columns)
    except Exception:
        logging.warning("Failed to read reference snapshot: %s", snapshot_path)
        return pd.DataFrame(columns=columns)


def load_reference_snapshot(
    snapshot_key: str,
    *,
    snapshot_dir: str | Path | None = None,
) -> pd.DataFrame:
    resolved_dir = str(_reference_snapshot_dir(snapshot_dir))
    return _load_reference_snapshot_cached(
        snapshot_key,
        get_reference_snapshot_version(resolved_dir),
        resolved_dir,
    )


def write_reference_snapshot(
    snapshot_key: str,
    df: pd.DataFrame,
    *,
    snapshot_dir: str | Path | None = None,
) -> Path:
    columns = _REFERENCE_SNAPSHOT_COLUMNS[snapshot_key]
    snapshot_path = list_reference_snapshot_paths(snapshot_dir)[snapshot_key]
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    normalize_reference_frame(df, columns).to_parquet(snapshot_path, index=False)
    return snapshot_path


__all__ = [
    "REFERENCE_SNAPSHOT_DIR",
    "_REFERENCE_SNAPSHOT_COLUMNS",
    "_REFERENCE_SNAPSHOT_FILENAMES",
    "get_reference_snapshot_version",
    "list_reference_snapshot_paths",
    "load_reference_snapshot",
    "normalize_reference_frame",
    "write_reference_snapshot",
]

