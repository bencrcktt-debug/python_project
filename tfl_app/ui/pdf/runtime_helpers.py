from __future__ import annotations

import importlib
from types import MappingProxyType
from typing import Any


_RUNTIME_HELPERS = MappingProxyType({})


def configure_helpers(**helpers: Any) -> None:
    global _RUNTIME_HELPERS
    _RUNTIME_HELPERS = MappingProxyType(dict(helpers))


def _runtime_helper(name: str):
    helper = _RUNTIME_HELPERS.get(name)
    if helper is None:
        raise KeyError(f"Missing ui.runtime helper: {name}")
    return helper


def _last_first_initial_key(*args, **kwargs):
    return _runtime_helper("_last_first_initial_key")(*args, **kwargs)


def bill_position_from_flags(*args, **kwargs):
    return _runtime_helper("bill_position_from_flags")(*args, **kwargs)


def build_activities(*args, **kwargs):
    return _runtime_helper("build_activities")(*args, **kwargs)


def build_activities_multi(*args, **kwargs):
    return _runtime_helper("build_activities_multi")(*args, **kwargs)


def build_author_bill_index(*args, **kwargs):
    return _runtime_helper("build_author_bill_index")(*args, **kwargs)


def build_disclosures(*args, **kwargs):
    return _runtime_helper("build_disclosures")(*args, **kwargs)


def build_disclosures_multi(*args, **kwargs):
    return _runtime_helper("build_disclosures_multi")(*args, **kwargs)


def build_member_activities(*args, **kwargs):
    return _runtime_helper("build_member_activities")(*args, **kwargs)


def ensure_cols(*args, **kwargs):
    return _runtime_helper("ensure_cols")(*args, **kwargs)


def last_name_norm_from_text(*args, **kwargs):
    return _runtime_helper("last_name_norm_from_text")(*args, **kwargs)


def last_name_norm_series(*args, **kwargs):
    return _runtime_helper("last_name_norm_series")(*args, **kwargs)


def match_entity_type(*args, **kwargs):
    return _runtime_helper("match_entity_type")(*args, **kwargs)


def norm_name(*args, **kwargs):
    return _runtime_helper("norm_name")(*args, **kwargs)


def norm_name_series(*args, **kwargs):
    return _runtime_helper("norm_name_series")(*args, **kwargs)


def norm_person_variants(*args, **kwargs):
    return _runtime_helper("norm_person_variants")(*args, **kwargs)


def normalize_bill(*args, **kwargs):
    return _runtime_helper("normalize_bill")(*args, **kwargs)


def parse_member_name(*args, **kwargs):
    return _runtime_helper("parse_member_name")(*args, **kwargs)


def _plotly_io():
    return importlib.import_module("plotly.io")


__all__ = [
    "_last_first_initial_key",
    "_plotly_io",
    "bill_position_from_flags",
    "build_activities",
    "build_activities_multi",
    "build_author_bill_index",
    "build_disclosures",
    "build_disclosures_multi",
    "build_member_activities",
    "configure_helpers",
    "ensure_cols",
    "last_name_norm_from_text",
    "last_name_norm_series",
    "match_entity_type",
    "norm_name",
    "norm_name_series",
    "norm_person_variants",
    "normalize_bill",
    "parse_member_name",
]
