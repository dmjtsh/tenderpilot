"""
Утилиты для определения субъекта РФ по почтовому индексу из FIAS-адреса.

Файл postal_region.json генерируется скриптом:
    python scripts/build_postal_region.py
и коммитится в репо.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

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


def extract_region_from_fias(address: str) -> str:
    """
    Определяет субъект РФ из FIAS-адреса по почтовому индексу.

    "625000, Г.. ТЮМЕНЬ, ул. Ленина, д. 5" → "Тюменская обл"
    "127006, Г.МОСКВА, ..."                 → "Москва"

    Возвращает '' если индекс не найден в маппинге.
    """
    if not address:
        return ""
    first = address.split(",")[0].strip()
    if re.match(r"^\d{6}$", first):
        return _load().get(first, "")
    return ""
