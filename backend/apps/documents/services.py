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
0 — техническое задание (главный документ с требованиями к работам)
1 — проект контракта / договор (условия, штрафы, сроки)
2 — требования к заявке / инструкция участника
3 — извещение о закупке
99 — проектная документация, чертежи, сметы, титульники, приложения

Верни JSON без markdown:
{{"filename1": 0, "filename2": 1, ...}}"""


def classify_documents_priority(filenames: list[str]) -> dict[str, int]:
    if not filenames:
        return {}

    from openai import OpenAI

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    prompt = CLASSIFY_PROMPT.format(filenames=json.dumps(filenames, ensure_ascii=False))

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0,
        )
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
        logger.warning("GPT classify_documents_priority failed: %s", exc)
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
