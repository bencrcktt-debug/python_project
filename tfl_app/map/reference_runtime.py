from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

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


try:
    import urllib3 as _urllib3

    _ARCGIS_HTTP = _urllib3.PoolManager(
        num_pools=16,
        maxsize=12,
        retries=False,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=_urllib3.Timeout(connect=10, read=30),
    )
except ImportError:  # pragma: no cover - optional dependency
    _urllib3 = None  # type: ignore[assignment]
    _ARCGIS_HTTP = None  # type: ignore[assignment]


def arcgis_get_json(url: str, params: dict | None = None, timeout: int = 30, retries: int = 3) -> dict[str, Any]:
    target = url
    if params:
        target = f"{url}?{urllib.parse.urlencode(params)}"
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            if _ARCGIS_HTTP is not None and _urllib3 is not None:
                response = _ARCGIS_HTTP.request(
                    "GET",
                    target,
                    timeout=_urllib3.Timeout(connect=10, read=timeout),
                )
                return json.loads(response.data.decode("utf-8"))
            request = urllib.request.Request(target, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(min(2**attempt, 4))
    logging.warning("ArcGIS request failed after %d attempts: %s | %s", retries, target[:120], last_exc)
    raise last_exc  # type: ignore[misc]


@st.cache_data(show_spinner=False, ttl=43200, max_entries=2)
def fetch_tea_school_district_centroids() -> pd.DataFrame:
    cols = ["fid", "name", "name2", "name20", "district_code", "district_code_compact", "lon", "lat"]
    rows: list[dict[str, Any]] = []
    page_size = 1000
    offset = 0
    try:
        while True:
            payload = arcgis_get_json(
                f"{TEA_ARCGIS_SCHOOL_DISTRICT_LAYER_URL}/query",
                params={
                    "where": "1=1",
                    "outFields": "FID,NAME,NAME2,NAME20,DISTRICT,DISTRICT_C",
                    "returnGeometry": "false",
                    "returnCentroid": "true",
                    "outSR": "4326",
                    "orderByFields": "FID ASC",
                    "resultRecordCount": page_size,
                    "resultOffset": offset,
                    "f": "json",
                },
            )
            features = payload.get("features", [])
            if not features:
                break
            for feat in features:
                attrs = feat.get("attributes", {}) or {}
                centroid = feat.get("centroid", {}) or {}
                fid = attrs.get("FID")
                if fid is None:
                    continue
                try:
                    lon = float(centroid.get("x"))
                    lat = float(centroid.get("y"))
                except (TypeError, ValueError):
                    continue
                rows.append(
                    {
                        "fid": int(fid),
                        "name": str(attrs.get("NAME", "")).strip(),
                        "name2": str(attrs.get("NAME2", "")).strip(),
                        "name20": str(attrs.get("NAME20", "")).strip(),
                        "district_code": str(attrs.get("DISTRICT", "")).strip(),
                        "district_code_compact": str(attrs.get("DISTRICT_C", "")).strip(),
                        "lon": lon,
                        "lat": lat,
                    }
                )
            if len(features) < page_size:
                break
            offset += len(features)
    except Exception:
        return pd.DataFrame(columns=cols)
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows, columns=cols)


