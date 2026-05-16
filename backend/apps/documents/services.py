from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

import tiktoken
from django.conf import settings

if TYPE_CHECKING:
    from apps.tenders.models import Tender

logger = logging.getLogger(__name__)

PRIORITY_KEYWORDS: dict[int, list[str]] = {
    0: ["техзадани", "тз", "задани"],
    1: ["контракт", "договор"],
    2: ["требовани", "документаци", "извещени"],
}

TOKENS_PER_PRIORITY: dict[int, int] = {
    0: 3000,
    1: 800,
    2: 500,
}
MAX_TOTAL_TOKENS = 4000
MAX_DOCS = 5

SUMMARY_QUERIES: list[str] = [
    "требования к участнику допуск квалификация",
    "срок выполнения исполнения поставки",
    "гарантийный срок качество обязательства",
    "обеспечение заявки контракта размер процент",
    "штрафы пени неустойка ответственность размер",
    "ограничения запреты условия исполнения",
    "приёмка результат передача согласование",
]

_RE_ONLY_DIGITS_PUNCT = re.compile(r"^[\d\s\W]+$")
_RE_MULTI_SPACES = re.compile(r"[ \t]{2,}")
_RE_MULTI_NEWLINES = re.compile(r"\n{3,}")

_encoding: tiktoken.Encoding | None = None


def _get_encoding() -> tiktoken.Encoding:
    global _encoding
    if _encoding is None:
        _encoding = tiktoken.get_encoding("cl100k_base")
    return _encoding


def count_tokens(text: str) -> int:
    return len(_get_encoding().encode(text))


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    enc = _get_encoding()
    tokens = enc.encode(text)
    if len(tokens) <= max_tokens:
        return text
    return enc.decode(tokens[:max_tokens])


def detect_content_priority(filename: str) -> int:
    name_lower = filename.lower()
    for priority, keywords in PRIORITY_KEYWORDS.items():
        for kw in keywords:
            if kw in name_lower:
                return priority
    return 99


CLASSIFY_PROMPT = """Ты эксперт по госзакупкам России.
Расставь приоритеты документов тендера для анализа.

Файлы: {filenames}

Приоритеты:
0 — техническое задание, описание объекта закупки (главный документ с требованиями к работам)
1 — проект контракта / договор / муниципальный контракт / государственный контракт (условия, штрафы, сроки). ВАЖНО: "Проект МК", "Проект ГК", "Проект контракта", "Проект муниципального контракта" — это контракт (1), НЕ проектная документация
2 — требования к заявке / инструкция участника
3 — извещение о закупке
99 — чертежи, сметы, локальные сметные расчёты (ЛСР), титульники, листы согласования, протоколы НМЦК, приложения с расчётами

Верни JSON без markdown:
{{"filename1": 0, "filename2": 1, ...}}"""


def classify_documents_priority(filenames: list[str]) -> dict[str, int]:
    if not filenames:
        return {}

    from apps.tenders.services import get_llm_client

    prompt = CLASSIFY_PROMPT.format(filenames=json.dumps(filenames, ensure_ascii=False))
    messages = [{"role": "user", "content": prompt}]

    try:
        client = get_llm_client("deepseek-chat")
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            max_tokens=500,
            temperature=0,
        )
    except Exception as e:
        logger.warning("DeepSeek classify failed, falling back to GPT-4o-mini: %s", e)
        try:
            client = get_llm_client("gpt-4o-mini")
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                max_tokens=500,
                temperature=0,
            )
        except Exception as exc:
            logger.warning("GPT classify_documents_priority also failed: %s", exc)
            return {fname: detect_content_priority(fname) for fname in filenames}

    try:
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        result: dict[str, int] = json.loads(raw)
        valid_priorities = {0, 1, 2, 3, 99}
        return {
            fname: p if p in valid_priorities else 99
            for fname, p in result.items()
        }
    except Exception as exc:
        logger.warning("classify_documents_priority parse failed: %s", exc)
        return {fname: detect_content_priority(fname) for fname in filenames}


