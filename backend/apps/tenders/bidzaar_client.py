"""
HTTP-клиент для Bidzaar (bidzaar.com).

API обнаружен через DevTools:
  GET /api/process/light/procedures/available  — список тендеров (пагинация)
  GET /api/process/light/procedures/base       — детали по UUID (бюджет, ОКПД)

Два уровня данных:
- search_tenders()        → быстрый список карточек (без бюджета)
- fetch_tender_detail()   → обогащение одного тендера по UUID (бюджет, описание)
"""
import logging
import time
from datetime import date, timedelta
from typing import Any

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://bidzaar.com"
LIST_API = BASE_URL + "/api/process/light/procedures/available"
DETAIL_API = BASE_URL + "/api/process/light/procedures/base"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://bidzaar.com/",
    "Origin": "https://bidzaar.com",
}

PAGE_SIZE = 25

# Статусы Bidzaar → наш статус
STATUS_MAP: dict[int, str] = {
    1: "active",
    2: "finished",
    3: "cancelled",
    4: "finished",   # завершён с победителем
}

# Типы процедур Bidzaar → наш procedure_type
PROCEDURE_TYPE_MAP: dict[int, str] = {
    1: "request_proposals",   # Торги заданного объёма / Прием предложений
    2: "request_quotations",  # Запрос котировок
    3: "auction",             # Аукцион
    4: "contest",             # Конкурс
    5: "single_source",       # Единственный поставщик
}


# ---------------------------------------------------------------------------
# Низкоуровневые утилиты
# ---------------------------------------------------------------------------

def _get(url: str, params: dict, retries: int = 2) -> dict | None:
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            if attempt < retries:
                wait = 3 * (attempt + 1)
                logger.warning("Retry %d for %s in %ds: %s", attempt + 1, url, wait, exc)
                time.sleep(wait)
            else:
                logger.error("Failed to fetch %s: %s", url, exc)
    return None


def _build_filters(days: int, status_active_only: bool = True) -> dict:
    """Собирает параметры фильтрации для LIST_API."""
    since = (date.today() - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00Z")
    params: dict[str, Any] = {
        "sorting.key": "publishDate",
        "sorting.direction": "desc",
        "logic": "and",
    }
    filter_idx = 0
    if status_active_only:
        params[f"filters[{filter_idx}].operator"] = "in"
        params[f"filters[{filter_idx}].field"] = "status"
        params[f"filters[{filter_idx}].value"] = "[1]"   # 1 = активный
        filter_idx += 1
    params[f"filters[{filter_idx}].operator"] = "gte"
    params[f"filters[{filter_idx}].field"] = "publishDate"
    params[f"filters[{filter_idx}].value"] = since
    return params


def _parse_region(item: dict) -> str:
    """Извлекает регион из deliveryAddresses."""
    addresses = item.get("deliveryAddresses") or []
    if not addresses:
        return ""
    addr = addresses[0]
    return addr.get("region") or addr.get("city") or ""


def _map_item(item: dict) -> dict:
    """Маппинг одного элемента списка → формат upsert_tender()."""
    bidzaar_id = item["id"]
    number = item.get("number", "")
    procedure_int = item.get("procedureType", 1)
    status_int = item.get("status", 1)

    return {
        "number": number,
        "title": item.get("name", ""),
        "customer_name": item.get("companyName", ""),
        "customer_inn": "",           # не приходит в списке, можно обогатить отдельно
        "region": _parse_region(item),
        "published_at": item.get("publishDate"),
        "deadline_at": item.get("acceptanceEndDate"),
        "auction_date": item.get("finishDate"),
        "status": STATUS_MAP.get(status_int, "active"),
        "law_type": "b2b",
        "procedure_type": PROCEDURE_TYPE_MAP.get(procedure_int, "other"),
        "trading_platform": "Bidzaar",
        "trading_platform_url": "https://bidzaar.com/",
        "source_url": f"https://bidzaar.com/requests/public/buy/{bidzaar_id}",
        "source": "bidzaar",
        "bidzaar_id": bidzaar_id,     # сохраним в raw_json для обогащения
    }


# ---------------------------------------------------------------------------
# Поиск тендеров (список)
# ---------------------------------------------------------------------------

def search_tenders(
    days: int = 7,
    query: str = "",
    max_pages: int = 20,
    active_only: bool = True,
) -> list[dict]:
    """
    Возвращает список тендеров из Bidzaar.

    Args:
        days:       За сколько дней искать (от сегодня назад).
        query:      Ключевые слова (передаются в поле search).
        max_pages:  Лимит страниц пагинации.
        active_only: Только активные (status=1).

    Returns:
        Список dict в формате upsert_tender().
    """
    results: list[dict] = []
    base_params = _build_filters(days, active_only)
    if query:
        base_params["search"] = query

    for page in range(1, max_pages + 1):
        params = {**base_params, "paging.page": page, "paging.size": PAGE_SIZE}
        data = _get(LIST_API, params)
        if not data:
            break

        items = data.get("items") or []
        if not items:
            break

        for item in items:
            results.append(_map_item(item))

        total = data.get("total") or data.get("totalCount") or 0
        fetched_so_far = page * PAGE_SIZE
        if len(items) < PAGE_SIZE or (total and fetched_so_far >= total):
            break

        time.sleep(0.4)

    return results


# ---------------------------------------------------------------------------
# Детальное обогащение (бюджет, описание, ОКПД)
# ---------------------------------------------------------------------------

def fetch_tender_detail(bidzaar_id: str) -> dict | None:
    """
    Запрашивает детали тендера по UUID через /procedures/base?ids=...
    Возвращает dict с дополнительными полями или None при ошибке.

    Поля которые можно обогатить:
      - nmck (budget / initialPrice)
      - description
      - okpd_codes
      - customer_inn (если вернёт)
    """
    data = _get(DETAIL_API, {"ids": bidzaar_id})
    if not data:
        return None

    # Ответ может быть списком или {"items": [...]}
    items = data if isinstance(data, list) else (data.get("items") or [])
    if not items:
        return None

    item = items[0]

    # Пробуем разные названия поля с бюджетом (уточнить после первого реального ответа)
    nmck = (
        item.get("budget")
        or item.get("initialPrice")
        or item.get("startPrice")
        or item.get("maxPrice")
    )

    okpd_raw = item.get("okpd") or item.get("okpd2") or item.get("okpdCodes") or []
    if isinstance(okpd_raw, list):
        okpd_codes = [
            o.get("code") or o if isinstance(o, str) else str(o)
            for o in okpd_raw
        ]
    else:
        okpd_codes = []

    return {
        "nmck": float(nmck) if nmck else None,
        "description": item.get("description") or item.get("subject") or "",
        "okpd_codes": [c for c in okpd_codes if c],
        "customer_inn": item.get("customerInn") or item.get("inn") or "",
        "raw_detail": item,
    }