@st.cache_data(show_spinner=False, ttl=43200, max_entries=2)
def fetch_tea_county_centroids() -> pd.DataFrame:
    cols = ["objectid", "name", "fips", "cntykey", "lon", "lat"]
    rows: list[dict[str, Any]] = []
    try:
        payload = arcgis_get_json(
            f"{TEA_ARCGIS_COUNTY_LAYER_URL}/query",
            params={
                "where": "1=1",
                "outFields": "OBJECTID,FIPS,CNTYKEY,FENAME",
                "returnGeometry": "false",
                "returnCentroid": "true",
                "outSR": "4326",
                "orderByFields": "OBJECTID ASC",
                "resultRecordCount": 1000,
                "f": "json",
            },
        )
        for feat in payload.get("features", []):
            attrs = feat.get("attributes", {}) or {}
            centroid = feat.get("centroid", {}) or {}
            src_id = attrs.get("OBJECTID")
            if src_id is None:
                continue
            try:
                lon = float(centroid.get("x"))
                lat = float(centroid.get("y"))
            except (TypeError, ValueError):
                continue
            rows.append(
                {
                    "objectid": int(src_id),
                    "name": str(attrs.get("FENAME", "")).strip(),
                    "fips": str(attrs.get("FIPS", "")).strip(),
                    "cntykey": str(attrs.get("CNTYKEY", "")).strip(),
                    "lon": lon,
                    "lat": lat,
                }
            )
    except Exception:
        return pd.DataFrame(columns=cols)
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows, columns=cols)


@st.cache_data(show_spinner=False, ttl=43200, max_entries=2)
def fetch_texas_city_centroids() -> pd.DataFrame:
    cols = ["objectid", "name", "basename", "geoid", "lon", "lat"]
    rows: list[dict[str, Any]] = []
    page_size = 2000
    offset = 0
    try:
        while True:
            payload = arcgis_get_json(
                f"{CENSUS_ARCGIS_TEXAS_CITY_LAYER_URL}/query",
                params={
                    "where": "STATE='48'",
                    "outFields": "OBJECTID,NAME,BASENAME,GEOID,CENTLON,CENTLAT",
                    "returnGeometry": "false",
                    "orderByFields": "OBJECTID ASC",
                    "resultRecordCount": page_size,
                    "resultOffset": offset,
                    "f": "json",
                },
            )
            features = payload.get("features", [])
            if not features:
                break
            for feat in features:
                attrs = feat.get("attributes", {}) or {}
                src_id = attrs.get("OBJECTID")
                if src_id is None:
                    continue
                try:
                    lon = float(str(attrs.get("CENTLON", "")).strip())
                    lat = float(str(attrs.get("CENTLAT", "")).strip())
                except (TypeError, ValueError):
                    continue
                rows.append(
                    {
                        "objectid": int(src_id),
                        "name": str(attrs.get("NAME", "")).strip(),
                        "basename": str(attrs.get("BASENAME", "")).strip(),
                        "geoid": str(attrs.get("GEOID", "")).strip(),
                        "lon": lon,
                        "lat": lat,
                    }
                )
            if len(features) < page_size:
                break
            offset += len(features)
    except Exception:
        return pd.DataFrame(columns=cols)
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows, columns=cols)


@st.cache_data(show_spinner=False, ttl=43200, max_entries=2)
def fetch_tceq_water_district_centroids() -> pd.DataFrame:
    cols = ["district_name", "district_code", "type_code", "type_desc", "lon", "lat"]
    rows: list[dict[str, Any]] = []
    page_size = 2000
    offset = 0
    try:
        while True:
            payload = arcgis_get_json(
                f"{TCEQ_WATER_DISTRICTS_LAYER_URL}/query",
                params={
                    "where": "1=1",
                    "outFields": "NAME,DISTRICT_ID,TYPE,TYPE_DESCRIPTION",
                    "returnGeometry": "false",
                    "returnCentroid": "true",
                    "outSR": "4326",
                    "orderByFields": "OBJECTID ASC",
                    "resultRecordCount": page_size,
                    "resultOffset": offset,
                    "f": "json",
                },
            )
            features = payload.get("features", [])
            if not features:
                break
            for feat in features:
                attrs = feat.get("attributes", {}) or {}
                centroid = feat.get("centroid", {}) or {}
                name = str(attrs.get("NAME", "")).strip()
                if not name:
                    continue
                try:
                    lon = float(centroid.get("x"))
                    lat = float(centroid.get("y"))
                except (TypeError, ValueError):
                    continue
                rows.append(
                    {
                        "district_name": name,
                        "district_code": str(attrs.get("DISTRICT_ID", "")).strip(),
                        "type_code": str(attrs.get("TYPE", "")).strip(),
                        "type_desc": str(attrs.get("TYPE_DESCRIPTION", "")).strip(),
                        "lon": lon,
                        "lat": lat,
                    }
                )
            if len(features) < page_size:
                break
            offset += len(features)
    except Exception:
        return pd.DataFrame(columns=cols)
    if not rows:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame(rows, columns=cols)
    return out.groupby(["district_name", "district_code", "type_code", "type_desc"], as_index=False).agg(
        lon=("lon", "mean"),
        lat=("lat", "mean"),
    )


