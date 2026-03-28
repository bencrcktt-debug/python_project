from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

try:
    import streamlit as st
except ModuleNotFoundError:  # pragma: no cover - import smoke fallback
    class _StreamlitStub:
        session_state: dict[str, Any] = {}

    st = _StreamlitStub()


def ensure_state_defaults(defaults: Mapping[str, Any]) -> None:
    for key, default in defaults.items():
        if key not in st.session_state:
            if isinstance(default, (list, dict, set)):
                st.session_state[key] = deepcopy(default)
            else:
                st.session_state[key] = default
