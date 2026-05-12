"""
Парсинг ссылок на документы со страницы ЕИС.
Отдельный модуль — eis_client.py не трогаем.
"""
import logging
import re
import time
from urllib.parse import urljoin

import requests
from lxml import html as lxml_html

logger = logging.getLogger(__name__)

BASE_URL = "https://zakupki.gov.ru"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "ru-RU,ru;q=0.9",
}

# Шаблоны для 44-ФЗ: ea44, ea20, zk44, ok44 + прочие
DOCUMENTS_URL_TEMPLATES_44 = [
    "/epz/order/notice/ea44/view/documents.html?regNumber={number}",
    "/epz/order/notice/ea20/view/documents.html?regNumber={number}",
    "/epz/order/notice/zk44/view/documents.html?regNumber={number}",
    "/epz/order/notice/ok44/view/documents.html?regNumber={number}",
]


def fetch_document_links(purchase_number: str, source_url: str = "") -> list[dict[str, str]]:
    """
    Возвращает список {url, filename} для документов тендера.
    Для 223-ФЗ (notice223) использует двухшаговый парсинг через noticeInfoId.
    Для 44-ФЗ пробует несколько шаблонов URL (ea44, ea20, zk44, ok44).
    """
    if "notice223" in source_url or "/223/" in source_url:
        links = _fetch_notice223_links(purchase_number)
        if links:
            return links
        logger.info("No documents found for 223-FZ tender %s", purchase_number)
        return []

    # 44-ФЗ и остальные форматы
    for template in DOCUMENTS_URL_TEMPLATES_44:
        url = BASE_URL + template.format(number=purchase_number)
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
            if resp.status_code == 200 and "document" in resp.url.lower():
                links = _extract_links(resp.text)
                if links:
                    logger.info(
                        "Found %d documents for %s at %s",
                        len(links), purchase_number, url,
                    )
                    return links
        except Exception as exc:
            logger.warning("Error fetching docs page %s: %s", url, exc)
        time.sleep(0.3)

    logger.info("No documents found for %s", purchase_number)
    return []


def _fetch_notice223_links(purchase_number: str) -> list[dict[str, str]]:
    """
    Двухшаговый парсинг документов 223-ФЗ:
    1. Получаем noticeInfoId из common-info страницы по regNumber (пробуем оба URL-формата)
    2. Парсим documents.html?noticeInfoId=XXX
    """
    common_info_urls = [
        f"{BASE_URL}/epz/order/notice/notice223/common-info.html?regNumber={purchase_number}",
        f"{BASE_URL}/223/purchase/public/purchase/info/common-info.html?regNumber={purchase_number}",
    ]
    notice_info_id = None
    for common_info_url in common_info_urls:
        try:
            resp = requests.get(common_info_url, headers=HEADERS, timeout=20, allow_redirects=True)
            if resp.status_code != 200:
                continue
            match = re.search(r'noticeInfoId=(\d+)', resp.text)
            if match:
                notice_info_id = match.group(1)
                break
        except Exception as exc:
            logger.warning("Error fetching notice223 common-info %s: %s", common_info_url, exc)

    if not notice_info_id:
        logger.warning("noticeInfoId not found for 223-FZ tender %s", purchase_number)
        return []

    docs_url = (
        f"{BASE_URL}/epz/order/notice/notice223/documents.html"
        f"?noticeInfoId={notice_info_id}"
    )
    try:
        resp = requests.get(docs_url, headers=HEADERS, timeout=20, allow_redirects=True)
        if resp.status_code != 200:
            logger.warning("notice223 documents page returned %d for noticeInfoId=%s", resp.status_code, notice_info_id)
            return []
        links = _extract_notice223_links(resp.text)
        if links:
            logger.info(
                "Found %d documents for 223-FZ tender %s (noticeInfoId=%s)",
                len(links), purchase_number, notice_info_id,
            )
        return links
    except Exception as exc:
        logger.warning("Error fetching notice223 documents for %s: %s", purchase_number, exc)
        return []


def _extract_notice223_links(html_text: str) -> list[dict[str, str]]:
    """Парсит ссылки на файлы со страницы документов 223-ФЗ."""
    tree = lxml_html.fromstring(html_text)
    results: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    for a in tree.xpath('//a[contains(@href, "/223/purchase/public/download/download.html")]'):
        href = a.get("href", "").strip()
        if not href:
            continue
        if not href.startswith("http"):
            href = urljoin(BASE_URL, href)
        if href in seen_urls:
            continue
        seen_urls.add(href)

        filename = re.sub(r'\s+', ' ', a.text_content()).strip()
        if not filename or len(filename) > 300:
            # Fallback: имя из data-tooltip
            tooltip = a.get("data-tooltip", "")
            m = re.search(r'custom-tooltiptext["\']?>([^<]+)<', tooltip)
            if m:
                filename = m.group(1).strip()
        if not filename:
            filename = href.split("id=")[-1]
        filename = re.sub(r'[<>:"/\\|?*]', "_", filename)

        results.append({"url": href, "filename": filename})

    return results


def _extract_links(html_text: str) -> list[dict[str, str]]:
    """Парсит ссылки на файлы со страниц документов 44-ФЗ."""
    tree = lxml_html.fromstring(html_text)
    results: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    for a in tree.xpath('//a[contains(@href, "download") or contains(@href, "fileStore")]'):
        href = a.get("href", "").strip()
        if not href:
            continue
        if not href.startswith("http"):
            href = urljoin(BASE_URL, href)
        if href in seen_urls:
            continue
        seen_urls.add(href)

        filename = a.text_content().strip()
        if not filename or len(filename) > 300:
            filename = href.split("/")[-1].split("?")[0]
        filename = re.sub(r'[<>:"/\\|?*]', "_", filename)

        results.append({"url": href, "filename": filename})

    return results


def download_file_from_url(url: str, timeout: int = 60) -> bytes | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, stream=True)
        resp.raise_for_status()
        return resp.content
    except Exception as exc:
        logger.error("Failed to download %s: %s", url, exc)
        return None
