import logging
from typing import TypedDict

from django.conf import settings

logger = logging.getLogger(__name__)


class CompanyInfo(TypedDict):
    name: str
    full_name: str
    inn: str
    region: str
    okved_main: str        # основной ОКВЭД
    okved_list: list[str]  # все ОКВЭД коды


def find_inn_by_name(name: str) -> str | None:
    token = settings.DADATA_TOKEN
    if not token or not name:
        return None
    try:
        from dadata import Dadata
        with Dadata(token) as client:
            results = client.suggest("party", name, count=1)
    except Exception as exc:
        logger.error("DaData suggest error for %r: %s", name, exc)
        return None
    if not results:
        return None
    inn = results[0].get("data", {}).get("inn", "")
    return inn if inn else None


def enrich_company_by_inn(inn: str) -> CompanyInfo | None:
    token = settings.DADATA_TOKEN
    if not token:
        logger.warning("DADATA_TOKEN not set")
        return None

    try:
        from dadata import Dadata
        with Dadata(token) as client:
            results = client.find_by_id("party", inn, count=1)
    except Exception as exc:
        logger.error("DaData API error for INN %s: %s", inn, exc)
        return None

    if not results:
        return None

    data = results[0].get("data", {})

    name = results[0].get("value", "") or ""
    full_name = (data.get("name") or {}).get("full_with_opf", "") or ""
    region = (data.get("address") or {}).get("data", {}).get("region_with_type", "") or ""

    okved_main = (data.get("okved") or "").strip()

    okved_list_raw = data.get("okveds") or []
    okved_list: list[str] = []
    for item in okved_list_raw:
        code = (item.get("code") or "").strip()
        if code:
            okved_list.append(code)

    # Основной ОКВЭД всегда первым
    if okved_main and okved_main not in okved_list:
        okved_list.insert(0, okved_main)

    return CompanyInfo(
        name=name,
        full_name=full_name,
        inn=inn,
        region=region,
        okved_main=okved_main,
        okved_list=okved_list,
    )