@st.cache_data(show_spinner=False, ttl=43200, max_entries=2)
def fetch_tceq_groundwater_district_centroids() -> pd.DataFrame:
    cols = ["district_name", "district_code", "lon", "lat"]
    rows: list[dict[str, Any]] = []
    page_size = 500
    offset = 0
    try:
        while True:
            payload = arcgis_get_json(
                f"{TCEQ_GROUNDWATER_DISTRICTS_LAYER_URL}/query",
                params={
                    "where": "1=1",
                    "outFields": "DISTNAME,DIST_NUM,SHORTNAM",
                    "returnGeometry": "false",
                    "returnCentroid": "true",
                    "outSR": "4326",
                    "orderByFields": "OBJECTID ASC",
                    "resultRecordCount": page_size,
                    "resultOffset": offset,
                    "f": "json",
                },
            )
            features = payload.get("features", [])
            if not features:
                break
            for feat in features:
                attrs = feat.get("attributes", {}) or {}
                centroid = feat.get("centroid", {}) or {}
                name = str(attrs.get("DISTNAME", "")).strip() or str(attrs.get("SHORTNAM", "")).strip()
                if not name:
                    continue
                try:
                    lon = float(centroid.get("x"))
                    lat = float(centroid.get("y"))
                except (TypeError, ValueError):
                    continue
                rows.append(
                    {
                        "district_name": name,
                        "district_code": str(attrs.get("DIST_NUM", "")).strip(),
                        "lon": lon,
                        "lat": lat,
                    }
                )
            if len(features) < page_size:
                break
            offset += len(features)
    except Exception:
        return pd.DataFrame(columns=cols)
    if not rows:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame(rows, columns=cols)
    return out.groupby(["district_name", "district_code"], as_index=False).agg(lon=("lon", "mean"), lat=("lat", "mean"))


@st.cache_data(show_spinner=False, ttl=43200, max_entries=2)
def fetch_texas_rma_centroids() -> pd.DataFrame:
    cols = ["district_name", "district_code", "lon", "lat"]
    rows: list[dict[str, Any]] = []
    try:
        payload = arcgis_get_json(
            f"{TEXAS_RMA_LAYER_URL}/query",
            params={
                "where": "1=1",
                "outFields": "OBJECTID,RMA,Label",
                "returnGeometry": "false",
                "returnCentroid": "true",
                "outSR": "4326",
                "orderByFields": "OBJECTID ASC",
                "resultRecordCount": 1000,
                "f": "json",
            },
        )
        for feat in payload.get("features", []):
            attrs = feat.get("attributes", {}) or {}
            centroid = feat.get("centroid", {}) or {}
            name = str(attrs.get("Label", "")).strip() or str(attrs.get("RMA", "")).strip()
            if not name:
                continue
            try:
                lon = float(centroid.get("x"))
                lat = float(centroid.get("y"))
            except (TypeError, ValueError):
                continue
            rows.append(
                {
                    "district_name": name,
                    "district_code": str(attrs.get("OBJECTID", "")).strip(),
                    "lon": lon,
                    "lat": lat,
                }
            )
    except Exception:
        return pd.DataFrame(columns=cols)
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows, columns=cols)


