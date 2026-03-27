from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True)
class _FrozenServices:
    values: Mapping[str, Any]

    @classmethod
    def build(cls, **values: Any):
        return cls(MappingProxyType(dict(values)))

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def require(self, key: str) -> Any:
        if key not in self.values:
            raise KeyError(f"Missing service: {key}")
        return self.values[key]

    def select(self, *keys: str) -> dict[str, Any]:
        return {key: self.require(key) for key in keys}


@dataclass(frozen=True)
class AppServices(_FrozenServices):
    pass


@dataclass(frozen=True)
class WorkspaceServices(_FrozenServices):
    pass


@dataclass(frozen=True)
class MapServices(_FrozenServices):
    pass
