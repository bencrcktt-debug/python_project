from __future__ import annotations

import hashlib
import json
from typing import Any

import pandas as pd


def stable_json_signature(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha1(encoded).hexdigest()


def hash_dataframe_for_cache(df: pd.DataFrame) -> str:
    try:
        digest = hashlib.sha1()
        digest.update(repr(tuple(df.columns)).encode("utf-8"))
        digest.update(repr(tuple(str(dtype) for dtype in df.dtypes)).encode("utf-8"))
        row_hash = pd.util.hash_pandas_object(df, index=False, categorize=False)
        digest.update(row_hash.to_numpy(dtype="uint64", copy=False).tobytes())
        return digest.hexdigest()
    except Exception:
        try:
            return hashlib.sha1(df.to_csv(index=False).encode("utf-8")).hexdigest()
        except Exception:
            return f"df:{id(df)}:{len(df)}:{len(df.columns)}"


def hash_dataframe_for_csv(df: pd.DataFrame) -> str:
    try:
        digest = hashlib.sha1()
        digest.update(repr(tuple(df.columns)).encode("utf-8"))
        digest.update(repr(tuple(str(dtype) for dtype in df.dtypes)).encode("utf-8"))
        row_hash = pd.util.hash_pandas_object(df, index=False, categorize=False)
        digest.update(row_hash.to_numpy(dtype="uint64", copy=False).tobytes())
        return digest.hexdigest()
    except Exception:
        try:
            return hashlib.sha1(df.to_csv(index=False).encode("utf-8")).hexdigest()
        except Exception:
            return f"csv:{id(df)}:{len(df)}:{len(df.columns)}"
