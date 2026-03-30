from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
try:
    import streamlit as st
except ModuleNotFoundError:  # pragma: no cover - import smoke fallback
    class _SessionStateStub(dict):
        pass

    class _StreamlitStub:
        session_state: dict[str, Any] = _SessionStateStub()

        def __getattr__(self, name: str):
            raise AttributeError(name)

    st = _StreamlitStub()
from fpdf import XPos, YPos

from tfl_app.ui.pdf.export_utils import fmt_usd
from tfl_app.ui.pdf.charts import (
    PDF_CHART_ERROR_KEY,
    _build_focus_chart,
    _calc_share_range,
    _chart_lines,
    _clear_pdf_chart_error,
    _coerce_pdf_bytes,
)
from tfl_app.ui.pdf.document import _create_report_pdf_shell
from tfl_app.ui.pdf.layout import (
    PDF_BODY_SIZE,
    PDF_CAPTION_SIZE,
    PDF_COLOR_NAVY_DARK,
    PDF_COLOR_TEXT,
    PDF_FOOTNOTE_SIZE,
    PDF_FONT_SANS,
    _pdf_add_bullets,
    _pdf_add_callout_box,
    _pdf_add_chart,
    _pdf_add_focus_highlights,
    _pdf_add_heading,
    _pdf_add_kpi_table,
    _pdf_add_numbered_section_title,
    _pdf_add_paragraph,
    _pdf_add_rule,
    _pdf_add_section_title,
    _pdf_add_subheading,
    _pdf_safe_text,
)
from tfl_app.ui.pdf.runtime_helpers import configure_helpers
from tfl_app.ui.pdf.section_conditionals import _derive_section_conditionals

from tfl_app.ui.pdf.builders import (
    _build_report_payload,
    _hydrate_report_inputs,
    _slugify,
)

