"""
TenderGuru API v2.3 client for tender discovery and enrichment.

API docs: https://www.tenderguru.ru/api/documentation
Base URL: https://www.tenderguru.ru/api2.3/export

Supports commercial (b2b), 44-FZ, 223-FZ tenders.
Commercial tenders have sparse structured fields — key data lives in Info HTML.
"""
from __future__ import annotations

import html
import logging
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://www.tenderguru.ru/api2.3/export"
USER_AGENT = "Tenderoll/1.0 (tender aggregator; support@tenderoll.ru)"

PROCEDURE_KEYWORDS: dict[str, str] = {
    "электронный аукцион": "auction",
    "аукцион": "auction",
    "открытый конкурс": "contest",
    "конкурс": "contest",
    "запрос котировок": "request_quotations",
    "запрос цен": "request_quotations",
    "запрос предложений": "request_proposals",
    "закупка у единственного поставщика": "single_source",
    "единственный поставщик": "single_source",
}


def _get_api_key() -> str:
    return getattr(settings, "TENDERGURU_API_KEY", "")


def _session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


# ---------------------------------------------------------------------------
# List endpoint
# ---------------------------------------------------------------------------

def search_tenders(
    *,
    page: int = 1,
    law_filter: str = "kom",
    actual: bool = True,
    sort_by: str = "by_date",
    sort_dest: str = "desc",
    price_min: int | None = None,
    price_max: int | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
    session: requests.Session | None = None,
    api_key: str | None = None,
) -> list[dict]:
    """
    Fetch a page of tenders from TenderGuru list API.

    law_filter: "kom" (commercial), "44", "223", or "" (all).
    date_start/date_end: filter by publication date, format "DD.MM.YYYY".
    Returns list of raw API dicts (without the Total item).
    """
    key = api_key or _get_api_key()
    params: dict[str, str | int] = {
        "dtype": "json",
        "page": page,
        "sort_by": sort_by,
        "sort_dest": sort_dest,
    }
    if key:
        params["api_code"] = key
    if law_filter:
        params["f"] = law_filter
    if actual:
        params["actual"] = 1
    if price_min is not None:
        params["price1"] = price_min
    if price_max is not None:
        params["price2"] = price_max
    if date_start is not None:
        params["date_start"] = date_start
    if date_end is not None:
        params["date_end"] = date_end

    sess = session or _session()
    resp = sess.get(BASE_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if not isinstance(data, list) or len(data) < 2:
        return []

    return data[1:]


def fetch_tender_detail(
    tender_id: int | str,
    *,
    session: requests.Session | None = None,
    api_key: str | None = None,
) -> dict | None:
    """Fetch detailed tender card by TenderGuru ID."""
    key = api_key or _get_api_key()
    params: dict[str, str | int] = {
        "dtype": "json",
        "id": tender_id,
    }
    if key:
        params["api_code"] = key

    sess = session or _session()
    try:
        resp = sess.get(BASE_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("TenderGuru detail %s failed: %s", tender_id, exc)
        return None

    if not isinstance(data, list) or not data:
        return None

    return data[0]


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_list_item(item: dict) -> dict | None:
    """Convert a TenderGuru list API item into upsert_tender-compatible dict."""
    tg_id = item.get("ID")
    title = _clean_html(item.get("TenderName", ""))
    if not tg_id or not title:
        return None

    fz = str(item.get("Fz", "")).strip()
    law_type = _map_law_type(fz)
    price = _parse_price(item.get("Price", ""))

    procedure = _detect_procedure_type(title)
    if procedure == "other":
        procedure = _detect_procedure_from_fragments(item.get("searchFragmentXML"))

    return {
        "number": f"tg-{tg_id}",
        "source": "tenderguru",
        "title": title,
        "nmck": str(price) if price is not None else None,
        "customer_name": _clean_html(item.get("Customer", "")),
        "customer_inn": "",
        "region": item.get("Region", "").strip(),
        "law_type": law_type,
        "procedure_type": procedure,
        "source_url": item.get("TenderLink", "") or item.get("TenderLinkInner", ""),
        "trading_platform": item.get("Etp", "").strip(),
        "trading_platform_url": "",
        "status": "active",
        "published_at": _parse_date(item.get("Date", "")),
        "deadline_at": _parse_date(item.get("EndTime", "")),
        "okpd_codes": [],
        "raw_json": {
            "tg_id": tg_id,
            "category": item.get("Category", ""),
            "fz": fz,
            "tender_link": item.get("TenderLink", ""),
            "tender_link_inner": item.get("TenderLinkInner", ""),
            "user_id": item.get("User_id", ""),
            "tender_num_outer": item.get("TenderNumOuter", ""),
        },
    }


def enrich_from_detail(base: dict, detail: dict) -> dict:
    """Merge detail API fields into a parsed list item dict."""
    info_html = detail.get("Info", "")
    info_parsed = _parse_info_html(info_html) if info_html else {}

    customer_inn = str(detail.get("CustomerINN", "")).strip()
    if "/" in customer_inn:
        customer_inn = customer_inn.split("/")[0].strip()
    if not customer_inn.isdigit() or len(customer_inn) > 12:
        customer_inn = ""
    if customer_inn and customer_inn != "0":
        base["customer_inn"] = customer_inn

    tender_type = detail.get("TenderType", "").strip()
    if tender_type:
        base["procedure_type"] = _map_procedure_type_from_api(tender_type)
    elif info_parsed.get("procedure_type"):
        base["procedure_type"] = info_parsed["procedure_type"]

    ob_price = _parse_price(detail.get("ObPrice", ""))
    if ob_price is not None:
        base["bid_security_amount"] = str(ob_price)
        base["bid_security_required"] = True

    ob_from_info = info_parsed.get("security_amount")
    if ob_from_info and not ob_price:
        base["bid_security_amount"] = str(ob_from_info)
        base["bid_security_required"] = True

    delivery_place = (
        detail.get("deliveryPlace", "").strip()
        or detail.get("delivery_place", "").strip()
        or info_parsed.get("delivery_place", "")
    )

    products = _parse_products(detail.get("productsXML"))
    okpd_codes = [p["code"] for p in products if p.get("code")]
    if okpd_codes:
        base["okpd_codes"] = okpd_codes

    docs = _parse_docs(detail.get("docsXML"))
    if not docs:
        docs = _parse_links_tender_xml(detail.get("linksTenderXML"))
    if not docs:
        docs = _parse_docs_from_html(info_html)

    source_url = detail.get("TenderLink", "").strip()
    if source_url:
        base["source_url"] = _unescape_amp(source_url)

    eis_link = detail.get("EisLink", "").strip()

    bidding_date = detail.get("biddingDate", "").strip()
    if bidding_date and bidding_date != "--":
        parsed_bd = _parse_date(bidding_date)
        if parsed_bd:
            base["auction_date"] = parsed_bd

    contact_name = detail.get("contactName", "").strip()
    contact_phone = detail.get("contactPhone", "").strip()
    contact_email = detail.get("contactEmail", "").strip()

    delivery_term = (
        detail.get("delivery_term", "").strip()
        or info_parsed.get("delivery_term", "")
    )

    base["raw_json"].update({
        "info_html": info_html[:50000],
        "delivery_place": delivery_place,
        "delivery_term": delivery_term,
        "products": products,
        "doc_files": docs,
        "eis_link": eis_link,
        "contact_name": contact_name,
        "contact_phone": contact_phone,
        "contact_email": contact_email,
        "tender_type_raw": tender_type,
        "smp": detail.get("smp", ""),
        "request_receiving_date": detail.get("request_receiving_date", ""),
        "request_examination_date": detail.get("request_examination_date", ""),
        "request_receiving_end_date": detail.get("request_receiving_end_date", ""),
    })

    return base


# ---------------------------------------------------------------------------
# Info HTML parser
# ---------------------------------------------------------------------------

def _parse_info_html(raw: str) -> dict:
    """Extract structured data from the Info HTML field."""
    text = html.unescape(raw)
    text = text.replace("![CDATA[", "").rstrip("]")
    text = re.sub(r"<[^>]+>", "\n", text)
    text = re.sub(r"\n{2,}", "\n", text).strip()

    result: dict = {}

    delivery_m = re.search(
        r"(?:Место доставки|Место поставки[^:]*|Адрес доставки)[:\s]*\n\s*(.+)",
        text, re.IGNORECASE,
    )
    if delivery_m:
        val = delivery_m.group(1).strip()
        if len(val) > 5 and not val.startswith("товар"):
            result["delivery_place"] = val[:500]

    term_m = re.search(
        r"(?:Максимальный срок поставки|Срок поставки[^:]*|Срок исполнения)[:\s]*\n\s*(.+)",
        text, re.IGNORECASE,
    )
    if term_m:
        result["delivery_term"] = term_m.group(1).strip()[:200]

    security_m = re.search(
        r"(?:Сумма обеспечения|Обеспечение заявки)[:\s]*\n?\s*([\d\s,.]+)\s*(?:руб|₽)?",
        text, re.IGNORECASE,
    )
    if security_m:
        result["security_amount"] = _parse_price(security_m.group(1))

    proc_m = re.search(
        r"(Запрос предложений|Запрос котировок|Аукцион|Электронный аукцион"
        r"|Открытый конкурс|Конкурс|Закупка у единственного поставщика)",
        text, re.IGNORECASE,
    )
    if proc_m:
        result["procedure_type"] = _map_procedure_type_from_api(proc_m.group(1))

    return result


def _parse_docs_from_html(raw: str) -> list[dict]:
    """Extract document download links embedded in Info HTML."""
    if not raw:
        return []
    text = html.unescape(raw).replace("![CDATA[", "").rstrip("]")
    result = []
    seen: set[str] = set()
    for m in re.finditer(
        r'href="([^"]+)"[^>]*>\s*(?:<[^>]*>\s*)*([^<]+)', text, re.I,
    ):
        link, name = m.group(1).strip(), m.group(2).strip()
        if not link or link in seen:
            continue
        if link.startswith("mailto:"):
            continue
        lnk = link.lower()
        name_l = name.lower()
        is_doc = (
            "open-api/documents/" in lnk
            or "filestore" in lnk and "download" in lnk
            or re.search(r"\.(pdf|docx?|xlsx?|zip|rar|rtf|csv|pptx?)(\?|$)", lnk)
        )
        if not is_doc:
            is_doc = re.search(r"\.(pdf|docx?|xlsx?|zip|rar|rtf|csv|pptx?)$", name_l)
        if not is_doc:
            continue
        if "подать" in name_l and "предложение" in name_l:
            continue
        seen.add(link)
        result.append({
            "title": name,
            "link": link,
            "extension": _guess_extension(name),
        })
    return result


# ---------------------------------------------------------------------------
# Products & docs parsers
# ---------------------------------------------------------------------------

def _parse_products(products_xml) -> list[dict]:
    """Parse productsXML into a list of product dicts."""
    if not products_xml:
        return []

    items = products_xml
    if isinstance(items, dict):
        if "product" in items:
            items = items["product"]
            if isinstance(items, dict):
                items = [items]
        else:
            return []

    if not isinstance(items, list):
        return []

    result = []
    for p in items:
        if not isinstance(p, dict):
            continue
        result.append({
            "name": p.get("ProductName", ""),
            "code": p.get("ProductCode", ""),
            "unit": p.get("Izm", ""),
            "quantity": p.get("Kolvo", ""),
            "unit_price": p.get("edPrice", ""),
            "total_price": p.get("ProductPrice", ""),
        })
    return result


def _parse_docs(docs_xml) -> list[dict]:
    """Parse docsXML into a list of document dicts."""
    if not docs_xml:
        return []

    items = docs_xml
    if isinstance(items, dict):
        if "document" in items:
            items = items["document"]
            if isinstance(items, dict):
                items = [items]
        else:
            return []

    if not isinstance(items, list):
        return []

    result = []
    for d in items:
        if not isinstance(d, dict):
            continue
        link = d.get("link", "")
        name = d.get("name", "")
        if link:
            result.append({
                "title": name,
                "link": link,
                "extension": _guess_extension(name),
            })
    return result


def _parse_links_tender_xml(links_xml) -> list[dict]:
    """Parse linksTenderXML into a list of document dicts (Bidzaar, B2B-Center, Portal)."""
    if not links_xml:
        return []

    items = links_xml.get("item") if isinstance(links_xml, dict) else None
    if not items:
        return []

    if isinstance(items, dict):
        items = [items]

    if not isinstance(items, list):
        return []

    result = []
    for d in items:
        if not isinstance(d, dict):
            continue
        raw_name = d.get("linkName", "")
        name = raw_name.strip().strip('"') if isinstance(raw_name, str) else ""
        raw_dl = d.get("linkURL", "") or d.get("download", "")
        download = raw_dl if isinstance(raw_dl, str) else ""
        if not download or not name:
            continue
        if name.lower() in ("источник",):
            continue
        if download.startswith("mailto:"):
            continue
        if "подать" in name.lower() and "предложение" in name.lower():
            continue
        result.append({
            "title": name,
            "link": download,
            "extension": _guess_extension(name),
        })
    return result


# ---------------------------------------------------------------------------
# Field helpers
# ---------------------------------------------------------------------------

def _clean_html(text: str) -> str:
    """Strip HTML tags and entities from text."""
    text = html.unescape(text)
    text = text.replace("&nbsp;", " ")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _unescape_amp(url: str) -> str:
    return url.replace("&amp;", "&")


def _parse_price(value) -> Decimal | None:
    if not value:
        return None
    text = str(value).strip()
    if not text or text == "0":
        return None
    cleaned = re.sub(r"[^\d,.]", "", text.replace("\xa0", ""))
    cleaned = cleaned.replace(",", ".")
    if not cleaned:
        return None
    try:
        result = Decimal(cleaned)
        return result if result > 0 else None
    except InvalidOperation:
        return None


def _parse_date(text: str | None) -> str | None:
    """Parse TenderGuru date format 'DD-MM-YYYY' or 'DD.MM.YYYY' → ISO string."""
    if not text or not text.strip():
        return None
    text = text.strip()

    from zoneinfo import ZoneInfo
    msk = ZoneInfo("Europe/Moscow")

    formats = [
        "%d-%m-%Y",
        "%d.%m.%Y",
        "%d-%m-%Y %H:%M:%S",
        "%d.%m.%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%d.%m.%Y %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(text, fmt)
            return dt.replace(tzinfo=msk).isoformat()
        except ValueError:
            continue
    return None


def _map_law_type(fz: str) -> str:
    if fz == "44":
        return "44-ФЗ"
    if fz == "223":
        return "223-ФЗ"
    return "b2b"


def _detect_procedure_type(title: str) -> str:
    """Detect procedure type from tender title keywords."""
    title_lower = title.lower()
    for keyword, ptype in PROCEDURE_KEYWORDS.items():
        if keyword in title_lower:
            return ptype
    return "other"


def _detect_procedure_from_fragments(fragments) -> str:
    """Detect procedure type from searchFragmentXML."""
    if not fragments:
        return "other"
    frags = fragments
    if isinstance(frags, dict):
        frags = frags.get("fragment", [])
    if isinstance(frags, str):
        frags = [frags]
    if not isinstance(frags, list):
        return "other"
    text = " ".join(str(f) for f in frags)
    return _map_procedure_type_from_api(text) if text else "other"


def _map_procedure_type_from_api(tender_type: str) -> str:
    """Map TenderGuru TenderType field to our procedure_type choices."""
    t = tender_type.lower().strip()
    for keyword, ptype in PROCEDURE_KEYWORDS.items():
        if keyword in t:
            return ptype
    return "other"


def _guess_extension(filename: str) -> str:
    if not filename:
        return ""
    m = re.search(r"\.(\w{2,5})(?:\.zip)?$", filename.lower())
    return m.group(1) if m else ""