@st.cache_data(show_spinner=False, ttl=43200, max_entries=2)
def fetch_texas_junior_college_centroids() -> pd.DataFrame:
    cols = ["district_name", "district_code", "name2", "lon", "lat"]
    rows: list[dict[str, Any]] = []
    page_size = 500
    offset = 0
    try:
        while True:
            payload = arcgis_get_json(
                f"{TEXAS_JUNIOR_COLLEGE_LAYER_URL}/query",
                params={
                    "where": "1=1",
                    "outFields": "OBJECTID,DISTRICT,NAME1,NAME2,NAME3",
                    "returnGeometry": "false",
                    "returnCentroid": "true",
                    "outSR": "4326",
                    "orderByFields": "OBJECTID ASC",
                    "resultRecordCount": page_size,
                    "resultOffset": offset,
                    "f": "json",
                },
            )
            features = payload.get("features", [])
            if not features:
                break
            for feat in features:
                attrs = feat.get("attributes", {}) or {}
                centroid = feat.get("centroid", {}) or {}
                name1 = str(attrs.get("NAME1", "")).strip()
                name2 = str(attrs.get("NAME2", "")).strip()
                name = name1 or name2
                if not name:
                    continue
                try:
                    lon = float(centroid.get("x"))
                    lat = float(centroid.get("y"))
                except (TypeError, ValueError):
                    continue
                rows.append(
                    {
                        "district_name": name,
                        "district_code": str(attrs.get("DISTRICT", "")).strip(),
                        "name2": name2,
                        "lon": lon,
                        "lat": lat,
                    }
                )
            if len(features) < page_size:
                break
            offset += len(features)
    except Exception:
        return pd.DataFrame(columns=cols)
    if not rows:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame(rows, columns=cols)
    return out.groupby(["district_name", "district_code", "name2"], as_index=False).agg(lon=("lon", "mean"), lat=("lat", "mean"))


@st.cache_data(show_spinner=False, ttl=43200, max_entries=2)
def fetch_texas_navigation_district_centroids() -> pd.DataFrame:
    cols = ["district_name", "district_code", "lon", "lat"]
    rows: list[dict[str, Any]] = []
    page_size = 1000
    offset = 0
    try:
        while True:
            payload = arcgis_get_json(
                f"{TEXAS_NAVIGATION_DISTRICT_LAYER_URL}/query",
                params={
                    "where": "1=1",
                    "outFields": "OBJECTID,DISTRICT_N",
                    "returnGeometry": "false",
                    "returnCentroid": "true",
                    "outSR": "4326",
                    "orderByFields": "OBJECTID ASC",
                    "resultRecordCount": page_size,
                    "resultOffset": offset,
                    "f": "json",
                },
            )
            features = payload.get("features", [])
            if not features:
                break
            for feat in features:
                attrs = feat.get("attributes", {}) or {}
                centroid = feat.get("centroid", {}) or {}
                name = str(attrs.get("DISTRICT_N", "")).strip()
                if not name:
                    continue
                try:
                    lon = float(centroid.get("x"))
                    lat = float(centroid.get("y"))
                except (TypeError, ValueError):
                    continue
                rows.append(
                    {
                        "district_name": name,
                        "district_code": str(attrs.get("OBJECTID", "")).strip(),
                        "lon": lon,
                        "lat": lat,
                    }
                )
            if len(features) < page_size:
                break
            offset += len(features)
    except Exception:
        return pd.DataFrame(columns=cols)
    if not rows:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame(rows, columns=cols)
    return out.groupby(["district_name"], as_index=False).agg(
        district_code=("district_code", "min"),
        lon=("lon", "mean"),
        lat=("lat", "mean"),
    )


