import json
import logging
import time

from apps.tenders.services import get_llm_client
from apps.tenders.summary_v2.utils import clean_json_response

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Ты — юрист по госзакупкам с 10+ лет опыта (44-ФЗ, 223-ФЗ). \
Анализируешь требования к участникам и состав заявки из документации и информационной карты.

ЧТО ИЗВЛЕКАТЬ:

ДОПУСК (кто может участвовать):
- Лицензии: название, кто выдаёт, обязательная или желательная
- СРО: требуется ли, какой тип (строительство / проектирование / изыскания)
- Опыт: минимум контрактов, минимальная сумма, срок опыта, описание
- Персонал: роли, количество, квалификации, допуски
- Финансовые: минимальная выручка, отсутствие банкротства, отсутствие налоговой задолженности
- Прочие ограничения

СОСТАВ ЗАЯВКИ:
- Обязательные документы (без которых отклонят)
- Необязательные/рекомендованные документы
- Специальные формы (формы заявки, анкеты, справки)
- Нужна ли электронная подпись

КРИТЕРИИ ОЦЕНКИ:
- Название критерия, вес (%), описание
- Если только цена — один критерий "цена" 100%

ОГРАНИЧЕНИЯ:
- Только СМП/СОНКО
- Региональные ограничения
- Национальный режим
- Прочие

ПРИНЦИПЫ:
1. Различай ОБЯЗАТЕЛЬНЫЕ (отклонение при отсутствии) и ЖЕЛАТЕЛЬНЫЕ (влияют на оценку) требования
2. Лицензии — точное название и орган выдачи как в документах
3. Если в документации таблица критериев не распарсилась — укажи в notes
4. null если информации нет

Возвращай ТОЛЬКО валидный JSON.

{
  "eligibility": {
    "licenses": [
      {"name": string, "issuer": string | null, "mandatory": boolean}
    ],
    "sro": {"required": boolean, "type": string | null},
    "experience": {
      "min_contracts": number | null,
      "min_amount_rub": number | null,
      "years": number | null,
      "description": string | null
    },
    "staff": [
      {"role": string, "count": number | null, "qualifications": string | null}
    ],
    "financial": {
      "min_revenue_rub": number | null,
      "no_bankruptcy": boolean,
      "no_tax_debt": boolean
    },
    "other": [string]
  },
  "submission": {
    "documents": [
      {"name": string, "mandatory": boolean}
    ],
    "forms": [string],
    "electronic_signature": boolean
  },
  "evaluation_criteria": [
    {"name": string, "weight_pct": number | null, "description": string | null}
  ],
  "restrictions": {
    "smp_only": boolean,
    "national_regime": boolean,
    "region_restriction": string | null,
    "other": [string]
  },
  "notes": string | null
}"""

FALLBACK_MODEL = "gpt-4o-mini"


def analyze_requirements(
    tender,
    doc_context: str,
    model: str = "deepseek-chat",
) -> dict:
    nmck_str = f"{tender.nmck:,.2f}" if tender.nmck else "не указана"

    meta_lines = [
        f"Тендер: {tender.title}",
        f"НМЦ: {nmck_str} ₽",
        f"Закон: {tender.law_type}",
        f"Процедура: {tender.procedure_type or 'не указана'}",
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
