from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import statistics
import sys
import time

import pandas as pd


ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "tfl_app").exists())
sys.path.insert(0, str(ROOT))

from tfl_app.services import WorkspaceServices
import tfl_app.ui.fragments.workspace_fragments as workspace_fragments


@dataclass(frozen=True)
class _ScopeBundle:
    overview: pd.DataFrame | None = None
    stats: dict[str, object] | None = None
    all_legislators: pd.DataFrame | None = None
    all_stats: dict[str, object] | None = None
    all_pivot: pd.DataFrame | None = None


@dataclass(frozen=True)
class _DetailBundle:
    context: dict[str, object]


def _time_call(fn, runs: int = 25) -> tuple[float, float, float]:
    samples: list[float] = []
    for _ in range(runs):
        start = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - start)
    return statistics.mean(samples), min(samples), max(samples)


def _services() -> WorkspaceServices:
    workspace_fragments.configure_page_fragment_helpers(
        get_app_state=lambda path: type(
            "_AppState",
            (),
            {
                "name_to_short": {"SMITHJOHN": "SMITHJ"},
                "short_to_names": {"SMITHJ": ["Smith, John"]},
                "filerid_to_short": {101: "SMITHJ"},
            },
        )(),
        get_client_scope_bundle=lambda path, scope, tfl: _ScopeBundle(
            overview=pd.DataFrame([{"Client": "City of Austin", "IsTFL": 1}]),
            stats={"total_clients": 1},
        ),
        get_client_workspace_detail_bundle=lambda path, session, tfl, client_name: _DetailBundle(
            {
                "client_has_rows": True,
                "client_lt": pd.DataFrame([{"Client": client_name, "LobbyShort": "SMITHJ"}]),
                "lobbyist_totals": pd.DataFrame([{"Lobbyist": "Smith, John"}]),
                "activities": pd.DataFrame([{"Type": "Food"}]),
            }
        ),
        get_member_session_bundle=lambda path, session: _ScopeBundle(
            all_legislators=pd.DataFrame([{"Legislator": "Bell, Keith", "Bills": 3}]),
            all_stats={"total_legislators": 1},
        ),
        get_member_workspace_detail_bundle=lambda path, session, tfl, member_name: _DetailBundle(
            {
                "authored": pd.DataFrame([{"Bill": "HB 1"}]),
                "witness": pd.DataFrame([{"Lobbyist": "Smith, John"}]),
                "activities": pd.DataFrame([{"Lobbyist": "Smith, John"}]),
            }
        ),
        get_lobby_scope_bundle=lambda path, scope, tfl: _ScopeBundle(
            all_pivot=pd.DataFrame([{"LobbyShort": "SMITHJ"}]),
            all_stats={"total_lobbyists": 1},
        ),
        get_lobby_workspace_detail_bundle=lambda path, session, tfl, lobbyshort, typed_norms, selected_names, selected_filer_ids: _DetailBundle(
            {
                "lobbyist_label": "Smith, John",
                "wit": pd.DataFrame([{"Bill": "HB 1"}]),
                "bills": pd.DataFrame([{"Bill": "HB 1"}]),
                "activities": pd.DataFrame([{"Type": "Food"}]),
            }
        ),
    )
    return WorkspaceServices.build()


def _rehydrate(services: WorkspaceServices, storage_key: str, payload: dict[str, object]) -> None:
    workspace_fragments._rehydrate_fragment_ctx(services, storage_key, payload)


if __name__ == "__main__":
    services = _services()
    targets = {
        "client_fragment_rehydrate": lambda: _rehydrate(
            services,
            "_client_workspace_ctx",
            {
                "PATH": "demo.parquet",
                "client_scope": "This Session",
                "client_session": "89R",
                "client_name": "City of Austin",
                "tfl_session_val": "89R",
            },
        ),
        "member_fragment_rehydrate": lambda: _rehydrate(
            services,
            "_member_workspace_ctx",
            {
                "PATH": "demo.parquet",
                "member_session": "89R",
                "member_name": "Bell, Keith",
                "tfl_session_val": "89R",
            },
        ),
        "lobby_fragment_rehydrate": lambda: _rehydrate(
            services,
            "_lobby_workspace_ctx",
            {
                "PATH": "demo.parquet",
                "scope": "This Session",
                "session": "89R",
                "tfl_session_val": "89R",
                "lobbyshort": "SMITHJ",
                "typed_norms_tuple": ("SMITHJOHN",),
                "selected_names": ("Smith, John",),
                "selected_filer_ids": (101,),
            },
        ),
    }

    for name, fn in targets.items():
        mean_s, min_s, max_s = _time_call(fn)
        print(f"{name}: runs=25 mean={mean_s:.6f} min={min_s:.6f} max={max_s:.6f}")
