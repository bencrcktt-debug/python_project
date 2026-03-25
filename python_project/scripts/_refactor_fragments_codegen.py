from __future__ import annotations

import ast
import pathlib
import textwrap


ROOT = pathlib.Path(__file__).resolve().parents[1]


def extract_compiled_sources(path_str: str) -> dict[str, str]:
    path = ROOT / path_str
    src = path.read_text(encoding="utf-8")
    mod = ast.parse(src)
    out: dict[str, str] = {}
    for node in mod.body:
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id.endswith("_CODE")
        ):
            call = node.value
            if not isinstance(call, ast.Call) or not call.args:
                continue
            code = call.args[0].value
            lines = code.splitlines()[1:-1]
            indent = 0
            for line in lines:
                if line.strip():
                    indent = len(line) - len(line.lstrip(" "))
                    break
            prefix = " " * indent
            body = "\n".join(
                line[len(prefix):] if line.startswith(prefix) else line
                for line in lines
            )
            out[node.targets[0].id] = body.rstrip() + "\n"
    return out


def make_renderer_module(
    sources: dict[str, str],
    mapping: dict[str, str],
    output: pathlib.Path,
    extra_imports: list[str],
) -> None:
    parts = [
        "from __future__ import annotations",
        "",
        "from typing import Any",
    ]
    parts.extend(extra_imports)
    parts.extend(
        [
            "",
            "try:",
            "    import streamlit as st",
            "except ModuleNotFoundError:  # pragma: no cover - import smoke fallback",
            "    class _StreamlitStub:",
            "        session_state: dict[str, Any] = {}",
            "    st = _StreamlitStub()",
            "",
            "_MISSING = object()",
            "",
            "def configure_helpers(**helpers: Any) -> None:",
            "    globals().update(helpers)",
            "",
            "def _push_context(ctx: dict[str, Any]) -> dict[str, Any]:",
            "    previous: dict[str, Any] = {}",
            "    for key, value in ctx.items():",
            "        previous[key] = globals().get(key, _MISSING)",
            "        globals()[key] = value",
            "    return previous",
            "",
            "def _pop_context(previous: dict[str, Any], ctx: dict[str, Any]) -> None:",
            "    for key in ctx.keys():",
            "        old_value = previous.get(key, _MISSING)",
            "        if old_value is _MISSING:",
            "            globals().pop(key, None)",
            "        else:",
            "            globals()[key] = old_value",
            "",
        ]
    )
    for const_name, func_name in mapping.items():
        body = textwrap.indent(sources[const_name], " " * 8)
        parts.extend(
            [
                f"def {func_name}(ctx: dict[str, Any]) -> None:",
                "    _previous = _push_context(ctx)",
                "    try:",
                body.rstrip(),
                "    finally:",
                "        _pop_context(_previous, ctx)",
                "",
            ]
        )
    output.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")


def write_page_fragments() -> None:
    page_fragments_src = """from __future__ import annotations

import importlib
from typing import Any

try:
    import streamlit as st
except ModuleNotFoundError:  # pragma: no cover - import smoke fallback
    class _FragmentStub:
        def __call__(self, *decorator_args, **decorator_kwargs):
            if decorator_args and callable(decorator_args[0]) and len(decorator_args) == 1 and not decorator_kwargs:
                return decorator_args[0]

            def decorator(func):
                return func

            return decorator

    class _StreamlitStub:
        fragment = _FragmentStub()
        session_state: dict[str, Any] = {}

    st = _StreamlitStub()


_HELPERS: dict[str, Any] = {}
_RENDERERS = {
    "_client_workspace_ctx": "render_client_workspace",
    "_member_workspace_ctx": "render_member_workspace",
    "_lobby_workspace_ctx": "render_lobby_workspace",
}


def configure_page_fragment_helpers(**helpers: Any) -> None:
    _HELPERS.update(helpers)


def _run_fragment(storage_key: str) -> None:
    ctx = {}
    if hasattr(st, "session_state"):
        raw = st.session_state.get(storage_key, {})
        if isinstance(raw, dict):
            ctx = raw
    renderer_name = _RENDERERS.get(storage_key)
    if not renderer_name:
        return
    module = importlib.import_module("src.page_workspace_renderers")
    module.configure_helpers(**_HELPERS)
    getattr(module, renderer_name)(ctx)


@st.fragment
def render_client_workspace_fragment(storage_key: str = "_client_workspace_ctx") -> None:
    _run_fragment(storage_key)


@st.fragment
def render_member_workspace_fragment(storage_key: str = "_member_workspace_ctx") -> None:
    _run_fragment(storage_key)


@st.fragment
def render_lobby_workspace_fragment(storage_key: str = "_lobby_workspace_ctx") -> None:
    _run_fragment(storage_key)
"""
    (ROOT / "src" / "page_fragments.py").write_text(page_fragments_src, encoding="utf-8")


