"""
Парсинг ссылок на документы со страницы ЕИС.
Отдельный модуль — eis_client.py не трогаем.
"""
import logging
import re
import time
from typing import Any
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

DOCUMENTS_URL_TEMPLATES = [
    "/epz/order/notice/ea44/view/documents.html?regNumber={number}",
    "/epz/order/notice/ea20/view/documents.html?regNumber={number}",
    "/epz/order/notice/zk44/view/documents.html?regNumber={number}",
    "/epz/order/notice/ok44/view/documents.html?regNumber={number}",
]


def fetch_document_links(purchase_number: str) -> list[dict[str, str]]:
    """
    Возвращает список {url, filename} для документов тендера.
    Пробует несколько шаблонов URL (ea44, ea20, zk44, ok44).
    """
    for template in DOCUMENTS_URL_TEMPLATES:
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


def _extract_links(html_text: str) -> list[dict[str, str]]:
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
