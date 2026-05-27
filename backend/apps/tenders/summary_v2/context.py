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
    total = sum(e["tokens"] for e in selected)

    info_html = _get_info_html(tender)
    if info_html:
        info_tokens = count_tokens(info_html)
        remaining = MAX_TOKENS_PER_STEP - total
        if remaining > 500:
            if info_tokens > remaining:
                info_html = truncate_to_tokens(info_html, remaining)
                info_tokens = remaining
            parts.append(f"[info_html - описание с площадки]\n{info_html}")
            total += info_tokens

    return {
        "context": "\n\n---\n\n".join(parts),
        "source": "full",
        "total_tokens": total,
        "original_total_tokens": original_total,
        "was_truncated": was_truncated,
        "truncated_reason": truncated_reason,
    }


def _get_info_html(tender: "Tender") -> str:
    """Extract and clean info_html from TenderGuru raw_json."""
    import html
    import re

    rj = tender.raw_json or {}
    nested = rj.get("raw_json", {})
    raw = (nested.get("info_html", "") if isinstance(nested, dict) else "") or rj.get("info_html", "")
    if not raw or len(raw) < 50:
        return ""

    text = html.unescape(raw)
    text = text.replace("![CDATA[", "").rstrip("]")
    text = re.sub(r"<[^>]+>", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    text = re.sub(r"[ \t]+", " ", text)

    if len(text) < 30:
        return ""
    return text


def _get_raw_info_html(tender: "Tender") -> str:
    """Get raw info_html string before any processing."""
    rj = tender.raw_json or {}
    nested = rj.get("raw_json", {})
    return (nested.get("info_html", "") if isinstance(nested, dict) else "") or rj.get("info_html", "")


def _get_info_html_sanitized(tender: "Tender") -> str:
    """Sanitize info_html for safe frontend rendering: keep structure, strip scripts."""
    import html as html_mod
    import re

    raw = _get_raw_info_html(tender)
    if not raw or len(raw) < 50:
        return ""

    text = html_mod.unescape(raw)
    text = text.replace("![CDATA[", "").rstrip("]")

    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"\s+on\w+\s*=\s*[\"'][^\"']*[\"']", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+on\w+\s*=\s*\S+", "", text, flags=re.IGNORECASE)

    ALLOWED_TAGS = {
        "div", "span", "p", "br", "hr",
        "table", "thead", "tbody", "tr", "th", "td",
        "ul", "ol", "li",
        "strong", "b", "em", "i", "u",
        "h1", "h2", "h3", "h4", "h5", "h6",
        "a", "img",
    }

    def _filter_tag(m: re.Match) -> str:
        tag_content = m.group(0)
        tag_match = re.match(r"</?(\w+)", tag_content)
        if not tag_match:
            return ""
        tag_name = tag_match.group(1).lower()
        if tag_name in ALLOWED_TAGS:
            return tag_content
        return ""

    text = re.sub(r"</?[a-zA-Z][^>]*>", _filter_tag, text)
    text = text.strip()

    if len(text) < 30:
        return ""
    return text


def get_customer_profile(tender: "Tender") -> "CustomerProfile | None":
    if not tender.customer:
        return None

    inn = tender.customer.inn
    if not inn and tender.customer.name:
        from apps.users.dadata import find_inn_by_name
        found = find_inn_by_name(tender.customer.name)
        if found:
            tender.customer.inn = found
            tender.customer.save(update_fields=["inn"])
            inn = found

    if not inn:
        return None
    from apps.customers.services.enrichment import enrich_customer
    try:
        return enrich_customer(inn)
    except Exception as e:
        logger.warning("Customer enrichment failed for %s: %s", inn, e)
        return None
