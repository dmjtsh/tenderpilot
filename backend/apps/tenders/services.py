import json
from typing import Any

from django.conf import settings
from django.utils import timezone

from .models import Customer, Tender

SUMMARY_PROMPT = """Ты эксперт по госзакупкам России. Проанализируй тендер.

Название: {title}
НМЦК: {nmck}
Дней до дедлайна: {days_left}
Регион: {region}
ОКПД: {okpd_names}
Заказчик: {customer_name}
Тип закупки: {law_type}
Обеспечение заявки: {bid_security}
Обеспечение контракта: {contract_security}
{docs_section}
Если предоставлены документы — извлеки из них конкретные требования: лицензии, СРО, опыт, штрафы, сроки выполнения.

Верни ТОЛЬКО JSON без пояснений:
{{
  "essence": "2-3 предложения — суть тендера и что нужно сделать",
  "requirements": ["требование 1", "требование 2"],
  "days_left": {days_left_val},
  "urgency": "low|medium|high|critical",
  "finances": "описание финансовых условий одним абзацем",
  "red_flags": ["флаг 1"],
  "verdict": "go|maybe|pass",
  "verdict_reason": "1 предложение — почему"
}}"""


def generate_tender_summary(tender: Tender) -> dict:
    from openai import OpenAI
    from apps.tenders.okved import okved_to_text
    from apps.documents.services import get_summary_context

    days_left = None
    if tender.deadline_at:
        days_left = (tender.deadline_at.date() - timezone.now().date()).days

    bid_security = (
        "не требуется" if tender.bid_security_required is False
        else f"{tender.bid_security_amount:,.0f} ₽".replace(",", " ") if tender.bid_security_amount
        else "не указано"
    )
    contract_security = (
        f"{tender.contract_security_amount:,.0f} ₽ ({tender.contract_security_percent}%)".replace(",", " ")
        if tender.contract_security_amount and tender.contract_security_percent
        else f"{tender.contract_security_percent}%" if tender.contract_security_percent
        else "не указано"
    )

    docs_context = get_summary_context(tender)
    has_docs = bool(docs_context)
    docs_section = f"Документы тендера:\n{docs_context}" if has_docs else ""

    prompt = SUMMARY_PROMPT.format(
        title=tender.title,
        nmck=f"{tender.nmck:,.0f} ₽".replace(",", " ") if tender.nmck else "не указана",
        days_left=f"{days_left}" if days_left is not None else "не указан",
        region=tender.region or "не указан",
        okpd_names=okved_to_text(tender.okpd_codes or []) or "не указан",
        customer_name=tender.customer.name if tender.customer else "не указан",
        law_type=tender.law_type or "не указан",
        bid_security=bid_security,
        contract_security=contract_security,
        days_left_val=days_left if days_left is not None else "null",
        docs_section=docs_section,
    )

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=800,
        temperature=0.3,
    )
    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    result = json.loads(raw)
    result["has_docs"] = has_docs
    return result


def get_or_create_summary(tender: Tender) -> dict:
    if tender.ai_summary:
        try:
            return json.loads(tender.ai_summary)
        except (json.JSONDecodeError, ValueError):
            pass  # старый формат plain text — перегенерировать

    summary = generate_tender_summary(tender)
    tender.ai_summary = json.dumps(summary, ensure_ascii=False)
    tender.save(update_fields=["ai_summary"])
    return summary


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
