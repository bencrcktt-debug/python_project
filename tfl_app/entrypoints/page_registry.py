from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import functools
import logging

import streamlit as st


PageRunner = Callable[[str, dict[str, object] | None], None]


@dataclass(frozen=True)
class PageRegistry:
    about_page: object
    lobby_page: object
    client_page: object
    map_page: object
    member_page: object
    solutions_page: object
    tap_page: object
    pages: list[object]


def _safe_page(page_name: str):
    """Wrap page renderers so one page crash does not take down navigation."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except st.runtime.scriptrunner.StopException:
                raise
            except Exception as exc:
                logging.exception("Unhandled error in page %s", page_name)
                st.error(
                    f"An unexpected error occurred on the **{page_name}** page. "
                    f"Try refreshing the browser or clearing filters.\n\n"
                    f"Error details: `{type(exc).__name__}: {exc}`"
                )
                if st.button("Reset and reload", key=f"crash_reset_{page_name}"):
                    for key in list(st.session_state.keys()):
                        del st.session_state[key]
                    st.rerun()

        return wrapper

    return decorator


def build_page_registry(run_page_renderer: PageRunner) -> PageRegistry:
    @_safe_page("About")
    def page_about() -> None:
        run_page_renderer("tfl_app.ui.pages.about")

    @_safe_page("Media Briefings")
    def page_turn_off_tap() -> None:
        run_page_renderer("tfl_app.ui.pages.multimedia")

    @_safe_page("Policy Context")
    def page_solutions() -> None:
        run_page_renderer("tfl_app.ui.pages.solutions")

    @_safe_page("Clients")
    def page_client_lookup() -> None:
        run_page_renderer("tfl_app.ui.pages.clients")

    @_safe_page("Legislators")
    def page_member_lookup() -> None:
        run_page_renderer("tfl_app.ui.pages.legislators")

    @_safe_page("Map & Address Full")
    def page_map_address_full_pass() -> None:
        run_page_renderer("tfl_app.ui.pages.map_address")

    @_safe_page("Map & Address Rebuild")
    def page_map_address_rebuild() -> None:
        page_map_address_full_pass()

    @_safe_page("Lobbyists")
    def page_lobby_lookup() -> None:
        run_page_renderer("tfl_app.ui.pages.lobbyists")

    about_page = st.Page(page_about, title="Start Here", url_path="about", default=True)
    lobby_page = st.Page(page_lobby_lookup, title="Lobbyists", url_path="lobbyists")
    client_page = st.Page(page_client_lookup, title="Clients", url_path="clients")
    map_page = st.Page(page_map_address_rebuild, title="Map & Address", url_path="map-address")
    member_page = st.Page(page_member_lookup, title="Legislators", url_path="legislators")
    solutions_page = st.Page(page_solutions, title="Policy Context", url_path="solutions")
    tap_page = st.Page(page_turn_off_tap, title="Media Briefings", url_path="multimedia")
    pages = [
        about_page,
        lobby_page,
        client_page,
        map_page,
        member_page,
        solutions_page,
        tap_page,
    ]

    return PageRegistry(
        about_page=about_page,
        lobby_page=lobby_page,
        client_page=client_page,
        map_page=map_page,
        member_page=member_page,
        solutions_page=solutions_page,
        tap_page=tap_page,
        pages=pages,
    )
