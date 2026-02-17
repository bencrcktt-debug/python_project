import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from .config import DEFAULT_REPORT_DIR


def save_report_pdf(
    report_id: str,
    pdf_bytes: bytes,
    payload: Dict,
    renderer: str = "fpdf",
    report_dir: Path = DEFAULT_REPORT_DIR,
) -> Path:
    """
    Persist a generated PDF and a small metadata sidecar under ./reports.
    Returns the PDF path.
    """
    report_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{report_id}-{renderer}"
    pdf_path = report_dir / f"{stem}.pdf"
    meta_path = report_dir / f"{stem}.json"

    pdf_path.write_bytes(pdf_bytes)

    metadata = {
        "report_id": report_id,
        "renderer": renderer,
        "generated_at": payload.get("generated_ts") or datetime.utcnow().isoformat(),
        "report_title": payload.get("report_title"),
        "session_label": payload.get("session_label"),
        "scope_label": payload.get("scope_label") or payload.get("scope_session_label"),
        "focus_label": payload.get("focus_label"),
        "filter_summary": payload.get("filter_summary"),
        "path": str(pdf_path),
    }
    try:
        meta_path.write_text(json.dumps(metadata, indent=2))
    except Exception:
        # Metadata failures should not block PDF saving.
        pass
    return pdf_path
