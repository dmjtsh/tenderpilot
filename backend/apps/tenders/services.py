from typing import Any
from .models import Customer, Tender


def upsert_tender(data: dict[str, Any]) -> Tender:
    """Создать или обновить тендер из сырых данных парсера."""
    customer = None
    inn = data.get("customer_inn", "").strip()
    name = data.get("customer_name", "").strip()
    if inn:
        customer, _ = Customer.objects.get_or_create(
            inn=inn,
            defaults={
                "name": name,
                "full_name": data.get("customer_full_name", ""),
                "region": data.get("customer_region", data.get("region", "")),
            },
        )
    elif name:
        # Без ИНН — ищем по имени, создаём с пустым ИНН (временно, до обогащения)
        customer, _ = Customer.objects.get_or_create(
            inn="",
            name=name,
            defaults={"region": data.get("customer_region", "")},
        )

    tender, created = Tender.objects.update_or_create(
        number=data["number"],
        defaults={
            "title": data.get("title", ""),
            "nmck": data.get("nmck"),
            "customer": customer,
            "region": data.get("region", ""),
            "okpd_codes": data.get("okpd_codes", []),
            "published_at": data.get("published_at"),
            "deadline_at": data.get("deadline_at"),
            "auction_date": data.get("auction_date"),
            "status": data.get("status", Tender.Status.ACTIVE),
            "law_type": data.get("law_type", ""),
            "trading_platform": data.get("trading_platform", ""),
            "trading_platform_url": data.get("trading_platform_url", ""),
            "bid_security_amount": data.get("bid_security_amount"),
            "bid_security_required": data.get("bid_security_required"),
            "contract_security_amount": data.get("contract_security_amount"),
            "contract_security_percent": data.get("contract_security_percent"),
            "source_url": data.get("source_url", ""),
            "raw_json": data,
        },
    )
    return tender
