import io
import logging
import os
import subprocess
import tempfile
import zipfile
from pathlib import Path

import fitz  # pymupdf
import rarfile
from docx import Document as DocxDocument

logger = logging.getLogger(__name__)

PARSABLE_TYPES = {"pdf", "docx", "doc"}
ARCHIVE_TYPES = {"rar", "zip"}
SCAN_TEXT_THRESHOLD = 100


def detect_file_type(filename: str) -> str:
    ext = Path(filename).suffix.lower().lstrip(".")
    # Реальные расширения не длиннее 10 символов.
    # Если суффикс длиннее — это часть имени файла (напр. "1. Приказ..."),
    # а не расширение.
    return ext if len(ext) <= 10 else ""


def detect_file_type_by_content(data: bytes) -> str:
    if data[:4] == b"%PDF":
        return "pdf"
    if data[:4] == b"PK\x03\x04":
        if _is_docx(data):
            return "docx"
        if _is_xlsx(data):
            return "xlsx"
        return "zip"
    if data[:7] == b"Rar!\x1a\x07\x00" or data[:8] == b"Rar!\x1a\x07\x01\x00":
        return "rar"
    return ""


def _is_docx(data: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            return "word/document.xml" in zf.namelist()
    except zipfile.BadZipFile:
        return False


def _is_xlsx(data: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            return "xl/workbook.xml" in zf.namelist()
    except zipfile.BadZipFile:
        return False


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


def parse_doc(data: bytes) -> str:
    """Parse legacy .doc using antiword (requires antiword installed on system)."""
    with tempfile.NamedTemporaryFile(suffix=".doc", delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        result = subprocess.run(
            ["antiword", "-w", "0", tmp_path],
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0:
            return result.stdout.decode("utf-8", errors="replace")
        raise RuntimeError(f"antiword failed: {result.stderr.decode('utf-8', errors='replace')[:200]}")
    except FileNotFoundError:
        raise RuntimeError("antiword not installed — cannot parse .doc files (apt install antiword)")
    finally:
        os.unlink(tmp_path)


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
