"""
Утилиты для определения субъекта РФ по почтовому индексу из FIAS-адреса.

Пайплайн:
  1. Извлекаем почтовый индекс из FIAS-адреса
  2. Смотрим в локальном кэше postal_region.json (быстро, без сети)
  3. Если промах — спрашиваем DaData и сохраняем в кэш

postal_region.json генерируется скриптом:
    python scripts/build_postal_region.py
и коммитится в репо. Кэш дополняется автоматически в рантайме.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_DATA_FILE = Path(__file__).parent / "data" / "postal_region.json"
_postal_map: dict[str, str] | None = None


def _load() -> dict[str, str]:
    global _postal_map
    if _postal_map is None:
        if _DATA_FILE.exists():
            _postal_map = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
        else:
            _postal_map = {}
    return _postal_map


def _save(postal_code: str, region: str) -> None:
    """Добавляет новый индекс в кэш и сохраняет файл."""
    m = _load()
    m[postal_code] = region
    _DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    _DATA_FILE.write_text(
        json.dumps(m, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def _lookup_dadata(postal_code: str) -> str:
    """Определяет субъект РФ по индексу через DaData suggest address."""
    try:
        from django.conf import settings
        from dadata import Dadata

        token = getattr(settings, "DADATA_TOKEN", "")
        if not token:
            return ""

        with Dadata(token) as client:
            results = client.suggest("address", postal_code, count=1)

        if not results:
            return ""

        data = results[0].get("data", {})
        region = (data.get("region") or "").strip()
        region_type = (data.get("region_type") or "").strip()

        if not region:
            return ""

        # Города-субъекты: Москва, Санкт-Петербург, Севастополь
        if region_type == "г":
            return region

        if region_type:
            return f"{region} {region_type}"

        return region

    except Exception as exc:
        logger.warning("DaData lookup failed for postal %s: %s", postal_code, exc)
        return ""


def get_region_by_postal(postal_code: str) -> str:
    """
    Возвращает канонический субъект РФ по почтовому индексу.

    Сначала смотрит в локальном кэше, при промахе — DaData,
    результат сохраняет в кэш для следующих вызовов.
    """
    cached = _load().get(postal_code)
    if cached is not None:
        return cached

    region = _lookup_dadata(postal_code)
    if region:
        logger.info("DaData: %s → %r (cached)", postal_code, region)
        _save(postal_code, region)

    return region


_REGION_KEYWORDS = ["ОБЛАСТЬ", "КРАЙ", "РЕСПУБЛИКА", "ОКРУГ", "МОСКВА", "САНКТ-ПЕТЕРБУРГ", "СЕВАСТОПОЛЬ"]

# Аббревиатуры в адресных строках → наш канонический суффикс
_TYPE_NORMALIZE = {
    "ОБЛАСТЬ": "обл",
    "КРАЙ": "край",
    "РЕСПУБЛИКА": "Респ",
    "ОКРУГ": "АО",
}


def _parse_region_from_address(address: str) -> str:
    """
    Fallback: извлекает регион из FIAS-адреса по ключевым словам.

    "241004, БРЯНСКАЯ ОБЛАСТЬ, г.о. ГОРОД БРЯНСК, ..." → "Брянская обл"
    "101000, Г.МОСКВА, ..." → "Москва"
    """
    parts = [p.strip() for p in address.split(",")]
    # пропускаем индекс
    if parts and re.match(r"^\d{6}$", parts[0]):
        parts = parts[1:]

    for part in parts:
        upper = part.upper()
        for kw in _REGION_KEYWORDS:
            if kw in upper:
                if kw == "МОСКВА":
                    return "Москва"
                if kw == "САНКТ-ПЕТЕРБУРГ":
                    return "Санкт-Петербург"
                if kw == "СЕВАСТОПОЛЬ":
                    return "Севастополь"
                # "БРЯНСКАЯ ОБЛАСТЬ" → "Брянская обл"
                name = part.strip().title()
                for full, short in _TYPE_NORMALIZE.items():
                    name = re.sub(full.title(), short, name, flags=re.IGNORECASE)
                return name.strip()
    return ""


def extract_region_from_fias(address: str) -> str:
    """
    Определяет субъект РФ из строки FIAS-адреса.

    Шаг 1: почтовый индекс → кэш → DaData
    Шаг 2: если промах — парсим ключевые слова в адресе напрямую

    "241004, БРЯНСКАЯ ОБЛАСТЬ, г.о. ГОРОД БРЯНСК, ..." → "Брянская обл"
    "625000, Г.. ТЮМЕНЬ, ул. Ленина, д. 5"            → "Тюменская обл"
    "127006, Г.МОСКВА, ..."                            → "Москва"
    """
    if not address:
        return ""

    first = address.split(",")[0].strip()
    if re.match(r"^\d{6}$", first):
        region = get_region_by_postal(first)
        if region:
            return region

    # Fallback: парсим адрес напрямую
    return _parse_region_from_address(address)
