import json
import logging
import time

from apps.tenders.services import get_llm_client
from apps.tenders.summary_v2.utils import clean_json_response

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Ты — риск-менеджер с опытом в госзакупках (44-ФЗ, 223-ФЗ). \
Анализируешь риски участия в тендере из проекта контракта, ТЗ и документации.

ЧТО ОЦЕНИВАТЬ:

СЕРТИФИКАЦИОННЫЕ РИСКИ:
- Какие лицензии/допуски нужны и есть ли они у типичного участника
- СРО, аккредитации, разрешения
- severity: high если лицензия редкая или долго получать

ФИНАНСОВЫЕ РИСКИ:
- Обеспечение заявки/контракта существенно выше типичного (заявка >2%, контракт >10%)
- Отсутствие аванса при длительных работах (оцени исходя из масштаба и НМЦ)
- Штрафные санкции непропорционально высокие
- Необходимость крупных предварительных вложений
- Риск неоплаты (задержка оплаты, бюджетные ограничения)

ТЕХНИЧЕСКИЕ РИСКИ:
- Объём работ не соответствует срокам
- Требования к оборудованию/материалам труднодоступным
- Сложность интеграции с существующими системами
- Требования к импортозамещению

ЮРИДИЧЕСКИЕ РИСКИ:
- Односторонний отказ от контракта
- Передача исключительных прав без доп. компенсации
- Кабальные условия (только в пользу заказчика)
- Неопределённые формулировки обязательств

ВРЕМЕННЫЕ РИСКИ:
- Мало времени до дедлайна подачи
- Нереалистичные сроки выполнения
- Жёсткие промежуточные дедлайны

НЕОБЫЧНЫЕ УСЛОВИЯ:
- Всё что отличается от стандартной практики
- Специфические требования заказчика

ИТОГОВАЯ ОЦЕНКА:
- overall_risk: high / medium / low
- risk_summary: 1-2 предложения — главное на что обратить внимание

ПРИНЦИПЫ:
1. Оценивай с точки зрения ПОДРЯДЧИКА/ПОСТАВЩИКА, а не заказчика
2. Стандартные условия (обеспечение ≤5%, пени 1/300 ставки) — НЕ РИСКИ
3. severity = high только для блокирующих рисков (нет лицензии = не подать заявку)
4. Конкретика: "обеспечение [N]% от НМЦ = [сумма с расчётом] ₽" лучше чем "высокое обеспечение" (используй реальные проценты и суммы из документов этого тендера)
5. КАЛИБРОВКА SEVERITY ПО АБСОЛЮТНОЙ СУММЕ:
   Прежде чем поставить severity=high финансовому риску — оцени АБСОЛЮТНУЮ сумму, не только процент.
   Шкала для обеспечения и крупных выплат:
   - <50К ₽ → почти всегда low (пустяк для любой компании)
   - 50К-500К ₽ → low/medium (большинство справится)
   - 500К-5М ₽ → medium (заметно для МСП, норма для крупных)
   - 5М-50М ₽ → high для МСП, medium для крупных
   - >50М ₽ → high практически для всех
   Шкала для штрафов:
   - 1К-10К ₽ → low, формальность
   - 10К-100К ₽ → medium
   - >100К ₽ → high
   ЗАПРЕЩЕНО:
   - Писать "блокирует оборотные средства" для сумм <500К ₽
   - Ставить high financial risk для обеспечения <50К ₽
   - Ставить overall_risk=high только из-за процентов без учёта абсолютных сумм
6. КАЛИБРОВКА OVERALL_RISK:
   overall_risk=high ТОЛЬКО если есть хотя бы один:
   - Действительно блокирующий риск (нет лицензии, пропущен дедлайн)
   - Сумма обеспечения >5М ₽ при отсутствии аванса на длинном проекте
   - Кабальные условия (штрафы >10% НМЦ, односторонний отказ без оснований)
   - Сложная техническая задача с явно нереалистичными сроками
   overall_risk=medium для:
   - Стандартных условий с одним заметным риском
   - Средних проектов где есть нюансы но без блокеров
   overall_risk=low для:
   - Простых поставок с типовыми условиями
   - Маленьких тендеров (<1М ₽) где даже формальные требования не создают серьёзных проблем

Возвращай ТОЛЬКО валидный JSON.

{
  "certification_risks": [
    {"risk": string, "severity": "high" | "medium" | "low"}
  ],
  "financial_risks": [
    {"risk": string, "severity": "high" | "medium" | "low"}
  ],
  "technical_risks": [
    {"risk": string, "severity": "high" | "medium" | "low"}
  ],
  "legal_risks": [
    {"risk": string, "severity": "high" | "medium" | "low"}
  ],
  "timeline_risks": [
    {"risk": string, "severity": "high" | "medium" | "low"}
  ],
  "unusual_conditions": [string],
  "overall_risk": "high" | "medium" | "low",
  "risk_summary": string
}"""

FALLBACK_MODEL = "gpt-4o-mini"


def _format_prior_analysis(prior: dict) -> str:
    parts = []
    for step_name, step_result in prior.items():
        if step_result is None:
            continue
        parts.append(f"--- {step_name.upper()} ---")
        parts.append(json.dumps(step_result, ensure_ascii=False, indent=1, default=str))
    if not parts:
        return ""
    return "РЕЗУЛЬТАТЫ ПРЕДВАРИТЕЛЬНОГО АНАЛИЗА:\n\n" + "\n\n".join(parts)


def analyze_risks(
    tender,
    doc_context: str,
    model: str = "deepseek-chat",
    prior_analysis: dict | None = None,
) -> dict:
    from datetime import date

    nmck_str = f"{tender.nmck:,.2f}" if tender.nmck else "не указана"

    meta_lines = [
        f"Тендер: {tender.title}",
        f"НМЦ: {nmck_str} ₽",
        f"Закон: {tender.law_type}",
    ]
    if tender.deadline_at:
        days_left = (tender.deadline_at.date() - date.today()).days
        meta_lines.append(f"Дедлайн подачи: {tender.deadline_at.strftime('%d.%m.%Y')} (дней до дедлайна: {days_left})")
    if tender.bid_security_amount:
        meta_lines.append(f"Обеспечение заявки: {tender.bid_security_amount:,.2f} ₽")
    if tender.contract_security_amount:
        meta_lines.append(f"Обеспечение контракта: {tender.contract_security_amount:,.2f} ₽")
    if tender.contract_security_percent:
        meta_lines.append(f"Обеспечение контракта: {tender.contract_security_percent}%")

    prior_section = ""
    if prior_analysis:
        prior_section = "\n\n" + _format_prior_analysis(prior_analysis) + "\n"

    user_prompt = "\n".join(meta_lines) + prior_section + f"\n\nДОКУМЕНТАЦИЯ:\n\n{doc_context}"

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
        from apps.tenders.services import deepseek_circuit
        deepseek_circuit.record_failure()
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