@st.cache_data(show_spinner=False, ttl=43200, max_entries=2)
def fetch_nctcog_transit_provider_centroids() -> pd.DataFrame:
    cols = ["provider_name", "classification", "district_code", "lon", "lat"]
    rows: list[dict[str, Any]] = []
    page_size = 1000
    offset = 0
    try:
        while True:
            payload = arcgis_get_json(
                f"{NCTCOG_TRANSIT_PROVIDERS_LAYER_URL}/query",
                params={
                    "where": "1=1",
                    "outFields": "OBJECTID,Name,Classification",
                    "returnGeometry": "true",
                    "outSR": "4326",
                    "orderByFields": "OBJECTID ASC",
                    "resultRecordCount": page_size,
                    "resultOffset": offset,
                    "f": "json",
                },
            )
            features = payload.get("features", [])
            if not features:
                break
            for feat in features:
                attrs = feat.get("attributes", {}) or {}
                geometry = feat.get("geometry", {}) or {}
                name = str(attrs.get("Name", "")).strip()
                if not name:
                    continue
                try:
                    rings = geometry.get("rings", []) or []
                    x_vals = [float(point[0]) for ring in rings for point in ring if isinstance(point, list) and len(point) >= 2]
                    y_vals = [float(point[1]) for ring in rings for point in ring if isinstance(point, list) and len(point) >= 2]
                    if not x_vals or not y_vals:
                        continue
                    lon = (min(x_vals) + max(x_vals)) / 2.0
                    lat = (min(y_vals) + max(y_vals)) / 2.0
                except (TypeError, ValueError, IndexError):
                    continue
                rows.append(
                    {
                        "provider_name": name,
                        "classification": str(attrs.get("Classification", "")).strip(),
                        "district_code": str(attrs.get("OBJECTID", "")).strip(),
                        "lon": lon,
                        "lat": lat,
                    }
                )
            if len(features) < page_size:
                break
            offset += len(features)
    except Exception:
        return pd.DataFrame(columns=cols)
    if not rows:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame(rows, columns=cols)
    return out.groupby(["provider_name", "classification", "district_code"], as_index=False).agg(
        lon=("lon", "mean"),
        lat=("lat", "mean"),
    )


@st.cache_data(show_spinner=False, ttl=43200, max_entries=2)
def fetch_txdot_seaport_centroids() -> pd.DataFrame:
    cols = ["port_name", "port_type", "port_code", "lon", "lat"]
    rows: list[dict[str, Any]] = []
    page_size = 1000
    offset = 0
    try:
        while True:
            payload = arcgis_get_json(
                f"{TXDOT_SEAPORTS_LAYER_URL}/query",
                params={
                    "where": "1=1",
                    "outFields": "OBJECTID,PORT_NM,PORT_TYPE",
                    "returnGeometry": "true",
                    "outSR": "4326",
                    "orderByFields": "OBJECTID ASC",
                    "resultRecordCount": page_size,
                    "resultOffset": offset,
                    "f": "json",
                },
            )
            features = payload.get("features", [])
            if not features:
                break
            for feat in features:
                attrs = feat.get("attributes", {}) or {}
                geometry = feat.get("geometry", {}) or {}
                name = str(attrs.get("PORT_NM", "")).strip()
                if not name:
                    continue
                try:
                    lon = float(geometry.get("x"))
                    lat = float(geometry.get("y"))
                except (TypeError, ValueError):
                    continue
                rows.append(
                    {
                        "port_name": name,
                        "port_type": str(attrs.get("PORT_TYPE", "")).strip(),
                        "port_code": str(attrs.get("OBJECTID", "")).strip(),
                        "lon": lon,
                        "lat": lat,
                    }
                )
            if len(features) < page_size:
                break
            offset += len(features)
    except Exception:
        return pd.DataFrame(columns=cols)
    if not rows:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame(rows, columns=cols)
    return out.groupby(["port_name", "port_type", "port_code"], as_index=False).agg(lon=("lon", "mean"), lat=("lat", "mean"))


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


