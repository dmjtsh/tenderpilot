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

# Коды субъектов РФ для ЕИС (параметр subjectRF)
REGION_CODES: dict[str, str] = {
    "Самарская область": "63",
    "Ульяновская область": "73",
    "Пензенская область": "58",
    "Оренбургская область": "56",
    "Саратовская область": "64",
    "Татарстан": "16",
    "Башкортостан": "2",
    "Пермский край": "59",
    "Нижегородская область": "52",
    "Мордовия": "13",
    "Чувашия": "21",
    "Московская область": "50",
    "Москва": "77",
    "Санкт-Петербург": "78",
}


def search_tenders(
    date_from: date,
    date_to: date,
    page: int = 1,
    fz44: bool = True,
    fz223: bool = True,
    region_code: str | None = None,
    search_string: str | None = None,
    only_accepting: bool = True,
    price_from: str | None = None,
    price_to: str | None = None,
) -> list[dict[str, Any]]:
    """
    Возвращает список карточек тендеров со страницы поиска ЕИС.
    search_string — ключевые слова для поиска по тексту тендера.
    only_accepting=True — только тендеры в статусе «Подача заявок» (af).
    price_from / price_to — фильтр по НМЦК (priceFromGeneral / priceToGeneral).
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
    }
    if not only_accepting:
        params["ca"] = "on"
        params["pc"] = "on"
        params["pa"] = "on"
    if fz44:
        params["fz44"] = "on"
    if fz223:
        params["fz223"] = "on"
    if search_string:
        params["searchString"] = search_string
    if price_from:
        params["priceFromGeneral"] = price_from
    if price_to:
        params["priceToGeneral"] = price_to

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


def fetch_day_count(day: date, fz44: bool = True, fz223: bool = True) -> int | None:
    """
    Возвращает кол-во тендеров за день по данным ЕИС (только «Подача заявок», как в sync).
    Парсит текст вида «более 5 600 записей» или «1 234 записи» с первой страницы поиска.
    Возвращает None если ЕИС недоступен или счётчик не найден.
    """
    params: dict[str, Any] = {
        "morphology": "on",
        "search-filter": "Дата размещения",
        "pageNumber": 1,
        "sortDirection": "false",
        "recordsPerPage": "_10",
        "showLotsInfoHidden": "false",
        "sortBy": "UPDATE_DATE",
        "publishDateFrom": day.strftime("%d.%m.%Y"),
        "publishDateTo": day.strftime("%d.%m.%Y"),
        "af": "on",
    }
    if fz44:
        params["fz44"] = "on"
    if fz223:
        params["fz223"] = "on"

    html = _fetch_html(SEARCH_URL, params=params)
    if not html:
        return None

    # «более 5 600 записей» / «1 234 записи» / «0 записей»
    # ЕИС использует неразрывный пробел ( ) как разделитель тысяч
    m = re.search(r"(?:более\s*)?([\d][\d\s ]*)\s*запис", html)
    if m:
        raw = re.sub(r"[\s ]", "", m.group(1))
        try:
            return int(raw)
        except ValueError:
            pass

    logger.warning("fetch_day_count: count not found in EIS response for %s", day)
    return None


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

    law_type = "223-ФЗ" if ("notice223" in href or "noticeInfoId" in href or "/223/" in href) else "44-ФЗ"

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

def _is_223_url(url: str) -> bool:
    return "/223/" in url or "notice223" in url


def _extract_inn_from_org_link(tree: etree._Element) -> str:
    """Extract customer INN from organization page link (44-ФЗ).

    44-ФЗ tender pages don't show INN directly — it's on a separate
    organization page linked via organizationCode parameter.
    """
    links = tree.xpath('//a[contains(@href,"organizationCode=")]/@href')
    if not links:
        return ""
    m = re.search(r"organizationCode=(\d+)", links[0])
    if not m:
        return ""
    org_code = m.group(1)
    org_url = f"{BASE_URL}/epz/organization/view/info.html?organizationCode={org_code}"
    try:
        resp = requests.get(org_url, headers=HEADERS, timeout=15, allow_redirects=True)
        resp.raise_for_status()
        org_tree = _tree_from_html(resp.text)
    except Exception as exc:
        logger.warning("Failed to fetch org page for code %s: %s", org_code, exc)
        return ""
    for title_el in org_tree.xpath('//*[contains(@class,"section__title")]'):
        if "ИНН" in title_el.text_content():
            info_el = title_el.getnext()
            if info_el is not None:
                candidate = info_el.text_content().strip()
                if re.match(r"^\d{10,12}$", candidate):
                    return candidate
    return ""


def _fetch_tender_detail_223(purchase_number: str, source_url: str) -> dict[str, Any]:
    """Парсит страницу common-info тендера 223-ФЗ."""
    info_url = source_url or ""
    if info_url:
        info_url = re.sub(r"/(?:documents|print-form|supplier-results)\.html",
                          "/common-info.html", info_url)
    else:
        info_url = (
            f"{BASE_URL}/epz/order/notice/notice223/common-info.html"
            f"?noticeInfoId={purchase_number}"
        )
    try:
        resp = requests.get(info_url, headers=HEADERS, timeout=20, allow_redirects=True)
        resp.raise_for_status()
        final_url = resp.url
        tree = _tree_from_html(resp.text)
    except Exception as exc:
        logger.error("Failed to fetch 223-FZ detail for %s: %s", purchase_number, exc)
        return {}

    f = lambda label: _field_after(tree, label)

    # НМЦК
    price_raw = ""
    for el in tree.xpath('//*[contains(@class,"price-block__value")]'):
        t = " ".join(s.strip() for s in el.xpath(".//text()") if s.strip())
        if t and any(c.isdigit() for c in t):
            price_raw = t
            break
    if not price_raw:
        price_raw = (
            f("Начальная (максимальная) цена договора")
            or f("Начальная цена договора")
            or f("Начальная (максимальная) цена контракта")
        )
    m_price = re.search(r"[\d\s]+[,.][\d]+", price_raw)
    nmck = _parse_price(m_price.group(0) if m_price else price_raw)

    # Заказчик
    customer_name = f("Заказчик") or f("Организация, осуществляющая закупку")
    customer_inn = ""
    inn_el = tree.xpath('//*[normalize-space(text())="ИНН"]/following-sibling::*[1]')
    if inn_el:
        candidate = inn_el[0].text_content().strip()
        if re.match(r"^\d{10,12}$", candidate):
            customer_inn = candidate

    # Регион из адреса места нахождения
    # Формат адреса ЕИС: "693020, САХАЛИНСКАЯ ОБЛАСТЬ, г.о. ГОРОД ЮЖНО-САХАЛИНСК, ..."
    # Первая часть — почтовый индекс (6 цифр), вторая — регион
    customer_region = ""
    location_raw = f("Место нахождения") or f("Место поставки, выполнения работ или оказания услуг")
    if location_raw:
        parts = [p.strip() for p in location_raw.split(",")]
        # Пропускаем почтовый индекс (6 цифр) в начале
        if parts and re.match(r"^\d{6}$", parts[0]):
            parts = parts[1:]
        # Ищем часть с ключевым словом региона
        REGION_KEYWORDS = ["ОБЛАСТЬ", "КРАЙ", "РЕСПУБЛИКА", "ОКРУГ", "МОСКВА", "САНКТ-ПЕТЕРБУРГ", "СЕВАСТОПОЛЬ", "БАЙКОНУР"]
        for part in parts:
            if any(word in part.upper() for word in REGION_KEYWORDS):
                customer_region = part.strip().title()
                break
        # Fallback: первая непустая часть, если не цифры
        if not customer_region:
            for part in parts:
                if part and not re.match(r"^\d+$", part):
                    customer_region = part.strip().title()
                    break

    # ОКПД2 — на common-info.html кодов нет, они на lot-list.html
    okpd_codes: list[str] = []
    lots_url = re.sub(r"common-info\.html", "lot-list.html", info_url)
    if lots_url != info_url:
        try:
            lots_resp = requests.get(lots_url, headers=HEADERS, timeout=15)
            if lots_resp.ok:
                lots_tree = _tree_from_html(lots_resp.text)
                for td in lots_tree.xpath("//td"):
                    text = td.text_content().strip()
                    if re.match(r"\d{2}\.\d{2}", text):
                        code = re.match(r"[\d.]+", text).group(0).rstrip(".")
                        if code not in okpd_codes:
                            okpd_codes.append(code)
        except Exception as exc:
            logger.warning("Failed to fetch lot-list for %s: %s", purchase_number, exc)

    # Дедлайн — 223-ФЗ использует другой лейбл с уточнением "по местному времени"
    deadline_raw = (
        f("Дата и время окончания срока подачи заявок (по местному времени заказчика)")
        or f("Дата и время окончания срока подачи заявок")
        or f("Окончание подачи заявок")
    )
    auction_date_raw = (
        f("Дата подведения итогов")
        or f("Дата и время проведения торгов")
        or f("Дата рассмотрения и оценки заявок")
    )
    published_raw = f("Дата размещения извещения") or f("Размещено")

    # Торговая площадка
    platform = (
        f("Наименование электронной площадки в информационно-телекоммуникационной сети \u00abИнтернет\u00bb")
        or f("Наименование электронной торговой площадки")
        or f("Наименование электронной площадки")
        or f("Место проведения")
    )
    platform_url = (
        f("Адрес электронной площадки в информационно-телекоммуникационной сети \u00abИнтернет\u00bb")
        or f("Адрес электронной торговой площадки")
        or f("Адрес электронной площадки")
        or ""
    )

    # Способ закупки → procedure_type
    placing_way = (
        f("Способ осуществления закупки")
        or f("Способ размещения закупки")
        or f("Способ закупки")
        or f("Способ определения поставщика")
        or ""
    ).lower()
    _223_PROCEDURE_MAP = [
        ("единственн", "single_source"),
        ("единтсвенн", "single_source"),
        ("у еп ", "single_source"),
        ("у еп(", "single_source"),
        ("аукцион", "auction"),
        ("конкурс", "contest"),
        ("конкурентный отбор", "contest"),
        ("запрос котировок", "request_quotations"),
        ("запрс котировок", "request_quotations"),
        ("запрос ценовых котировок", "request_quotations"),
        ("запрос цен", "request_quotations"),
        ("ценовой запрос", "request_quotations"),
        ("ценового запрос", "request_quotations"),
        ("состязательный запрос", "request_quotations"),
        ("сбор заявок", "request_quotations"),
        ("запрос предложений", "request_proposals"),
        ("запрос коммерческих предложений", "request_proposals"),
        ("запрос оферт", "request_proposals"),
        ("отбор оферт", "request_proposals"),
        ("анализ предложений", "request_proposals"),
        ("формирование конкурентного листа", "request_proposals"),
        ("электронн", "request_quotations"),
        ("неконкурентн", "request_quotations"),
        ("маркетинговое исследование", "request_proposals"),
        ("маркетинговые исследования", "request_proposals"),
    ]
    procedure_type = "other"
    for key, val in _223_PROCEDURE_MAP:
        if key in placing_way:
            procedure_type = val
            break

    return {
        "number": purchase_number,
        "title": f("Наименование закупки") or f("Наименование объекта закупки"),
        "nmck": nmck,
        "customer_name": customer_name,
        "customer_region": customer_region,
        "customer_inn": customer_inn,
        "region": customer_region,
        "okpd_codes": okpd_codes,
        "published_at": _parse_date(published_raw),
        "deadline_at": _parse_date(deadline_raw),
        "auction_date": _parse_date(auction_date_raw) if auction_date_raw else None,
        "law_type": "223-ФЗ",
        "procedure_type": procedure_type,
        "trading_platform": platform,
        "trading_platform_url": platform_url,
        "bid_security_amount": None,
        "bid_security_required": None,
        "contract_security_amount": None,
        "contract_security_percent": None,
        "status": "active",
        "source_url": final_url,
        "raw_json": {},
    }


def fetch_tender_detail(purchase_number: str, fallback_url: str = "") -> dict[str, Any]:
    """
    Парсит страницу common-info тендера (44-ФЗ или 223-ФЗ).
    Определяет тип закона по fallback_url и вызывает нужный парсер.
    Возвращает нормализованный словарь, совместимый с services.upsert_tender().
    """
    if _is_223_url(fallback_url):
        return _fetch_tender_detail_223(purchase_number, fallback_url)

    if fallback_url:
        info_url = re.sub(r"/(?:documents|print-form|supplier-results)\.html",
                          "/common-info.html", fallback_url)
    else:
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
    customer_inn = _extract_inn_from_org_link(tree)

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
