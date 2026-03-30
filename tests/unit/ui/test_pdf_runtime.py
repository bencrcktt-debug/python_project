from __future__ import annotations

from tfl_app.ui.pdf_runtime import _build_report_pdf_bytes


def test_build_report_pdf_bytes_minimal_payload() -> None:
    pdf_bytes = _build_report_pdf_bytes({})
    assert isinstance(pdf_bytes, (bytes, bytearray))
    assert pdf_bytes[:4] == b"%PDF"
