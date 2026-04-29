"""
HTTP-клиент для ЕИС (zakupki.gov.ru).

Два уровня данных:
- search_tenders()     → быстрый список из поисковой выдачи (карточки)
- fetch_tender_detail() → полный парсинг страницы отдельного тендера
"""
import logging
import re
import time
from datetime import date, timedelta
from typing import Any

import requests
from lxml import etree, html as lxml_html

logger = logging.getLogger(__name__)

BASE_URL = "https://zakupki.gov.ru"
SEARCH_URL = BASE_URL + "/epz/order/extendedsearch/results.html"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "ru-RU,ru;q=0.9",
}

RECORDS_PER_PAGE = 50


# ---------------------------------------------------------------------------
# Низкоуровневые утилиты
# ---------------------------------------------------------------------------

def _fetch_html(url: str, params: dict | None = None, retries: int = 2) -> str | None:
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
            resp.raise_for_status()
            return resp.text
        except Exception as exc:
            if attempt < retries:
                wait = 3 * (attempt + 1)
                logger.warning("Retry %d for %s in %ds: %s", attempt + 1, url, wait, exc)
                time.sleep(wait)
            else:
                logger.error("Failed to fetch %s: %s", url, exc)
    return None


def _parse_price(s: str) -> float | None:
    cleaned = re.sub(r"[^\d,.]", "", s).replace(",", ".")
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def _parse_date(s: str) -> str | None:
    if not s:
        return None
    s = s.strip().split("(")[0].strip()
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})(?:\s+(\d{2}:\d{2}))?", s)
    if not m:
        return None
    d, mo, y, t = m.groups()
    # Moscow time (UTC+3) — ЕИС публикует время по МСК
    return f"{y}-{mo}-{d}T{t}:00+03:00" if t else f"{y}-{mo}-{d}T00:00:00+03:00"


def _tree_from_html(html_text: str) -> lxml_html.HtmlElement:
    return lxml_html.fromstring(html_text)


def _field_after(tree: etree._Element, label: str) -> str:
    for el in tree.xpath(f'//*[normalize-space(text())="{label}"]'):
        parent = el.getparent()
        if parent is None:
            continue
        children = list(parent)
        try:
            idx = children.index(el)
        except ValueError:
            continue
        for sibling in children[idx + 1 :]:
            texts = [t.strip() for t in sibling.xpath(".//text()") if t.strip()]
            val = " ".join(t for t in texts if not t.startswith("$("))
            if val:
                return val
    return ""


# ---------------------------------------------------------------------------
# Поиск тендеров (список)
# ---------------------------------------------------------------------------

def search_tenders(
    date_from: date,
    date_to: date,
    page: int = 1,
    fz44: bool = True,
    fz223: bool = True,
) -> list[dict[str, Any]]:
    """
    Возвращает список карточек тендеров со страницы поиска ЕИС.
    Каждая карточка содержит базовые поля без дополнительных HTTP-запросов.
    """
    params: dict[str, Any] = {
        "morphology": "on",
        "search-filter": "Дата размещения",
        "pageNumber": page,
        "sortDirection": "false",
        "recordsPerPage": f"_{RECORDS_PER_PAGE}",
        "showLotsInfoHidden": "false",
        "publishDateFrom": date_from.strftime("%d.%m.%Y"),
        "publishDateTo": date_to.strftime("%d.%m.%Y"),
        "af": "on",
        "ca": "on",
        "pc": "on",
        "pa": "on",
    }
    if fz44:
        params["fz44"] = "on"
    if fz223:
        params["fz223"] = "on"

    html = _fetch_html(SEARCH_URL, params=params)
    if not html:
        return []

    tree = _tree_from_html(html)
    results = []

    for entry in tree.xpath('//*[contains(@class,"search-registry-entry-block")]'):
        tender = _parse_search_entry(entry)
        if tender:
            results.append(tender)

    logger.info(
        "Search page=%d dates=%s..%s → %d results",
        page,
        date_from,
        date_to,
        len(results),
    )
    return results