def clean_text(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if len(stripped) < 10:
            continue
        if _RE_ONLY_DIGITS_PUNCT.match(stripped):
            continue
        lines.append(stripped)
    result = "\n".join(lines)
    result = _RE_MULTI_SPACES.sub(" ", result)
    result = _RE_MULTI_NEWLINES.sub("\n\n", result)
    return result.strip()


def _get_summary_context_from_text(
    tender: Tender, max_tokens: int = MAX_TOTAL_TOKENS,
) -> str:
    from apps.documents.models import TenderDocument

    docs = (
        TenderDocument.objects
        .filter(
            tender=tender,
            parse_status=TenderDocument.ParseStatus.DONE,
            is_scanned=False,
            content_priority__lt=99,
        )
        .exclude(parsed_text="")
        .order_by("content_priority", "filename")[:MAX_DOCS]
    )

    result: list[str] = []
    total = 0
    for doc in docs:
        limit = min(
            TOKENS_PER_PRIORITY.get(doc.content_priority, 0),
            max_tokens - total,
        )
        if limit <= 0:
            break
        text = truncate_to_tokens(clean_text(doc.parsed_text), limit)
        if not text:
            continue
        result.append(f"[{doc.filename}]\n{text}")
        total += count_tokens(text)

    return "\n\n---\n\n".join(result)


FULL_TZ_TOKEN_LIMIT = 8000
MAX_CHUNKS_PER_DOC = 2


def _get_full_tz(tender: Tender) -> tuple[str, int] | None:
    """Return (cleaned_text, token_count) for priority=0 docs if they fit."""
    from apps.documents.models import TenderDocument

    tz_docs = (
        TenderDocument.objects.filter(
            tender=tender,
            parse_status=TenderDocument.ParseStatus.DONE,
            content_priority=0,
            is_scanned=False,
        )
        .exclude(parsed_text="")
        .order_by("filename")
    )
    if not tz_docs.exists():
        return None

    parts: list[str] = []
    total_tokens = 0
    for doc in tz_docs:
        text = clean_text(doc.parsed_text)
        if not text:
            continue
        tokens = count_tokens(text)
        total_tokens += tokens
        parts.append(f"[{doc.filename}]\n{text}")

    if not parts or total_tokens > FULL_TZ_TOKEN_LIMIT:
        return None

    return "\n\n---\n\n".join(parts), total_tokens


def _rag_for_other_docs(
    tender: Tender,
    exclude_doc_ids: set[int],
    max_tokens: int,
) -> list[str]:
    """RAG search for priority 1+ documents, excluding given doc IDs."""
    from apps.search.embedder import Embedder
    from apps.search.services import qdrant

    embedder = Embedder()
    seen: dict[tuple[int, int], dict] = {}

    try:
        for query in SUMMARY_QUERIES:
            vector = embedder.embed_query(query)
            hits = qdrant.search_doc_chunks(
                vector=vector,
                tender_id=tender.id,
                limit=2,
                score_threshold=0.3,
            )
            for hit in hits:
                if hit.get("document_id", 0) in exclude_doc_ids:
                    continue
                key = (hit.get("document_id", 0), hit.get("chunk_index", 0))
                if key not in seen or hit["score"] > seen[key]["score"]:
                    seen[key] = hit
    except Exception as exc:
        logger.warning("Qdrant doc_chunks search failed: %s", exc)

    if not seen:
        return []

    chunks = sorted(seen.values(), key=lambda c: c["score"], reverse=True)

    result: list[str] = []
    total = 0
    doc_counts: dict[int, int] = {}
    for chunk in chunks:
        doc_id = chunk.get("document_id", 0)
        if doc_counts.get(doc_id, 0) >= MAX_CHUNKS_PER_DOC:
            continue
        text = chunk.get("text", "")
        filename = chunk.get("filename", "документ")
        entry = f"[{filename}]\n{text}"
        entry_tokens = count_tokens(entry)
        if total + entry_tokens > max_tokens:
            remaining = max_tokens - total
            if remaining > 50:
                result.append(truncate_to_tokens(entry, remaining))
                doc_counts[doc_id] = doc_counts.get(doc_id, 0) + 1
            break
        result.append(entry)
        total += entry_tokens
        doc_counts[doc_id] = doc_counts.get(doc_id, 0) + 1

    return result


QA_PROMPT = """Ты эксперт по госзакупкам России.
Отвечай ТОЛЬКО на основе документации тендера ниже.
Если ответа нет в документах — скажи об этом прямо.
Не придумывай и не используй общие знания.

ДОКУМЕНТАЦИЯ:
{context}

ВОПРОС: {question}"""


def answer_question(tender_id: int, question: str) -> dict:
    from apps.documents.models import TenderDocument
    from apps.search.embedder import Embedder
    from apps.search.services import qdrant
    from apps.tenders.services import get_llm_client

    has_any_docs = TenderDocument.objects.filter(
        tender_id=tender_id,
        parse_status=TenderDocument.ParseStatus.DONE,
    ).exists()

    if not has_any_docs:
        return {"answer": None, "has_docs": False, "sources": []}

    embedder = Embedder()
    vector = embedder.embed_query(question)

    hits = qdrant.search_doc_chunks(
        vector=vector,
        tender_id=tender_id,
        limit=5,
        score_threshold=0.0,
    )

    if not hits:
        return {"answer": None, "has_docs": True, "sources": [], "needs_reindex": True}

    context_parts: list[str] = []
    sources: list[dict] = []
    for hit in hits:
        filename = hit.get("filename", "документ")
        text = hit.get("text", "")
        chunk_index = hit.get("chunk_index", 0)
        context_parts.append(f"[{filename}]\n{text}")
        sources.append({
            "filename": filename,
            "chunk_index": chunk_index,
            "text": text,
            "document_id": hit.get("document_id"),
        })

    context = "\n\n---\n\n".join(context_parts)
    prompt = QA_PROMPT.format(context=context, question=question)

    model_name = "deepseek-chat"
    try:
        client = get_llm_client(model_name)
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
            temperature=0.2,
        )
        answer = response.choices[0].message.content.strip()
    except Exception:
        logger.warning("DeepSeek QA failed for tender %d, falling back to gpt-4o-mini", tender_id)
        model_name = "gpt-4o-mini"
        client = get_llm_client(model_name)
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
            temperature=0.2,
        )
        answer = response.choices[0].message.content.strip()

    return {"answer": answer, "has_docs": True, "sources": sources, "needs_reindex": False}


