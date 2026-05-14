import logging
import random
import re
import time
from typing import Any
from urllib.parse import urlencode

import requests
from django.core.cache import cache
from lxml import html as lxml_html

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]

CACHE_KEY_LAST_REQUEST = "rusprofile:last_request"


def _parse_number(text: str) -> int | None:
    """'250 310 000 руб.' → 250310000, '2 481' → 2481."""
    if not text:
        return None
    cleaned = re.sub(r"[^\d]", "", text)
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def _text(elements: list) -> str:
    if not elements:
        return ""
    return (elements[0].text_content() or "").strip()


def _unit_multiplier(unit: str) -> int:
    if "млрд" in unit:
        return 1_000_000_000
    if "млн" in unit:
        return 1_000_000
    if "тыс" in unit:
        return 1_000
    return 1


def _extract_rusprofile_id(url: str) -> int | None:
    m = re.search(r"/id/(\d+)", url)
    return int(m.group(1)) if m else None


class RusProfileParser:
    BASE_URL = "https://www.rusprofile.ru"
    CACHE_TTL_DAYS = 30
    MIN_DELAY = 2.0

    def get_company_info(self, inn: str) -> dict[str, Any] | None:
        self._rate_limit()
        search_url = f"{self.BASE_URL}/search?{urlencode({'query': inn})}"
        resp = self._fetch(search_url)
        if resp is None:
            return None

        page_html, final_url = resp
        rusprofile_id = _extract_rusprofile_id(final_url)

        data = self._parse(page_html)
        if not data:
            return None

        data["rusprofile_id"] = rusprofile_id
        data["source_url"] = final_url
        return data

    def _fetch(self, url: str) -> tuple[str, str] | None:
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }
        try:
            resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
            if resp.status_code == 429:
                logger.warning("RusProfile rate limited (429)")
                return None
            if resp.status_code == 503:
                logger.warning("RusProfile unavailable (503)")
                return None
            if resp.status_code != 200:
                logger.warning("RusProfile HTTP %d for %s", resp.status_code, url)
                return None
            return resp.text, resp.url
        except requests.RequestException as e:
            logger.error("RusProfile request failed: %s", e)
            return None

    def _rate_limit(self) -> None:
        last = cache.get(CACHE_KEY_LAST_REQUEST)
        if last is not None:
            elapsed = time.monotonic() - last
            if elapsed < self.MIN_DELAY:
                time.sleep(self.MIN_DELAY - elapsed)
        cache.set(CACHE_KEY_LAST_REQUEST, time.monotonic(), timeout=60)

    def _parse(self, page_html: str) -> dict[str, Any] | None:
        try:
            tree = lxml_html.fromstring(page_html)
        except Exception:
            logger.error("RusProfile HTML parse failed")
            return None

        # Проверяем что это страница компании (есть h1 с названием)
        name_els = tree.cssselect('h1[itemprop="name"]')
        if not name_els:
            logger.warning("RusProfile: no company name found, likely search results page")
            return None

        result: dict[str, Any] = {}
        result.update(self._parse_header(tree))
        result.update(self._parse_accounting(tree))
        result.update(self._parse_licenses(tree))
        result.update(self._parse_procurement(tree))
        result.update(self._parse_arbitration(tree))
        result.update(self._parse_fssp(tree))
        return result

    def _parse_header(self, tree) -> dict[str, Any]:
        data: dict[str, Any] = {}

        data["name"] = _text(tree.cssselect('h1[itemprop="name"]'))

        data["inn"] = _text(tree.cssselect("span#clip_inn"))
        data["ogrn"] = _text(tree.cssselect("span#clip_ogrn"))

        data["founded_date"] = _text(tree.cssselect('dd[itemprop="foundingDate"]'))
        data["region"] = _text(tree.cssselect('span[itemprop="addressRegion"]'))

        director_els = tree.cssselect("a.gtm_main_fl span.margin-right-s")
        data["director_name"] = _text(director_els) if director_els else ""

        # Статус — ищем warning-text
        status_els = tree.cssselect(".company-header__icon .warning-text")
        if status_els:
            data["status"] = _text(status_els)
            data["is_liquidated"] = True
        else:
            data["status"] = "Действующая"
            data["is_liquidated"] = False

        return data

    def _parse_section_values(self, tree, section_name: str) -> dict[str, str]:
        """Извлекает key-value из секции div[data-name=X]."""
        section = tree.cssselect(f'div[data-name="{section_name}"]')
        if not section:
            return {}

        el = section[0]
        if el.get("data-empty") == "true":
            return {}

        pairs: dict[str, str] = {}
        cols = el.cssselect(".connexion-col")
        for col in cols:
            title = _text(col.cssselect(".connexion-col__title"))
            num_el = col.cssselect(".connexion-col__num .num")
            num = _text(num_el) if num_el else _text(col.cssselect(".connexion-col__num"))
            if title:
                pairs[title.lower()] = num
        return pairs

    def _parse_section_text(self, tree, section_name: str) -> str:
        section = tree.cssselect(f'div[data-name="{section_name}"]')
        if not section:
            return ""
        text_els = section[0].cssselect(".tile-item__text")
        return _text(text_els)

    def _parse_accounting(self, tree) -> dict[str, Any]:
        section = tree.cssselect('div[data-name="accounting"]')
        if not section or section[0].get("data-empty") == "true":
            return {}

        el = section[0]
        data: dict[str, Any] = {}

        # Год из текста "за 2024 год"
        header_text = el.text_content()
        year_match = re.search(r"за\s+(20[12]\d)\s+год", header_text)
        if year_match:
            data["revenue_year"] = int(year_match.group(1))

        # finance-col: каждый столбец содержит label + span.num + span.num-text
        cols = el.cssselect(".finance-col")
        for col in cols:
            label = col.text_content().lower()
            num_el = col.cssselect("span.num")
            unit_el = col.cssselect("span.num-text")
            if not num_el:
                continue
            raw_num = _text(num_el)
            unit = _text(unit_el).lower() if unit_el else ""
            value = _parse_number(raw_num)
            if value is None:
                continue

            multiplier = _unit_multiplier(unit)
            value_rub = value * multiplier

            if "выручка" in label:
                data["revenue_rub"] = value_rub
            elif "прибыль" in label or "убыток" in label:
                # Отрицательная прибыль (убыток)
                if raw_num.strip().startswith("-"):
                    data["profit_rub"] = -abs(value_rub)
                else:
                    data["profit_rub"] = value_rub

        # Точные данные из data-points (JSON в атрибуте графика выручки)
        revenue_chart = el.cssselect('.finance-chart[data-tab_name="tab_revenue"] .acc-diagram')
        if revenue_chart:
            points_str = revenue_chart[0].get("data-points", "")
            scale_str = revenue_chart[0].get("data-scale", "1")
            try:
                import json
                points = json.loads(points_str)
                scale = int(scale_str)
                if points:
                    last_year = max(points.keys())
                    data["revenue_rub"] = points[last_year] * scale
                    data["revenue_year"] = int(last_year)
            except (json.JSONDecodeError, ValueError):
                pass

        profit_chart = el.cssselect('.finance-chart[data-tab_name="tab_profit"] .acc-diagram')
        if profit_chart:
            points_str = profit_chart[0].get("data-points", "")
            scale_str = profit_chart[0].get("data-scale", "1")
            try:
                import json
                points = json.loads(points_str)
                scale = int(scale_str)
                if points:
                    last_year = max(points.keys())
                    data["profit_rub"] = points[last_year] * scale
            except (json.JSONDecodeError, ValueError):
                pass

        # Fallback: connexion-col (некоторые страницы используют старый формат)
        if not data:
            vals = self._parse_section_values(tree, "accounting")
            for key, val in vals.items():
                if "выручка" in key:
                    data["revenue_rub"] = _parse_number(val)
                elif "прибыль" in key or "убыток" in key:
                    data["profit_rub"] = _parse_number(val)
                elif "числен" in key or "сотрудник" in key:
                    data["employees_count"] = _parse_number(val)

        return data

    def _parse_licenses(self, tree) -> dict[str, Any]:
        vals = self._parse_section_values(tree, "licenses")
        summary = self._parse_section_text(tree, "licenses")

        data: dict[str, Any] = {}
        for key, val in vals.items():
            if "всего" in key or "действ" in key:
                data["licenses_count"] = _parse_number(val)
                break

        if not data.get("licenses_count") and vals:
            first_val = next(iter(vals.values()), "")
            data["licenses_count"] = _parse_number(first_val)

        data["licenses_summary"] = summary
        return data

    def _parse_procurement(self, tree) -> dict[str, Any]:
        data: dict[str, Any] = {}

        # Секция gz: вкладки "Поставщика" / "Заказчика", числа в .connexion-col__num .num
        section = tree.cssselect('div[data-name="gz"]')
        if section and section[0].get("data-empty") != "true":
            el = section[0]
            # Первое число (.num) — количество закупок как поставщик (активная вкладка)
            nums = el.cssselect(".connexion-col__num .num")
            if nums:
                data["purchases_supplier_count"] = _parse_number(_text(nums[:1]))

        # Количество госзакупок как заказчик — в секции history
        hist_vals = self._parse_section_values(tree, "history")
        for key, val in hist_vals.items():
            if "госзакупки" in key:
                data["purchases_customer_count"] = _parse_number(val)

        return data

    def _parse_arbitration(self, tree) -> dict[str, Any]:
        section = tree.cssselect('div[data-name="arbitr"]')
        if not section or section[0].get("data-empty") == "true":
            return {}

        # Число дел — первый .num внутри секции
        nums = section[0].cssselect(".num")
        if nums:
            count = _parse_number(_text(nums[:1]))
            if count:
                return {"arbitration_count": count}
        return {}

    def _parse_fssp(self, tree) -> dict[str, Any]:
        section = tree.cssselect('div[data-name="fssp"]')
        if not section or section[0].get("data-empty") == "true":
            return {}

        # Число производств — в .connexion-col__num .num или текст секции
        vals = self._parse_section_values(tree, "fssp")
        for key, val in vals.items():
            if "производств" in key or "всего" in key:
                count = _parse_number(val)
                if count:
                    return {"fssp_count": count}

        # Fallback: первый .num
        nums = section[0].cssselect(".num")
        if nums:
            count = _parse_number(_text(nums[:1]))
            if count:
                return {"fssp_count": count}
        return {}