def _parse_search_entry(entry: lxml_html.HtmlElement) -> dict[str, Any] | None:
    # Ссылка на common-info (не printForm)
    link_el = entry.xpath('.//div[contains(@class,"registry-entry__header-mid__number")]//a')
    if not link_el:
        # fallback: любая ссылка с common-info
        link_el = entry.xpath('.//a[contains(@href,"common-info")]')
    if not link_el:
        return None

    href = link_el[0].get("href", "")
    if not href.startswith("http"):
        href = BASE_URL + href

    m = re.search(r"regNumber=(\w+)", href)
    purchase_number = m.group(1) if m else ""
    if not purchase_number:
        m = re.search(r"noticeInfoId=(\d+)", href)
        purchase_number = m.group(1) if m else ""
    if not purchase_number:
        return None

    law_type = "223-ФЗ" if ("notice223" in href or "noticeInfoId" in href) else "44-ФЗ"

    # Название (объект закупки)
    title = ""
    title_els = entry.xpath(
        './/div[@class="registry-entry__body-block"]'
        '//div[@class="registry-entry__body-value"]'
    )
    if title_els:
        title = title_els[0].text_content().strip()

    # НМЦК
    price: float | None = None
    price_els = entry.xpath('.//div[contains(@class,"price-block__value")]')
    if price_els:
        raw = price_els[0].text_content().strip()
        price = _parse_price(raw)

    # Заказчик
    customer_name = ""
    customer_region = ""
    customer_els = entry.xpath('.//div[@class="registry-entry__body-href"]//a')
    if customer_els:
        customer_name = customer_els[0].text_content().strip()

    # Дата размещения
    published_at: str | None = None
    date_title_els = entry.xpath('.//div[@class="data-block__title"]')
    for dt in date_title_els:
        if dt.text_content().strip() == "Размещено":
            val_el = dt.getnext()
            if val_el is not None:
                published_at = _parse_date(val_el.text_content().strip())
            break

    # ОКПД2 из карточки (иногда есть)
    okpd_codes: list[str] = []
    for okpd_el in entry.xpath('.//*[contains(@class,"registry-entry__body-okpd")]'):
        raw = okpd_el.text_content().strip()
        codes = re.findall(r"\d{2}\.\d[\d.]*", raw)
        okpd_codes.extend(codes)

    return {
        "number": purchase_number,
        "title": title,
        "nmck": price,
        "law_type": law_type,
        "source_url": href,
        "published_at": published_at,
        "okpd_codes": okpd_codes,
        "customer_name": customer_name,
        "customer_region": customer_region,
    }


# ---------------------------------------------------------------------------
# Детальный парсинг страницы тендера
# ---------------------------------------------------------------------------

