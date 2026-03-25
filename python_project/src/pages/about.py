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
                kicker="Start Here",
                title="Texas Taxpayer Lobbying Transparency Center",
                subtitle=(
                    "Use official filings to trace who receives public money for lobbying, where that activity is concentrated, "
                    "and how it connects to legislation and local jurisdictions."
                ),
                pills=[
                    "Coverage: 85th-89th sessions",
                    "Primary records: TEC + TLO",
                    "Purpose: taxpayer protection and transparency",
                ],
            )
            _render_journey("about")
            _render_workspace_guide(
                question=(
                    "Where is taxpayer-funded lobbying concentrated, and which entities, bills, and jurisdictions show the highest exposure?"
                ),
                steps=[
                    "Start in Lobbyists to establish statewide scale.",
                    "Move to Clients to verify entity-level filings and disclosures.",
                    "Use Map & Address to test local overlap by jurisdiction or street address.",
                    "Use Legislators to add bill, witness, and staff context.",
                ],
                method_note=(
                    "Compensation is filed as ranges, not exact invoices. Preserve low/high bounds in every interpretation."
                ),
            )
            _render_quickstart(
                "about",
                [
                    "Choose session and scope first.",
                    "Validate any claim in at least two workspaces before publishing.",
                    "Export tables with active filters to preserve auditability.",
                ],
                note="Single charts are directional; defensible findings require cross-page corroboration.",
            )
            _render_evidence_guardrails(
                can_answer=[
                    "Where reported taxpayer-funded lobbying appears most concentrated by session and entity type.",
                    "Which filings connect entities, lobbyists, bills, and jurisdictions in this dataset.",
                    "How large compensation ranges are relative to one another within the selected scope.",
                ],
                cannot_answer=[
                    "Exact invoice-level spend for any single contract.",
                    "Motivation, intent, or legal compliance beyond what filings explicitly report.",
                    "Causal claims without corroboration from additional sources.",
                ],
                next_checks=[
                    "Confirm identity resolution before citing profile-level totals.",
                    "Cross-check findings in at least one adjacent workspace.",
                    "Export table evidence with session and scope preserved.",
                ],
            )

            st.markdown('<div class="section-title">Read This First</div>', unsafe_allow_html=True)
            wf1, wf2 = st.columns([1.5, 1.1])
            with wf1:
                st.markdown(
                    """
        <div class="policy-panel">
          <h3>How to interpret compensation totals</h3>
          <p>Texas Ethics Commission compensation filings are reported as ranges. Treat every total as bounded evidence, not an exact payment ledger.</p>
        </div>
        """,
                    unsafe_allow_html=True,
                )
                st.markdown(
                    """
        <div class="policy-panel">
          <h3>What "taxpayer-funded" means in this app</h3>
          <p>Entities are classified from source records and shown alongside private relationships so users can compare public and private funding exposure in the same frame.</p>
        </div>
        """,
                    unsafe_allow_html=True,
                )
            with wf2:
                st.markdown(
                    """
        <div class="policy-panel">
          <h3>Name matching limitations</h3>
          <p>Public records vary in initials, abbreviations, and spelling. Matching logic improves recall but ambiguity remains; confirm the selected entity before citing profile-level outputs.</p>
        </div>
        """,
                    unsafe_allow_html=True,
                )
                st.markdown(
                    """
        <div class="policy-panel">
          <h3>Data-quality correction process</h3>
          <p>Email <a class="about-link" href="mailto:communications@texaspolicy.com">communications@texaspolicy.com</a> with the session, entity/person name, and a concise issue description.</p>
        </div>
        """,
                    unsafe_allow_html=True,
                )

            st.markdown('<div class="section-title">Recommended Workflow</div>', unsafe_allow_html=True)
            st.markdown(
                """
        <div class="policy-panel">
          <h3>Four-step investigation workflow</h3>
          <p>1) Build the statewide baseline in <b>Lobbyists</b>.<br>
          2) Validate entity-level evidence in <b>Clients</b>.<br>
          3) Test local overlap in <b>Map &amp; Address</b>.<br>
          4) Add legislative context in <b>Legislators</b> before final conclusions.</p>
        </div>
        """,
                unsafe_allow_html=True,
            )

            st.markdown('<div class="section-title">Sources and Methods</div>', unsafe_allow_html=True)
            with st.expander("Texas Ethics Commission (TEC)", expanded=True):
                st.markdown(
                    "Lobby registrations, client relationships, compensation ranges, subject disclosures, and activity reporting."
                )
                st.markdown("[Lobbyist Search and Filings](https://www.ethics.state.tx.us/search/lobby/)")
            with st.expander("Texas Legislature Online (TLO)", expanded=False):
                st.markdown(
                    "Bill status, witness lists, fiscal notes, and bill-subject files used to connect lobbying activity to legislative outcomes."
                )
                st.markdown(
                    "[Bill Files and Downloads](https://capitol.texas.gov/billlookup/filedownloads.aspx) | "
                    "[Bills-by Reports](https://capitol.texas.gov/reports/BillsBy.aspx)"
                )
            with st.expander("Supplemental reference sources", expanded=False):
                st.markdown(
                    "[Transparency USA](https://www.transparencyusa.org/tx/lobbying/clients?cycle=2015-to-now) "
                    "and [House Research Organization staff listings](https://hro.house.texas.gov/staff.aspx) are used for supplemental cross-checks."
                )

            st.markdown('<div class="section-title">Open A Workspace</div>', unsafe_allow_html=True)
            _render_workspace_links(
                "about_open",
                [
                    ("Open Lobbyists", _lobby_page, "Step 1: build statewide totals and concentration."),
                    ("Open Clients", _client_page, "Step 2: verify entity-level contracts, bills, and disclosures."),
                    ("Open Map & Address", _map_page, "Step 3: test local overlap by subdivision and address."),
                    ("Open Legislators", _member_page, "Step 4: add authored-bill and witness context."),
                ],
            )
    finally:
        _pop_context(globals(), _previous, _ctx)
