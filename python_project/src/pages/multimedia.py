from __future__ import annotations

from typing import Any

try:
    import streamlit as st
except ModuleNotFoundError:  # pragma: no cover - import smoke fallback
    class _StreamlitStub:
        session_state: dict[str, Any] = {}

    st = _StreamlitStub()

from ._runtime import configure_helpers as _configure_helpers
from ._runtime import pop_context as _pop_context
from ._runtime import push_context as _push_context

HELPER_KEYS = (
    '_client_page',
    '_lobby_page',
    '_member_page',
    '_render_evidence_guardrails',
    '_render_journey',
    '_render_page_intro',
    '_render_quickstart',
    '_render_workspace_guide',
    '_render_workspace_links',
    'html',
)


def configure_helpers(**helpers: Any) -> None:
    _configure_helpers(globals(), **helpers)


def render_page(ctx: dict[str, Any] | None = None) -> None:
    _ctx = ctx or {}
    _previous = _push_context(globals(), _ctx)
    try:
            _render_page_intro(
                kicker="Media Briefings",
                title="Public Statements And Media Clips",
                subtitle=(
                    "External interviews and explainers related to taxpayer-funded lobbying. Use this page as claim context, "
                    "then verify every claim in filing-based workspaces."
                ),
                pills=[
                    "Context only, not evidence",
                    "Cross-check with filing data",
                ],
            )
            _render_journey("multimedia")
            _render_workspace_guide(
                question="What public claims are being made, and are they supported by official records?",
                steps=[
                    "Capture the exact claim, bill number, entity, and date reference.",
                    "Switch to Lobbyists, Clients, or Legislators to verify against filings.",
                    "Export the supporting table with active filters for reproducibility.",
                ],
                method_note="Media clips can guide inquiry but do not replace source filings.",
            )
            _render_workspace_links(
                "media_open",
                [
                    ("Open Lobbyists", _lobby_page, "Verify statewide and profile-level claims."),
                    ("Open Clients", _client_page, "Validate claims about specific entities."),
                    ("Open Legislators", _member_page, "Check claims tied to authored bills and witnesses."),
                ],
            )
            _render_quickstart(
                "media",
                [
                    "Write down the exact claim in neutral language.",
                    "Confirm or reject it using at least one filing-based workspace.",
                    "Attach exported evidence when sharing findings.",
                ],
                note="Treat every clip as a hypothesis prompt, not a standalone conclusion.",
            )
            _render_evidence_guardrails(
                can_answer=[
                    "What claims are being made in public-facing interviews and explainers.",
                    "Which claims should be tested in Lobbyists, Clients, or Legislators next.",
                ],
                cannot_answer=[
                    "Whether a claim is true without checking filing data.",
                    "Quantitative conclusions without exported supporting tables.",
                ],
                next_checks=[
                    "Capture claim language, bill numbers, and dates before verification.",
                    "Use filing-based workspaces to confirm or refute each claim.",
                ],
            )

            videos = [
                {
                    "id": "VfNk92xJImg",
                    "embed": "https://www.youtube.com/embed/VfNk92xJImg?si=f5Yn716z6UcdLKWW",
                    "title": "Taking on Taxpayer Funded Lobbying with Rep. Hillary Hickland | Parent Empowerment with Mandy Drogin",
                    "summary": "Rep. Hillary Hickland discusses how taxpayer-funded lobbying affects education policy and local taxpayer interests.",
                },
                {
                    "id": "5ozqYYpP1VI",
                    "embed": "https://www.youtube.com/embed/5ozqYYpP1VI?si=Iy7APVxAq3cBgdUi",
                    "title": "Taxpayer Empowerment | Episode 11: Property Taxes, Lobbyists & PFAs with Rep. Helen Kerwin",
                    "summary": "Rep. Helen Kerwin covers property tax reform, PFAS policy, and claims about taxpayer-funded lobbying around those issues.",
                },
                {
                    "id": "p644amuejVE",
                    "embed": "https://www.youtube.com/embed/p644amuejVE?si=U_DXk6ttlI_M4HhA",
                    "title": "Taxpayer Empowerment | Episode 6: Property Taxes & Taxpayer-Funded Lobbying with Rep. Cody Vasut",
                    "summary": "Rep. Cody Vasut discusses legislative approaches to property tax relief and limiting taxpayer-funded lobbying.",
                },
                {
                    "id": "RWLD-zC9Slg",
                    "embed": "https://www.youtube.com/embed/RWLD-zC9Slg?si=CCapZXXDO4xOaQFw",
                    "title": "Fund Students Not Lobbyists | Fast Facts",
                    "summary": "A short explainer focused on school district spending priorities and lobbying expenditures.",
                },
                {
                    "id": "RAClQAg_JpU",
                    "embed": "https://www.youtube.com/embed/RAClQAg_JpU?si=D4RrYgtq4FIdUTrb",
                    "title": "Lobbyists Paid By You | Fast Facts",
                    "summary": "A short explainer about public funds used for lobbying and related taxpayer accountability questions.",
                },
                {
                    "id": "LUxuCq0SeQA",
                    "embed": "https://www.youtube.com/embed/LUxuCq0SeQA?si=dxLmQ4Vo621qmCBV",
                    "title": "Parent Empowerment with Mandy Drogin | Local Government Reform with Senator Mayes Middleton",
                    "summary": "Senator Mayes Middleton discusses local government finance, debt, and reform arguments tied to taxpayer accountability.",
                },
            ]

            video_titles = [video["title"] for video in videos]
            if (
                "tap_selected_title" not in st.session_state
                or st.session_state.tap_selected_title not in video_titles
            ):
                st.session_state.tap_selected_title = video_titles[0]

            controls = st.columns([3, 1])
            with controls[0]:
                selected_title = st.selectbox(
                    "Choose a video",
                    video_titles,
                    help="Select a featured video to preview in the player.",
                    key="tap_selected_title",
                    label_visibility="collapsed",
                )
            with controls[1]:
                show_all_players = st.checkbox(
                    "Show all players",
                    value=False,
                    help="Display every embedded player below the gallery.",
                )

            selected = next(video for video in videos if video["title"] == selected_title)
            selected_watch_url = f"https://www.youtube.com/watch?v={selected['id']}"
            selected_summary = selected.get("summary", "").strip()
            selected_title_html = html.escape(selected.get("title", ""), quote=True)
            selected_summary_html = (
                f'<div class="tap-feature-summary">{html.escape(selected_summary, quote=True)}</div>'
                if selected_summary
                else ""
            )

            st.markdown(
                f"""
        <div class="card tap-feature">
          <div class="tap-feature-head">
            <div>
              <div class="tap-feature-kicker">Now Playing</div>
              <div class="tap-feature-title">{selected_title_html}</div>{selected_summary_html}
            </div>
            <a class="tap-feature-link" href="{selected_watch_url}" target="_blank" rel="noopener">Open in YouTube</a>
          </div>
          <div class="video-embed tap-feature-embed">
            <iframe src="{selected['embed']}" title="YouTube video player" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>
          </div>
        </div>
        """,
                unsafe_allow_html=True,
            )

            st.markdown('<div class="tap-gallery-title">Gallery</div>', unsafe_allow_html=True)
            gallery_cards = []
            for video in videos:
                watch_url = f"https://www.youtube.com/watch?v={video['id']}"
                thumb_url = f"https://img.youtube.com/vi/{video['id']}/hqdefault.jpg"
                summary = video.get("summary", "").strip()
                safe_title = html.escape(video.get("title", ""), quote=True)
                summary_html = (
                    f'<div class="tap-card-summary">{html.escape(summary, quote=True)}</div>'
                    if summary
                    else ""
                )
                active_class = " is-active" if video["title"] == selected_title else ""
                gallery_cards.append(
                    f"""
          <div class="video-card{active_class}">
            <a class="tap-thumb" href="{watch_url}" target="_blank" rel="noopener">
              <img src="{thumb_url}" alt="{safe_title} thumbnail"/>
            </a>
            <div class="tap-card-title">{safe_title}</div>{summary_html}
            <a class="tap-card-link" href="{watch_url}" target="_blank" rel="noopener">Open in YouTube</a>
          </div>
        """
                )
            st.markdown(f'<div class="video-grid">{"".join(gallery_cards)}</div>', unsafe_allow_html=True)
            st.caption("Tip: use the selector to play in-page. Thumbnails open YouTube in a new tab.")

            if show_all_players:
                st.markdown('<div class="tap-gallery-title">All Players</div>', unsafe_allow_html=True)
                all_cards = []
                for video in videos:
                    all_cards.append(
                        f"""
          <div class="video-card">
            <div class="video-embed">
              <iframe src="{video['embed']}" title="YouTube video player" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>
            </div>
            <div class="tap-card-title">{video['title']}</div>
          </div>
        """
                    )
                st.markdown(f'<div class="video-grid">{"".join(all_cards)}</div>', unsafe_allow_html=True)
    finally:
        _pop_context(globals(), _previous, _ctx)
