"""
Утилиты для нормализации регионов тендеров.

Пайплайн для 223-ФЗ (FIAS-адрес):
  "625000, Г.. ТЮМЕНЬ, ул. Ленина 5"
    → extract postal_code "625000"
    → lookup в postal_region.json
    → "Тюменская обл"

Файл postal_region.json генерируется скриптом:
    python scripts/build_postal_region.py
и коммитится в репо.
"""
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


def get_region_by_postal(postal_code: str) -> str:
    """Возвращает канонический субъект по почтовому индексу или '' если не найден."""
    return _load().get(postal_code, "")


def extract_region_from_fias(address: str) -> str:
    """
    Извлекает субъект РФ из строки FIAS-адреса.

    Формат: "625000, Г.. ТЮМЕНЬ, ул. Ленина, д. 5"
    → ищет 6-значный индекс в начале → lookup → "Тюменская обл"

    Возвращает '' если индекс не найден или не в маппинге.
    """
    if not address:
        return ""
    parts = [p.strip() for p in address.split(",")]
    if not parts:
        return ""
    first = parts[0]
    if re.match(r"^\d{6}$", first):
        return get_region_by_postal(first)
    return ""