def fetch_tender_detail(purchase_number: str, fallback_url: str = "") -> dict[str, Any]:
    """
    Парсит страницу common-info тендера (44-ФЗ).
    Возвращает нормализованный словарь, совместимый с services.upsert_tender().
    """
    info_url = (
        f"{BASE_URL}/epz/order/notice/ea44/view/common-info.html"
        f"?regNumber={purchase_number}"
    )
    try:
        resp = requests.get(info_url, headers=HEADERS, timeout=20, allow_redirects=True)
        resp.raise_for_status()
        final_url = resp.url
        tree = _tree_from_html(resp.text)
    except Exception as exc:
        logger.error("Failed to fetch detail for %s: %s", purchase_number, exc)
        return {}

    f = lambda label: _field_after(tree, label)

    # НМЦК из блока цены
    price_raw = ""
    for el in tree.xpath('//*[contains(@class,"price-block__value")]'):
        t = " ".join(s.strip() for s in el.xpath(".//text()") if s.strip())
        if t and any(c.isdigit() for c in t):
            price_raw = t
            break
    if not price_raw:
        price_raw = f("Начальная (максимальная) цена контракта")
    m_price = re.search(r"[\d\s]+[,.][\d]+", price_raw)
    nmck = _parse_price(m_price.group(0) if m_price else price_raw)

    # Заказчик
    customer_name = f("Организация, осуществляющая размещение")
    customer_region = f("Регион")
    customer_inn = ""
    inn_el = tree.xpath('//*[contains(text(),"ИНН")]/following-sibling::*[1]')
    if inn_el:
        customer_inn = inn_el[0].text_content().strip()

    # ОКПД2 из позиций
    okpd_codes: list[str] = []
    for row in tree.xpath('//*[contains(@class,"tableBlock__row") or contains(@class,"lots-position")]'):
        cells = row.xpath('.//*[contains(@class,"col") or self::td]')
        texts = [
            " ".join(t.strip() for t in c.xpath(".//text()") if t.strip())
            for c in cells
        ]
        texts = [t for t in texts if t]
        if texts and re.match(r"\d{2}\.\d{2}", texts[0]):
            code = re.match(r"[\d.]+", texts[0]).group(0).rstrip(".")
            okpd_codes.append(code)

    # Дата торгов — реальная метка из ЕИС для электронного аукциона (ea20/ea44)
    auction_date_raw = (
        f("Дата проведения процедуры подачи предложений о цене контракта либо о сумме цен единиц товара, работы, услуги")
        or f("Дата и время проведения аукциона в электронной форме")
        or f("Дата и время проведения торгов")
        or f("Дата рассмотрения и оценки заявок")
        or f("Дата и время рассмотрения и оценки первых частей заявок")
    )

    # Торговая площадка — реальная метка из ЕИС (с «»)
    platform = (
        f("Наименование электронной площадки в информационно-телекоммуникационной сети \u00abИнтернет\u00bb")
        or f("Наименование электронной торговой площадки")
        or f("Место проведения")
    )
    platform_url = (
        f("Адрес электронной площадки в информационно-телекоммуникационной сети \u00abИнтернет\u00bb")
        or f("Адрес электронной площадки")
        or ""
    )

    # Обеспечение заявки
    bid_sec_raw = (
        f("Размер обеспечения заявки")
        or f("Обеспечение заявки на участие в открытом конкурсе в электронной форме")
        or f("Обеспечение заявки")
    )
    bid_security_amount: float | None = None
    bid_security_required: bool | None = None
    # Если метка есть, но значение пустое — значит не требуется (поле скрыто)
    if bid_sec_raw:
        lower = bid_sec_raw.lower()
        if "не требуется" in lower or "не установлено" in lower or "0" == bid_sec_raw.strip():
            bid_security_required = False
            bid_security_amount = None
        else:
            bid_security_amount = _parse_price(bid_sec_raw)
            bid_security_required = bid_security_amount is not None and bid_security_amount > 0

    # Обеспечение исполнения контракта — может быть суммой ("10 793 ₽") или % ("10 %")
    contract_sec_raw = (
        f("Размер обеспечения исполнения контракта")
        or f("Обеспечение исполнения контракта")
    )
    contract_security_amount: float | None = None
    contract_security_percent: float | None = None
    if contract_sec_raw:
        # Сначала пробуем извлечь процент
        pct_match = re.search(r"([\d]+[,.]?[\d]*)\s*%", contract_sec_raw)
        # Пробуем извлечь рублёвую сумму (наличие цифры перед ₽ или просто большое число)
        rub_match = re.search(r"([\d\s]+[,.][\d]+)\s*(?:₽|руб)", contract_sec_raw)
        if not rub_match and "%" not in contract_sec_raw:
            rub_match = re.search(r"([\d\s]+[,.][\d]+)", contract_sec_raw)

        if rub_match:
            contract_security_amount = _parse_price(rub_match.group(1))
        if pct_match:
            contract_security_percent = _parse_price(pct_match.group(1))

    # Тип закона — из содержимого страницы (надёжнее чем URL)
    law_type = ""
    for el in tree.xpath('//*[contains(@class,"section__title") or contains(@class,"registry-entry__header-mid__title")]'):
        t = el.text_content().strip()
        if "223-ФЗ" in t:
            law_type = "223-ФЗ"
            break
        if "44-ФЗ" in t:
            law_type = "44-ФЗ"
            break
    if not law_type:
        # fallback из URL
        if "notice223" in final_url:
            law_type = "223-ФЗ"
        elif any(x in final_url for x in ("ea44", "ea20", "zk44", "ok44", "zp44")):
            law_type = "44-ФЗ"

    return {
        "number": purchase_number,
        "title": f("Наименование объекта закупки"),
        "nmck": nmck,
        "customer_name": customer_name,
        "customer_region": customer_region,
        "customer_inn": customer_inn,
        "region": customer_region,
        "okpd_codes": okpd_codes,
        "published_at": _parse_date(f("Размещено")),
        "deadline_at": _parse_date(f("Дата и время окончания срока подачи заявок")),
        "auction_date": _parse_date(auction_date_raw) if auction_date_raw else None,
        "law_type": law_type,
        "trading_platform": platform,
        "trading_platform_url": platform_url,
        "bid_security_amount": bid_security_amount,
        "bid_security_required": bid_security_required,
        "contract_security_amount": contract_security_amount,
        "contract_security_percent": contract_security_percent,
        "status": "active",
        "source_url": final_url,
        "raw_json": {},
    }
