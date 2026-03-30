from __future__ import annotations


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


def _safe_list(value) -> list:
    return value if isinstance(value, list) else []


def _safe_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _derive_section_conditionals(payload: dict) -> dict[str, str]:
    out = {
        "scale": "",
        "activity": "",
        "bills": "",
        "subjects": "",
        "conclusion": "",
    }

    total_clients = int(_safe_float(payload.get("unique_clients_total"), 0.0))
    tfl_clients = int(_safe_float(payload.get("unique_clients_tfl"), 0.0))
    if total_clients > 0:
        tfl_client_share = (tfl_clients / total_clients) * 100.0
        if tfl_client_share >= 50:
            out["scale"] = (
                "Taxpayer-funded entities make up a majority of unique clients in this scope, indicating broad institutional participation in lobbying activity."
            )
        elif tfl_client_share >= 30:
            out["scale"] = (
                "Taxpayer-funded entities represent a substantial minority of unique clients in this scope, indicating durable institutional presence in lobbying activity."
            )
        elif tfl_client_share > 0:
            out["scale"] = (
                "Taxpayer-funded entities represent a smaller but observable share of unique clients in this scope."
            )

    tfl_counts = _safe_dict(payload.get("witness_counts", {})).get("tfl", {})
    pri_counts = _safe_dict(payload.get("witness_counts", {})).get("private", {})
    tfl_against = int(_safe_float(_safe_dict(tfl_counts).get("Against"), 0.0))
    tfl_for = int(_safe_float(_safe_dict(tfl_counts).get("For"), 0.0))
    pri_against = int(_safe_float(_safe_dict(pri_counts).get("Against"), 0.0))
    pri_for = int(_safe_float(_safe_dict(pri_counts).get("For"), 0.0))
    if (tfl_against + tfl_for + pri_against + pri_for) > 0:
        if tfl_against > tfl_for and pri_against > pri_for:
            out["activity"] = (
                "Both taxpayer-funded and private interests show a net-opposition profile in witness testimony for this scope."
            )
        elif tfl_against > tfl_for and not (pri_against > pri_for):
            out["activity"] = (
                "Taxpayer-funded witness activity leans more opposition-oriented than private witness activity in this scope."
            )
        elif tfl_for > tfl_against:
            out["activity"] = (
                "Taxpayer-funded witness activity includes a stronger support component than opposition in this scope."
            )

    top_bills = _safe_list(payload.get("top_bills"))
    if top_bills:
        bill_counts = [int(_safe_float(_safe_dict(row).get("tfl"), 0.0)) for row in top_bills]
        total_bill_opp = sum(bill_counts)
        top_bill_opp = max(bill_counts) if bill_counts else 0
        if total_bill_opp > 0 and top_bill_opp > 0:
            concentration = (top_bill_opp / total_bill_opp) * 100.0
            if concentration >= 40:
                out["bills"] = (
                    "Opposition is relatively concentrated in the top-ranked bill, suggesting focused taxpayer-funded advocacy around a narrow set of proposals."
                )
            else:
                out["bills"] = (
                    "Opposition is distributed across multiple high-priority bills rather than concentrated in a single proposal."
                )

    top_subjects = _safe_list(payload.get("top_subjects"))
    if top_subjects:
        subject_counts = [
            int(_safe_float(_safe_dict(row).get("Oppositions"), 0.0))
            for row in top_subjects
        ]
        total_subject_opp = sum(subject_counts)
        top_subject_opp = max(subject_counts) if subject_counts else 0
        if total_subject_opp > 0 and top_subject_opp > 0:
            concentration = (top_subject_opp / total_subject_opp) * 100.0
            if concentration >= 45:
                out["subjects"] = (
                    "Policy-area opposition is concentrated in a leading subject, indicating a tighter taxpayer-funded advocacy focus."
                )
            else:
                out["subjects"] = (
                    "Policy-area opposition is spread across several subjects, indicating broader taxpayer-funded issue engagement."
                )

    tfl_mid_share = _safe_float(payload.get("tfl_mid_share_pct_value"), 0.0)
    if tfl_mid_share >= 50:
        out["conclusion"] = (
            "At midpoint estimates, taxpayer-funded activity constitutes a majority share of reported lobbying compensation in this scope."
        )
    elif tfl_mid_share >= 35:
        out["conclusion"] = (
            "At midpoint estimates, taxpayer-funded activity constitutes a substantial share of reported lobbying compensation in this scope."
        )
    elif tfl_mid_share > 0:
        out["conclusion"] = (
            "At midpoint estimates, taxpayer-funded activity remains an identifiable share of reported lobbying compensation in this scope."
        )
    return out


__all__ = ["_derive_section_conditionals"]
