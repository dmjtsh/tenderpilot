import json
import logging
import os

import numpy as np
from openai import OpenAI

logger = logging.getLogger(__name__)

HYDE_PROMPT = """Ты эксперт по госзакупкам России.

Компания: {name}
ОКВЭД: {okved_text}
Ключевые слова: {keywords}
НМЦ: от {nmck_min} до {nmck_max} ₽
Типы закупок: {law_types}

Напиши {n} разных описания тендеров (2-3 предложения каждый), \
которые идеально подошли бы этой компании.
Используй официальный язык госзакупок.
Верни ТОЛЬКО JSON массив строк без пояснений."""


def _get_client() -> OpenAI:
    from django.conf import settings
    return OpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL or None)


def generate_hyde_texts(direction, n: int = 3) -> list[str]:
    from apps.tenders.okved import okved_to_text

    okved_text = okved_to_text(direction.okved_codes or []) or "не указан"
    keywords = ", ".join(direction.keywords or []) or "не указаны"
    nmck_min = f"{direction.nmck_min:,}".replace(",", " ") if direction.nmck_min else "не ограничен"
    nmck_max = f"{direction.nmck_max:,}".replace(",", " ") if direction.nmck_max else "не ограничен"
    law_types = ", ".join(direction.law_types or ["44-ФЗ", "223-ФЗ", "615-ПП"])

    client = _get_client()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": HYDE_PROMPT.format(
            name=direction.name,
            okved_text=okved_text,
            keywords=keywords,
            nmck_min=nmck_min,
            nmck_max=nmck_max,
            law_types=law_types,
            n=n,
        )}],
        max_tokens=600,
        temperature=0.7,
    )

    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)


def build_direction_vector(direction) -> tuple[list[float], list[str]]:
    from apps.search.embedder import Embedder

    hyde_texts = generate_hyde_texts(direction, n=3)
    logger.info("HyDE texts generated for direction %d: %d texts", direction.id, len(hyde_texts))

    embedder = Embedder()
    vectors = embedder.embed_passages(hyde_texts)
    avg_vector = np.mean(vectors, axis=0).tolist()

    return avg_vector, hyde_texts
