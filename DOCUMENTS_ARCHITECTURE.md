# Documents Architecture — Tender SaaS

## Зачем это нужно

AI-резюме тендера без документов работает только на метаданных (название, НМЦ, сроки).
С документами — извлекает реальные требования, лицензии, штрафы, условия.
Разница между "наличие опыта" и "СРО обязательно, опыт от 2 контрактов за 3 года".

---

## Три слоя хранения

```
MinIO                    Postgres                  Qdrant
─────────────────        ──────────────────        ──────────────────
original/                TenderDocument            doc_chunks
  {number}/              ├── id                    ├── vector 1024d
    извещение.pdf        ├── tender_id             ├── tender_id (filter)
    документация.rar     ├── filename              ├── document_id (delete)
    смета.xlsx           ├── file_type             ├── chunk_index
                         ├── s3_key                ├── text
extracted/               ├── parent_document_id    ├── filename
  {number}/              ├── archive_path          └── content_priority
    ТЗ_кровля.pdf        ├── parsed_text
    контракт.docx        ├── is_scanned
                         ├── file_hash (MD5)
                         ├── parse_status
                         ├── parse_error
                         ├── content_priority
                         ├── created_at
                         └── parsed_at
```

MinIO: оригинальные файлы сохраняем все (даже xlsx, сканы).
Postgres: метаданные + извлечённый текст — источник правды.
Qdrant doc_chunks: только для RAG (вопросы пользователя). НЕ для резюме.

---

## Поддерживаемые форматы

| Формат | Действие |
|--------|----------|
| PDF текстовый | парсим через pymupdf |
| PDF скан | сохраняем, is_scanned=True, пропускаем |
| .docx / .doc | парсим через python-docx |
| .rar | распаковываем, парсим содержимое |
| .zip | распаковываем, парсим содержимое |
| .xlsx / .xls | сохраняем, parse_status=skipped |
| прочее | сохраняем, parse_status=skipped |

---

## content_priority — приоритет для резюме

```python
PRIORITY_KEYWORDS = {
    0: ["техзадани", "тз", "задани"],        # техническое задание
    1: ["контракт", "договор"],              # проект контракта
    2: ["требовани", "документаци", "извещени"],  # требования / извещение
}
# всё остальное → 99
```

---

## Два режима использования документов

### Режим А — контекст для AI резюме (НЕ через Qdrant)

```
TenderDocument (parse_status=done, not scanned)
      ↓ order_by(content_priority)
Топ-5 документов
      ↓ clean_text() + truncate_to_tokens()
1500 токенов итого:
  техзадание:  800 токенов
  контракт:    500 токенов
  остальное:   200 токенов
      ↓
GPT-4o-mini промпт → ai_summary JSON
```

Берём напрямую из parsed_text в Postgres — быстро и без векторного поиска.

### Режим Б — ответы на вопросы пользователя (через Qdrant RAG)

```
"нужна ли лицензия ФСБ?"
      ↓
embed вопроса (multilingual-e5-large)
      ↓
Qdrant поиск с filter(tender_id=X), limit=5
      ↓
топ-5 релевантных чанков
      ↓
GPT-4o-mini: "отвечай только по документации"
      ↓
{answer, sources:[{filename, preview}], has_docs}
```

---

## Умная обрезка текста

Проблема: первые N символов документа — часто реквизиты (ИНН, КПП, ОГРН, адрес).
Решение: структурное извлечение + очистка.

```python
TOKENS_PER_PRIORITY = {
    0: 800,   # техзадание — больше всего
    1: 500,   # контракт
    2: 300,   # требования
    99: 200,  # прочее
}
MAX_TOTAL_TOKENS = 1500

def clean_text(text: str) -> str:
    # убрать строки < 10 символов
    # убрать строки только из цифр/знаков
    # убрать дублирующиеся пробелы
    # НЕ трогать содержательный текст

def get_summary_context(tender, max_tokens=1500) -> str:
    docs = get_priority_docs(tender)
    result = []
    total = 0
    for doc in docs:
        limit = min(TOKENS_PER_PRIORITY[doc.content_priority], max_tokens - total)
        if limit <= 0: break
        text = truncate_to_tokens(clean_text(doc.parsed_text), limit)
        result.append(f"[{doc.filename}]\n{text}")
        total += count_tokens(text)
    return "\n\n---\n\n".join(result)
```

