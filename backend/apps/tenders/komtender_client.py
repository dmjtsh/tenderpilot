"""
Scraper for komtender.ru — commercial tenders aggregator.

Discovery: 7 sitemap XML files → ~80k tender URLs with lastmod.
Detail: public HTML pages at /tender/{id}, parsed with BeautifulSoup.
Documents: JS object `tendersData` contains file links (/files?t=TOKEN).
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree

import requests
from django.utils import timezone

logger = logging.getLogger(__name__)

BASE_URL = "https://www.komtender.ru"
SITEMAP_URLS = [f"{BASE_URL}/sitemap-url-{i}.xml" for i in range(7)]
SITEMAP_NS = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
USER_AGENT = "Tenderoll/1.0 (tender aggregator; support@tenderoll.ru)"
DEFAULT_DELAY = 0.5

PROCEDURE_MAP: dict[str, str] = {
    "аукцион": "auction",
    "электронный аукцион": "auction",
    "конкурс": "contest",
    "открытый конкурс": "contest",
    "запрос котировок": "request_quotations",
    "запрос предложений": "request_proposals",
    "единственный поставщик": "single_source",
    "закупка у единственного поставщика": "single_source",
}


def _session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


# ---------------------------------------------------------------------------
# Sitemap
# ---------------------------------------------------------------------------

def fetch_sitemap_urls(
    since: datetime | None = None,
    session: requests.Session | None = None,
) -> list[dict]:
    """Fetch tender URLs from all sitemaps, optionally filtered by lastmod > since."""
    sess = session or _session()
    results: list[dict] = []

    for sitemap_url in SITEMAP_URLS:
        try:
            resp = sess.get(sitemap_url, timeout=60)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("Failed to fetch sitemap %s: %s", sitemap_url, exc)
            continue

        root = ElementTree.fromstring(resp.content)
        for url_el in root.findall("ns:url", SITEMAP_NS):
            loc_el = url_el.find("ns:loc", SITEMAP_NS)
            lastmod_el = url_el.find("ns:lastmod", SITEMAP_NS)
            if loc_el is None or loc_el.text is None:
                continue

            loc = loc_el.text.strip()
            m = re.search(r"/tender/(\d+)$", loc)
            if not m:
                continue

            lastmod = None
            if lastmod_el is not None and lastmod_el.text:
                try:
                    lastmod = datetime.fromisoformat(lastmod_el.text.strip())
                    if lastmod.tzinfo is None:
                        lastmod = lastmod.replace(tzinfo=timezone.utc)
                except ValueError:
                    pass

            if since and lastmod and lastmod <= since:
                continue

            results.append({
                "url": loc,
                "komtender_id": m.group(1),
                "lastmod": lastmod,
            })

        time.sleep(1)

    return results


# ---------------------------------------------------------------------------
# Detail page parser
# ---------------------------------------------------------------------------

def parse_tender_page(
    url: str,
    session: requests.Session | None = None,
) -> dict | None:
    """Parse a komtender.ru detail page, return dict for upsert_tender."""
    sess = session or _session()

    try:
        resp = sess.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Failed to fetch %s: %s", url, exc)
        return None

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(resp.text, "lxml")

    h1 = soup.find("h1")
    if not h1:
        logger.warning("No <h1> on %s — probably 404 page", url)
        return None

    title_raw = h1.get_text(strip=True)
    if title_raw.startswith("Ой!") or "не туда" in title_raw:
        logger.debug("404-like page: %s", url)
        return None

    title = re.sub(r"^Тендер:\s*", "", title_raw).strip()
    if not title:
        return None

    m = re.search(r"/tender/(\d+)", url)
    komtender_id = m.group(1) if m else ""

    labels = _extract_labels(soup)

    nmck = _parse_price(labels.get("Начальная цена", ""))
    customer_name_raw = labels.get("Организатор закупки", "")
    customer_name = "" if "доступно после регистрации" in customer_name_raw.lower() else customer_name_raw
    customer_inn_raw = labels.get("ИНН", "")
    customer_inn = "" if "доступно после регистрации" in customer_inn_raw.lower() else customer_inn_raw
    region_raw = labels.get("Место поставки", "")
    procedure_raw = labels.get("Способ размещения", "")
    deadline_raw = labels.get("Подача заявок (МСК)", "") or labels.get("Подача заявок", "")
    delivery_raw = labels.get("Срок поставки (МСК)", "") or labels.get("Срок поставки", "")

    status_div = soup.find("div", class_="tender-status__title")
    status_text = status_div.get_text(strip=True) if status_div else ""
    status = _map_status(status_text)

    pub_div = soup.find("div", class_="tender-info-header-start_date")
    published_at = None
    if pub_div:
        pub_text = pub_div.get_text(strip=True)
        pub_match = re.search(r"от\s+(\d{2}\.\d{2}\.\d{2,4})", pub_text)
        if pub_match:
            published_at = _parse_date(pub_match.group(1))

    deadline_at = _parse_date(re.sub(r"^по\s+", "", deadline_raw))

    platform_name, platform_away_url = _extract_platform(soup)

    region = _normalize_region(region_raw)

    doc_files = _extract_documents_from_js(resp.text, komtender_id)
    industry = _extract_industry(soup)

    data: dict = {
        "number": komtender_id,
        "source": "komtender",
        "title": title,
        "nmck": str(nmck) if nmck is not None else None,
        "customer_name": _clean_customer_name(customer_name),
        "customer_inn": customer_inn.strip(),
        "region": region,
        "law_type": "b2b",
        "procedure_type": _map_procedure_type(procedure_raw),
        "source_url": url,
        "trading_platform": platform_name,
        "trading_platform_url": "",
        "status": status,
        "published_at": published_at.isoformat() if published_at else None,
        "deadline_at": deadline_at.isoformat() if deadline_at else None,
        "okpd_codes": [],
        "raw_json": {
            "komtender_url": url,
            "doc_files": doc_files,
            "industry": industry,
            "delivery_term": delivery_raw,
            "platform_away_url": platform_away_url,
            "procedure_raw": procedure_raw,
            "status_raw": status_text,
        },
    }
    return data


# ---------------------------------------------------------------------------
# Label extraction
# ---------------------------------------------------------------------------

def _extract_labels(soup) -> dict[str, str]:
    """Extract all tender-body__label → next sibling text pairs."""
    labels: dict[str, str] = {}
    for span in soup.find_all("span", class_="tender-body__label"):
        key = span.get_text(strip=True)
        sibling = span.find_next_sibling()
        if sibling:
            value = sibling.get_text(" ", strip=True)
        else:
            value = ""
        labels[key] = value

    inn_span = soup.find(string=re.compile(r"^ИНН$"))
    if inn_span:
        nxt = inn_span.parent.find_next_sibling()
        if nxt:
            labels["ИНН"] = nxt.get_text(strip=True)

    return labels


# ---------------------------------------------------------------------------
# Field parsers
# ---------------------------------------------------------------------------

def _parse_price(text: str) -> Decimal | None:
    if not text:
        return None
    cleaned = re.sub(r"[^\d,.]", "", text.replace("\xa0", ""))
    cleaned = cleaned.replace(",", ".")
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _parse_date(text: str) -> datetime | None:
    if not text or not text.strip():
        return None
    text = text.strip()

    from zoneinfo import ZoneInfo
    msk = ZoneInfo("Europe/Moscow")

    formats = [
        "%d.%m.%Y %H:%M",
        "%d.%m.%Y",
        "%d.%m.%y %H:%M",
        "%d.%m.%y",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(text, fmt)
            return dt.replace(tzinfo=msk)
        except ValueError:
            continue
    return None


def _map_status(raw: str) -> str:
    raw_lower = raw.lower().strip()
    if "завершён" in raw_lower or "завершен" in raw_lower:
        return "finished"
    if "отменён" in raw_lower or "отменен" in raw_lower:
        return "cancelled"
    return "active"


def _map_procedure_type(raw: str) -> str:
    if not raw:
        return "other"
    raw_lower = raw.lower().strip()
    for key, value in PROCEDURE_MAP.items():
        if key in raw_lower:
            return value
    return "other"


def _clean_customer_name(name: str) -> str:
    name = re.sub(r"Анализ заказчика.*$", "", name).strip()
    return name


def _normalize_region(raw: str) -> str:
    if not raw:
        return ""
    parts = [p.strip() for p in raw.replace(",", ",").split(",")]
    for part in reversed(parts):
        if "область" in part or "край" in part or "республика" in part.lower():
            return part.strip()
        if "Москва" in part:
            return "Москва"
        if "Санкт-Петербург" in part or "Петербург" in part:
            return "Санкт-Петербург"
    return parts[-1].strip() if parts else ""


def _extract_platform(soup) -> tuple[str, str]:
    """Extract platform name and /away URL."""
    away_links = soup.find_all("a", href=re.compile(r"/away\?"))
    for a in away_links:
        name = a.get_text(strip=True)
        href = a.get("href", "")
        if name and "/away?" in href:
            return name, href
    return "", ""


def _extract_industry(soup) -> str:
    label = soup.find("span", class_="tender-body__label", string=re.compile("Отрасль"))
    if not label:
        return ""
    nxt_div = label.find_next("div")
    if nxt_div:
        links = nxt_div.find_all("a")
        if links:
            return links[0].get_text(strip=True)
        text = nxt_div.get_text(strip=True)
        if text:
            return text[:200]
    return ""


def _extract_documents_from_js(html: str, komtender_id: str) -> list[dict]:
    """Extract file list from tendersData JS object."""
    m = re.search(r"var\s+tendersData\s*=\s*(\{.*?\})\s*;", html, re.DOTALL)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except (json.JSONDecodeError, ValueError):
        return []

    files: list[dict] = []
    for _tid, tdata in data.items():
        for _date, flist in tdata.get("files_by_date", {}).items():
            for f in flist:
                files.append({
                    "title": f.get("title", ""),
                    "link": f.get("link", ""),
                    "size": f.get("size", 0),
                    "extension": f.get("extension", ""),
                })
    return files
