from __future__ import annotations

import importlib


def test_pdf_runtime_helpers_import() -> None:
    module = importlib.import_module("tfl_app.ui.pdf.runtime_helpers")
    assert hasattr(module, "configure_helpers")
    assert hasattr(module, "build_activities")


def test_pdf_charts_import() -> None:
    module = importlib.import_module("tfl_app.ui.pdf.charts")
    assert hasattr(module, "_fig_to_png_bytes")
    assert hasattr(module, "_build_focus_chart")


def test_pdf_builders_import() -> None:
    module = importlib.import_module("tfl_app.ui.pdf.builders")
    assert hasattr(module, "_build_report_payload")
    assert hasattr(module, "_hydrate_report_inputs")


def test_pdf_layout_import() -> None:
    module = importlib.import_module("tfl_app.ui.pdf.layout")
    assert hasattr(module, "_pdf_add_chart")
    assert hasattr(module, "_pdf_add_paragraph")


def test_pdf_pages_import() -> None:
    module = importlib.import_module("tfl_app.ui.pdf.pages")
    assert hasattr(module, "_pdf_add_cover_page")
    assert hasattr(module, "_pdf_add_contents_page")


def test_pdf_document_import() -> None:
    module = importlib.import_module("tfl_app.ui.pdf.document")
    assert hasattr(module, "ReportPDF")
    assert hasattr(module, "_create_report_pdf_shell")


def test_pdf_export_utils_import() -> None:
    module = importlib.import_module("tfl_app.ui.pdf.export_utils")
    assert hasattr(module, "export_dataframe")
    assert hasattr(module, "fmt_usd")


def test_pdf_session_state_import() -> None:
    module = importlib.import_module("tfl_app.ui.pdf.session_state")
    assert hasattr(module, "reset_filters")
    assert hasattr(module, "_session_label")


def test_pdf_section_conditionals_import() -> None:
    module = importlib.import_module("tfl_app.ui.pdf.section_conditionals")
    assert hasattr(module, "_derive_section_conditionals")


def test_runtime_pdf_facade_import() -> None:
    module = importlib.import_module("tfl_app.ui.runtime_pdf")
    assert hasattr(module, "configure_helpers")
    assert hasattr(module, "_render_pdf_report_section")
