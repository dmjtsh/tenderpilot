import json
import re
from typing import Any

from django.conf import settings
from django.utils import timezone

from .models import Customer, Tender


_PROCEDURE_URL_MAP = [
    (r"/notice/ea(?:20|44)/", Tender.ProcedureType.AUCTION),
    (r"/notice/ok(?:20|44)/", Tender.ProcedureType.CONTEST),
    (r"/notice/zk(?:20|44)/", Tender.ProcedureType.REQUEST_QUOTATIONS),
    (r"/notice/(?:ezt20|zp44)/", Tender.ProcedureType.REQUEST_PROPOSALS),
]


def detect_procedure_type(source_url: str) -> str:
    for pattern, proc_type in _PROCEDURE_URL_MAP:
        if re.search(pattern, source_url):
            return proc_type
    return Tender.ProcedureType.OTHER

SUMMARY_PROMPT = """Ты эксперт по госзакупкам России.
Определи тип тендера по названию и ОКВЭД:
строительство / поставка / услуги / проектирование / IT / другое.
Адаптируй анализ под тип.

ДАННЫЕ ТЕНДЕРА:
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

Проверь каждый пункт и извлеки конкретные значения:

□ Требования к участнику: допуски, лицензии, аттестации, квалификация, опыт
□ Сроки: срок выполнения (конкретная дата или период), этапы
□ Гарантия: срок (конкретно: "5 лет", "24 месяца"), условия
□ Финансы: обеспечение заявки, обеспечение контракта (% и сумма)
□ Ответственность: штрафы и пени (размер, условия)
□ Ограничения: запреты, особые условия заказчика
□ Приёмка: особые условия, дополнительные согласования

Верни JSON без markdown:
{{
  "essence": "одно предложение что конкретно нужно сделать",
  "requirements": ["конкретное требование с цифрами если есть"],
  "deadlines": {{
    "execution_period": "конкретный срок или null",
    "urgency": "нормально | сжато | очень сжато"
  }},
  "financials": {{
    "bid_security_rub": 0,
    "contract_security_pct": 0
  }},
  "red_flags": ["конкретный риск с цифрами"],
  "verdict": "участвовать | изучить | пропустить",
  "verdict_reason": "одно предложение",
  "tender_type": "строительство | поставка | услуги | проектирование | IT | другое"
}}

ГЛАВНОЕ ПРАВИЛО: все числовые значения (сроки, проценты, суммы)
копируй ТОЧНО как написано в документах.
Не округляй, не конвертируй, не интерпретируй.
Если написано "не менее 3 лет" — пиши "не менее 3 лет".
Если написано "1/300 ключевой ставки" — пиши "1/300 ключевой ставки".

Правила:
- извлекай ВСЕ конкретные требования из документов
- requirements: допуски, лицензии, сертификаты, квалификация, гарантийные сроки, условия приёмки
- red_flags: штрафы/пени с размером, запрет субподряда, сжатые сроки, необычные ограничения
- если факт подходит и туда и туда — дублируй в оба списка
- обеспечение контракта НЕ является красным флагом если <= 15%
- обеспечение контракта > 15% → добавь в red_flags с точным процентом
- НЕ придумывай то чего нет в документах
- НЕ пиши общие фразы типа "соответствие нормативам" — пиши конкретно"""

VERDICT_MAP: dict[str, str] = {
    "участвовать": "go",
    "изучить": "maybe",
    "пропустить": "pass",
}

URGENCY_MAP: dict[str, str] = {
    "нормально": "low",
    "сжато": "medium",
    "очень сжато": "high",
}


def _format_finances(financials: dict) -> str:
    parts: list[str] = []
    bid = financials.get("bid_security_rub")
    if bid:
        parts.append(f"Обеспечение заявки: {bid:,.0f} ₽".replace(",", " "))
    pct = financials.get("contract_security_pct")
    if pct:
        parts.append(f"Обеспечение контракта: {pct}%")
    return ". ".join(parts) if parts else ""


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

    ctx = get_summary_context(tender)
    source = ctx["source"]
    has_docs = source in ("rag", "text", "full_tz")

    if source == "full_tz":
        docs_section = f"ДОКУМЕНТАЦИЯ (техзадание целиком + релевантные разделы других документов):\n{ctx['context']}"
    elif source == "rag":
        docs_section = f"ДОКУМЕНТАЦИЯ (релевантные разделы):\n{ctx['context']}"
    elif source == "text":
        docs_section = f"ДОКУМЕНТАЦИЯ (полный текст):\n{ctx['context']}"
    else:
        docs_section = "ВНИМАНИЕ: документы не загружены, анализ только по метаданным."

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

    gpt_result = json.loads(raw)

    deadlines = gpt_result.get("deadlines") or {}
    financials = gpt_result.get("financials") or {}
    verdict_raw = gpt_result.get("verdict", "изучить")
    urgency_raw = deadlines.get("urgency", "нормально")

    red_flags = gpt_result.get("red_flags", [])
    contract_pct = tender.contract_security_percent
    if contract_pct is not None:
        has_security_flag = any("обеспечен" in f.lower() for f in red_flags)
        if contract_pct > 15 and not has_security_flag:
            red_flags.append(f"Обеспечение контракта {contract_pct}% (выше 15%)")
        elif contract_pct <= 15:
            red_flags = [f for f in red_flags if "обеспечен" not in f.lower()]

    return {
        "essence": gpt_result.get("essence", ""),
        "requirements": gpt_result.get("requirements", []),
        "days_left": days_left,
        "urgency": URGENCY_MAP.get(urgency_raw, urgency_raw),
        "execution_period": deadlines.get("execution_period"),
        "finances": _format_finances(financials),
        "financials": financials,
        "red_flags": red_flags,
        "verdict": VERDICT_MAP.get(verdict_raw, verdict_raw),
        "verdict_reason": gpt_result.get("verdict_reason", ""),
        "has_docs": has_docs,
        "tender_type": gpt_result.get("tender_type", "другое"),
    }


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

    source_url = data.get("source_url", "")
    procedure_type = data.get("procedure_type") or detect_procedure_type(source_url)

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
            "procedure_type": procedure_type,
            "trading_platform": data.get("trading_platform", ""),
            "trading_platform_url": data.get("trading_platform_url", ""),
            "bid_security_amount": data.get("bid_security_amount"),
            "bid_security_required": data.get("bid_security_required"),
            "contract_security_amount": data.get("contract_security_amount"),
            "contract_security_percent": data.get("contract_security_percent"),
            "source_url": source_url,
            "raw_json": data,
        },
    )
    return tender
