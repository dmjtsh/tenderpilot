# ML-часть: embedding + векторный поиск тендеров

## Обзор пайплайна

```
Tender (Postgres)
    ↓ tender_text()
Текст для embedding
    ↓ Embedder.embed_passages()
Вектор float[1024]
    ↓ QdrantService.upsert_tender()
Qdrant (коллекция tenders)
    ↑ QdrantService.search_tenders()
Поисковый запрос → embed_query() → вектор → ANN-поиск
```

---

## 1. Модель: intfloat/multilingual-e5-large

**Что это:** sentence-transformer модель от Интела, обученная на мультиязычных данных (94 языка, включая русский). Основана на XLM-RoBERTa-large.

**Почему именно она:**
- Хорошо работает с русским языком
- 1024-мерные векторы — хороший баланс качество/память
- В топе MTEB (Massive Text Embedding Benchmark) среди мультиязычных моделей
- Есть ONNX-версия для быстрого инференса без PyTorch

**Альтернатива** из CLAUDE.md: `deepvk/USER-bge-m3` — российская модель, заточена под русский, но нет ONNX → нужен PyTorch → тяжелее.

---

## 2. Критичная деталь: префиксы query/passage

multilingual-e5 обучена с **asymmetric retrieval** — разные префиксы для документов и запросов:

```python
# При индексации документов:
"passage: Поставка медицинского оборудования 85.13 ГБУЗ Москва"

# При поиске:
"query: медицинское оборудование больница"
```

**Почему это важно:** без префиксов косинусное сходство считается некорректно — модель не знает, что одно это "документ", а другое "запрос". Качество поиска деградирует заметно.

Источник: [оригинальная статья E5](https://arxiv.org/abs/2212.03533), раздел 3.

---

## 3. Текст тендера для embedding

```python
# apps/search/embedder.py
def tender_text(title, okpd_codes, customer_name=""):
    parts = [title]
    if okpd_codes:
        parts.append(" ".join(str(c) for c in okpd_codes))
    if customer_name:
        parts.append(customer_name)
    return " ".join(parts)
```

**Что входит и почему:**
- `title` — основное название закупки, самое важное для поиска
- `okpd_codes` — коды ОКПД2 (классификатор продукции). Позволяет находить тендеры по коду даже если в названии другие слова. Пример: `85.11` → медицинские услуги
- `customer_name` — заказчик. Помогает искать "тендеры Минздрава" или "закупки РЖД"

**Что НЕ входит пока:**
- `nmck` (цена) — не семантически значимо для embedding
- `region` — фильтруем через metadata filter в Qdrant, не через вектор
- `deadline_at` — аналогично

---

## 4. Runtime: fastembed вместо sentence-transformers

**fastembed** (от Qdrant) — лёгкая обёртка, запускает модель через ONNX Runtime вместо PyTorch.

| | sentence-transformers | fastembed |
|---|---|---|
| Зависимости | torch (~2GB) | onnxruntime (~50MB) |
| Скорость CPU | baseline | ~1.5-2x быстрее |
| RAM | ~3GB | ~1GB |
| GPU | да | нет (только CPU/CoreML) |

Для нашего случая (локальная разработка, CPU MacBook) — fastembed лучше.

**Предупреждение при запуске:**
```
UserWarning: The model intfloat/multilingual-e5-large now uses mean pooling 
instead of CLS embedding.
```
Это **ок**. Mean pooling — правильный способ для E5 моделей. CLS embedding был ошибкой в старых версиях fastembed. Нас предупреждают что поведение изменилось, но новое поведение лучше.

---

## 5. Singleton паттерн для модели

```python
class Embedder:
    _instance: "Embedder | None" = None
    _model: "TextEmbedding | None" = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
```

**Почему важно:** модель весит ~450MB и загружается ~3-5 секунд. Если создавать новый экземпляр на каждый запрос — катастрофа. Singleton гарантирует что модель загружается один раз на процесс (Django worker или Celery worker).

**Lazy import:**
```python
def _get_model(self):
    if self._model is None:
        from fastembed import TextEmbedding  # импорт здесь, не на уровне модуля
        self._model = TextEmbedding(...)
```
Нужно чтобы `django check`, `makemigrations` и другие management commands не загружали модель при старте.

---

## 6. Qdrant: схема хранения

**Коллекция `tenders`:**
```
vector: float[1024], distance=COSINE
payload: {
    number:       str,   # "0273100001126000204"
    title:        str,   # полное название
    nmck:         float, # начальная цена
    customer_name: str,
    region:       str,
    status:       str,   # "active" / "finished" / "cancelled"
    published_at: str,   # ISO datetime
}
```

**Point ID = tender.pk (integer)** — так мы можем дополнить результаты из Postgres без дополнительного mapping.

**Коллекция `doc_chunks`** — зарезервирована для RAG (день 6-7), чанки PDF документов тендеров.

---

## 7. Батчевая индексация

```python
# index_tenders --batch-size=32
texts = [tender_text(...) for t in batch]
vectors = embedder.embed_passages(texts)  # один вызов на батч
qdrant.upsert_tenders_batch([(id, vec, payload), ...])
```

**Почему батчинг важен:** ONNX Runtime эффективнее обрабатывает несколько текстов за раз (параллельно по матрицам). Батч 32 примерно в 10x быстрее чем 32 отдельных вызова.

---

## 8. Поиск: API и фильтры

```
POST /api/v1/search/
{
  "query": "поставка медикаментов для больницы",
  "limit": 20,
  "region": "Москва",
  "status": "active",
  "nmck_max": 5000000
}
```

**Как работает:**
1. `embed_query("query: поставка медикаментов для больницы")` → вектор
2. Qdrant ANN-поиск (HNSW индекс) с pre-filtering по payload
3. Результаты обогащаются из Postgres (customer FK, точные данные)
4. Возвращаются отсортированные по cosine similarity (score 0..1)

**Pre-filtering в Qdrant** — фильтры применяются ДО поиска по векторам, не после. Это эффективнее post-filtering для больших коллекций.

---

## 9. Что будет в день 6-7 (RAG для документов)

Коллекция `doc_chunks`:
- Chunk size: 512 токенов, overlap: 50 (из CLAUDE.md)
- Каждый чанк = вектор + payload `{tender_id, chunk_index, text}`
- При вопросе по тендеру → ищем релевантные чанки → передаём в Claude как контекст

Это позволит отвечать на вопросы типа "какие требования к участникам в тендере X?" по содержимому PDF документации.

---

## Потенциальные проблемы / что стоит проверить

1. **Качество русского поиска** — E5-large хороша, но стоит протестировать реальными запросами. Если плохо — переключиться на `deepvk/USER-bge-m3` (нужен PyTorch).

2. **Размерность** — в `services.py` захардкожено `EMBEDDING_DIM = 1024`. При смене модели надо пересоздать коллекцию.

3. **Синхронизация Postgres ↔ Qdrant** — сейчас `embedding_id` на тендере показывает что вектор загружен. При удалении тендера из Postgres нужно вызывать `qdrant.delete_tender(id)` (метод есть в `services.py`).

4. **Масштаб** — Qdrant HNSW хорошо работает до ~10M векторов. Для нашего объёма (тысячи-десятки тысяч тендеров) проблем нет.