def answer_question_with_variant(tender_id: int, question: str, variant: dict) -> dict:
    """Run QA with a specific model/prompt. Production answer_question() is not affected."""
    import time
    from apps.documents.models import TenderDocument
    from apps.tenders.models import PromptTemplate
    from apps.tenders.services import get_llm_client, calculate_cost
    from apps.search.embedder import Embedder
    from apps.search.services import qdrant

    model_name = variant.get("model", "gpt-4o-mini")
    prompt_slug = variant.get("prompt_template", "chat_qa_v1")

    template = PromptTemplate.objects.filter(name=prompt_slug, is_active=True).order_by("-version").first()
    if not template:
        raise ValueError(f"PromptTemplate '{prompt_slug}' not found or inactive")

    has_any_docs = TenderDocument.objects.filter(
        tender_id=tender_id,
        parse_status=TenderDocument.ParseStatus.DONE,
    ).exists()

    if not has_any_docs:
        return {
            "answer": None, "sources": [], "has_docs": False,
            "metrics": {"model": model_name, "input_tokens": 0, "output_tokens": 0,
                        "cost_usd": 0, "duration_ms": 0, "actual_model": ""},
        }

    embedder = Embedder()
    vector = embedder.embed_query(question)
    hits = qdrant.search_doc_chunks(vector=vector, tender_id=tender_id, limit=5, score_threshold=0.0)

    if not hits:
        return {
            "answer": None, "sources": [], "has_docs": True, "needs_reindex": True,
            "metrics": {"model": model_name, "input_tokens": 0, "output_tokens": 0,
                        "cost_usd": 0, "duration_ms": 0, "actual_model": ""},
        }

    context_parts: list[str] = []
    sources: list[dict] = []
    for hit in hits:
        filename = hit.get("filename", "документ")
        text = hit.get("text", "")
        chunk_index = hit.get("chunk_index", 0)
        context_parts.append(f"[{filename}]\n{text}")
        sources.append({
            "filename": filename, "chunk_index": chunk_index,
            "text": text, "document_id": hit.get("document_id"),
        })

    context = "\n\n---\n\n".join(context_parts)
    prompt = template.user_template.format(context=context, question=question)

    client = get_llm_client(model_name)
    messages = [{"role": "user", "content": prompt}]

    start_ns = time.monotonic_ns()
    response = client.chat.completions.create(
        model=model_name, messages=messages, max_tokens=600, temperature=0.2,
    )
    duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000

    answer = response.choices[0].message.content.strip()
    actual_model = getattr(response, "model", "") or ""

    usage = response.usage
    input_tokens = usage.prompt_tokens if usage else 0
    output_tokens = usage.completion_tokens if usage else 0
    cost = calculate_cost(model_name, input_tokens, output_tokens)

    return {
        "answer": answer,
        "sources": sources,
        "has_docs": True,
        "metrics": {
            "model": model_name,
            "actual_model": actual_model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": float(cost),
            "duration_ms": duration_ms,
        },
    }