def _normalize_reference_frame(df: pd.DataFrame | None, columns: list[str]) -> pd.DataFrame:
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
        return _normalize_reference_frame(pd.read_parquet(snapshot_path), columns)
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
    _normalize_reference_frame(df, columns).to_parquet(snapshot_path, index=False)
    return snapshot_path


def _load_or_fetch_reference_snapshot(
    snapshot_key: str,
    snapshot_version: str,
) -> pd.DataFrame:
    del snapshot_version
    cached = load_reference_snapshot(snapshot_key)
    if not cached.empty:
        return cached
    return _normalize_reference_frame(_get_reference_remote_fetcher(snapshot_key)(), _REFERENCE_SNAPSHOT_COLUMNS[snapshot_key])


_fetch_tea_school_district_centroids_remote = fetch_tea_school_district_centroids
_fetch_tea_county_centroids_remote = fetch_tea_county_centroids
_fetch_texas_city_centroids_remote = fetch_texas_city_centroids
_fetch_tceq_water_district_centroids_remote = fetch_tceq_water_district_centroids
_fetch_tceq_groundwater_district_centroids_remote = fetch_tceq_groundwater_district_centroids
_fetch_texas_rma_centroids_remote = fetch_texas_rma_centroids
_fetch_texas_junior_college_centroids_remote = fetch_texas_junior_college_centroids
_fetch_texas_navigation_district_centroids_remote = fetch_texas_navigation_district_centroids
_fetch_nctcog_transit_provider_centroids_remote = fetch_nctcog_transit_provider_centroids
_fetch_txdot_seaport_centroids_remote = fetch_txdot_seaport_centroids
_REFERENCE_REMOTE_FETCHER_NAMES: dict[str, str] = {
    "tea_school_district_centroids": "_fetch_tea_school_district_centroids_remote",
    "tea_county_centroids": "_fetch_tea_county_centroids_remote",
    "texas_city_centroids": "_fetch_texas_city_centroids_remote",
    "tceq_water_district_centroids": "_fetch_tceq_water_district_centroids_remote",
    "tceq_groundwater_district_centroids": "_fetch_tceq_groundwater_district_centroids_remote",
    "texas_rma_centroids": "_fetch_texas_rma_centroids_remote",
    "texas_junior_college_centroids": "_fetch_texas_junior_college_centroids_remote",
    "texas_navigation_district_centroids": "_fetch_texas_navigation_district_centroids_remote",
    "nctcog_transit_provider_centroids": "_fetch_nctcog_transit_provider_centroids_remote",
    "txdot_seaport_centroids": "_fetch_txdot_seaport_centroids_remote",
}


def _get_reference_remote_fetcher(snapshot_key: str) -> Callable[[], pd.DataFrame]:
    fetcher_name = _REFERENCE_REMOTE_FETCHER_NAMES[snapshot_key]
    fetcher = globals().get(fetcher_name)
    if not callable(fetcher):
        raise TypeError(f"Reference fetcher is not callable: {fetcher_name}")
    return fetcher


def refresh_reference_snapshot(
    snapshot_key: str,
    *,
    snapshot_dir: str | Path | None = None,
) -> Path:
    frame = _normalize_reference_frame(_get_reference_remote_fetcher(snapshot_key)(), _REFERENCE_SNAPSHOT_COLUMNS[snapshot_key])
    return write_reference_snapshot(snapshot_key, frame, snapshot_dir=snapshot_dir)


def refresh_all_reference_snapshots(snapshot_dir: str | Path | None = None) -> dict[str, Path]:
    written: dict[str, Path] = {}
    for snapshot_key in _REFERENCE_SNAPSHOT_COLUMNS:
        written[snapshot_key] = refresh_reference_snapshot(snapshot_key, snapshot_dir=snapshot_dir)
    return written


