from dataclasses import dataclass
from typing import Dict, Optional

import pandas as pd


@dataclass
class MetricResult:
    value: Optional[float]
    notes: str = ""
    extra: Dict[str, str] = None


def taxpayer_dependency(comp: pd.DataFrame) -> MetricResult:
    """
    Compute taxpayer dependency index:
    taxpayer-funded compensation / total compensation.
    Expects columns that identify taxpayer-funded rows and compensation bands.
    """
    if comp.empty:
        return MetricResult(value=None, notes="No compensation rows provided.", extra={})

    cols = {c.lower(): c for c in comp.columns}
    taxpayer_col = cols.get("taxpayerfunded") or cols.get("taxpayer_flag")
    low_col = cols.get("complow") or cols.get("low")
    high_col = cols.get("comphigh") or cols.get("high")

    if not taxpayer_col or not low_col or not high_col:
        return MetricResult(
            value=None,
            notes="Missing expected columns: taxpayer flag, CompLow, CompHigh.",
            extra={"available_columns": ", ".join(comp.columns)},
        )

    comp = comp.copy()
    comp["low_num"] = pd.to_numeric(comp[low_col], errors="coerce")
    comp["high_num"] = pd.to_numeric(comp[high_col], errors="coerce")
    comp["mid"] = comp[["low_num", "high_num"]].mean(axis=1)

    denom = comp["mid"].sum()
    numer = comp.loc[comp[taxpayer_col] == True, "mid"].sum()  # noqa: E712

    if denom == 0:
        return MetricResult(value=None, notes="Compensation midpoint sums to zero.", extra={})

    pct = float(numer / denom)
    return MetricResult(
        value=round(pct, 4),
        notes="Computed on midpoint of compensation bands.",
        extra={"rows": len(comp), "taxpayer_rows": int((comp[taxpayer_col] == True).sum())},
    )


def stance_efficacy(witness: pd.DataFrame, bill_outcomes: pd.DataFrame) -> MetricResult:
    """
    Success rate of testified positions vs bill outcomes.
    Placeholder logic until column mapping is finalized.
    """
    if witness.empty or bill_outcomes.empty:
        return MetricResult(
            value=None,
            notes="Witness or bill outcome data not available.",
            extra={"witness_rows": len(witness), "outcome_rows": len(bill_outcomes)},
        )
    # TODO: join on bill id and compare stance to outcome once schema is defined.
    return MetricResult(value=None, notes="Join logic pending schema confirmation.", extra={})


def policy_concentration(subjects: pd.DataFrame) -> MetricResult:
    """
    Computes a concentration index (HHI) across policy areas to flag over-exposure.
    """
    if subjects.empty:
        return MetricResult(value=None, notes="No subject-matter rows.", extra={})

    counts = subjects["Subject"].fillna("Unknown").value_counts(normalize=True)
    hhi = float((counts**2).sum())
    return MetricResult(
        value=round(hhi, 4),
        notes="Higher is more concentrated. Uses share of subject mentions.",
        extra={"categories": len(counts)},
    )
