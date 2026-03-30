from __future__ import annotations

import pandas as pd

import tfl_app.bundles.page_bundles as _page_bundles
from tfl_app.data.loaders import get_table_manifest

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


DATA_SOURCE_LABELS = {
    "Wit_All": "Texas Legislature Online (Witness lists)",
    "Bill_Status_All": "Texas Legislature Online (Bill status)",
    "Fiscal_Impact": "Texas Legislature Online (Fiscal notes)",
    "Bill_Sub_All": "Texas Legislature Online (Bill subjects)",
    "Lobby_Sub_All": "Texas Ethics Commission (Subject matter filings)",
    "Lobby_TFL_Client_All": "Texas Ethics Commission (Lobbyist filings and compensation)",
    "Staff_All": "House Research Organization (Legislative staff lists)",
    "LaFood": "Texas Ethics Commission (Activity: Food)",
    "LaEnt": "Texas Ethics Commission (Activity: Entertainment)",
    "LaTran": "Texas Ethics Commission (Activity: Travel)",
    "LaGift": "Texas Ethics Commission (Activity: Gifts)",
    "LaEvnt": "Texas Ethics Commission (Activity: Events)",
    "LaAwrd": "Texas Ethics Commission (Activity: Awards)",
    "LaCvr": "Texas Ethics Commission (Disclosure: Coverage)",
    "LaDock": "Texas Ethics Commission (Disclosure: Docket)",
    "LaI4E": "Texas Ethics Commission (Disclosure: On Behalf)",
    "LaSub": "Texas Ethics Commission (Disclosure: Subject Matter)",
}


def source_label(key: str) -> str:
    return DATA_SOURCE_LABELS.get(key, key)


@st.cache_data(show_spinner=False, ttl=3600, max_entries=16)
def data_health_table(path: str) -> pd.DataFrame:
    manifest = get_table_manifest(str(path or ""))
    return _page_bundles.build_data_health_table(manifest or {}, DATA_SOURCE_LABELS)

