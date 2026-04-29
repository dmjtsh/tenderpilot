"""
Fetches and extracts text from ALL tender documents on EIS.
Supports 44-ФЗ and 223-ФЗ, PDF, DOCX, ZIP, RAR archives.
"""
import io
import logging
import os
import re
import subprocess
import tempfile
import time
import zipfile

import pdfplumber
import requests
from docx import Document
from lxml import etree

logger = logging.getLogger(__name__)

BASE_URL = "http://zakupki.gov.ru"
BASE_URL_HTTPS = "https://zakupki.gov.ru"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "ru-RU,ru;q=0.9",
}

# Файлы которые не несут смысловой нагрузки для AI-анализа — пропускаем
SKIP_KEYWORDS = [
    "нмцк", "обоснование цены", "смета", "ведомость", "протокол нмцк",
    "подпись", "эцп", "sig", ".xlsx", ".xls", ".sig",
]

# Приоритет при выборе документа (выше индекс = выше приоритет)
TZ_KEYWORDS = [
    "документация",
    "описание объекта",
    "ооз",
    "тз_", "_тз.", " тз ",
    "тех.задание",
    "тех задание",
    "техзадание",
    "технические требования",
    "техническое задание",
]


def _score_filename(name: str) -> int:
    """Приоритет документа: выше = важнее для AI. 0 = пропустить."""
    name_lower = name.lower().replace("_", " ")

    # Пропускаем финансовые/технические таблицы
    if any(kw in name_lower for kw in SKIP_KEYWORDS):
        return 0

    for i, kw in enumerate(TZ_KEYWORDS):
        kw_norm = kw.strip("_ ")
        if kw in name_lower or kw_norm in name_lower:
            return i + 1  # 1..len(TZ_KEYWORDS)

    # Всё остальное (проект контракта, требования к заявке, etc.) — берём с низким приоритетом
    return 0


def _fetch_html(url: str, retries: int = 2) -> str | None:
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            if attempt < retries:
                wait = 3 * (attempt + 1)
                logger.warning(f"Retry {attempt+1} for {url} in {wait}s: {e}")
                time.sleep(wait)
            else:
                logger.error(f"Failed to fetch {url}: {e}")
    return None


def _get_docs_44fz(reg_number: str) -> list[dict]:
    """Список всех документов 44-ФЗ тендера."""
    info_url = f"http://zakupki.gov.ru/epz/order/notice/ea44/view/common-info.html?regNumber={reg_number}"
    try:
        resp = requests.get(info_url, headers=HEADERS, timeout=20, allow_redirects=True)
        resp.raise_for_status()
        final_url = resp.url
    except Exception as e:
        logger.error(f"Failed common-info for {reg_number}: {e}")
        return []

    docs_url = final_url.replace("/common-info.html", "/documents.html")
    html = _fetch_html(docs_url)
    if not html:
        return []

    parser = etree.HTMLParser()
    tree = etree.fromstring(html.encode(), parser)
    docs = []
    for link in tree.xpath("//a[@href]"):
        href = link.get("href", "")
        if "filestore" not in href and "download/priz" not in href:
            continue
        name = " ".join(t.strip() for t in link.xpath(".//text()") if t.strip())
        if not name:
            name = href.split("=")[-1]
        if not href.startswith("http"):
            href = BASE_URL_HTTPS + href
        docs.append({"name": name, "url": href})
    return docs


def _get_docs_223fz(notice_info_id: str) -> list[dict]:
    """Список всех документов 223-ФЗ тендера."""
    url = f"{BASE_URL}/epz/order/notice/notice223/documents.html?noticeInfoId={notice_info_id}"
    html = _fetch_html(url)
    if not html:
        return []

    parser = etree.HTMLParser()
    tree = etree.fromstring(html.encode(), parser)
    docs = []
    for link in tree.xpath("//a[@href]"):
        href = link.get("href", "")
        if "download.html?id=" not in href or "render" in href:
            continue
        name = " ".join(t.strip() for t in link.xpath(".//text()") if t.strip())
        if not name:
            continue
        if not href.startswith("http"):
            href = BASE_URL_HTTPS + href
        docs.append({"name": name, "url": href})
    return docs