def write_map_fragments() -> None:
    map_fragments_src = """from __future__ import annotations

import hashlib
import importlib
import json
from typing import Any

try:
    import streamlit as st
except ModuleNotFoundError:  # pragma: no cover - import smoke fallback
    class _FragmentStub:
        def __call__(self, *decorator_args, **decorator_kwargs):
            if decorator_args and callable(decorator_args[0]) and len(decorator_args) == 1 and not decorator_kwargs:
                return decorator_args[0]

            def decorator(func):
                return func

            return decorator

    class _StreamlitStub:
        fragment = _FragmentStub()
        session_state: dict[str, Any] = {}

    st = _StreamlitStub()


_HELPERS: dict[str, Any] = {}


def configure_map_fragment_helpers(**helpers: Any) -> None:
    _HELPERS.update(helpers)


def _build_forensics_source_signature(atlas_bundle: Any) -> str:
    spend_lookup = getattr(atlas_bundle, "spend_lookup", {}) or {}
    normalized_spend = []
    if isinstance(spend_lookup, dict):
        for client, payload in sorted(spend_lookup.items(), key=lambda item: str(item[0]).strip().lower()):
            payload_dict = payload if isinstance(payload, dict) else {}
            normalized_spend.append(
                {
                    "client": str(client).strip(),
                    "entity_type": str(payload_dict.get("EntityType", "")).strip(),
                    "low": round(float(payload_dict.get("Low", 0.0) or 0.0), 2),
                    "high": round(float(payload_dict.get("High", 0.0) or 0.0), 2),
                    "lobbyists": int(payload_dict.get("Lobbyists", 0) or 0),
                }
            )
    payload = {
        "map_payload_signature": str(getattr(atlas_bundle, "map_payload_signature", "")).strip(),
        "spend_lookup": normalized_spend,
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(encoded.encode("utf-8")).hexdigest()


def _refresh_map_runtime_context(ctx: dict[str, Any]) -> dict[str, Any]:
    required = (
        "PATH",
        "get_map_state",
        "_tfl_session_for_filter",
        "_map_runtime",
        "get_map_forensics_bundle",
        "get_map_atlas_bundle",
    )
    if any(name not in _HELPERS for name in required):
        return ctx

    try:
        path = str(_HELPERS["PATH"])
        map_state = _HELPERS["get_map_state"](path)
        tfl_sessions = set(getattr(map_state, "map_sessions", []) or [])
        session_for_filter = _HELPERS["_tfl_session_for_filter"](
            st.session_state.get("map_session"),
            tfl_sessions,
        )
        selected_subdivision_signature = _HELPERS["_map_runtime"].build_selected_subdivision_signature(
            st.session_state.get("map_selected_subdivision_context", {}),
        )
        map_forensics_bundle = _HELPERS["get_map_forensics_bundle"](
            path,
            str(st.session_state.get("map_scope", "")),
            session_for_filter,
            selected_subdivision_signature,
        )
        atlas_bundle = _HELPERS["get_map_atlas_bundle"](
            path,
            str(st.session_state.get("map_scope", "")),
            session_for_filter,
        )
    except Exception:
        return ctx

    subdivision_matches = map_forensics_bundle.subdivision_matches.copy()
    docket = st.session_state.get("map_watchlist", [])
    docket_count = len(docket) if isinstance(docket, list) else 0
    atlas_count = len(subdivision_matches) if not subdivision_matches.empty else 0
    forensics_source_signature = _build_forensics_source_signature(atlas_bundle)
    if str(ctx.get("_map_forensics_source_signature", "")).strip() != forensics_source_signature:
        st.session_state.pop("_mp5_forensics_bundle_v1", None)
        st.session_state.pop("_mp5_forensics_rows_v1", None)
        st.session_state.pop("_mp5_filtered_forensics_bundle_v1", None)

    refreshed = dict(ctx)
    refreshed.update(
        {
            "tfl_sessions": tfl_sessions,
            "session_for_filter": session_for_filter,
            "selected_subdivision_signature": selected_subdivision_signature,
            "map_forensics_bundle": map_forensics_bundle,
            "atlas_bundle": atlas_bundle,
            "totals": map_forensics_bundle.totals.copy(),
            "tfl_spend": map_forensics_bundle.tfl_spend.copy(),
            "subdivision_matches": subdivision_matches,
            "matched_clients": set(map_forensics_bundle.matched_clients),
            "total_tfl": int(map_forensics_bundle.total_tfl or 0),
            "total_high": float(map_forensics_bundle.total_high or 0.0),
            "mapped_high": float(map_forensics_bundle.mapped_high or 0.0),
            "mapped_rate": float(map_forensics_bundle.mapped_rate or 0.0),
            "unmapped_count": int(map_forensics_bundle.unmapped_count or 0),
            "hotspot_label": map_forensics_bundle.hotspot_label or "--",
            "hotspot_high": float(map_forensics_bundle.hotspot_high or 0.0),
            "_map_forensics_source_signature": forensics_source_signature,
            "_atlas_count": atlas_count,
            "_docket_count": docket_count,
            "_atlas_label": f"🗺️ Coverage Atlas ({atlas_count:,})",
            "_forensics_label": "🔍 Address Forensics",
            "_docket_label": (
                f"📋 Case Docket ({docket_count:,})"
                if docket_count
                else "📋 Case Docket"
            ),
        }
    )
    return refreshed


def _run_fragment(storage_key: str) -> None:
    ctx = {}
    if hasattr(st, "session_state"):
        raw = st.session_state.get(storage_key, {})
        if isinstance(raw, dict):
            ctx = raw
        ctx = _refresh_map_runtime_context(ctx)
        st.session_state[storage_key] = ctx
    module = importlib.import_module("src.map_workspace_renderer")
    module.configure_helpers(**_HELPERS)
    module.render_map_workspace(ctx)


@st.fragment
def render_map_workspace_fragment(storage_key: str = "_map_workspace_ctx") -> None:
    _run_fragment(storage_key)
"""
    (ROOT / "src" / "map_fragments.py").write_text(map_fragments_src, encoding="utf-8")


def main() -> None:
    page_sources = extract_compiled_sources("src/page_fragments.py")
    make_renderer_module(
        page_sources,
        {
            "_CLIENT_WORKSPACE_CODE": "render_client_workspace",
            "_MEMBER_WORKSPACE_CODE": "render_member_workspace",
            "_LOBBY_WORKSPACE_CODE": "render_lobby_workspace",
        },
        ROOT / "src" / "page_workspace_renderers.py",
        [
            "import html",
            "from datetime import datetime",
            "import pandas as pd",
            "import plotly.express as px",
        ],
    )

    map_sources = extract_compiled_sources("src/map_fragments.py")
    make_renderer_module(
        map_sources,
        {"_MAP_WORKSPACE_CODE": "render_map_workspace"},
        ROOT / "src" / "map_workspace_renderer.py",
        [
            "import html",
            "from concurrent.futures import ThreadPoolExecutor, as_completed",
            "from datetime import datetime",
            "import pandas as pd",
            "import plotly.express as px",
        ],
    )

    write_page_fragments()
    write_map_fragments()
    print("generated renderer modules and rewrote fragment wrappers")


if __name__ == "__main__":
    main()
