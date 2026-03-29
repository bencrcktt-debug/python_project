from __future__ import annotations

from dataclasses import fields, is_dataclass
from typing import Any


def clone_prepared_value(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        payload = {
            field.name: clone_prepared_value(getattr(value, field.name))
            for field in fields(value)
        }
        return type(value)(**payload)
    if isinstance(value, dict):
        return {key: clone_prepared_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return tuple(value)
    if isinstance(value, set):
        return set(value)
    return value


def remember_scoped_prepared_context(
    cache: dict[tuple[str, str], Any],
    scope_key: str,
    signature: str,
    value: Any,
) -> None:
    stale_keys = [key for key in cache.keys() if key[0] == scope_key and key[1] != signature]
    for key in stale_keys:
        cache.pop(key, None)
    cache[(scope_key, signature)] = clone_prepared_value(value)


def get_scoped_prepared_context(
    cache: dict[tuple[str, str], Any],
    scope_key: str,
    signature: str,
) -> Any | None:
    cached = cache.get((scope_key, signature))
    if cached is None:
        return None
    return clone_prepared_value(cached)


def remember_single_prepared_context(
    cache: dict[str, Any],
    signature: str,
    value: Any,
) -> None:
    stale_keys = [key for key in cache.keys() if key != signature]
    for key in stale_keys:
        cache.pop(key, None)
    cache[signature] = clone_prepared_value(value)


def get_single_prepared_context(cache: dict[str, Any], signature: str) -> Any | None:
    cached = cache.get(signature)
    if cached is None:
        return None
    return clone_prepared_value(cached)
