from __future__ import annotations

import html

import streamlit as st


def journey_steps() -> list[tuple[str, str, str, object]]:
    return []


def render_page_intro(kicker: str, title: str, subtitle: str, pills: list[str] | None = None) -> None:
    kicker_safe = html.escape(kicker or "", quote=True)
    title_safe = html.escape(title or "", quote=True)
    subtitle_safe = html.escape(subtitle or "", quote=True)
    kicker_html = f'<div class="policy-kicker">{kicker_safe}</div>' if kicker_safe else ""
    pill_html = ""
    if pills:
        tokens = [f'<span class="policy-pill">{html.escape(str(p), quote=True)}</span>' for p in pills if str(p).strip()]
        if tokens:
            pill_html = f'<div class="policy-pill-list">{"".join(tokens)}</div>'
    st.markdown(
        f"""
<div class="card policy-hero">
  {kicker_html}
  <div class="policy-title">{title_safe}</div>
  <p class="policy-subtitle">{subtitle_safe}</p>
  {pill_html}
</div>
""",
        unsafe_allow_html=True,
    )


def is_guided_mode() -> bool:
    return False


def render_journey(current_key: str) -> None:
    del current_key
    return


def render_workspace_guide(
    question: str,
    steps: list[str] | None = None,
    method_note: str | None = None,
) -> None:
    del question, steps, method_note
    return


def render_quickstart(
    page_key: str,
    steps: list[str],
    note: str | None = None,
) -> None:
    del page_key, steps, note
    return


def render_evidence_guardrails(
    can_answer: list[str] | None = None,
    cannot_answer: list[str] | None = None,
    next_checks: list[str] | None = None,
) -> None:
    del can_answer, cannot_answer, next_checks
    return


def render_workspace_links(
    key_prefix: str,
    actions: list[tuple[str, object, str]],
) -> None:
    valid_actions = [
        (label, page, help_text)
        for label, page, help_text in actions
        if str(label).strip()
    ]
    if not valid_actions:
        return
    st.markdown('<div class="workspace-links-heading">Continue The Investigation</div>', unsafe_allow_html=True)
    cols = st.columns(len(valid_actions))
    for idx, (label, page, help_text) in enumerate(valid_actions):
        with cols[idx]:
            if st.button(
                label,
                key=f"{key_prefix}_nav_{idx}",
                width="stretch",
                help=help_text,
            ):
                st.switch_page(page)
            if help_text:
                st.markdown(
                    f'<div class="workspace-link-help">{html.escape(help_text, quote=True)}</div>',
                    unsafe_allow_html=True,
                )
