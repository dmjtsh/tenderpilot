# Семантический поиск — apps/search

Дата обновления: 28 мая 2026

## Архитектура

Вектор = **только семантика** (title + ОКПД названия). Всё остальное (регион, закон, НМЦ, площадка, дедлайн) = Qdrant payload фильтры + DB фильтры.

## Embedder (embedder.py)

- Модель: `multilingual-e5-large` (ONNX, fastembed, ~450MB, CPU, singleton)
- `tender_text(tender)` → str: title + ОКПД названия через запятую
- `embed_passages(texts)` → list[list[float]] (1024-dim)
- **Не менять модель** — все векторы в Qdrant привязаны к ней

## HyDE (hyde.py)

- `generate_hyde_texts(direction, n=5)` → list[str]
  - DeepSeek → 5 синтетических текстов в формате "Title. Вид работ: ОКПД."
  - Использует ТОЛЬКО name + okved_codes + keywords (НЕ description — размывает вектора)
- `build_direction_vector(direction)` → (vector, hyde_texts)
  - Генерирует 5 текстов, усредняет эмбеддинги → profile_vector

## Scoring (scoring.py)

```python
score_label(cosine):
  ≥0.82 → "Отличное совпадение"
  ≥0.75 → "Хорошее"
  ≥0.65 → "Среднее"
  <0.65 → "Слабое"
```

Smart Score удалён — чистый cosine достаточен при правильных фильтрах.

## QdrantService (services.py)

Коллекции:
- `tenders` — векторы тендеров (cosine, 1024-dim)
  - payload: number, title, nmck, customer_name, region, law_type, status, published_at, procedure_type, deadline_at_ts
- `doc_chunks` — RAG чанки документов
  - payload: tender_id, document_id, chunk_index, text, filename, content_priority
- **mmap включён** для обеих (memmap_threshold=10000, on_disk HNSW)

### match_profile логика
1. Итерирует по направлениям с profile_vector
2. Payload-фильтры: status=active, deadline_at_ts>now, regions MatchAny, nmck Range, law_types MatchAny, procedure_types MatchAny
3. Скоринг: `0.5*hyde_score + (0.5/N)*sum(won_scores)` где N = количество won_vectors
4. Фильтрует exclude_keywords из title/okpd (negative matching)
5. Дедупликация по tender_id, возвращает до limit*10 для пагинации
6. UI фильтры (extra_regions, extra_law_types и т.д.) переопределяют настройки направлений

## Celery Tasks (tasks.py)

- `embed_tender(tender_id, force)` — max_retries=3, delay=30. Пропускает non-active если не force
- `rebuild_direction_vector(direction_id)` — checks needs_reindex(), countdown=30, фиксированный task_id для debounce

## Management Commands

| Команда | Назначение |
|---------|-----------|
| `index_tenders [--only-new]` | Индексация тендеров в Qdrant |
| `reindex_payloads [--dry-run] [--batch=1000] [--limit=N]` | Обновление payload без пересчёта вектора |

## API Endpoints

```
POST /api/v1/search/        — семантический поиск (query → embedding → Qdrant)
GET  /api/v1/search/match/  — матчинг под профиль (direction_ids, profile_id, фильтры)
```

Параметры match: `profile_id, direction_ids, offset, limit, sort, law_types, regions, procedure_types, nmck_min, nmck_max`
