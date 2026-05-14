import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.customers.models import CustomerProfile
    from apps.tenders.models import Tender

logger = logging.getLogger(__name__)

MAX_TOKENS_PER_STEP = 80_000

STEP_PRIORITY_ORDER: dict[str, list[int]] = {
    "financial": [1, 2, 0, 99],
    "timeline": [1, 0, 2, 99],
    "requirements": [2, 1, 0, 99],
    "work": [0, 2, 1, 99],
    "risks": [0, 1, 2, 99],
    "customer": [2, 1, 0, 99],
}


def get_full_document_context(tender: "Tender") -> dict:
    from apps.documents.services import get_full_context
    return get_full_context(tender)


def get_step_context(tender: "Tender", step: str) -> dict:
    """Контекст с приоритетами релевантными для конкретного шага."""
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
        entries.append({
            "doc": d,
            "text": text,
            "tokens": count_tokens(text),
            "priority": d.content_priority,
        })

    if not entries:
        return {"context": "", "source": "none", "total_tokens": 0,
                "original_total_tokens": 0, "was_truncated": False, "truncated_reason": ""}

    original_total = sum(e["tokens"] for e in entries)

    priority_order = STEP_PRIORITY_ORDER.get(step, [0, 1, 2, 99])

    ordered = sorted(entries, key=lambda e: (
        priority_order.index(e["priority"]) if e["priority"] in priority_order else len(priority_order),
        e["doc"].filename,
    ))

    # Дедупликация: нормализуем имя (убираем v2, даты, подчёркивания)
    # и оставляем последнюю версию (уже отсортировано по filename → v2 после v1)
    import re as _re
    seen_bases: dict[str, int] = {}
    deduped = []
    for e in ordered:
        name = e["doc"].filename
        base = _re.sub(r"_?v\d+", "", name)
        base = _re.sub(r"_?\d{2}\.\d{2}\.\d{4}", "", base)
        base = base.strip("_ ")
        if base in seen_bases:
            # Replace earlier version with this one (later = newer)
            deduped[seen_bases[base]] = e
            continue
        seen_bases[base] = len(deduped)
        deduped.append(e)
    ordered = deduped

    selected = []
    total = 0
    was_truncated = False
    truncated_reason = ""

    for e in ordered:
        if total + e["tokens"] <= MAX_TOKENS_PER_STEP:
            selected.append(e)
            total += e["tokens"]
        elif total < MAX_TOKENS_PER_STEP:
            remaining = MAX_TOKENS_PER_STEP - total
            e["text"] = truncate_to_tokens(e["text"], remaining)
            e["tokens"] = remaining
            selected.append(e)
            total += remaining
            was_truncated = True
            truncated_reason = f"truncated_{e['doc'].filename}"
            break
        else:
            was_truncated = True
            truncated_reason = f"dropped_{e['doc'].filename}"

    parts = [f"[{e['doc'].filename}]\n{e['text']}" for e in selected]

    return {
        "context": "\n\n---\n\n".join(parts),
        "source": "full",
        "total_tokens": sum(e["tokens"] for e in selected),
        "original_total_tokens": original_total,
        "was_truncated": was_truncated,
        "truncated_reason": truncated_reason,
    }


def get_customer_profile(tender: "Tender") -> "CustomerProfile | None":
    if not tender.customer or not tender.customer.inn:
        return None
    from apps.customers.services.enrichment import enrich_customer
    try:
        return enrich_customer(tender.customer.inn)
    except Exception as e:
        logger.warning("Customer enrichment failed for %s: %s", tender.customer.inn, e)
        return None
