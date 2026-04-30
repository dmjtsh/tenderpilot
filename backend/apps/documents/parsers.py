import io
import logging
import os
import tempfile
import zipfile
from pathlib import Path

import fitz  # pymupdf
import rarfile
from docx import Document as DocxDocument

logger = logging.getLogger(__name__)

PARSABLE_TYPES = {"pdf", "docx"}
ARCHIVE_TYPES = {"rar", "zip"}
SCAN_TEXT_THRESHOLD = 100


def detect_file_type(filename: str) -> str:
    ext = Path(filename).suffix.lower().lstrip(".")
    return ext


def can_parse(file_type: str) -> bool:
    return file_type in PARSABLE_TYPES


def is_archive(file_type: str) -> bool:
    return file_type in ARCHIVE_TYPES


def parse_pdf(data: bytes) -> tuple[str, bool]:
    doc = fitz.open(stream=data, filetype="pdf")
    texts: list[str] = []
    for page in doc:
        texts.append(page.get_text())
    doc.close()

    full_text = "\n".join(texts).strip()
    is_scanned = len(full_text) < SCAN_TEXT_THRESHOLD
    return full_text, is_scanned


def parse_docx(data: bytes) -> str:
    doc = DocxDocument(io.BytesIO(data))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)


def extract_archive(data: bytes, file_type: str) -> list[tuple[str, bytes]]:
    results: list[tuple[str, bytes]] = []

    if file_type == "zip":
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                filename = _decode_archive_filename(info.filename)
                results.append((filename, zf.read(info)))

    elif file_type == "rar":
        with tempfile.NamedTemporaryFile(suffix=".rar", delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        try:
            with rarfile.RarFile(tmp_path) as rf:
                for info in rf.infolist():
                    if info.is_dir():
                        continue
                    filename = _decode_archive_filename(info.filename)
                    results.append((filename, rf.read(info)))
        finally:
            os.unlink(tmp_path)

    return results


def _decode_archive_filename(name: str) -> str:
    try:
        return name.encode("cp437").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        try:
            return name.encode("cp437").decode("cp866")
        except (UnicodeDecodeError, UnicodeEncodeError):
            return name
