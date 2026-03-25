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
    '_map_page',
    '_member_page',
    '_render_evidence_guardrails',
    '_render_journey',
    '_render_page_intro',
    '_render_quickstart',
    '_render_workspace_guide',
    '_render_workspace_links',
)


def configure_helpers(**helpers: Any) -> None:
    _configure_helpers(globals(), **helpers)


def render_page(ctx: dict[str, Any] | None = None) -> None:
    _ctx = ctx or {}
    _previous = _push_context(globals(), _ctx)
    try:
            _render_page_intro(
                kicker="Policy Context",
                title="Policy Design Framework",
                subtitle=(
                    "A structured drafting framework for ending taxpayer-funded lobbying through clear definitions, "
                    "enforceable standards, and auditable reporting."
                ),
                pills=[
                    "Framework only, not legal advice",
                    "Use with empirical evidence",
                    "Priority: enforceability and transparency",
                ],
            )
            _render_journey("solutions")
            _render_workspace_guide(
                question="Which policy designs reduce taxpayer-funded lobbying while remaining enforceable and transparent?",
                steps=[
                    "Define covered entities, funds, and lobbying-related activity.",
                    "Set prohibitions and exceptions in operational language.",
                    "Specify disclosure fields, audit authority, and enforcement triggers.",
                    "Test draft language against observed patterns in this dataset.",
                ],
                method_note="This page is a drafting framework, not legal advice.",
            )
            _render_quickstart(
                "solutions",
                [
                    "Write the objective and covered scope before drafting restrictions.",
                    "Test each requirement against available record types.",
                    "Document assumptions when filings do not provide direct evidence.",
                ],
                note="Strong policy design ties every requirement to a verifiable record type.",
            )
            _render_evidence_guardrails(
                can_answer=[
                    "Which drafting choices are likely to be auditable with available filing fields.",
                    "How observed spending and disclosure patterns inform policy tradeoffs.",
                ],
                cannot_answer=[
                    "Final legal sufficiency or constitutional analysis.",
                    "Implementation outcomes without agency process and enforcement data.",
                ],
                next_checks=[
                    "Link each requirement to a verifiable record in this app.",
                    "Flag assumptions that require external legal or fiscal review.",
                ],
            )

            st.markdown(
                '<div class="app-note"><strong>Use with evidence:</strong> Policy drafting choices should be tested against observed spending ranges, entity concentration, bill activity, and witness records in this app.</div>',
                unsafe_allow_html=True,
            )

            p1, p2, p3 = st.columns(3)
            with p1:
                st.markdown(
                    """
        <div class="policy-panel">
          <h3>Observed policy tension</h3>
          <p>Public entities can finance lobbying directly (contracts or staff) or indirectly (dues and associations), creating a persistent consent and accountability gap for taxpayers.</p>
        </div>
        """,
                    unsafe_allow_html=True,
                )
            with p2:
                st.markdown(
                    """
        <div class="policy-panel">
          <h3>Common legislative levers</h3>
          <p>Drafts typically address paid lobbying contracts, association dues used for advocacy, standardized disclosure fields, and enforceable consequences for noncompliance.</p>
        </div>
        """,
                    unsafe_allow_html=True,
                )
            with p3:
                st.markdown(
                    """
        <div class="policy-panel">
          <h3>Implementation risks</h3>
          <p>Ambiguous definitions, inconsistent reporting standards, and unclear enforcement authority can weaken outcomes even when statutory intent is clear.</p>
        </div>
        """,
                    unsafe_allow_html=True,
                )

            st.markdown('<div class="section-title">Illustrative Drafting Framework</div>', unsafe_allow_html=True)
            st.markdown(
                """
        1. **Scope**: Define covered political subdivisions, public funds, and activity definitions.
        2. **Restrictions**: Prohibit or limit use of public funds for registered lobbying and lobbying-related dues.
        3. **Disclosure**: Require standardized reporting fields that can be audited.
        4. **Enforcement**: Establish agency authority, complaint pathways, and penalty structure.
        5. **Transition**: Set timelines for existing contracts, memberships, and reporting updates.
        """
            )

            st.markdown('<div class="section-title">Use Data To Evaluate Policy Tradeoffs</div>', unsafe_allow_html=True)
            st.markdown(
                "Use the workspaces below to quantify exposure, identify concentration by entity type, and connect spending patterns to legislative activity."
            )
            _render_workspace_links(
                "solutions_open",
                [
                    ("Open Lobbyists Data", _lobby_page, "Measure statewide totals, concentration, and trend lines."),
                    ("Open Clients Data", _client_page, "Inspect entity-level contracts, disclosures, and bill activity."),
                    ("Open Map & Address", _map_page, "Evaluate local overlap by jurisdiction."),
                    ("Open Legislators", _member_page, "Connect funding patterns to authored bills and witness activity."),
                ],
            )
    finally:
        _pop_context(globals(), _previous, _ctx)
