import json
import logging
import time

from apps.tenders.services import get_llm_client
from apps.tenders.summary_v2.utils import clean_json_response

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Ты — аналитик контрагентов в госзакупках (44-ФЗ, 223-ФЗ). \
Оцениваешь надёжность заказчика на основе документации и обогащённого профиля.

ЧТО АНАЛИЗИРОВАТЬ:

ПРОФИЛЬ ОРГАНИЗАЦИИ:
- Полное название, ИНН, регион
- Тип: ФГБУ, ГУП, МУП, АО, ООО, ИП, другое
- Отрасль / сфера деятельности
- Дата основания

ФИНАНСЫ (из профиля обогащения, если есть):
- Выручка (рубли, год)
- Прибыль
- Количество сотрудников
- Динамика: растёт / стабильна / падает

ЗАКУПОЧНАЯ ПРАКТИКА:
- Количество закупок в нашей базе
- Общий объём закупок в рублях
- Средний контракт
- Типичные категории закупок

ИНДИКАТОРЫ РИСКА:
- Арбитражные дела (количество)
- Исполнительные производства ФССП
- Лицензии (количество, какие)
- Красные флаги: банкротство, ликвидация, массовый адрес, дисквалификация руководителя

ЗАМЕТКИ:
- ОКВЭД заказчика не совпадает с предметом тендера — подозрительно или нормально?
- Первая крупная закупка — повышенный риск?
- Госструктура — стабильный, но может быть бюрократия

НАДЁЖНОСТЬ:
- high: крупная госструктура / стабильная компания / хорошая история
- medium: средний бизнес / первая закупка / мало данных
- low: арбитражи / ФССП / убыточность / ликвидация
- unknown: нет данных для оценки

ПРИНЦИПЫ:
1. Используй ВСЕ доступные данные: и из документации, и из профиля обогащения
2. Числа ТОЧНО как в данных
3. Не придумывай данные — если профиль обогащения пуст, финансы = null
4. red_flags — только подтверждённые фактами

Возвращай ТОЛЬКО валидный JSON.

