import json
import logging
import time

from apps.tenders.services import get_llm_client
from apps.tenders.summary_v2.utils import clean_json_response

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Ты — технический эксперт по госзакупкам (44-ФЗ, 223-ФЗ). \
Анализируешь предмет закупки, объём и технические требования из ТЗ и документации.

ЧТО ИЗВЛЕКАТЬ:

ПРЕДМЕТ:
- Краткое описание сути работ (1-2 предложения)
- Тип тендера: строительство / поставка / услуги / проектирование / IT / другое
- Объект: что именно создаётся/поставляется/ремонтируется

ОБЪЁМ РАБОТ:
- Основные виды работ/услуг (список)
- Результаты (deliverables): что передаётся заказчику
- Количественные метрики: площадь, длина, штуки, единицы и т.д.

МЕСТО ВЫПОЛНЕНИЯ:
- Адрес или регион
- Если несколько объектов — перечислить

ТЕХНИЧЕСКИЕ ТРЕБОВАНИЯ:
- Стандарты (ГОСТы, СНиПы, СП)
- Требования к материалам
- Требования к оборудованию
- Требования к ПО (для IT)

ПРИЁМКА:
- Процедура приёмки (кто, как, сроки рассмотрения)
- Гарантийные обязательства
- Техническая поддержка после сдачи

СУБПОДРЯД:
- Разрешён ли
- Максимальный процент субподряда
- Ограничения

ПРИНЦИПЫ:
1. Конкретика: метры, штуки, названия стандартов — точно как в документах
2. Не придумывай требования которых нет
3. null если данных нет
4. Для крупных ТЗ — выделяй ключевые пункты, не копируй весь текст

Возвращай ТОЛЬКО валидный JSON.

{
  "subject": string,
  "tender_type": "строительство" | "поставка" | "услуги" | "проектирование" | "IT" | "другое",
  "scope": {
    "main_activities": [string],
    "deliverables": [string],
    "volume_metrics": [
      {"metric": string, "value": string}
    ]
  },
  "location": {
    "address": string | null,
    "region": string | null
  },
  "technical_specs": {
    "standards": [string],
    "materials": [string],
    "equipment": [string],
    "software": [string]
  },
  "acceptance": {
    "procedure": string | null,
    "review_days": number | null,
    "warranty_months": number | null,
    "support_after_delivery": string | null
  },
  "subcontracting": {
    "allowed": boolean | null,
    "max_pct": number | null,
    "restrictions": string | null
  }
}"""

FALLBACK_MODEL = "gpt-4o-mini"


def analyze_work(
    tender,
    doc_context: str,
    model: str = "deepseek-chat",
) -> dict:
    nmck_str = f"{tender.nmck:,.2f}" if tender.nmck else "не указана"

    meta_lines = [
        f"Тендер: {tender.title}",
        f"НМЦ: {nmck_str} ₽",
        f"Закон: {tender.law_type}",
        f"Регион: {tender.region or 'не указан'}",
    ]

    user_prompt = "\n".join(meta_lines) + f"\n\nДОКУМЕНТАЦИЯ:\n\n{doc_context}"

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
            max_tokens=3500,
            temperature=0.2,
        )
    except Exception as e:
        logger.warning("Primary model %s failed: %s, falling back to %s", model, e, FALLBACK_MODEL)
        client = get_llm_client(FALLBACK_MODEL)
        response = client.chat.completions.create(
            model=FALLBACK_MODEL,
            messages=messages,
            max_tokens=3500,
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
