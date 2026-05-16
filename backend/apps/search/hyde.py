import json
import logging

import numpy as np

logger = logging.getLogger(__name__)

HYDE_PROMPT = """Ты эксперт по российским госзакупкам.

Компания ищет тендеры по направлению:
Направление: {name}
{description_block}ОКВЭД: {okved_text}
Ключевые слова: {keywords}

Сгенерируй {n} примеров тендеров, которые идеально подходят этой компании.

Формат КАЖДОГО примера — одна строка:
"[Название тендера как на zakupki.gov.ru, конкретное, с объектом и адресом]. Вид работ: [конкретный вид работ из ОКВЭД]."

Пример:
"Капитальный ремонт мягкой кровли здания МБОУ «Школа №45» по адресу: г. Воронеж, ул. Ленина, д. 12. Вид работ: производство кровельных работ."

Требования:
- Названия реалистичные, как на ЕИС (zakupki.gov.ru)
- Описания конкретные: объект, адрес, вид работ
- Заказчики разнообразные: школы, больницы, администрации, МУПы
- Каждый пример — СТРОКА, не объект

Верни JSON массив из {n} строк. Без пояснений."""


def _dict_to_text(d: dict) -> str:
    title = d.get("Название тендера") or d.get("title") or ""
    work = d.get("Вид работ") or d.get("work_type") or ""
    parts = [f"{title}.", f"Вид работ: {work}." if work else ""]
    return " ".join(p for p in parts if p)


def generate_hyde_texts(direction, n: int = 5) -> list[str]:
    from apps.tenders.okved import okved_to_text
    from apps.tenders.services import get_llm_client

    okved_text = okved_to_text(direction.okved_codes or []) or "не указан"
    keywords = ", ".join(direction.keywords or []) or "не указаны"

    desc = (direction.description or "").strip()
    description_block = f"Описание: {desc}\n" if len(desc) >= 30 else ""

    client = get_llm_client("deepseek-chat")
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": HYDE_PROMPT.format(
            name=direction.name,
            description_block=description_block,
            okved_text=okved_text,
            keywords=keywords,
            n=n,
        )}],
        max_tokens=2000,
        temperature=0.8,
    )

    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    items = json.loads(raw)
    result = []
    for item in items:
        if isinstance(item, dict):
            result.append(_dict_to_text(item))
        else:
            result.append(str(item))
    return result


def build_direction_vector(direction) -> tuple[list[float], list[str]]:
    from apps.search.embedder import Embedder

    hyde_texts = generate_hyde_texts(direction, n=5)
    logger.info("HyDE texts generated for direction %d: %d texts", direction.id, len(hyde_texts))

    embedder = Embedder()
    vectors = embedder.embed_passages(hyde_texts)
    avg_vector = np.mean(vectors, axis=0).tolist()

    return avg_vector, hyde_texts
