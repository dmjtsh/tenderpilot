import json
import logging
import time

from apps.tenders.services import get_llm_client
from apps.tenders.summary_v2.utils import clean_json_response

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Ты — специалист по управлению проектами в госзакупках (44-ФЗ, 223-ФЗ). \
Анализируешь сроки и этапы тендера из проекта контракта, календарного плана и документации.

ЧТО ИЗВЛЕКАТЬ:

ОБЩИЙ СРОК:
- Длительность выполнения работ (дни, месяцы)
- Тип дней (рабочие / календарные)
- Описание: "с даты подписания" или конкретные даты

ЭТАПЫ:
- Номер, название, длительность каждого этапа
- Конкретные даты начала/окончания если указаны
- Результаты (deliverables) каждого этапа
- Если этапы не указаны или указан только общий срок — stages = []

КЛЮЧЕВЫЕ ДАТЫ:
- Дедлайн подачи заявки
- Дата аукциона/торгов
- Срок подписания контракта после определения победителя (в днях)
- Гарантийный срок (в месяцах)

ОЦЕНКА СРОЧНОСТИ:
- Сколько дней до дедлайна подачи
- Достаточно ли времени на подготовку заявки
- Реалистичен ли срок выполнения для объёма работ

ПРИНЦИПЫ:
1. Даты и сроки — ТОЧНО как в документах
2. Если данных нет — null, не придумывай
3. Если calendar_plan — таблица которая не распарсилась — stages = [], укажи в notes

Возвращай ТОЛЬКО валидный JSON. Никаких markdown обёрток.

{
  "total_duration": {
    "days": number | null,
    "day_type": "календарных" | "рабочих" | null,
    "description": string | null
  },
  "stages": [
    {
      "number": number,
      "name": string,
      "duration_days": number | null,
      "start_date": string | null,
      "end_date": string | null,
      "deliverables": [string]
    }
  ],
  "key_dates": {
    "submission_deadline": string | null,
    "auction_date": string | null,
    "contract_sign_deadline_days": number | null,
    "warranty_months": number | null
  },
  "urgency_note": string | null
}"""

FALLBACK_MODEL = "gpt-4o-mini"


def analyze_timeline(
    tender,
    doc_context: str,
    model: str = "deepseek-chat",
) -> dict:
    nmck_str = f"{tender.nmck:,.2f}" if tender.nmck else "не указана"

    meta_lines = [
        f"Тендер: {tender.title}",
        f"НМЦ: {nmck_str} ₽",
        f"Закон: {tender.law_type}",
    ]
    if tender.deadline_at:
        meta_lines.append(f"Дедлайн подачи заявки: {tender.deadline_at.strftime('%d.%m.%Y %H:%M')}")
    if tender.auction_date:
        meta_lines.append(f"Дата аукциона: {tender.auction_date.strftime('%d.%m.%Y')}")

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
            max_tokens=2800,
            temperature=0.2,
        )
    except Exception as e:
        logger.warning("Primary model %s failed: %s, falling back to %s", model, e, FALLBACK_MODEL)
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
