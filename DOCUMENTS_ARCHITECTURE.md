# Documents Architecture — Tender SaaS

## Зачем это нужно

AI резюме без документов работает только на метаданных.
С документами — извлекает реальные требования, лицензии, штрафы, гарантии.
RAG через Qdrant даёт умную выборку вместо случайной обрезки текста.

---

## Три слоя хранения

```
MinIO                      Postgres                    Qdrant
──────────────────         ────────────────────        ──────────────────
tender-documents/          TenderDocument               doc_chunks
  {number}/                ├── id                      ├── vector 1024d
    original/              ├── tender_id               ├── tender_id  ← фильтр
      извещение.pdf        ├── filename                ├── document_id ← удаление
      документация.rar     ├── file_type               ├── chunk_index
      смета.xlsx           ├── s3_key                  ├── text
    extracted/             ├── parent_document_id      ├── filename
      ТЗ.pdf               ├── archive_path            └── content_priority
      контракт.docx        ├── parsed_text
                           ├── is_scanned
                           ├── file_hash (MD5)
                           ├── parse_status
                           ├── parse_error
                           ├── content_priority
                           ├── created_at
                           └── parsed_at
```

MinIO: все файлы (даже xlsx, сканы) — оригиналы всегда сохраняем.
Postgres: метаданные + parsed_text — источник правды.
Qdrant doc_chunks: чанки для RAG поиска по вопросам пользователя.

---

## Поддерживаемые форматы

| Формат | Действие |
|--------|----------|
| PDF текстовый | pymupdf → parsed_text |
| PDF скан | сохраняем, is_scanned=True, пропускаем |
| .docx | python-docx → parsed_text |
| .rar | rarfile → распаковать → парсить содержимое |
| .zip | zipfile → распаковать → парсить содержимое |
| .xlsx | сохраняем, parse_status=skipped |
| прочее | сохраняем, parse_status=skipped |

---

## content_priority — приоритет документа

GPT-4o-mini определяет приоритет по имени файла (один батч-вызов после скачивания):

```
0 — техническое задание
1 — проект контракта / договор
2 — требования к заявке / инструкция участника
3 — извещение о закупке
99 — проектная документация, сметы, титульники, приложения
```

Один вызов GPT на весь тендер (~$0.0001) — умнее regex, универсально.

---

## Два режима использования документов

### Режим А — RAG контекст для AI резюме

Умная выборка через Qdrant вместо тупой обрезки:

```python
SUMMARY_QUERIES = [
    "требования к участнику допуск квалификация",
    "срок выполнения исполнения поставки",
    "гарантийный срок качество обязательства",
    "обеспечение заявки контракта размер",
    "штрафы пени неустойка ответственность",
    "ограничения запреты условия исполнения",
    "приёмка результат передача документы",
]
# Универсальные запросы — работают для любого типа тендера

def get_summary_context(tender, max_tokens=2000) -> dict:
    # 1. Для каждого запроса — поиск в doc_chunks
    # 2. Топ-2 чанка на запрос с score > 0.3
    # 3. Дедупликация, сортировка по score
    # 4. Лимит 2000 токенов
    # 5. Fallback на parsed_text если чанков нет
    return {"context": text, "source": "rag" | "text" | "none"}
```

### Режим Б — ответы на вопросы пользователя

```
"нужна ли лицензия ФСБ?"
→ embed вопроса
→ Qdrant filter(tender_id=X), limit=5
→ топ-5 чанков
→ GPT-4o-mini
→ {answer, sources, has_docs}
```

---

## Промпт AI резюме — ключевые принципы

**Чеклист вместо категорий** — GPT получает явный список что искать:
```
□ Требования к участнику: допуск, лицензии, аттестация, квалификация
□ Срок выполнения: конкретная дата или период
□ Гарантия: срок в месяцах/годах
□ Обеспечение контракта: процент (флаг если > 15%)
□ Штрафы/пени: размер и условия
□ Ограничения: субподряд, материалы, место исполнения
□ Приёмка: особые условия, этапы, согласования
```

**Конкретные значения** — "Гарантия 5 лет", не "гарантийные обязательства".

**Красные флаги** — только из документов, не придумывать:
- Обеспечение > 15% → флаг с процентом
- Пени за каждый день → флаг с размером
- Запрет субподряда → флаг

**Тип тендера** — GPT определяет сам по названию и ОКВЭД, адаптирует извлечение.

**source в контексте** — если source="none" (нет документов) → промпт явно
указывает что анализ только по метаданным, резюме может быть неполным.

---

## Celery pipeline

```
enrich_tender(tender_id)
        ↓
download_and_parse_documents(tender_id)  ← только по запросу пользователя
        ↓
  для каждого файла:
  ├── save to MinIO (все форматы)
  ├── create TenderDocument(status=pending)
  └── parse_document.delay(doc_id)
              ↓
        parse_document(doc_id)
        ├── PDF → pymupdf
        ├── DOCX → python-docx
        ├── RAR/ZIP → распаковать → рекурсивно
        └── сохранить parsed_text, status=done
              ↓
        classify_documents_priority(tender_id)
        ← один GPT вызов на все файлы тендера
              ↓
        index_document_chunks(document_id)
        ← embed → Qdrant doc_chunks
              ↓
        invalidate_ai_summary(tender_id)
        ← Tender.ai_summary = None
```

Документы качаются только по явному запросу — не при парсинге ЕИС.

---

## Инвалидация кэша резюме

```python
@receiver(post_save, sender=TenderDocument)
def invalidate_summary_on_new_doc(sender, instance, **kwargs):
    if instance.parse_status == 'done':
        Tender.objects.filter(id=instance.tender_id).update(ai_summary=None)
```

ai_summary = None → при следующем открытии регенерируется с новыми документами.

---

## Очистка — Celery beat каждое воскресенье 3:00

```python
@shared_task
def cleanup_old_documents():
    cutoff = timezone.now() - timedelta(days=730)
    old_ids = Tender.objects.filter(deadline_at__lt=cutoff).values_list('id', flat=True)

    # Удаляем тяжёлое
    qdrant.delete("doc_chunks", filter(tender_id IN old_ids))
    minio.delete_prefix(f"tender-documents/{number}/")

    # Обнуляем текст, оставляем метаданные
    TenderDocument.objects.filter(tender_id__in=old_ids).update(
        parsed_text='', parse_status='cleaned'
    )
    # ai_summary НЕ трогаем — 500 байт, историческая ценность
```

---

## Переиндексация документа

```python
def reindex_document(document_id):
    # Сначала удалить старые чанки
    qdrant.delete("doc_chunks", filter(document_id=document_id))
    # Потом индексировать заново
    index_document_chunks(document_id)
```

document_id в каждом Qdrant payload — точечное удаление без пересборки коллекции.

---

## Стоимость

| Операция | Токены | Стоимость |
|----------|--------|-----------|
| Классификация документов (GPT) | ~200 | $0.0001/тендер |
| AI резюме с RAG контекстом | ~2500 | $0.0015 |
| Вопрос по тендеру (RAG) | ~1500 | $0.0008 |
| 1000 резюме в месяц | — | ~$1.5 |

Кэш в ai_summary — повторные просмотры бесплатны.

---

## Зависимости

```bash
pip install pymupdf python-docx rarfile tiktoken

# Docker / Dockerfile:
apt-get install -y unrar-free
```