def _download_file(url: str, retries: int = 2) -> tuple[bytes | None, str]:
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=60)
            resp.raise_for_status()
            return resp.content, resp.headers.get("Content-Type", "")
        except Exception as e:
            if attempt < retries:
                wait = 5 * (attempt + 1)
                logger.warning(f"Retry {attempt+1} for {url} in {wait}s: {e}")
                time.sleep(wait)
            else:
                logger.error(f"Download failed {url}: {e}")
    return None, ""


def _extract_text_pdf(content: bytes) -> str:
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            parts = [page.extract_text() for page in pdf.pages]
            return "\n".join(p for p in parts if p)
    except Exception as e:
        logger.debug(f"PDF failed: {e}")
        return ""


def _extract_text_docx(content: bytes) -> str:
    try:
        doc = Document(io.BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as e:
        logger.debug(f"DOCX failed: {e}")
        return ""


def _detect_format(content: bytes, filename: str, content_type: str) -> str:
    fname = filename.lower()
    if fname.endswith(".zip"):
        fname = fname[:-4]  # strip .zip double ext
    if fname.endswith(".pdf"):
        return "pdf"
    if fname.endswith(".docx") or fname.endswith(".doc"):
        return "docx"
    ct = content_type.lower()
    if "pdf" in ct:
        return "pdf"
    if "wordprocessingml" in ct or "openxmlformats" in ct:
        return "docx"
    # Byte signatures — %PDF is unambiguous; PK is DOCX or ZIP, handled below
    if content[:4] == b"%PDF":
        return "pdf"
    return "unknown"


def _extract_from_bytes(content: bytes, filename: str, content_type: str = "") -> str:
    """Извлекает текст из файла. Если ZIP — обрабатывает содержимое рекурсивно."""
    fname = filename.lower()

    # Explicit .zip → treat as archive
    if fname.endswith(".zip"):
        return _extract_from_zip(content)

    # RAR archive — byte signature Rar!
    if fname.endswith(".rar") or content[:4] == b"Rar!":
        return _extract_from_rar(content)

    fmt = _detect_format(content, filename, content_type)
    if fmt == "pdf":
        return _extract_text_pdf(content)
    elif fmt == "docx":
        return _extract_text_docx(content)

    # Unknown extension + PK signature: try DOCX first, fall back to ZIP
    if content[:4] == b"PK\x03\x04":
        text = _extract_text_docx(content)
        if text:
            return text
        return _extract_from_zip(content)

    text = _extract_text_pdf(content)
    if not text:
        text = _extract_text_docx(content)
    return text


def _extract_from_zip(content: bytes) -> str:
    """Распаковывает ZIP и извлекает текст из всех PDF/DOCX внутри."""
    texts = []
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            for name in zf.namelist():
                name_lower = name.lower()
                # Пропускаем служебные файлы
                if any(name_lower.endswith(ext) for ext in [".xlsx", ".xls", ".sig", ".p7s"]):
                    continue
                if not any(name_lower.endswith(ext) for ext in [".pdf", ".docx", ".doc"]):
                    continue
                try:
                    file_bytes = zf.read(name)
                    text = _extract_from_bytes(file_bytes, name)
                    if text and len(text) > 50:
                        texts.append(f"[Файл: {name}]\n{text}")
                        logger.debug(f"  ZIP/{name}: {len(text)} chars")
                except Exception as e:
                    logger.debug(f"  ZIP/{name} failed: {e}")
    except Exception as e:
        logger.warning(f"ZIP extraction failed: {e}")
    return "\n\n".join(texts)


def _extract_from_rar(content: bytes) -> str:
    """Распаковывает RAR через unar и извлекает текст из PDF/DOCX внутри."""
    texts = []
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            rar_path = os.path.join(tmpdir, "archive.rar")
            with open(rar_path, "wb") as f:
                f.write(content)
            subprocess.run(
                ["unar", "-o", tmpdir, "-f", rar_path],
                capture_output=True, timeout=30,
            )
            for root, _, files in os.walk(tmpdir):
                for fname in files:
                    if fname == "archive.rar":
                        continue
                    name_lower = fname.lower()
                    if any(name_lower.endswith(ext) for ext in [".xlsx", ".xls", ".sig", ".p7s"]):
                        continue
                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath, "rb") as f:
                            file_bytes = f.read()
                        text = _extract_from_bytes(file_bytes, fname)
                        if text and len(text) > 50:
                            texts.append(f"[Файл: {fname}]\n{text}")
                            logger.debug(f"  RAR/{fname}: {len(text)} chars")
                    except Exception as e:
                        logger.debug(f"  RAR/{fname} failed: {e}")
    except Exception as e:
        logger.warning(f"RAR extraction failed: {e}")
    return "\n\n".join(texts)