@st.cache_data(show_spinner=False, max_entries=16)
def _fetch_reference_snapshot_cached(snapshot_key: str, snapshot_version: str) -> pd.DataFrame:
    return _load_or_fetch_reference_snapshot(
        snapshot_key,
        snapshot_version,
    )


def fetch_tea_school_district_centroids() -> pd.DataFrame:
    return _fetch_reference_snapshot_cached("tea_school_district_centroids", get_reference_snapshot_version())


def fetch_tea_county_centroids() -> pd.DataFrame:
    return _fetch_reference_snapshot_cached("tea_county_centroids", get_reference_snapshot_version())


def fetch_texas_city_centroids() -> pd.DataFrame:
    return _fetch_reference_snapshot_cached("texas_city_centroids", get_reference_snapshot_version())


def fetch_tceq_water_district_centroids() -> pd.DataFrame:
    return _fetch_reference_snapshot_cached("tceq_water_district_centroids", get_reference_snapshot_version())


def fetch_tceq_groundwater_district_centroids() -> pd.DataFrame:
    return _fetch_reference_snapshot_cached("tceq_groundwater_district_centroids", get_reference_snapshot_version())


def fetch_texas_rma_centroids() -> pd.DataFrame:
    return _fetch_reference_snapshot_cached("texas_rma_centroids", get_reference_snapshot_version())


def fetch_texas_junior_college_centroids() -> pd.DataFrame:
    return _fetch_reference_snapshot_cached("texas_junior_college_centroids", get_reference_snapshot_version())


def fetch_texas_navigation_district_centroids() -> pd.DataFrame:
    return _fetch_reference_snapshot_cached("texas_navigation_district_centroids", get_reference_snapshot_version())


def fetch_nctcog_transit_provider_centroids() -> pd.DataFrame:
    return _fetch_reference_snapshot_cached("nctcog_transit_provider_centroids", get_reference_snapshot_version())


def fetch_txdot_seaport_centroids() -> pd.DataFrame:
    return _fetch_reference_snapshot_cached("txdot_seaport_centroids", get_reference_snapshot_version())


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


__all__ = [
    "ARCGIS_GEOCODER_URL",
    "CENSUS_ARCGIS_TEXAS_CITY_LAYER_URL",
    "MAP_BASEMAP_OPTIONS",
    "NCTCOG_TRANSIT_PROVIDERS_LAYER_URL",
    "REFERENCE_SNAPSHOT_DIR",
    "TCEQ_GROUNDWATER_DISTRICTS_LAYER_URL",
    "TCEQ_WATER_DISTRICTS_LAYER_URL",
    "TEA_ARCGIS_COUNTY_LAYER_URL",
    "TEA_ARCGIS_SCHOOL_DISTRICT_LAYER_URL",
    "TEA_ARCGIS_WEBAPP_URL",
    "TEXAS_HOUSE_DISTRICTS_LAYER_URL",
    "TEXAS_JUNIOR_COLLEGE_LAYER_URL",
    "TEXAS_NAVIGATION_DISTRICT_LAYER_URL",
    "TEXAS_RMA_LAYER_URL",
    "TEXAS_SENATE_DISTRICTS_LAYER_URL",
    "TXDOT_SEAPORTS_LAYER_URL",
    "arcgis_get_json",
    "fetch_nctcog_transit_provider_centroids",
    "fetch_tceq_groundwater_district_centroids",
    "fetch_tceq_water_district_centroids",
    "fetch_tea_county_centroids",
    "fetch_tea_school_district_centroids",
    "fetch_texas_city_centroids",
    "fetch_texas_junior_college_centroids",
    "fetch_texas_navigation_district_centroids",
    "fetch_texas_rma_centroids",
    "fetch_txdot_seaport_centroids",
    "get_reference_snapshot_version",
    "list_reference_snapshot_paths",
    "load_reference_snapshot",
    "refresh_all_reference_snapshots",
    "refresh_reference_snapshot",
    "write_reference_snapshot",
]
