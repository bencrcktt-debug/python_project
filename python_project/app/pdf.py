import os
from pathlib import Path
from typing import Callable, Dict, Optional

from .config import DEFAULT_REPORT_DIR


def _inject_windows_gtk() -> None:
    """
    On Windows, WeasyPrint needs GTK/Pango/Cairo DLLs. If the GTK runtime
    is installed in the common path, add it to the DLL search path.
    """
    if os.name != "nt":
        return
    candidates = [
        Path(r"C:\Program Files\GTK3-Runtime Win64\bin"),
        Path(r"C:\Program Files\GTK3-Runtime Win64\lib"),
    ]
    for c in candidates:
        if c.exists():
            try:
                os.add_dll_directory(str(c))
            except Exception:
                pass
            os.environ["PATH"] = f"{c};{os.environ.get('PATH', '')}"


def html_to_pdf_bytes(html: str) -> bytes:
    """
    Convert HTML to PDF. Prefers WeasyPrint if installed, otherwise raises.
    Use this in the async report queue to keep the UI responsive.
    """
    _inject_windows_gtk()
    try:
        from weasyprint import HTML
    except ImportError as exc:  # pragma: no cover - dependency may be optional
        raise RuntimeError("weasyprint is not installed.") from exc

    return HTML(string=html).write_pdf()


def save_pdf(pdf_bytes: bytes, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pdf_bytes)
    return path


def generate_pdf(
    html_builder: Callable[[], str],
    output_dir: Path = DEFAULT_REPORT_DIR,
    filename: Optional[str] = None,
) -> Path:
    """
    Convenience helper that builds HTML, renders to PDF, and saves it.
    The caller provides the HTML builder so expensive queries stay outside
    the PDF function.
    """
    html = html_builder()
    pdf_bytes = html_to_pdf_bytes(html)

    fname = filename or "tfl-report.pdf"
    output_path = output_dir / fname
    return save_pdf(pdf_bytes, output_path)