---

## Celery pipeline

```
enrich_tender(tender_id)              ← уже работает
        ↓
download_and_parse_documents(tender_id)  ← новый task
        ↓
  для каждого файла:
  ├── save to MinIO (все форматы)
  ├── create TenderDocument(status=pending)
  └── parse_document.delay(doc_id)
              ↓
        parse_document(doc_id)
        ├── PDF → pymupdf extract_structured_text()
        ├── DOCX → python-docx
        ├── RAR/ZIP → распаковать → рекурсивно
        ├── SKIP → status=skipped
        └── сохранить parsed_text, status=done
              ↓
        все документы done?
              ↓
        invalidate_ai_summary(tender_id)
        (Tender.ai_summary = None → перегенерится при следующем открытии)
```

Каждый документ парсится независимо — если один упал, остальные продолжают.

---

## Инвалидация кэша резюме

```python
# apps/documents/signals.py
@receiver(post_save, sender=TenderDocument)
def invalidate_summary_on_new_doc(sender, instance, **kwargs):
    if instance.parse_status == 'done':
        Tender.objects.filter(id=instance.tender_id).update(ai_summary=None)
```

ai_summary генерируется заново при следующем открытии тендера.
Хранить пустой кэш нормально — это 500 байт JSON.

---

## Очистка старых данных — Celery beat еженедельно

```python
@shared_task
def cleanup_old_documents():
    """Запускать каждое воскресенье в 3:00"""
    cutoff = timezone.now() - timedelta(days=730)  # 2 года

    old_ids = list(Tender.objects.filter(
        deadline_at__lt=cutoff
    ).values_list('id', flat=True))

    if not old_ids:
        return "nothing to clean"

    # 1. Удалить чанки из Qdrant одной операцией
    qdrant.delete("doc_chunks", filter(tender_id IN old_ids))

    # 2. Удалить файлы из MinIO
    for tender in Tender.objects.filter(id__in=old_ids):
        minio.remove_prefix(f"tender-documents/{tender.number}/")

    # 3. Обнулить текст в Postgres (метаданные и ai_summary оставить)
    TenderDocument.objects.filter(tender_id__in=old_ids).update(
        parsed_text='',
        parse_status='cleaned',
    )

    return f"cleaned {len(old_ids)} tenders"
```

**Что удаляем:** векторы в Qdrant, файлы в MinIO, parsed_text в Postgres.
**Что оставляем:** метаданные TenderDocument, ai_summary на Tender (500 байт, полезно).

---

## Переиндексация документа (при необходимости)

```python
def reindex_document(document_id: int):
    # Сначала удалить старые чанки
    qdrant.delete("doc_chunks", filter(document_id=document_id))
    # Потом индексировать заново
    parse_and_index_document(document_id)
```

Ключевой принцип: document_id в каждом Qdrant payload
→ можно точечно удалить и переиндексировать без пересборки коллекции.

---

## Endpoint для вопросов

```
POST /api/v1/tenders/{id}/ask/
Body: {question: str}

Response:
{
  data: {
    answer: "Да, требуется членство в СРО...",
    sources: [
      {filename: "техзадание.pdf", chunk_index: 3, preview: "..."}
    ],
    has_docs: true
  },
  error: null
}

Если документов нет:
{data: {answer: null, has_docs: false}, error: null}
```

---

## Зависимости

```
pip install pymupdf python-docx rarfile tiktoken

# В Dockerfile / docker-compose:
apt-get install -y unrar-free
```

---

## Стоимость

| Операция | Токены | Стоимость |
|----------|--------|-----------|
| AI резюме с документами | ~2100 | $0.001 |
| Вопрос по тендеру (RAG) | ~1500 | $0.0008 |
| 1000 резюме в месяц | — | ~$1 |
| 5000 вопросов в месяц | — | ~$4 |

Кэширование ai_summary в Postgres — повторные просмотры бесплатны.
