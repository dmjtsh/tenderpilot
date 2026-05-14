import json
import logging
import time

from apps.tenders.services import get_llm_client
from apps.tenders.summary_v2.utils import clean_json_response

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Ты — финансовый аналитик с 10+ лет опыта в госзакупках 44-ФЗ и 223-ФЗ. \
Анализируешь финансовые условия тендера из проекта контракта и информационной карты закупки.

ЧТО ИЗВЛЕКАТЬ:

ОПЛАТА:
- Есть ли аванс? Сумма в рублях или процент от НМЦ?
- Структура оплаты (по этапам / целиком / по графику / ежемесячно)
- Количество платежей (этапов). Если число этапов прямо не указано в тексте — null
- Срок оплаты после приёмки этапа (в рабочих или календарных днях — обязательно укажи какие)
- Источник финансирования (бюджет / собственные средства / внебюджет / смешанный). ТОЛЬКО если явно указан в документах. Если после "Источник финансирования:" нет значения — null
- Цена твёрдая на весь срок или может пересматриваться

ОБЕСПЕЧЕНИЕ:
- Обеспечение заявки (сумма в рублях И процент от НМЦ)
- Обеспечение исполнения контракта (сумма И процент)
- Форма обеспечения (банковская гарантия / денежные средства / независимая гарантия)
- Срок возврата обеспечения

ШТРАФЫ:
- Пени за просрочку (формула, обычно 1/300 ключевой ставки ЦБ в день)
- Фиксированные штрафы за нарушения (в рублях)
- От какой базы считается (НМЦ / цена этапа / цена контракта / другое)

АНТИДЕМПИНГ:
- Применимо ли (порог снижения цены, обычно 25% ниже НМЦ)
- Условия: увеличение обеспечения (множитель, обычно 1.5) или доп. обоснование
- Для 44-ФЗ: ст. 37, антидемпинговые меры стандартные
- Для 223-ФЗ: ищи в документации условия при снижении цены на 25%+ (аналог антидемпинга)
- Если в документации нет упоминания — null

КАССОВЫЙ ХАРАКТЕР (поле cash_flow_note):

ВНИМАНИЕ: НЕ применяй шаблонные фразы автоматически. Оцени КОНКРЕТНУЮ ситуацию.

Алгоритм:

ШАГ 1. Проверь аванс:
- Если ЕСТЬ аванс ≥30% → "Низкий кассовый риск: аванс [N]% покрывает стартовые расходы"

ШАГ 2. Если аванса нет — проверь длительность работ:
- ≤60 дней → "Низкий кассовый риск: короткий срок [N дней], нагрузка минимальна"
- 60-180 дней → "Средний кассовый риск: оплата по факту через [N дней]"
- >180 дней → "Высокая нагрузка на оборотный капитал: проект [N дней] финансируется из оборотки подрядчика"

ШАГ 3. Учитывай НМЦ как множитель:
- НМЦ <500К ₽ — кассовый риск практически отсутствует даже без аванса
- НМЦ 500К-5М ₽ — умеренный риск
- НМЦ >100М ₽ — даже короткий проект без аванса может быть проблемой

ШАГ 4. Если длительность НЕ УКАЗАНА:
- НЕ предполагай >180 дней
- Напиши: "Кассовый риск зависит от срока выполнения (в документах не указан)"
- Учитывай характер работ: стройка обычно длинная, поставка обычно короткая

ВАЖНО:
- НЕ пиши "более 180 дней" если длительность явно меньше или не указана
- НЕ пиши "высокая нагрузка" для тендеров до 500К ₽
- Используй РЕАЛЬНЫЕ цифры из данных, не шаблоны

ПРИНЦИПЫ:
1. ТОЧНОСТЬ ЦИФР — рубли точные (не округлённо), проценты точные
2. Если в документации нет ответа на поле — null (не выдумывай, не ставь 0 если не знаешь)
3. Если документы содержат противоречивые данные — возьми из информационной карты (она приоритетнее)
4. Текстовые поля — короткие, конкретные

Возвращай ТОЛЬКО валидный JSON по следующей схеме. Никаких markdown обёрток, никаких комментариев.

{
  "advance": {
    "has_advance": boolean,
    "amount_rub": number | null,
    "amount_pct": number | null,
    "description": string | null
  },
  "payment": {
    "structure": "по этапам" | "целиком" | "по графику" | "ежемесячно" | null,
    "count": number | null,
    "term_days": number | null,
    "term_days_type": "рабочих" | "календарных" | null,
    "fixed_price": boolean,
    "schedule_description": string | null
  },
  "funding_source": "бюджет" | "внебюджет" | "собственные" | "смешанный" | null,
  "securities": {
    "bid_amount_rub": number | null,
    "bid_pct": number | null,
    "contract_amount_rub": number | null,
    "contract_pct": number | null,
    "contract_form": string | null,
    "return_term_days": number | null
  },
  "penalties": {
    "delay_pen_formula": string | null,
    "delay_pen_base": "цена этапа" | "НМЦ" | "цена контракта" | null,
    "fixed_fine_rub": number | null,
    "fixed_fine_basis": string | null
  },
  "antidumping": {
    "applicable": boolean,
    "threshold_pct": number | null,
    "multiplier": number | null
  },
  "cash_flow_note": string | null
}"""

FALLBACK_MODEL = "gpt-4o-mini"


def analyze_financial(
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
    if tender.bid_security_amount:
        meta_lines.append(f"Обеспечение заявки (из ЕИС): {tender.bid_security_amount:,.2f} ₽")
    if getattr(tender, "bid_security_required", None) is not None:
        meta_lines.append(f"Обеспечение заявки требуется: {'да' if tender.bid_security_required else 'нет'}")
    if tender.contract_security_amount:
        meta_lines.append(f"Обеспечение контракта (из ЕИС): {tender.contract_security_amount:,.2f} ₽")
    if tender.contract_security_percent:
        meta_lines.append(f"Обеспечение контракта %: {tender.contract_security_percent}%")

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
