import json
import logging
from typing import Iterator

from apps.tenders.models import Tender

logger = logging.getLogger(__name__)

CHAT_SYSTEM_PROMPT = """Ты — эксперт по госзакупкам (44-ФЗ, 223-ФЗ). \
Отвечаешь на вопросы пользователя о тендере \
ИСКЛЮЧИТЕЛЬНО на основе предоставленной документации.

КОНТЕКСТ ТЕНДЕРА:

Название: {title}
НМЦ: {nmck} ₽
Закон: {law_type}
Заказчик: {customer_name}
Регион: {region}
Дедлайн подачи: {deadline_at}

КАК ОТВЕЧАТЬ:

1. КРАТКО И ПО ДЕЛУ
   - Прямой ответ в 1-3 предложениях
   - Без воды и общих рассуждений
   - **Жирный шрифт** для ключевых цифр и фактов
   - Точные цифры и формулировки из документов

2. ИСТОЧНИКИ ОТДЕЛЬНОЙ СТРОКОЙ
   В конце ответа:

   Источники:
   • Название документа, п. X.X

   Указывай ТОЛЬКО названия документов и пункты если они есть. \
НЕ ЦИТИРУЙ выдранные куски текста.

3. ЕСЛИ НЕТ ИНФОРМАЦИИ
   Прямо скажи "В предоставленных документах этой информации нет". \
НЕ выдумывай, не предполагай.

4. ЕСЛИ ВОПРОС ОБЩИЙ (не про этот тендер)
   Кратко ответь как эксперт, но укажи что это общая информация \
не из документов тендера.

5. ПОЛНОТА ПОИСКА
   При поиске информации ИСПОЛЬЗУЙ ВСЕ поданные документы, \
не ограничивайся одним разделом:
   - **ЛИЦЕНЗИИ И ДОПУСКИ — КРИТИЧНО**: НЕЛЬЗЯ отвечать "не \
установлено" или "не требуются", не проверив ВСЕ документы. \
Формальные требования к участникам (Информационная карта) могут \
говорить "не установлено", но Техническое задание может требовать \
конкретные лицензии для отдельных этапов работ (ФСТЭК, ФСБ, \
МЧС, Ростехнадзор, СРО и т.д.). ВСЕГДА проверяй ТЗ на наличие \
лицензионных требований в описании этапов. Если ТЗ требует \
лицензию для любого этапа — это ОБЯЗАТЕЛЬНОЕ требование, даже \
если Информационная карта говорит "не установлено".
   - Документы для подачи заявки описываются в разделе "Состав \
заявки" Документации конкурса. Если встречается ссылка на \
конкретный раздел (например "Образцы форм, раздел V") — поищи \
его содержимое в поданных документах.
   - ОБЩЕЕ ПРАВИЛО: если в одном документе указано "не \
установлено", а в другом есть конкретные требования — приоритет \
у конкретных требований. Никогда не останавливайся на первом \
найденном "не установлено".
   - В ответе явно указывай ВСЕ обнаруженные источники, даже \
если они в разных документах.

ФОРМАТ ОТВЕТА:

[Прямой ответ с **выделенными цифрами**]

[Опционально 1-2 предложения уточнения]

Источники:
- [название документа], [пункт если знаешь]

ЗАПРЕЩЕНО:
- Длинные ответы на простой вопрос
- Выдранные цитаты в стиле "...считается дата..."
- Markdown таблицы/код для коротких ответов
- Предположения там где нет данных
"""


CHAT_MAX_TOKENS = 120_000


def _get_docs_text(tender: Tender) -> str:
    """Get ALL parsed documents for a tender, prioritizing breadth over depth."""
    from apps.documents.models import TenderDocument
    from apps.documents.services import clean_text, count_tokens, truncate_to_tokens

    docs = list(
        TenderDocument.objects.filter(
            tender=tender,
            parse_status=TenderDocument.ParseStatus.DONE,
            is_scanned=False,
        )
        .exclude(parsed_text="")
        .order_by("content_priority", "filename")
    )

    entries = []
    for d in docs:
        text = clean_text(d.parsed_text)
        if not text:
            continue
        entries.append({"filename": d.filename, "text": text, "tokens": count_tokens(text), "priority": d.content_priority})

    if not entries:
        from apps.tenders.summary_v2.context import _get_info_html
        info_html = _get_info_html(tender)
        if info_html:
            return f"[info_html]\n{info_html}"
        return ""

    # Deduplicate versioned files (keep latest)
    import re as _re
    seen: dict[str, int] = {}
    deduped = []
    for e in entries:
        base = _re.sub(r"_?v\d+", "", e["filename"])
        base = _re.sub(r"_?\d{2}\.\d{2}\.\d{4}", "", base)
        base = base.strip("_ ")
        if base in seen:
            deduped[seen[base]] = e
            continue
        seen[base] = len(deduped)
        deduped.append(e)

    # Sort: contract (1) first, then requirements (2), then TZ (0), then other (99)
    # This ensures broad coverage — contract has penalties/guarantees, docs have procedures
    chat_priority = {1: 0, 2: 1, 0: 2, 99: 3}
    deduped.sort(key=lambda e: (chat_priority.get(e["priority"], 4), e["filename"]))

    selected = []
    total = 0
    for e in deduped:
        if total + e["tokens"] <= CHAT_MAX_TOKENS:
            selected.append(e)
            total += e["tokens"]
        elif total < CHAT_MAX_TOKENS:
            remaining = CHAT_MAX_TOKENS - total
            e["text"] = truncate_to_tokens(e["text"], remaining)
            e["tokens"] = remaining
            selected.append(e)
            total += remaining
            break

    return "\n\n---\n\n".join(f"[{e['filename']}]\n{e['text']}" for e in selected)


def _build_system_prompt(tender: Tender) -> str:
    return CHAT_SYSTEM_PROMPT.format(
        title=tender.title,
        nmck=tender.nmck or "не указана",
        law_type=tender.law_type or "не указан",
        customer_name=tender.customer.name if tender.customer else "не указан",
        region=tender.region or "не указан",
        deadline_at=tender.deadline_at.strftime("%d.%m.%Y %H:%M") if tender.deadline_at else "не указан",
    )


def chat_with_tender_full_context(
    tender_id: int,
    message: str,
    chat_history: list[dict],
    model: str = "deepseek-chat",
) -> Iterator[str]:
    """Stream chat response using full document context."""
    from apps.tenders.services import get_llm_client, deepseek_circuit

    tender = Tender.objects.select_related("customer").get(pk=tender_id)
    docs_text = _get_docs_text(tender)

    if not docs_text:
        yield json.dumps({"error": "no_docs"})
        return

    system_prompt = _build_system_prompt(tender)

    messages = [{"role": "system", "content": system_prompt}]

    # Add chat history (last 10 messages max)
    for msg in chat_history[-10:]:
        role = msg.get("role", "user")
        content = msg.get("text", msg.get("content", ""))
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})

    user_content = f"{message}\n\nДокументация тендера:\n{docs_text}"
    messages.append({"role": "user", "content": user_content})

    actual_model = model
    circuit_model: list[str] = []
    client = get_llm_client(model, _circuit_model=circuit_model)
    if circuit_model:
        actual_model = circuit_model[0]

    try:
        response = client.chat.completions.create(
            model=actual_model,
            messages=messages,
            stream=True,
            temperature=0.3,
            max_tokens=2000,
        )

        for chunk in response:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content

    except Exception as e:
        logger.exception("Chat streaming failed for tender %s", tender_id)
        if model.startswith("deepseek"):
            deepseek_circuit.record_failure()
        yield json.dumps({"error": str(e)})