def get_summary_context(
    tender: Tender, max_tokens: int = 6000,
) -> dict[str, str]:
    from apps.documents.models import TenderDocument

    has_any_docs = TenderDocument.objects.filter(
        tender=tender,
        parse_status=TenderDocument.ParseStatus.DONE,
    ).exists()

    if not has_any_docs:
        return {"context": "", "source": "none"}

    tz_result = _get_full_tz(tender)

    if tz_result is not None:
        tz_text, tz_tokens = tz_result
        remaining_budget = max_tokens - tz_tokens

        tz_doc_ids = set(
            TenderDocument.objects.filter(
                tender=tender,
                content_priority=0,
            ).values_list("id", flat=True)
        )

        rag_parts = []
        if remaining_budget > 200:
            rag_parts = _rag_for_other_docs(tender, tz_doc_ids, remaining_budget)

        parts = [tz_text] + rag_parts
        return {
            "context": "\n\n---\n\n".join(parts),
            "source": "full_tz",
        }

    from apps.search.embedder import Embedder
    from apps.search.services import qdrant

    embedder = Embedder()
    seen: dict[tuple[int, int], dict] = {}

    try:
        for query in SUMMARY_QUERIES:
            vector = embedder.embed_query(query)
            hits = qdrant.search_doc_chunks(
                vector=vector,
                tender_id=tender.id,
                limit=3,
                score_threshold=0.3,
            )
            for hit in hits:
                key = (hit.get("document_id", 0), hit.get("chunk_index", 0))
                if key not in seen or hit["score"] > seen[key]["score"]:
                    seen[key] = hit
    except Exception as exc:
        logger.warning("Qdrant doc_chunks search failed: %s", exc)

    if not seen:
        text = _get_summary_context_from_text(tender, max_tokens)
        if text:
            return {"context": text, "source": "text"}
        return {"context": "", "source": "none"}

    chunks = sorted(seen.values(), key=lambda c: c["score"], reverse=True)

    result: list[str] = []
    total = 0
    doc_counts: dict[int, int] = {}
    for chunk in chunks:
        doc_id = chunk.get("document_id", 0)
        if doc_counts.get(doc_id, 0) >= MAX_CHUNKS_PER_DOC:
            continue
        text = chunk.get("text", "")
        filename = chunk.get("filename", "документ")
        entry = f"[{filename}]\n{text}"
        entry_tokens = count_tokens(entry)
        if total + entry_tokens > max_tokens:
            remaining = max_tokens - total
            if remaining > 50:
                result.append(truncate_to_tokens(entry, remaining))
                doc_counts[doc_id] = doc_counts.get(doc_id, 0) + 1
            break
        result.append(entry)
        total += entry_tokens
        doc_counts[doc_id] = doc_counts.get(doc_id, 0) + 1

    return {"context": "\n\n---\n\n".join(result), "source": "rag"}


FULL_CONTEXT_MAX_TOKENS = 100_000


def get_full_context(tender: "Tender") -> dict:
    from apps.documents.models import TenderDocument

    docs = list(
        TenderDocument.objects.filter(
            tender=tender,
            parse_status=TenderDocument.ParseStatus.DONE,
            is_scanned=False,
        )
        .exclude(parsed_text="")
        .order_by("content_priority", "filename")
    )

    entries: list[dict] = []
    for d in docs:
        text = clean_text(d.parsed_text)
        if not text:
            continue
        entries.append({"doc": d, "text": text, "tokens": count_tokens(text), "priority": d.content_priority})

    if not entries:
        return {
            "context": "", "source": "none", "total_tokens": 0,
            "original_total_tokens": 0, "was_truncated": False, "truncated_reason": "",
        }

    original_total = sum(e["tokens"] for e in entries)
    was_truncated = False
    truncated_reason = ""

    if original_total > FULL_CONTEXT_MAX_TOKENS:
        for drop_priority in [99, 3, 2, 1]:
            before = len(entries)
            entries = [e for e in entries if e["priority"] < drop_priority]
            if len(entries) < before:
                was_truncated = True
                truncated_reason = f"removed_priority_{drop_priority}"
                if sum(e["tokens"] for e in entries) <= FULL_CONTEXT_MAX_TOKENS:
                    break

        total = sum(e["tokens"] for e in entries)

        while total > FULL_CONTEXT_MAX_TOKENS and len(entries) > 1:
            largest_idx = max(range(len(entries)), key=lambda i: entries[i]["tokens"])
            removed = entries.pop(largest_idx)
            total -= removed["tokens"]
            was_truncated = True
            truncated_reason = "dropped_largest_doc"

        if total > FULL_CONTEXT_MAX_TOKENS and entries:
            entry = entries[-1]
            entry["text"] = truncate_to_tokens(entry["text"], FULL_CONTEXT_MAX_TOKENS - (total - entry["tokens"]))
            entry["tokens"] = count_tokens(entry["text"])
            was_truncated = True
            truncated_reason = "truncated_last_doc"

    total = sum(e["tokens"] for e in entries)
    parts = [f"[{e['doc'].filename}]\n{e['text']}" for e in entries]

    return {
        "context": "\n\n---\n\n".join(parts),
        "source": "full",
        "total_tokens": total,
        "original_total_tokens": original_total,
        "was_truncated": was_truncated,
        "truncated_reason": truncated_reason,
    }
