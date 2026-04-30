from __future__ import annotations

import re
from typing import TYPE_CHECKING

import tiktoken

if TYPE_CHECKING:
    from apps.tenders.models import Tender

PRIORITY_KEYWORDS: dict[int, list[str]] = {
    0: ["техзадани", "тз", "задани"],
    1: ["контракт", "договор"],
    2: ["требовани", "документаци", "извещени"],
}

TOKENS_PER_PRIORITY: dict[int, int] = {
    0: 800,
    1: 500,
    2: 300,
    99: 200,
}
MAX_TOTAL_TOKENS = 1500
MAX_DOCS = 5

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


def get_summary_context(tender: Tender, max_tokens: int = MAX_TOTAL_TOKENS) -> str:
    from apps.documents.models import TenderDocument

    docs = (
        TenderDocument.objects
        .filter(
            tender=tender,
            parse_status=TenderDocument.ParseStatus.DONE,
            is_scanned=False,
        )
        .exclude(parsed_text="")
        .order_by("content_priority", "filename")[:MAX_DOCS]
    )

    result: list[str] = []
    total = 0
    for doc in docs:
        limit = min(
            TOKENS_PER_PRIORITY.get(doc.content_priority, 200),
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