def _build_report_pdf_bytes(payload: dict) -> bytes:
    payload = dict(payload) if isinstance(payload, dict) else {}

    def _safe_str(value, default: str = "") -> str:
        if value is None:
            return default
        try:
            return str(value)
        except Exception:
            return default

    def _safe_float(value, default: float = 0.0) -> float:
        if value is None:
            return default
        try:
            if isinstance(value, str):
                txt = value.strip().replace(",", "")
                if txt == "":
                    return default
                return float(txt)
            return float(value)
        except Exception:
            return default

    def _safe_bool(value, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return bool(value)
        txt = _safe_str(value).strip().lower()
        if txt in {"true", "1", "yes", "y"}:
            return True
        if txt in {"false", "0", "no", "n"}:
            return False
        return default

    def _safe_list(value) -> list:
        return value if isinstance(value, list) else []

    def _safe_dict(value) -> dict:
        return value if isinstance(value, dict) else {}

    default_payload = {
        "report_title": "Lobby Look-Up Report",
        "session_label": "Selected Session",
        "scope_label": "Selected Session",
        "scope_session_label": "Selected Session",
        "focus_label": "All",
        "generated_date": datetime.now().strftime("%B %d, %Y"),
        "generated_ts": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_low": "$0",
        "total_high": "$0",
        "tfl_low": "$0",
        "tfl_high": "$0",
        "private_low": "$0",
        "private_high": "$0",
        "tfl_share_low_pct": "0.0",
        "tfl_share_high_pct": "0.0",
        "unique_lobbyists_total": "0",
        "unique_lobbyists_tfl": "0",
        "unique_clients_total": "0",
        "unique_clients_tfl": "0",
        "witness_activity_summary": "No witness-list data available for this scope/session.",
        "existing_law_gap_summary": "",
        "recommended_fix_statute": "",
        "implementation_notes": "",
        "data_sources_bullets": "",
        "disclaimer_note": "",
        "scope_note": "",
        "focus_section": {},
        "witness_counts": {},
        "top_bills": [],
        "top_subjects": [],
        "chart_entity_types_data": [],
        "conditional_exec_sentences": [],
        "conditional_focus_sentence": "",
        "focus_highlights_intro": "",
        "focus_snapshot_paragraph": "",
        "has_top_bills": False,
        "has_top_subjects": False,
    }
    for key, value in default_payload.items():
        payload.setdefault(key, value)

    numeric_defaults = {
        "total_low_value": 0.0,
        "total_high_value": 0.0,
        "tfl_low_value": 0.0,
        "tfl_high_value": 0.0,
        "private_low_value": 0.0,
        "private_high_value": 0.0,
        "tfl_share_low_pct_value": 0.0,
        "tfl_share_high_pct_value": 0.0,
        "private_share_low_pct_value": 0.0,
        "private_share_high_pct_value": 0.0,
        "tfl_mid_share_pct_value": 0.0,
    }
    for key, fallback in numeric_defaults.items():
        payload[key] = _safe_float(payload.get(key), fallback)

    string_keys = [
        "report_title",
        "session_label",
        "scope_label",
        "scope_session_label",
        "focus_label",
        "generated_date",
        "generated_ts",
        "total_low",
        "total_high",
        "tfl_low",
        "tfl_high",
        "private_low",
        "private_high",
        "tfl_share_low_pct",
        "tfl_share_high_pct",
        "unique_lobbyists_total",
        "unique_lobbyists_tfl",
        "unique_clients_total",
        "unique_clients_tfl",
        "witness_activity_summary",
        "existing_law_gap_summary",
        "recommended_fix_statute",
        "implementation_notes",
        "data_sources_bullets",
        "disclaimer_note",
        "scope_note",
        "conditional_focus_sentence",
        "focus_highlights_intro",
        "focus_snapshot_paragraph",
    ]
    for key in string_keys:
        payload[key] = _safe_str(payload.get(key), _safe_str(default_payload.get(key, "")))

    payload["focus_section"] = _safe_dict(payload.get("focus_section"))
    payload["witness_counts"] = _safe_dict(payload.get("witness_counts"))
    payload["top_bills"] = [b for b in _safe_list(payload.get("top_bills")) if isinstance(b, dict)]
    payload["top_subjects"] = [s for s in _safe_list(payload.get("top_subjects")) if isinstance(s, dict)]
    payload["chart_entity_types_data"] = [
        r for r in _safe_list(payload.get("chart_entity_types_data")) if isinstance(r, dict)
    ]
    payload["conditional_exec_sentences"] = [
        _safe_str(s).strip()
        for s in _safe_list(payload.get("conditional_exec_sentences"))
        if _safe_str(s).strip()
    ]
    payload["has_top_bills"] = _safe_bool(payload.get("has_top_bills"), False) or bool(payload["top_bills"])
    payload["has_top_subjects"] = _safe_bool(payload.get("has_top_subjects"), False) or bool(payload["top_subjects"])

    if payload["focus_section"]:
        fs = payload["focus_section"]
        fs["title"] = _safe_str(fs.get("title", ""))
        fs["summary"] = _safe_str(fs.get("summary", ""))

        metrics_safe = []
        for item in _safe_list(fs.get("metrics")):
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                metrics_safe.append((_safe_str(item[0]), _safe_str(item[1])))
        fs["metrics"] = metrics_safe

        fs["bullets"] = [
            _safe_str(item).strip()
            for item in _safe_list(fs.get("bullets"))
            if _safe_str(item).strip()
        ]
        fs["charts"] = _safe_list(fs.get("charts"))
        payload["focus_section"] = fs

    if not _safe_str(payload.get("total_low")).strip():
        payload["total_low"] = fmt_usd(payload["total_low_value"])
    if not _safe_str(payload.get("total_high")).strip():
        payload["total_high"] = fmt_usd(payload["total_high_value"])
    if not _safe_str(payload.get("tfl_low")).strip():
        payload["tfl_low"] = fmt_usd(payload["tfl_low_value"])
    if not _safe_str(payload.get("tfl_high")).strip():
        payload["tfl_high"] = fmt_usd(payload["tfl_high_value"])
    if not _safe_str(payload.get("private_low")).strip():
        payload["private_low"] = fmt_usd(payload["private_low_value"])
    if not _safe_str(payload.get("private_high")).strip():
        payload["private_high"] = fmt_usd(payload["private_high_value"])

    if payload["tfl_share_low_pct_value"] == 0.0 and payload["tfl_share_high_pct_value"] == 0.0:
        share_low, share_high = _calc_share_range(
            payload["tfl_low_value"],
            payload["tfl_high_value"],
            payload["total_low_value"],
            payload["total_high_value"],
        )
        payload["tfl_share_low_pct_value"] = share_low
        payload["tfl_share_high_pct_value"] = share_high
    if not _safe_str(payload.get("tfl_share_low_pct")).strip():
        payload["tfl_share_low_pct"] = f"{payload['tfl_share_low_pct_value']:.1f}"
    if not _safe_str(payload.get("tfl_share_high_pct")).strip():
        payload["tfl_share_high_pct"] = f"{payload['tfl_share_high_pct_value']:.1f}"

    top_bills_safe = []
    for bill in payload["top_bills"]:
        top_bills_safe.append(
            {
                "id": _safe_str(bill.get("id"), "-").strip() or "-",
                "tfl": int(_safe_float(bill.get("tfl"), 0.0)),
                "private": int(_safe_float(bill.get("private"), 0.0)),
                "caption": _safe_str(bill.get("caption"), "").strip(),
                "summary": _safe_str(bill.get("summary"), "").strip(),
            }
        )
    payload["top_bills"] = top_bills_safe

    top_subjects_safe = []
    for subject in payload["top_subjects"]:
        top_subjects_safe.append(
            {
                "Subject": _safe_str(subject.get("Subject"), "").strip(),
                "Oppositions": int(_safe_float(subject.get("Oppositions"), 0.0)),
            }
        )
    payload["top_subjects"] = top_subjects_safe

    entity_rows_safe = []
    for row in payload["chart_entity_types_data"]:
        label = _safe_str(row.get("type"), "").strip()
        if not label:
            continue
        entity_rows_safe.append({"type": label, "count": int(_safe_float(row.get("count"), 0.0))})
    payload["chart_entity_types_data"] = entity_rows_safe

    witness_counts_safe = _safe_dict(payload.get("witness_counts"))
    witness_counts_safe["tfl"] = _safe_dict(witness_counts_safe.get("tfl"))
    witness_counts_safe["private"] = _safe_dict(witness_counts_safe.get("private"))
    for bucket in ("tfl", "private"):
        for position in ("Against", "For", "On"):
            witness_counts_safe[bucket][position] = int(
                _safe_float(witness_counts_safe[bucket].get(position), 0.0)
            )
    payload["witness_counts"] = witness_counts_safe

    def _derive_exec_conditionals() -> list[str]:
        total_mid = (payload["total_low_value"] + payload["total_high_value"]) / 2.0
        tfl_mid = (payload["tfl_low_value"] + payload["tfl_high_value"]) / 2.0
        private_mid = (payload["private_low_value"] + payload["private_high_value"]) / 2.0
        out = []

        if total_mid <= 0:
            out.append("No reportable lobbying compensation was identified for the selected scope.")
        else:
            tfl_mid_pct = (tfl_mid / total_mid) * 100.0
            if tfl_mid_pct >= 50:
                out.append(
                    "Midpoint estimates indicate taxpayer-funded entities represent a majority share of reported lobbying compensation in this scope."
                )
            elif tfl_mid_pct >= 35:
                out.append(
                    "Midpoint estimates indicate taxpayer-funded entities represent a substantial share of reported lobbying compensation in this scope."
                )
            elif tfl_mid_pct >= 15:
                out.append(
                    "Midpoint estimates indicate taxpayer-funded entities represent a material, non-trivial share of reported lobbying compensation in this scope."
                )
            else:
                out.append(
                    "Midpoint estimates indicate taxpayer-funded entities represent a smaller share of reported lobbying compensation in this scope."
                )

            delta = tfl_mid - private_mid
            if abs(delta) <= (0.10 * total_mid):
                out.append("The midpoint funding mix is near parity between taxpayer-funded and private activity.")
            elif delta > 0:
                out.append("The midpoint funding mix shows taxpayer-funded activity outweighing private activity.")
            else:
                out.append("The midpoint funding mix shows private activity outweighing taxpayer-funded activity.")

        tfl_counts = payload["witness_counts"].get("tfl", {})
        tfl_against = int(tfl_counts.get("Against", 0))
        tfl_for = int(tfl_counts.get("For", 0))
        tfl_on = int(tfl_counts.get("On", 0))
        if (tfl_against + tfl_for + tfl_on) <= 0:
            out.append("No witness-position activity was available in the selected scope/session.")
        else:
            if tfl_against >= max(tfl_for, tfl_on):
                stance = "taxpayer-funded testimony skews toward opposition"
            elif tfl_for >= max(tfl_against, tfl_on):
                stance = "taxpayer-funded testimony skews toward support"
            else:
                stance = "taxpayer-funded testimony is mixed across positions"
            out.append(
                f"In witness data, {stance} ({tfl_against:,} Against, {tfl_for:,} For, {tfl_on:,} On)."
            )
        return [s for s in out if _safe_str(s).strip()]

    def _derive_focus_context_sentence() -> tuple[str, str]:
        focus_label_txt = _safe_str(payload.get("focus_label")).strip().lower()
        focus_title_txt = _safe_str(payload.get("focus_section", {}).get("title", "")).strip().lower()
        focus_hint = f"{focus_label_txt} {focus_title_txt}".strip()

        if "client" in focus_hint:
            return (
                "This snapshot is client-centered and updates with the selected client and filters.",
                "Client-specific indicators drawn from linked lobbying activity and session-scoped records.",
            )
        if "lobbyist" in focus_hint:
            return (
                "This snapshot is lobbyist-centered and updates with the selected lobbyist and filters.",
                "Lobbyist-specific indicators drawn from linked client relationships and session activity.",
            )
        if "legislator" in focus_hint:
            return (
                "This snapshot is legislator-centered and updates with the selected legislator and filters.",
                "Legislator-specific indicators drawn from authored bills, witness behavior, and related activity.",
            )
        if "bill" in focus_hint:
            return (
                "This snapshot is bill-centered and updates with the selected bill and filters.",
                "Bill-specific indicators drawn from witness records, status history, and subject patterns.",
            )
        return (
            "This snapshot updates from the current filters and focus selection.",
            "Most relevant findings generated for the selected focus.",
        )

    computed_exec_conditionals = _derive_exec_conditionals()
    combined_exec_conditionals = []
    for sentence in payload["conditional_exec_sentences"] + computed_exec_conditionals:
        clean_sentence = _safe_str(sentence).strip()
        if clean_sentence and clean_sentence not in combined_exec_conditionals:
            combined_exec_conditionals.append(clean_sentence)
    payload["conditional_exec_sentences"] = combined_exec_conditionals

    default_focus_sentence, default_focus_intro = _derive_focus_context_sentence()
    if not _safe_str(payload.get("conditional_focus_sentence")).strip():
        payload["conditional_focus_sentence"] = default_focus_sentence
    if not _safe_str(payload.get("focus_highlights_intro")).strip():
        payload["focus_highlights_intro"] = default_focus_intro

    def _derive_focus_snapshot_paragraph() -> str:
        focus_section_local = _safe_dict(payload.get("focus_section"))
        focus_title = _safe_str(focus_section_local.get("title", "")).strip()
        focus_label = _safe_str(payload.get("focus_label"), "This focus").strip() or "This focus"
        focus_subject = focus_title or focus_label
        focus_hint = f"{focus_label.lower()} {focus_title.lower()}".strip()

        if "client" in focus_hint:
            focus_type = "client"
        elif "lobbyist" in focus_hint:
            focus_type = "lobbyist"
        elif "legislator" in focus_hint:
            focus_type = "legislator"
        elif "bill" in focus_hint:
            focus_type = "bill"
        else:
            focus_type = "general"

        metric_map = {}
        for metric in _safe_list(focus_section_local.get("metrics")):
            if not isinstance(metric, (list, tuple)) or len(metric) < 2:
                continue
            label = " ".join(_safe_str(metric[0]).strip().lower().split())
            if label:
                metric_map[label] = _safe_str(metric[1]).strip()

        def _extract_numbers(value) -> list[float]:
            txt = _safe_str(value).replace(",", "").strip()
            if not txt:
                return []
            cleaned = "".join(ch if (ch.isdigit() or ch in ".-") else " " for ch in txt)
            out = []
            for token in cleaned.split():
                try:
                    out.append(float(token))
                except Exception:
                    continue
            return out

        def _first_number(value) -> float:
            nums = _extract_numbers(value)
            return nums[0] if nums else 0.0

        def _range_midpoint(value) -> float:
            nums = _extract_numbers(value)
            if not nums:
                return 0.0
            if len(nums) == 1:
                return nums[0]
            return (nums[0] + nums[1]) / 2.0

        def _metric_value(*labels: str) -> str:
            for label in labels:
                key = " ".join(_safe_str(label).strip().lower().split())
                if key and key in metric_map:
                    val = _safe_str(metric_map.get(key, "")).strip()
                    if val:
                        return val
            return ""

        def _metric_int(*labels: str) -> int:
            val = _metric_value(*labels)
            if not val:
                return 0
            return int(_first_number(val))

        def _first_int_after_keyword(text: str, keyword: str) -> int | None:
            text_norm = _safe_str(text)
            key_norm = _safe_str(keyword).strip().lower()
            idx = text_norm.lower().find(key_norm)
            if idx < 0:
                return None
            tail = text_norm[idx + len(key_norm):]
            cleaned = "".join(ch if ch.isdigit() else " " for ch in tail)
            tokens = [tok for tok in cleaned.split() if tok]
            if not tokens:
                return None
            try:
                return int(tokens[0])
            except Exception:
                return None

        def _sentence_case(text: str) -> str:
            t = _safe_str(text).strip()
            if not t:
                return ""
            return t[0].upper() + t[1:]

        parts = []
        signals_used = 0
        focus_specific_signals = 0

        if focus_type == "client":
            parts.append(f"{focus_subject} functions as a client-centered hub in the advocacy network for this scope.")
        elif focus_type == "lobbyist":
            parts.append(f"{focus_subject} functions as a lobbyist-centered conduit between client portfolios and legislative influence.")
        elif focus_type == "legislator":
            parts.append(f"{focus_subject} is evaluated through authored-bill outcomes and observed witness pressure patterns.")
        elif focus_type == "bill":
            parts.append(f"{focus_subject} functions as a bill-level pressure point where support and opposition activity converge.")
        else:
            parts.append(f"{focus_subject} reflects a concentrated set of relationships in the selected scope.")

        focus_clients_total = 0
        focus_clients_tfl = 0
        client_scope = "none"
        if focus_type == "client":
            # Client focus represents a single selected client; infer TFL status from client metrics.
            focus_clients_total = 1
            client_tfl_flag = _metric_value("taxpayer funded")
            normalized_flag = client_tfl_flag.strip().lower() if client_tfl_flag else ""
            if normalized_flag in {"yes", "true", "1"}:
                focus_clients_tfl = 1
                client_scope = "focus"
            elif normalized_flag in {"no", "false", "0"}:
                focus_clients_tfl = 0
                client_scope = "focus"
            else:
                # If classification is unavailable, suppress this ratio sentence for client focus.
                focus_clients_total = 0
                focus_clients_tfl = 0
        elif focus_type == "lobbyist":
            focus_clients_total = _metric_int("total clients")
            focus_clients_tfl = _metric_int("taxpayer-funded clients", "taxpayer funded clients")
            private_clients = _metric_int("private clients")
            if focus_clients_total <= 0 and (focus_clients_tfl + private_clients) > 0:
                focus_clients_total = focus_clients_tfl + private_clients
            if focus_clients_total <= 0:
                focus_clients_total = int(_safe_float(payload.get("focus_clients_total"), 0.0))
            if focus_clients_tfl <= 0:
                focus_clients_tfl = int(_safe_float(payload.get("focus_clients_tfl"), 0.0))
            if focus_clients_total > 0:
                client_scope = "focus"
        elif focus_type == "general":
            focus_clients_total = int(_safe_float(payload.get("focus_clients_total"), 0.0))
            focus_clients_tfl = int(_safe_float(payload.get("focus_clients_tfl"), 0.0))
            if focus_clients_total > 0:
                client_scope = "focus"
            else:
                focus_clients_total = int(_safe_float(payload.get("unique_clients_total"), 0.0))
                focus_clients_tfl = int(_safe_float(payload.get("unique_clients_tfl"), 0.0))
                if focus_clients_total > 0:
                    client_scope = "scope"

        if focus_clients_total > 0 and focus_clients_tfl > focus_clients_total:
            focus_clients_tfl = focus_clients_total
        if focus_clients_total > 0 and client_scope == "focus":
            focus_specific_signals += 1

        add_client_mix = focus_type in {"lobbyist", "general"}
        if add_client_mix and focus_clients_total > 0:
            signals_used += 1
            client_share_tfl = focus_clients_tfl / focus_clients_total
            prefix = "Across the selected scope, " if client_scope == "scope" else ""
            client_base_noun = "clients in the selected scope" if client_scope == "scope" else "associated clients"
            if client_share_tfl >= 0.60:
                parts.append(
                    f"{prefix}taxpayer-funded entities represent {focus_clients_tfl:,} of {focus_clients_total:,} {client_base_noun} "
                    f"({client_share_tfl:.0%}), indicating a strongly public-sector weighted client base."
                )
            elif client_share_tfl >= 0.30:
                parts.append(
                    f"{prefix}taxpayer-funded entities represent {focus_clients_tfl:,} of {focus_clients_total:,} {client_base_noun} "
                    f"({client_share_tfl:.0%}), indicating mixed but meaningful institutional exposure."
                )
            elif client_share_tfl > 0:
                parts.append(
                    f"{prefix}taxpayer-funded clients are present ({focus_clients_tfl:,} of {focus_clients_total:,} {client_base_noun}) but remain a minority share."
                )
            else:
                parts.append(f"{prefix}no taxpayer-funded clients are visible in the current client set.")

        if focus_type == "client":
            lobbyists_count = _metric_int("lobbyists")
            if lobbyists_count > 0:
                signals_used += 1
                focus_specific_signals += 1
                if lobbyists_count >= 10:
                    parts.append(f"This client is connected to {lobbyists_count:,} lobbyists, indicating broad representation capacity.")
                elif lobbyists_count >= 4:
                    parts.append(f"This client is connected to {lobbyists_count:,} lobbyists, suggesting meaningful representation depth.")
                else:
                    parts.append(f"This client is connected to {lobbyists_count:,} lobbyists in the current scope.")
            tfl_flag = _metric_value("taxpayer funded")
            if tfl_flag:
                signals_used += 1
                focus_specific_signals += 1
                normalized_flag = tfl_flag.strip().lower()
                if normalized_flag in {"yes", "true", "1"}:
                    parts.append("The client is classified as taxpayer-funded in the underlying records.")
                elif normalized_flag in {"no", "false", "0"}:
                    parts.append("The client is not classified as taxpayer-funded in the underlying records.")

        if focus_type == "lobbyist":
            lobby_total_clients = _metric_int("total clients")
            lobby_tfl_clients = _metric_int("taxpayer-funded clients", "taxpayer funded clients")
            if lobby_total_clients > 0:
                signals_used += 1
                focus_specific_signals += 1
                if lobby_tfl_clients > lobby_total_clients:
                    lobby_tfl_clients = lobby_total_clients
                share = (lobby_tfl_clients / lobby_total_clients) if lobby_total_clients > 0 else 0.0
                if share >= 0.60:
                    parts.append(
                        f"At the focus level, this lobbyist's client book is majority taxpayer-funded ({lobby_tfl_clients:,} of {lobby_total_clients:,})."
                    )
                elif share >= 0.30:
                    parts.append(
                        f"At the focus level, taxpayer-funded clients account for {lobby_tfl_clients:,} of {lobby_total_clients:,}, indicating a mixed portfolio."
                    )
                else:
                    parts.append(
                        f"At the focus level, taxpayer-funded clients account for {lobby_tfl_clients:,} of {lobby_total_clients:,}, with private clients dominant."
                    )

        if focus_type == "legislator":
            bills_authored = _metric_int("bills authored")
            bills_opposed_tfl = _metric_int("bills opposed by tfl lobbyists", "tfl lobbyists opposed")
            if bills_authored > 0:
                signals_used += 1
                focus_specific_signals += 1
                if bills_opposed_tfl > bills_authored:
                    bills_opposed_tfl = bills_authored
                if bills_opposed_tfl > 0:
                    oppose_share = bills_opposed_tfl / bills_authored
                    if oppose_share >= 0.50:
                        parts.append(
                            f"A substantial share of authored bills ({bills_opposed_tfl:,} of {bills_authored:,}) drew taxpayer-funded opposition."
                        )
                    elif oppose_share >= 0.25:
                        parts.append(
                            f"A meaningful share of authored bills ({bills_opposed_tfl:,} of {bills_authored:,}) drew taxpayer-funded opposition."
                        )
                    else:
                        parts.append(
                            f"Only a smaller share of authored bills ({bills_opposed_tfl:,} of {bills_authored:,}) drew taxpayer-funded opposition."
                        )
                else:
                    parts.append(f"No authored bills are shown as opposed by taxpayer-funded lobbyists out of {bills_authored:,} authored bills.")

        if focus_type == "bill":
            witness_rows = _metric_int("witness rows")
            tfl_witness = _metric_int("tfl lobbyists (any position)")
            private_witness = _metric_int("private lobbyists (any position)")
            if witness_rows > 0:
                signals_used += 1
                focus_specific_signals += 1
                if witness_rows >= 50:
                    parts.append(f"Witness-list volume is high for this bill ({witness_rows:,} rows), indicating elevated engagement intensity.")
                elif witness_rows >= 20:
                    parts.append(f"Witness-list volume is moderate for this bill ({witness_rows:,} rows).")
                else:
                    parts.append(f"Witness-list volume is limited for this bill ({witness_rows:,} rows).")
            if (tfl_witness + private_witness) > 0:
                signals_used += 1
                focus_specific_signals += 1
                total_w = tfl_witness + private_witness
                tfl_share = tfl_witness / total_w if total_w > 0 else 0.0
                if tfl_share >= 0.60:
                    parts.append(
                        f"Taxpayer-funded participation dominates witness representation ({tfl_witness:,} of {total_w:,} lobbyists recorded by funding class)."
                    )
                elif tfl_share >= 0.40:
                    parts.append(
                        f"Taxpayer-funded and private witness representation are comparatively balanced ({tfl_witness:,} vs {private_witness:,})."
                    )
                else:
                    parts.append(
                        f"Private witness representation exceeds taxpayer-funded participation ({private_witness:,} vs {tfl_witness:,})."
                    )

        focus_tfl_range_value = _metric_value("taxpayer-funded range", "taxpayer funded range")
        focus_private_range_value = _metric_value("private range")
        has_focus_comp_ranges = bool(focus_tfl_range_value or focus_private_range_value)
        tfl_mid = _range_midpoint(focus_tfl_range_value)
        pri_mid = _range_midpoint(focus_private_range_value)
        if has_focus_comp_ranges:
            focus_specific_signals += 1
        if (tfl_mid + pri_mid) <= 0:
            tfl_low = max(_safe_float(payload.get("tfl_low_value"), 0.0), 0.0)
            tfl_high = max(_safe_float(payload.get("tfl_high_value"), 0.0), 0.0)
            pri_low = max(_safe_float(payload.get("private_low_value"), 0.0), 0.0)
            pri_high = max(_safe_float(payload.get("private_high_value"), 0.0), 0.0)
            tfl_mid = (tfl_low + tfl_high) / 2.0 if (tfl_low > 0 or tfl_high > 0) else 0.0
            pri_mid = (pri_low + pri_high) / 2.0 if (pri_low > 0 or pri_high > 0) else 0.0

        funding_mid_total = tfl_mid + pri_mid
        if funding_mid_total > 0:
            signals_used += 1
            funding_delta = tfl_mid - pri_mid
            comp_scope = "within this focus" if has_focus_comp_ranges else "across the selected scope"
            if abs(funding_delta) <= (0.10 * funding_mid_total):
                parts.append(
                    f"Midpoint compensation estimates indicate near parity between taxpayer-funded and private financing {comp_scope}."
                )
            elif funding_delta > 0:
                parts.append(
                    f"Midpoint compensation estimates indicate taxpayer-funded financing exceeds private financing {comp_scope}."
                )
            else:
                parts.append(
                    f"Midpoint compensation estimates indicate private financing exceeds taxpayer-funded financing {comp_scope}."
                )

        tfl_against = 0
        tfl_for = 0
        tfl_on = 0
        witness_scope = "scope"
        for bullet in _safe_list(focus_section_local.get("bullets")):
            bullet_txt = _safe_str(bullet)
            if "witness positions" not in bullet_txt.lower():
                continue
            parsed_against = _first_int_after_keyword(bullet_txt, "Against")
            parsed_for = _first_int_after_keyword(bullet_txt, "For")
            parsed_on = _first_int_after_keyword(bullet_txt, "On")
            if parsed_against is not None:
                tfl_against = parsed_against
            if parsed_for is not None:
                tfl_for = parsed_for
            if parsed_on is not None:
                tfl_on = parsed_on
            witness_scope = "focus"
            focus_specific_signals += 1
            break
        if (tfl_against + tfl_for + tfl_on) <= 0:
            tfl_bucket = _safe_dict(_safe_dict(payload.get("witness_counts", {})).get("tfl", {}))
            tfl_against = int(_safe_float(tfl_bucket.get("Against"), 0.0))
            tfl_for = int(_safe_float(tfl_bucket.get("For"), 0.0))
            tfl_on = int(_safe_float(tfl_bucket.get("On"), 0.0))

        witness_total = tfl_against + tfl_for + tfl_on
        if witness_total > 0:
            signals_used += 1
            witness_prefix = "Across the selected scope, " if witness_scope == "scope" else "At the focus level, "
            if tfl_against > max(tfl_for, tfl_on):
                parts.append(
                    f"{witness_prefix}witness posture skews toward opposition ({tfl_against:,} Against vs {tfl_for:,} For)."
                )
            elif tfl_for > max(tfl_against, tfl_on):
                parts.append(
                    f"{witness_prefix}witness posture skews toward support ({tfl_for:,} For vs {tfl_against:,} Against)."
                )
            else:
                parts.append(
                    f"{witness_prefix}witness posture is mixed ({tfl_against:,} Against, {tfl_for:,} For, {tfl_on:,} On)."
                )

        bill_signal_count = _metric_int("bills opposed by tfl lobbyists", "tfl lobbyists opposed")
        if bill_signal_count > 0 and focus_type != "legislator":
            signals_used += 1
            focus_specific_signals += 1
            if bill_signal_count >= 10:
                parts.append(
                    "Focus-level opposition intensity is high, with double-digit taxpayer-funded opposition tied to at least one measure."
                )
            elif bill_signal_count >= 5:
                parts.append("Focus-level opposition intensity is moderate across selected measures.")
            else:
                parts.append("Focus-level opposition is present but not concentrated at high volume.")
        elif bill_signal_count <= 0:
            top_bill_counts = [
                int(_safe_float(_safe_dict(bill).get("tfl"), 0.0))
                for bill in _safe_list(payload.get("top_bills"))
                if int(_safe_float(_safe_dict(bill).get("tfl"), 0.0)) > 0
            ]
            total_top_bill = sum(top_bill_counts)
            top_bill_opp = max(top_bill_counts) if top_bill_counts else 0
            top_bill_share = (top_bill_opp / total_top_bill) if total_top_bill > 0 else 0.0
            if top_bill_opp > 0:
                signals_used += 1
                if top_bill_opp >= 10 or top_bill_share >= 0.45:
                    parts.append("Scope-level bill data indicates concentrated opposition around a narrow set of proposals.")
                elif top_bill_opp >= 5 or top_bill_share >= 0.30:
                    parts.append("Scope-level bill data indicates moderate concentration in opposition activity.")
                else:
                    parts.append("Scope-level bill data indicates opposition activity is relatively diffuse.")

        if focus_specific_signals >= 3:
            parts.append(
                "Taken together, focus-specific signals indicate a clear and internally consistent advocacy profile within the broader taxpayer-funded lobbying landscape."
            )
        elif signals_used >= 3:
            parts.append(
                "Taken together, the available indicators provide a coherent directional profile for this focus, though portions of the profile rely on scope-level context."
            )
        else:
            parts.append(
                "Available focus-specific indicators are limited, but the observable record still places this focus within the broader taxpayer-funded lobbying landscape."
            )

        clean_parts = [_sentence_case(p.rstrip(".")) + "." for p in parts if _safe_str(p).strip()]
        return " ".join(clean_parts)

    if not _safe_str(payload.get("focus_snapshot_paragraph")).strip():
        payload["focus_snapshot_paragraph"] = _derive_focus_snapshot_paragraph()

    section_conditionals = _derive_section_conditionals(payload)
    pdf = _create_report_pdf_shell(payload)

    y0 = pdf.get_y()
    pdf.set_fill_color(*PDF_COLOR_NAVY_DARK)
    pdf.rect(pdf.l_margin, y0, pdf.w - pdf.l_margin - pdf.r_margin, 1.8, "F")
    pdf.ln(2.6)

    _pdf_add_heading(pdf, "TAXPAYER-FUNDED LOBBYING IN TEXAS", size=17)
    _pdf_add_subheading(
        pdf,
        f"Analysis of the {payload['session_label']} Legislative Session",
        size=12,
    )
    pdf.set_font(PDF_FONT_SANS, "", PDF_BODY_SIZE - 0.3)
    pdf.set_text_color(*PDF_COLOR_TEXT)
    pdf.cell(0, 4.8, _pdf_safe_text("Prepared by Texas Taxpayer Lobbying Transparency Center"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 4.8, _pdf_safe_text(f"Generated: {payload['generated_date']}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 4.8, _pdf_safe_text(f"Scope: {payload['scope_session_label']}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 4.8, _pdf_safe_text(f"Focus: {payload['focus_label']}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1.2)
    _pdf_add_rule(pdf)

    _pdf_add_section_title(pdf, "Executive Summary")
    exec_summary = (
        "Texas taxpayers should not be compelled to finance political advocacy through their own government. "
        f"During the {payload['session_label']} Legislative Session, registered lobbying activity reported "
        f"compensation ranges totaling between {payload['total_low']} and {payload['total_high']}. Within that total, "
        f"taxpayer-funded lobbying activity accounted for approximately {payload['tfl_low']} to {payload['tfl_high']}, "
        f"while privately funded lobbying accounted for approximately {payload['private_low']} to {payload['private_high']}. "
        f"Even under conservative assumptions, taxpayer-funded lobbying represented roughly {payload['tfl_share_low_pct']}% "
        f"to {payload['tfl_share_high_pct']}% of all reported lobbying compensation during this scope."
    )
    _pdf_add_paragraph(pdf, exec_summary, size=11)
    if payload.get("scope_note"):
        _pdf_add_paragraph(pdf, payload["scope_note"], size=10)
    exec_summary_2 = (
        "This report explains why taxpayer-funded lobbying is structurally inconsistent with transparent and "
        "accountable government, documents the scale of the practice in "
        f"{payload['session_label']}, and identifies the legislation and policy areas most frequently opposed by "
        "taxpayer-funded lobbyists. The conclusion is straightforward: Texas should abolish taxpayer-funded lobbying "
        "by political subdivisions and close both direct and indirect funding pathways so public money is used to provide "
        "public services, not to finance political advocacy."
    )
    _pdf_add_paragraph(pdf, exec_summary_2, size=11)
    exec_conditional = [
        str(s).strip() for s in payload.get("conditional_exec_sentences", []) if str(s).strip()
    ]
    if exec_conditional:
        _pdf_add_callout_box(pdf, "Data-Driven Context", exec_conditional[0])
        if len(exec_conditional) > 1:
            _pdf_add_bullets(pdf, exec_conditional[1:], size=9.8, line_h=4.8)

    _pdf_add_subheading(pdf, "Key Metrics", size=11)
    metrics = [
        ("Total lobbying range", f"{payload['total_low']} - {payload['total_high']}"),
        ("Taxpayer-funded range", f"{payload['tfl_low']} - {payload['tfl_high']}"),
        ("Private range", f"{payload['private_low']} - {payload['private_high']}"),
        ("Unique lobbyists", payload["unique_lobbyists_total"]),
        ("Lobbyists w/ TFL clients", payload["unique_lobbyists_tfl"]),
        ("Unique clients", payload["unique_clients_total"]),
        ("Taxpayer-funded clients", payload["unique_clients_tfl"]),
    ]
    _pdf_add_kpi_table(pdf, metrics, size=10)

    highlights = [
        f"Taxpayer-funded share: {payload['tfl_share_low_pct']}% - {payload['tfl_share_high_pct']}%",
        f"Taxpayer-funded range: {payload['tfl_low']} - {payload['tfl_high']}",
        f"Private range: {payload['private_low']} - {payload['private_high']}",
    ]
    _pdf_add_subheading(pdf, "Report Highlights", size=10)
    _pdf_add_bullets(pdf, highlights, size=10)
    _pdf_add_callout_box(
        pdf,
        "Key Claim: Taxpayer-Funded Share Range",
        (
            f"Even under conservative assumptions, taxpayer-funded lobbying represented "
            f"{payload['tfl_share_low_pct']}% to {payload['tfl_share_high_pct']}% of all reported "
            "lobbying compensation in this scope."
        ),
    )

    focus_section = payload.get("focus_section")
    if focus_section and isinstance(focus_section, dict):
        title = focus_section.get("title", "").strip()
        summary = focus_section.get("summary", "").strip()
        metrics = focus_section.get("metrics", [])
        bullets = focus_section.get("bullets", [])
        charts = focus_section.get("charts", [])

        if title or summary or metrics or bullets or charts:
            _pdf_add_section_title(pdf, "Focus Snapshot")
            if title:
                _pdf_add_subheading(pdf, title, size=11)
            if summary:
                _pdf_add_paragraph(pdf, summary, size=11)
            focus_dynamic_sentence = str(payload.get("conditional_focus_sentence", "")).strip()
            if focus_dynamic_sentence:
                _pdf_add_callout_box(
                    pdf,
                    "Focus Lens",
                    focus_dynamic_sentence,
                    accent=(34, 96, 74),
                )
            focus_snapshot_paragraph = _safe_str(payload.get("focus_snapshot_paragraph", "")).strip()
            if focus_snapshot_paragraph:
                _pdf_add_paragraph(pdf, focus_snapshot_paragraph, size=10.8, line_h=5.2)
            if bullets:
                _pdf_add_subheading(pdf, "Focus Highlights", size=10)
                _pdf_add_paragraph(
                    pdf,
                    str(payload.get("focus_highlights_intro", "Most relevant findings for the selected focus.")),
                    size=9.8,
                    line_h=5.0,
                )
                _pdf_add_focus_highlights(pdf, bullets, size=10)
            if charts:
                _pdf_add_subheading(pdf, "Focus Charts", size=10)
                for chart in charts:
                    fig = _build_focus_chart(chart if isinstance(chart, dict) else {})
                    if fig:
                        caption = str(chart.get("caption", "Focus Chart")).strip() if isinstance(chart, dict) else "Focus Chart"
                        _pdf_add_chart(pdf, fig, caption)
            _pdf_add_rule(pdf)

    _pdf_add_numbered_section_title(pdf, 1, f"THE SCALE OF LOBBYING IN {payload['session_label']}")
    scale_p1 = (
        "Lobbying in Texas is a major industry, and the compensation ranges reported to the state reflect the scale "
        "at which public policy is contested. For the "
        f"{payload['session_label']} session, the total reported lobbying compensation range across the selected scope "
        f"was {payload['total_low']} to {payload['total_high']}. Taxpayer-funded entities accounted for "
        f"{payload['tfl_low']} to {payload['tfl_high']} of that total, while privately funded entities accounted for "
        f"{payload['private_low']} to {payload['private_high']}. Because compensation is disclosed in ranges rather than "
        "precise amounts, these figures should be understood as conservative estimates of the activity captured in "
        "the underlying registrations and filings."
    )
    _pdf_add_paragraph(pdf, scale_p1, size=11)
    scale_p2 = (
        "The composition of the participating universe underscores why taxpayer-funded lobbying is not a marginal "
        "phenomenon. Across this scope, "
        f"{payload['unique_lobbyists_total']} unique lobbyists were observed, including {payload['unique_lobbyists_tfl']} "
        "who represented at least one taxpayer-funded client. Likewise, "
        f"{payload['unique_clients_total']} clients appeared in the data, including {payload['unique_clients_tfl']} that "
        "qualify as governmental or taxpayer-funded entities. The point is not merely that local governments participate "
        "in the process; it is that they do so at a scale capable of shaping agendas, crowding out citizen influence, "
        "and resisting reforms that would otherwise be evaluated on their merits."
    )
    _pdf_add_paragraph(pdf, scale_p2, size=11)
    if _safe_str(section_conditionals.get("scale")).strip():
        _pdf_add_paragraph(pdf, section_conditionals["scale"], size=10.5)

    comp_df = pd.DataFrame(
        [
            {"Funding": "Taxpayer Funded", "Low": payload["tfl_low_value"], "High": payload["tfl_high_value"]},
            {"Funding": "Private", "Low": payload["private_low_value"], "High": payload["private_high_value"]},
        ]
    )
    comp_long = comp_df.melt(id_vars="Funding", value_vars=["Low", "High"], var_name="Estimate", value_name="Total")
    if not comp_long.empty and comp_long["Total"].sum() > 0:
        fig_comp = px.bar(
            comp_long,
            x="Funding",
            y="Total",
            color="Estimate",
            barmode="group",
            text="Total",
            color_discrete_map={"Low": "#004c6d", "High": "#1f77b4"},
        )
        fig_comp.update_traces(texttemplate="$%{text:,.0f}", textposition="outside", cliponaxis=False)
        fig_comp.update_layout(
            template="plotly_white",
            title="Lobbying Compensation Range by Funding Type",
            yaxis_title="Reported compensation",
            xaxis_title="",
            legend_title="Estimate",
            margin=dict(l=40, r=20, t=50, b=30),
        )
        fig_comp.update_yaxes(tickprefix="$", tickformat="~s")
        _pdf_add_chart(pdf, fig_comp, "Chart 1. Lobbying Compensation Range by Funding Type")

    tfl_mid = (payload["tfl_low_value"] + payload["tfl_high_value"]) / 2
    pri_mid = (payload["private_low_value"] + payload["private_high_value"]) / 2
    if (tfl_mid + pri_mid) > 0:
        share_df = pd.DataFrame(
            {"Funding": ["Taxpayer Funded", "Private"], "Total": [tfl_mid, pri_mid]}
        )
        fig_share = px.pie(
            share_df,
            names="Funding",
            values="Total",
            hole=0.5,
            color="Funding",
            color_discrete_map={"Taxpayer Funded": "#0ea5a4", "Private": "#4c78a8"},
        )
        fig_share.update_layout(
            template="plotly_white",
            title="Share of Total Lobbying (Midpoint)",
            margin=dict(l=20, r=20, t=50, b=20),
        )
        _pdf_add_chart(pdf, fig_share, "Chart 2. Share of Total Lobbying - Taxpayer vs Private", width_px=700, height_px=420)

    _pdf_add_numbered_section_title(pdf, 2, "WHAT TAXPAYER-FUNDED LOBBYING IS - AND WHY IT MATTERS")
    def_p1 = (
        "Taxpayer-funded lobbying occurs when political subdivisions use public funds to employ registered lobbyists, "
        "contract with lobbying firms, or pay dues and assessments to associations that, in turn, employ lobbyists. "
        "In practice, the entities involved often include cities, counties, independent school districts, special "
        "districts, authorities, and intergovernmental associations funded by member governments. The distinctive "
        "feature is not the subject matter they address -- nearly any policy can be lobbied -- but the source of the "
        "money used to do it. When advocacy is financed with tax revenue or statutorily compelled fees, citizens are "
        "required to fund political activity as a condition of living, owning property, or receiving basic public services."
    )
    _pdf_add_paragraph(pdf, def_p1, size=11)
    def_p2 = (
        "That is why taxpayer-funded lobbying is a different category of problem than private-sector lobbying. "
        "Private entities spend their own money and must persuade contributors, shareholders, or members that the "
        "advocacy is worthwhile. Public entities spend money that was collected under compulsion and therefore operate "
        "without meaningful donor consent. This creates an unavoidable mismatch between who pays and who benefits. "
        "It also creates a confidence problem: citizens reasonably conclude that government is using their money to "
        "entrench itself, grow its authority, and resist reforms -- especially reforms aimed at fiscal restraint, "
        "regulatory limits, or transparency."
    )
    _pdf_add_paragraph(pdf, def_p2, size=11)

    entity_counts = payload.get("chart_entity_types_data", [])
    if entity_counts:
        entity_df = pd.DataFrame(entity_counts)
        fig_entities = px.bar(
            entity_df.sort_values("count"),
            x="count",
            y="type",
            orientation="h",
            text="count",
            color_discrete_sequence=["#4c78a8"],
        )
        fig_entities.update_traces(textposition="outside", cliponaxis=False)
        fig_entities.update_layout(
            template="plotly_white",
            title="Taxpayer-Funded Clients by Entity Type",
            xaxis_title="Clients",
            yaxis_title="",
            margin=dict(l=40, r=20, t=50, b=30),
        )
        _pdf_add_chart(pdf, fig_entities, "Chart 3. Taxpayer-Funded Clients by Entity Type")

    _pdf_add_numbered_section_title(pdf, 3, f"LEGISLATIVE ACTIVITY PATTERNS IN {payload['session_label']}")
    act_p1 = (
        "Compensation totals explain scale, but legislative activity signals show how that scale is used. "
        f"Across the {payload['session_label']} session, taxpayer-funded lobbyists appeared repeatedly in committee "
        "processes, filing and testifying in ways that illustrate institutional priorities. The witness-list record "
        "indicates that taxpayer-funded entities did not simply monitor legislation; they frequently intervened in it "
        "-- especially on proposals with direct implications for local discretion, budgets, and oversight."
    )
    _pdf_add_paragraph(pdf, act_p1, size=11)
    act_p2 = (
        "Within this scope, witness positions for taxpayer-funded and privately funded interests can be summarized as follows: "
        f"{payload['witness_activity_summary']} The distribution of positions matters because it is a proxy for the "
        "incentives embedded in taxpayer-funded lobbying."
    )
    _pdf_add_paragraph(pdf, act_p2, size=11)
    if _safe_str(section_conditionals.get("activity")).strip():
        _pdf_add_paragraph(pdf, section_conditionals["activity"], size=10.5)

    w_counts = payload.get("witness_counts", {})
    if w_counts:
        w_rows = []
        for position in ["Against", "For", "On"]:
            w_rows.append(
                {
                    "Position": position,
                    "Taxpayer Funded": int(w_counts.get("tfl", {}).get(position, 0)),
                    "Private": int(w_counts.get("private", {}).get(position, 0)),
                }
            )
        w_df = pd.DataFrame(w_rows)
        if not w_df.empty and w_df[["Taxpayer Funded", "Private"]].sum().sum() > 0:
            w_long = w_df.melt(id_vars="Position", var_name="Funding", value_name="Count")
            fig_wit = px.bar(
                w_long,
                x="Position",
                y="Count",
                color="Funding",
                barmode="group",
                text="Count",
                color_discrete_map={"Taxpayer Funded": "#ff6b6b", "Private": "#4c78a8"},
            )
            fig_wit.update_traces(textposition="outside", cliponaxis=False)
            fig_wit.update_layout(
                template="plotly_white",
                title="Witness Positions by Funding Type",
                yaxis_title="Positions",
                xaxis_title="",
                margin=dict(l=40, r=20, t=50, b=30),
            )
            _pdf_add_chart(pdf, fig_wit, "Chart 4. Witness Positions by Funding Type")

    _pdf_add_numbered_section_title(pdf, 4, "THE BILLS MOST OPPOSED BY TAXPAYER-FUNDED LOBBYISTS")
    if payload.get("has_top_bills"):
        bills_p = (
            "The most direct way to see taxpayer-funded lobbying in action is to identify the bills that generated "
            "concentrated opposition from taxpayer-funded entities. The bills below are ranked by the number of "
            "Against filings by taxpayer-funded lobbyists."
        )
        _pdf_add_paragraph(pdf, bills_p, size=11)
        if _safe_str(section_conditionals.get("bills")).strip():
            _pdf_add_paragraph(pdf, section_conditionals["bills"], size=10.5)
        top_bills = payload.get("top_bills", [])
        if top_bills:
            bill_df = pd.DataFrame(
                [{"Bill": b["id"], "Oppositions": b.get("tfl", 0)} for b in top_bills]
            )
            fig_bills = px.bar(
                bill_df.sort_values("Oppositions"),
                x="Oppositions",
                y="Bill",
                orientation="h",
                text="Oppositions",
                color_discrete_sequence=["#d14b4b"],
            )
            fig_bills.update_traces(textposition="outside", cliponaxis=False)
            fig_bills.update_layout(
                template="plotly_white",
                title="Top Bills Opposed by Taxpayer-Funded Lobbyists",
                xaxis_title="Oppositions",
                yaxis_title="",
                margin=dict(l=40, r=20, t=50, b=30),
            )
            _pdf_add_chart(pdf, fig_bills, "Chart 5. Top 5 Bills Opposed by Taxpayer-Funded Lobbyists")
    else:
        _pdf_add_paragraph(pdf, "No bill-level opposition data was available for the selected scope/session.", size=11)

    _pdf_add_numbered_section_title(pdf, 5, "THE POLICY AREAS MOST OPPOSED BY TAXPAYER-FUNDED LOBBYISTS")
    if payload.get("has_top_subjects"):
        subject_p = (
            "Bills are discrete, but policy areas reveal patterns. When opposition is aggregated by subject matter, "
            "taxpayer-funded lobbying tends to cluster in the places where the Legislature can most directly alter "
            "local fiscal and regulatory authority."
        )
        _pdf_add_paragraph(pdf, subject_p, size=11)
        if _safe_str(section_conditionals.get("subjects")).strip():
            _pdf_add_paragraph(pdf, section_conditionals["subjects"], size=10.5)
        top_subjects = payload.get("top_subjects", [])
        if top_subjects:
            subj_df = pd.DataFrame(
                [{"Subject": s["Subject"], "Oppositions": s.get("Oppositions", 0)} for s in top_subjects]
            )
            fig_subjects = px.bar(
                subj_df.sort_values("Oppositions"),
                x="Oppositions",
                y="Subject",
                orientation="h",
                text="Oppositions",
                color_discrete_sequence=["#7aa6c2"],
            )
            fig_subjects.update_traces(textposition="outside", cliponaxis=False)
            fig_subjects.update_layout(
                template="plotly_white",
                title="Top Policy Areas Opposed by Taxpayer-Funded Lobbyists",
                xaxis_title="Oppositions",
                yaxis_title="",
                margin=dict(l=40, r=20, t=50, b=30),
            )
            _pdf_add_chart(pdf, fig_subjects, "Chart 6. Top 5 Policy Areas Opposed by Taxpayer-Funded Lobbyists")
    else:
        _pdf_add_paragraph(pdf, "No subject-level opposition data was available for the selected scope/session.", size=11)

    _pdf_add_numbered_section_title(pdf, 6, "STRUCTURAL INCENTIVES AND THE COMPULSION PROBLEM")
    _pdf_add_paragraph(
        pdf,
        "Taxpayer-funded lobbying persists because it is rational for institutions. Political subdivisions face "
        "budget pressures, political pressures, and administrative demands, and they naturally seek to preserve the "
        "widest possible discretion to manage those pressures. But rationality for institutions is not the same as "
        "legitimacy for taxpayers. When the money used to lobby is collected under compulsion, the normal disciplining "
        "forces of voluntary association are absent. The cost of advocacy is dispersed across taxpayers, while the "
        "perceived benefits -- expanded authority, preserved revenues, reduced oversight -- accrue to the institution.",
        size=11,
    )
    _pdf_add_paragraph(
        pdf,
        "The result is a misalignment: the payer is not the decision-maker, and the decision-maker has an incentive "
        "to externalize the cost. That is why taxpayer-funded lobbying is not merely politics as usual. It is a "
        "financing structure that undermines accountability and encourages institutional self-protection. Over time, "
        "it becomes a form of self-reinforcing governance: public entities use public funds to defend and expand the "
        "very powers that allow them to collect and deploy public funds.",
        size=11,
    )

    _pdf_add_numbered_section_title(pdf, 7, "LEGAL PARITY AND STATUTORY INCONSISTENCY")
    _pdf_add_paragraph(
        pdf,
        "Texas has already recognized that using public money to hire lobbyists raises concerns. State agencies face "
        "statutory restrictions that prevent them from employing registered lobbyists with public funds. Yet political "
        "subdivisions are not subject to uniform prohibitions, and the result is a parity failure. "
        f"{payload['existing_law_gap_summary']}",
        size=11,
    )
    _pdf_add_paragraph(
        pdf,
        "If the state has concluded that state agencies should not use taxpayer dollars to hire registered lobbyists, "
        "the same logic applies -- often more urgently -- to political subdivisions. Local entities are numerous, "
        "collectively spend vast sums, and frequently coordinate through associations that amplify their influence. "
        "In that environment, the absence of a clear prohibition invites continual expansion of the practice and "
        "continued erosion of public trust.",
        size=11,
    )

    _pdf_add_numbered_section_title(pdf, 8, "POLICY SOLUTION: A COMPREHENSIVE BAN ON TAXPAYER-FUNDED LOBBYING")
    _pdf_add_paragraph(
        pdf,
        "The policy principle is simple: public money should not be used to lobby government. A workable statutory "
        "approach is equally straightforward: Texas should extend the existing state-agency prohibition framework to "
        "political subdivisions and close indirect funding pathways that allow local governments to outsource lobbying "
        "through membership associations.",
        size=11,
    )
    _pdf_add_callout_box(
        pdf,
        "Key Claim: Recommended Statutory Reform",
        f"Recommended statutory reform: {payload['recommended_fix_statute']}",
    )
    _pdf_add_paragraph(
        pdf,
        f"A recommended statutory reform is: {payload['recommended_fix_statute']}. Under this approach, the law should "
        "prohibit political subdivisions from using public funds to employ registered lobbyists directly, contract with "
        "registered lobbyists, or pay membership dues or assessments to organizations that employ registered lobbyists "
        "for the purpose of influencing legislation. The ban must be drafted to address both direct payments and indirect "
        "routing of funds. Otherwise, enforcement will become a game of accounting rather than a real protection for taxpayers.",
        size=11,
    )
    _pdf_add_paragraph(
        pdf,
        "Implementation should include clear definitions of political subdivision, public funds, and lobbying "
        "services, and should make explicit that the prohibition applies regardless of whether the money is labeled "
        "appropriated, fee-based, enterprise, or interlocal. The Legislature should also specify enforceable remedies. "
        f"{payload['implementation_notes']}",
        size=11,
    )

    _pdf_add_numbered_section_title(pdf, 9, "DATA SOURCES AND METHODOLOGY")
    _pdf_add_paragraph(pdf, "This report is based on public information drawn from:", size=11)
    bullets = [
        b.strip().lstrip("- ").strip()
        for b in payload.get("data_sources_bullets", "").splitlines()
        if b.strip()
    ]
    _pdf_add_bullets(pdf, bullets, size=10)
    _pdf_add_paragraph(
        pdf,
        "Compensation figures reflect statutory reporting ranges filed with the Texas Ethics Commission. Totals were "
        "calculated by aggregating minimum and maximum disclosed ranges within the selected scope. Witness list activity "
        "reflects publicly available committee records compiled into the Lobby Look-Up dataset. Because compensation is "
        "reported in ranges rather than exact amounts, the totals presented here should be interpreted as conservative "
        "estimates rather than precise expenditures.",
        size=11,
    )

    _pdf_add_numbered_section_title(pdf, 10, "CONCLUSION")
    _pdf_add_paragraph(
        pdf,
        f"During the {payload['session_label']} Legislative Session, taxpayers indirectly financed lobbying activity "
        f"totaling between {payload['tfl_low']} and {payload['tfl_high']} in reported compensation ranges. This practice "
        "compels political financing, entrenches institutional self-interest, and undermines public confidence that "
        "government is operating transparently and accountably.",
        size=11,
    )
    _pdf_add_paragraph(
        pdf,
        "Texas should abolish taxpayer-funded lobbying by political subdivisions and close both direct and indirect "
        "funding pathways. Public money should be used to provide public services -- not to finance political advocacy.",
        size=11,
    )
    if _safe_str(section_conditionals.get("conclusion")).strip():
        _pdf_add_paragraph(pdf, section_conditionals["conclusion"], size=10.5)
    pdf.ln(2)
    pdf.set_font("Helvetica", "I", PDF_CAPTION_SIZE)
    pdf.cell(0, 5, _pdf_safe_text("Prepared by Texas Taxpayer Lobbying Transparency Center"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "I", PDF_FOOTNOTE_SIZE)
    pdf.cell(0, 5, _pdf_safe_text(payload["disclaimer_note"]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    output = pdf.output()
    return output if isinstance(output, (bytes, bytearray)) else output.encode("latin-1")

def _render_pdf_report_section(
    *,
    key_prefix: str,
    session_val: str | None,
    scope_label: str,
    focus_label: str,
    tfl_session_val: str | None,
    report_table_loader=None,
    focus_context: dict | None = None,
) -> None:
    """Render PDF report generation section in an expander."""
    with st.expander("Custom PDF report", expanded=False):
        st.caption("Generate a PDF report using the current filters and selections.")

        sig_key = f"{key_prefix}_report_sig"
        pdf_key = f"{key_prefix}_report_pdf"
        name_key = f"{key_prefix}_report_name"
        signature = f"{session_val}|{scope_label}|{focus_label}"

        if st.session_state.get(sig_key) != signature:
            st.session_state[sig_key] = signature
            if pdf_key in st.session_state:
                del st.session_state[pdf_key]
            if name_key in st.session_state:
                del st.session_state[name_key]

        generate_clicked = st.button(
            "Generate report",
            key=f"{key_prefix}_report_build",
            width="stretch",
            help="Build a PDF using the current filters and selections.",
        )

        if generate_clicked:
            _clear_pdf_chart_error()
            try:
                with st.status("Generating PDF...", expanded=False):
                    loaded_tables: dict[str, pd.DataFrame] = {}
                    if callable(report_table_loader):
                        loaded = report_table_loader()
                        if isinstance(loaded, dict):
                            loaded_tables = {
                                str(key): value
                                for key, value in loaded.items()
                                if isinstance(value, pd.DataFrame)
                            }
                    report_bill_sub_all, report_focus_context = _hydrate_report_inputs(focus_context, loaded_tables)
                    payload = _build_report_payload(
                        session_val=session_val,
                        scope_label=scope_label,
                        focus_label=focus_label,
                        Lobby_TFL_Client_All=loaded_tables.get("Lobby_TFL_Client_All", pd.DataFrame()),
                        Wit_All=loaded_tables.get("Wit_All", pd.DataFrame()),
                        Bill_Status_All=loaded_tables.get("Bill_Status_All", pd.DataFrame()),
                        Bill_Sub_All=report_bill_sub_all,
                        tfl_session_val=tfl_session_val,
                        focus_context=report_focus_context,
                    )
                    pdf_bytes = _coerce_pdf_bytes(_build_report_pdf_bytes(payload))
                    if pdf_bytes and len(pdf_bytes) > 0:
                        st.session_state[pdf_key] = pdf_bytes
                        st.session_state[name_key] = f"tfl-report-{_slugify(focus_label)}.pdf"
                        st.success("Report generated")
            except Exception as e:
                st.error(f"Report generation failed: {str(e)}")

        if pdf_key in st.session_state and st.session_state.get(PDF_CHART_ERROR_KEY):
            st.warning(
                "PDF rendering encountered an issue (charts). "
                "Common cause: missing Kaleido for Plotly images."
            )
            st.caption(st.session_state[PDF_CHART_ERROR_KEY])

        if pdf_key in st.session_state and isinstance(st.session_state[pdf_key], bytes):
            st.download_button(
                "Download PDF",
                st.session_state[pdf_key],
                st.session_state.get(name_key, "report.pdf"),
                "application/pdf",
                key=f"{key_prefix}_dl",
                width="stretch",
            )

PLOTLY_CONFIG = {
    "displayModeBar": "hover",
    "responsive": True,
    "displaylogo": False,
    "modeBarButtonsToRemove": ["select2d", "lasso2d", "autoScale2d"],
    "modeBarButtonsToAdd": ["toggleSpikelines"],
    "toImageButtonOptions": {
        "format": "png",
        "filename": "tfl-chart-export",
        "height": 600,
        "width": 1000,
        "scale": 2,
    },
}
CHART_COLORS = [
    "#8caed3",
    "#6f92b9",
    "#5e7fa3",
    "#4f6f8e",
    "#4f8871",
    "#7d8fa6",
    "#8d7d96",
    "#7b6f86",
    "#a58a64",
    "#6d7682",
]
FUNDING_COLOR_MAP = {"Taxpayer Funded": "#8caed3", "Private": "#6d7682"}
OPPOSITION_COLOR_MAP = {"Opposed by TFL lobbyist": "#be7b7b", "Not opposed by TFL lobbyist": "#748bb0"}
TREND_COLOR_MAP = {"Low estimate": "#8d7d96", "High estimate": "#8caed3"}

def _apply_plotly_layout(
    fig,
    *,
    height: int | None = None,
    showlegend: bool = False,
    legend_title: str | None = None,
    margin_top: int = 30,
):
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="IBM Plex Sans", color="rgba(235,245,255,0.92)", size=12),
        margin=dict(l=8, r=8, t=margin_top, b=8),
        showlegend=showlegend,
        legend_title_text=legend_title,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            font=dict(size=11, color="rgba(223,234,247,0.78)"),
        ),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor="rgba(16,27,41,0.96)",
            bordercolor="rgba(255,255,255,0.10)",
            font=dict(color="rgba(237,245,255,0.95)", size=12),
        ),
        transition=dict(duration=300, easing="cubic-in-out"),
    )
    if height:
        fig.update_layout(height=height)
    fig.update_xaxes(
        showgrid=False,
        zeroline=False,
        showline=False,
        ticks="outside",
        tickfont=dict(color="rgba(223,234,247,0.78)"),
        showspikes=True,
        spikecolor="rgba(134,167,198,0.3)",
        spikethickness=1,
        spikedash="dot",
        spikemode="across",
    )
    fig.update_yaxes(
        showgrid=False,
        zeroline=False,
        showline=False,
        ticks="outside",
        tickfont=dict(color="rgba(223,234,247,0.78)"),
        showspikes=True,
        spikecolor="rgba(134,167,198,0.3)",
        spikethickness=1,
        spikedash="dot",
        spikemode="across",
    )
    return fig
