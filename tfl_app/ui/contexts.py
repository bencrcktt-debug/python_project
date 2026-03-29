from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class AppLookupMaps:
    name_to_short: dict[str, str]
    short_to_names: dict[str, list[str]]
    filerid_to_short: dict[int, str]

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any] | None) -> "AppLookupMaps":
        payload = dict(values or {})
        return cls(
            name_to_short=dict(payload.get("name_to_short", {}) or {}),
            short_to_names={
                str(key): list(value or [])
                for key, value in dict(payload.get("short_to_names", {}) or {}).items()
            },
            filerid_to_short={
                int(key): str(value)
                for key, value in dict(payload.get("filerid_to_short", {}) or {}).items()
            },
        )


@dataclass(frozen=True)
class ClientWorkspaceSelector:
    path: str = ""
    client_scope: str | None = None
    client_session: str = ""
    client_name: str = ""
    tfl_session_val: str | None = None
    prepared_signature: str = ""

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "ClientWorkspaceSelector":
        values = dict(payload or {})
        return cls(
            path=str(values.get("PATH", "") or "").strip(),
            client_scope=values.get("client_scope"),
            client_session=str(values.get("client_session", "") or "").strip(),
            client_name=str(values.get("client_name", "") or "").strip(),
            tfl_session_val=(
                None
                if values.get("tfl_session_val") in {None, ""}
                else str(values.get("tfl_session_val")).strip()
            ),
            prepared_signature=str(values.get("_prepared_signature", "") or "").strip(),
        )

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "PATH": self.path,
            "client_scope": self.client_scope,
            "client_session": self.client_session,
            "client_name": self.client_name,
            "tfl_session_val": self.tfl_session_val,
        }
        if self.prepared_signature:
            payload["_prepared_signature"] = self.prepared_signature
        return payload


@dataclass(frozen=True)
class MemberWorkspaceSelector:
    path: str = ""
    member_session: str = ""
    member_name: str = ""
    tfl_session_val: str | None = None
    prepared_signature: str = ""

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "MemberWorkspaceSelector":
        values = dict(payload or {})
        return cls(
            path=str(values.get("PATH", "") or "").strip(),
            member_session=str(values.get("member_session", "") or "").strip(),
            member_name=str(values.get("member_name", "") or "").strip(),
            tfl_session_val=(
                None
                if values.get("tfl_session_val") in {None, ""}
                else str(values.get("tfl_session_val")).strip()
            ),
            prepared_signature=str(values.get("_prepared_signature", "") or "").strip(),
        )

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "PATH": self.path,
            "member_session": self.member_session,
            "member_name": self.member_name,
            "tfl_session_val": self.tfl_session_val,
        }
        if self.prepared_signature:
            payload["_prepared_signature"] = self.prepared_signature
        return payload


@dataclass(frozen=True)
class LobbyWorkspaceSelector:
    path: str = ""
    scope: str | None = None
    session: str = ""
    tfl_session_val: str | None = None
    lobbyshort: str = ""
    typed_norms_tuple: tuple[str, ...] = ()
    selected_names: tuple[str, ...] = ()
    selected_filer_ids: tuple[int, ...] = ()
    prepared_signature: str = ""

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "LobbyWorkspaceSelector":
        values = dict(payload or {})
        return cls(
            path=str(values.get("PATH", "") or "").strip(),
            scope=values.get("scope"),
            session=str(values.get("session", "") or "").strip(),
            tfl_session_val=(
                None
                if values.get("tfl_session_val") in {None, ""}
                else str(values.get("tfl_session_val")).strip()
            ),
            lobbyshort=str(values.get("lobbyshort", "") or "").strip(),
            typed_norms_tuple=tuple(values.get("typed_norms_tuple", ()) or ()),
            selected_names=tuple(values.get("selected_names", ()) or ()),
            selected_filer_ids=tuple(int(value) for value in (values.get("selected_filer_ids", ()) or ())),
            prepared_signature=str(values.get("_prepared_signature", "") or "").strip(),
        )

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "PATH": self.path,
            "scope": self.scope,
            "session": self.session,
            "tfl_session_val": self.tfl_session_val,
            "lobbyshort": self.lobbyshort,
            "typed_norms_tuple": self.typed_norms_tuple,
            "selected_names": self.selected_names,
            "selected_filer_ids": self.selected_filer_ids,
        }
        if self.prepared_signature:
            payload["_prepared_signature"] = self.prepared_signature
        return payload


@dataclass(frozen=True)
class MapWorkspaceSelector:
    path: str = ""
    runtime_signature: str = ""
    forensics_source_signature: str = ""

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "MapWorkspaceSelector":
        values = dict(payload or {})
        return cls(
            path=str(values.get("PATH", "") or "").strip(),
            runtime_signature=str(values.get("_map_runtime_signature", "") or "").strip(),
            forensics_source_signature=str(values.get("_map_forensics_source_signature", "") or "").strip(),
        )

    def to_payload(self) -> dict[str, Any]:
        payload = {"PATH": self.path}
        if self.runtime_signature:
            payload["_map_runtime_signature"] = self.runtime_signature
        if self.forensics_source_signature:
            payload["_map_forensics_source_signature"] = self.forensics_source_signature
        return payload


@dataclass(frozen=True)
class ClientWorkspacePreparedContext:
    selector: ClientWorkspaceSelector
    app_lookups: AppLookupMaps
    scope_bundle: Any
    detail_bundle: Any
    payload: dict[str, Any]


@dataclass(frozen=True)
class MemberWorkspacePreparedContext:
    selector: MemberWorkspaceSelector
    app_lookups: AppLookupMaps
    session_bundle: Any
    detail_bundle: Any
    payload: dict[str, Any]


@dataclass(frozen=True)
class LobbyWorkspacePreparedContext:
    selector: LobbyWorkspaceSelector
    app_lookups: AppLookupMaps
    scope_bundle: Any
    detail_bundle: Any
    payload: dict[str, Any]


@dataclass(frozen=True)
class MapWorkspacePreparedContext:
    selector: MapWorkspaceSelector
    payload: dict[str, Any]