def fetch_all_docs_text(tender: dict) -> str:
    """
    Скачивает ВСЕ документы тендера и возвращает объединённый текст.
    Приоритет: ТЗ-документы первыми, затем остальные (проект контракта, требования).
    Финансовые таблицы (НМЦК, сметы, .xlsx) — пропускаем.
    """
    purchase_number = tender.get("purchase_number", "")
    law_type = tender.get("law_type", "")
    href = tender.get("href", "")

    logger.info(f"Fetching all docs for {purchase_number} ({law_type})")

    if "223" in law_type:
        m = re.search(r"noticeInfoId=(\d+)", href)
        if not m:
            logger.warning(f"No noticeInfoId in href: {href}")
            return ""
        docs = _get_docs_223fz(m.group(1))
    else:
        docs = _get_docs_44fz(purchase_number)

    if not docs:
        logger.warning(f"No documents found for {purchase_number}")
        return ""

    logger.info(f"Found {len(docs)} documents for {purchase_number}")

    # Сортируем: высокий score (ТЗ) → впереди, score=0 → в конце, но тоже качаем
    def sort_key(d):
        score = _score_filename(d["name"])
        # Пропускаем явный мусор
        name_lower = d["name"].lower()
        if any(kw in name_lower for kw in [".xlsx", ".xls", ".sig", "нмцк", "смета"]):
            return -1
        return score

    docs_sorted = sorted(docs, key=sort_key, reverse=True)
    # Убираем мусор
    docs_sorted = [d for d in docs_sorted if sort_key(d) >= 0]

    all_texts = []
    for doc in docs_sorted:
        logger.info(f"  Downloading: {doc['name']}")
        content, content_type = _download_file(doc["url"])
        if not content:
            continue
        text = _extract_from_bytes(content, doc["name"], content_type)
        if text and len(text) > 50:
            all_texts.append(f"=== {doc['name']} ===\n{text}")
            logger.info(f"  → {len(text):,} символов")
        else:
            logger.debug(f"  → пусто или не читается")
        time.sleep(0.3)

    combined = "\n\n".join(all_texts)
    logger.info(f"Total extracted: {len(combined):,} chars from {len(all_texts)} docs")
    return combined


# Алиас для обратной совместимости с eis_parser.py
def fetch_tz_text(tender: dict) -> str:
    return fetch_all_docs_text(tender)


def fetch_tz_for_tenders(tenders: list[dict], delay: float = 1.5) -> dict[str, str]:
    results = {}
    for i, tender in enumerate(tenders, 1):
        pn = tender.get("purchase_number", "")
        logger.info(f"[{i}/{len(tenders)}] {pn}")
        try:
            text = fetch_all_docs_text(tender)
            results[pn] = text
        except Exception as e:
            logger.error(f"Error for {pn}: {e}")
            results[pn] = ""
        if i < len(tenders):
            time.sleep(delay)
    return results
