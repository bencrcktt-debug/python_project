from __future__ import annotations


def fmt_usd(value: float, decimals: int = 0) -> str:
    try:
        return f"${value:,.{decimals}f}"
    except Exception:
        return "$0"


def shorten_text(value: str, max_len: int = 36) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."
