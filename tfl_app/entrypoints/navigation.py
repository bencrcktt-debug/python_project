from __future__ import annotations

import streamlit as st

from tfl_app.ui.page_state import ensure_nav_state


def same_page(left: object, right: object) -> bool:
    return getattr(left, "url_path", None) == getattr(right, "url_path", None)


def render_navigation_shell(pages: list[object]) -> tuple[object, str, bool, object]:
    active_page = st.navigation(pages, position="hidden")
    nav_items = [
        (pages[0], "Start Here", "./"),
        (pages[1], "Lobbyists", "./lobbyists"),
        (pages[2], "Clients", "./clients"),
        (pages[3], "Map & Address", "./map-address"),
        (pages[4], "Legislators", "./legislators"),
        (pages[5], "Policy", "./solutions"),
        (pages[6], "Media", "./multimedia"),
    ]
    nav_links = []
    for page, label, href in nav_items:
        active = " active" if same_page(page, active_page) else ""
        nav_links.append(f'<a class="nav-link{active}" href="{href}" target="_self">{label}</a>')

    st.markdown(
        f"""
<div class="custom-nav">
  <div class="nav-inner">
    <div class="brand">
      <div class="brand-top">Texas Taxpayer Protection</div>
      <div class="brand-bottom">Lobbying Transparency Center</div>
    </div>
    <div class="nav-links">
      {''.join(nav_links)}
    </div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    ensure_nav_state()

    def _nav_submit() -> None:
        st.session_state.nav_search_trigger = True

    nav_query_raw = st.text_input(
        "Nav search",
        key="nav_search_query",
        placeholder="Global search: lobbyist, client, legislator, or bill (example: HB 4)",
        label_visibility="collapsed",
        on_change=_nav_submit,
        help="Routes to the best workspace and carries your query forward.",
    )
    nav_query = nav_query_raw.strip()
    nav_search_submitted = False
    if nav_query and st.session_state.nav_search_trigger:
        nav_search_submitted = True
        st.session_state.nav_search_last = nav_query
        st.session_state.nav_search_trigger = False
    elif not nav_query:
        st.session_state.nav_search_trigger = False
    nav_suggest_slot = st.empty()
    return active_page, nav_query, nav_search_submitted, nav_suggest_slot
