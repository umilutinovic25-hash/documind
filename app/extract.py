"""Text extraction: embedded PDF text first, OCR fallback for scanned pages (macOS Vision via ocrmac)."""
from __future__ import annotations

import io
import os
import subprocess
import tempfile

from pypdf import PdfReader

MIN_CHARS = 25  # a page with less embedded text than this is treated as a scan


class ExtractionError(Exception):
    pass


def _ocr_page(pdf_path: str, page_no: int, tmp: str) -> str:
    try:
        from ocrmac import ocrmac
    except ImportError as e:  # not macOS / not installed
        raise ExtractionError("Skeniran PDF: OCR nije dostupan (instaliraj ocrmac na macOS).") from e
    prefix = os.path.join(tmp, f"p{page_no}")
    subprocess.run(
        ["pdftoppm", "-r", "150", "-f", str(page_no), "-l", str(page_no), "-png", "-singlefile", pdf_path, prefix],
        check=True,
        capture_output=True,
    )
    lines = ocrmac.OCR(prefix + ".png", recognition_level="accurate").recognize()
    return "\n".join(t for t, _conf, _box in lines)


def extract_pages(filename: str, data: bytes) -> tuple[list[str], int]:
    """Returns (pages, ocr_page_count)."""
    if not filename.lower().endswith(".pdf"):
        text = data.decode("utf-8", "ignore")
        if not text.strip():
            raise ExtractionError("Fajl je prazan.")
        return [text], 0

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [(p.extract_text() or "") for p in reader.pages]
    except Exception as e:
        raise ExtractionError(f"PDF se ne može pročitati: {e}") from e

    ocr_count = 0
    weak = [i for i, t in enumerate(pages) if len(t.strip()) < MIN_CHARS]
    if weak:
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = os.path.join(tmp, "in.pdf")
            with open(pdf_path, "wb") as f:
                f.write(data)
            for i in weak:
                try:
                    pages[i] = _ocr_page(pdf_path, i + 1, tmp)
                    ocr_count += 1
                except ExtractionError:
                    if not any(t.strip() for t in pages):
                        raise
                except (subprocess.CalledProcessError, FileNotFoundError):
                    pass
    if not any(t.strip() for t in pages):
        raise ExtractionError("U dokumentu nema čitljivog teksta.")
    return pages, ocr_count