{
  "name": string,
  "inn": string | null,
  "region": string | null,
  "org_type": string | null,
  "industry": string | null,
  "founded_date": string | null,
  "financials": {
    "revenue_rub": number | null,
    "profit_rub": number | null,
    "employees_count": number | null,
    "revenue_year": number | null
  },
  "procurement_history": {
    "total_purchases": number | null,
    "total_amount_rub": number | null,
    "avg_contract_rub": number | null
  },
  "risk_indicators": {
    "arbitration_count": number | null,
    "fssp_count": number | null,
    "licenses_count": number | null,
    "red_flags": [string]
  },
  "notes": [string],
  "reliability": "high" | "medium" | "low" | "unknown"
}"""

FALLBACK_MODEL = "gpt-4o-mini"

_RISK_LABELS = {
    "has_arbitration": "арбитражные дела",
    "has_fssp": "исполнительные производства ФССП",
    "is_bankrupt": "процедура банкротства",
    "is_liquidating": "ликвидация",
    "is_liquidated": "ликвидирована",
    "is_mass_address": "массовый адрес регистрации",
    "is_disqualified": "дисквалификация руководителя",
    "has_tax_debt": "налоговая задолженность",
}


def _format_risk_indicators(indicators: dict) -> str | None:
    if not indicators:
        return None
    active = []
    for key, value in indicators.items():
        if not (value is True or (isinstance(value, (int, float)) and value > 0)):
            continue
        label = _RISK_LABELS.get(key)
        if label:
            active.append(label)
    return ", ".join(active) if active else None


def _build_customer_section(tender) -> str:
    from apps.tenders.summary_v2.context import get_customer_profile

    lines = ["ДАННЫЕ ЗАКАЗЧИКА:"]

    customer = tender.customer
    if customer:
        lines.append(f"Название: {customer.name or 'не указано'}")
        lines.append(f"ИНН: {customer.inn or 'не указан'}")
        lines.append(f"Регион: {customer.region or 'не указан'}")
    else:
        lines.append("Заказчик: не указан")

    profile = get_customer_profile(tender)
    if profile:
        lines.append("")
        lines.append("ПРОФИЛЬ ОБОГАЩЕНИЯ (RusProfile/DaData):")
        if profile.full_name:
            lines.append(f"Полное название: {profile.full_name}")
        if profile.okved_main:
            lines.append(f"Основной ОКВЭД: {profile.okved_main}")
        if profile.status:
            lines.append(f"Статус: {profile.status}")
        if profile.director_name:
            lines.append(f"Руководитель: {profile.director_name}")
        if profile.founded_date:
            lines.append(f"Дата основания: {profile.founded_date}")
        if profile.revenue_rub is not None:
            lines.append(f"Выручка: {profile.revenue_rub:,.0f} ₽ ({profile.revenue_year or '?'} г.)")
        if profile.profit_rub is not None:
            lines.append(f"Прибыль: {profile.profit_rub:,.0f} ₽")
        if profile.employees_count:
            lines.append(f"Сотрудников: {profile.employees_count}")
        if profile.licenses_count:
            lines.append(f"Лицензий: {profile.licenses_count}")
            if profile.licenses_summary:
                lines.append(f"Лицензии: {profile.licenses_summary[:500]}")
        if profile.purchases_customer_count:
            lines.append(f"Закупок как заказчик: {profile.purchases_customer_count}")
        if profile.purchases_customer_amount:
            lines.append(f"Сумма закупок: {profile.purchases_customer_amount:,.0f} ₽")
        if profile.purchases_supplier_count:
            lines.append(f"Закупок как поставщик: {profile.purchases_supplier_count}")
        if profile.arbitration_count:
            lines.append(f"Арбитражных дел: {profile.arbitration_count}")
        if profile.fssp_count:
            lines.append(f"Исполнительных производств ФССП: {profile.fssp_count}")
        risk_summary = _format_risk_indicators(profile.risk_indicators)
        if risk_summary:
            lines.append(f"Красные флаги: {risk_summary}")
    else:
        lines.append("")
        lines.append("ПРОФИЛЬ ОБОГАЩЕНИЯ: не удалось получить")

    return "\n".join(lines)


def analyze_customer(
    tender,
    doc_context: str,
    model: str = "deepseek-chat",
) -> dict:
    nmck_str = f"{tender.nmck:,.2f}" if tender.nmck else "не указана"

    customer_section = _build_customer_section(tender)

    user_prompt = (
        f"Тендер: {tender.title}\n"
        f"НМЦ: {nmck_str} ₽\n"
        f"Закон: {tender.law_type}\n\n"
        f"{customer_section}\n\n"
        f"ДОКУМЕНТАЦИЯ (фрагменты):\n\n{doc_context}"
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    client = get_llm_client(model)
    start_ns = time.monotonic_ns()

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=2800,
            temperature=0.2,
        )
    except Exception as e:
        logger.warning("Primary model %s failed: %s, falling back to %s", model, e, FALLBACK_MODEL)
        from apps.tenders.services import deepseek_circuit
        deepseek_circuit.record_failure()
        client = get_llm_client(FALLBACK_MODEL)
        response = client.chat.completions.create(
            model=FALLBACK_MODEL,
            messages=messages,
            max_tokens=2800,
            temperature=0.2,
        )
        model = FALLBACK_MODEL

    duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000

    raw = response.choices[0].message.content.strip()
    cleaned = clean_json_response(raw)
    result = json.loads(cleaned)

    usage = response.usage
    input_tokens = usage.prompt_tokens if usage else 0
    output_tokens = usage.completion_tokens if usage else 0
    actual_model = getattr(response, "model", "") or model

    return {
        "result": result,
        "metrics": {
            "model": model,
            "actual_model": actual_model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "duration_ms": duration_ms,
        },
    }
