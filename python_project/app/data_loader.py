import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd
import streamlit as st

from .config import DEFAULT_DATA_FILENAME, ENV_DATA_PATH


def _default_candidates(default_filename: str) -> list[Path]:
    here = Path(__file__).resolve().parent
    return [
        here / default_filename,
        here / "data" / default_filename,
        here.parent / "data" / default_filename,
        here.parent / default_filename,
    ]


def resolve_data_path(default_filename: str = DEFAULT_DATA_FILENAME) -> str:
    """
    Resolve a parquet bundle path from env or common locations.
    Returns an empty string if nothing is found so callers can handle gracefully.
    """
    env_path = os.getenv(ENV_DATA_PATH, "").strip()
    if env_path:
        return env_path

    for candidate in _default_candidates(default_filename):
        if candidate.exists():
            return str(candidate)
    return ""


@st.cache_resource(show_spinner=False)
def connect_duckdb(data_path: str) -> duckdb.DuckDBPyConnection:
    """
    Create a reusable DuckDB connection and mount the parquet bundle
    as a view. Downstream modules can build materialized views on top.
    """
    if not data_path:
        raise FileNotFoundError(
            "Data path is empty. Set DATA_PATH or place the parquet bundle in ./data."
        )
    conn = duckdb.connect(database=":memory:")
    conn.execute("PRAGMA threads=4;")
    conn.execute(
        "CREATE OR REPLACE VIEW tfl_raw AS SELECT * FROM read_parquet(?);", [data_path]
    )
    return conn


@lru_cache(maxsize=32)
def fetch_df(conn: duckdb.DuckDBPyConnection, sql: str) -> pd.DataFrame:
    """
    Cached wrapper for SELECT queries. Use sparingly for hot paths
    like summary metrics; do not cache user-specific data without
    including filter keys in the SQL.
    """
    return conn.execute(sql).df()


def ensure_materialized_views(conn: duckdb.DuckDBPyConnection) -> None:
    """
    Placeholder for standardized views (sessions, lobbyist-client pairs,
    taxpayer-funded entities, witness rows, activities, staff history).
    Implement as schema knowledge solidifies.
    """
    # Example scaffold (commented until schema is confirmed):
    # conn.execute("""
    #   CREATE OR REPLACE VIEW v_compensation AS
    #   SELECT Session, Lobbyist, Client, CompLow, CompHigh, TaxpayerFunded
    #   FROM tfl_raw;
    # """)
    return None
