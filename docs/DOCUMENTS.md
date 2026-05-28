# Документы — apps/documents

Дата обновления: 28 мая 2026

## Модель TenderDocument

```python
tender           FK → Tender (related_name=documents)
filename         CharField(500)
file_type        CharField(20, blank)           # pdf, docx, doc, rar, zip...
s3_key           CharField(1000, unique)         # MinIO path: original/{number}/{filename}
file_size        PositiveIntegerField(default=0)
parent_document  FK self (nullable)              # для файлов из архивов
archive_path     CharField(1000, blank)          # путь внутри архива
parsed_text      TextField(blank)                # очищается TTL-очисткой
is_scanned       BooleanField(default=False)
file_hash        CharField(32, blank, db_index)  # MD5
parse_status     CharField(PENDING|PROCESSING|DONE|FAILED|SKIPPED|CLEANED, default=PENDING, db_index)
parse_error      TextField(blank)
content_priority PositiveSmallIntegerField(default=99)  # 0=ТЗ, 1=контракт, 2=требования, 3=извещение, 99=прочее
created_at       DateTimeField
parsed_at        DateTimeField(nullable)
```

## Парсеры (parsers.py)

- `parse_pdf(data)` → str (PyMuPDF)
- `parse_docx(data)` → str (python-docx)
- `parse_doc(data)` → str (fallback)
- `extract_archive(data, filename)` → list[tuple(filename, content)]
- `is_archive(filename)` → bool
- `can_parse(filename)` → bool

## Storage (storage.py) — MinIO

- `upload_file(s3_key, data)` → bool
- `download_file(s3_key)` → bytes | None
- `delete_file(s3_key)` → bool
- `delete_prefix(prefix)` → bool

## Services (services.py)

- `get_summary_context(tender, max_tokens=4000)` → dict {source, context, was_truncated...}
  - Priority-based: p0 (3000 tok) → p1 (800) → p2 (500) → max 5 docs
  - Возвращает source: "full_tz", "rag", "text", "none"
- `get_full_context(tender, max_tokens=100000)` → dict — все документы, truncation по приоритетам
- `answer_question(tender_id, question)` → dict {answer, sources, needs_reindex}
  - RAG через Qdrant doc_chunks (filter by tender_id)
  - needs_reindex: true если доки есть но чанки очищены (TTL)
- `classify_documents_priority(filenames)` → dict[filename: int] — DeepSeek / fallback GPT-4o-mini
- `count_tokens(text)` → int (cl100k_base)
- `truncate_to_tokens(text, max_tokens)` → str

## Celery Pipeline

```
download_and_parse_documents(tender_id)
  ├── download каждого файла → MinIO (s3_key=original/{number}/{filename})
  ├── создание TenderDocument записей
  └── queue parse_document для каждого

parse_document(doc_id)
  ├── определение file_type
  ├── парсинг: PDF/DOCX/archive
  ├── parsed_text + parse_status=DONE
  └── queue index_document_chunks

index_document_chunks(tender_id)
  ├── chunking: 512 токенов, overlap=50
  ├── embedding → Qdrant doc_chunks
  └── tender.docs_indexed_at = now
```

**Документы качаются ТОЛЬКО по явному запросу пользователя** (не при парсинге).

## TTL-очистка

| Задача | Расписание | Что делает |
|--------|-----------|-----------|
| `cleanup_doc_chunks` | каждый час | Удаляет чанки из Qdrant + parsed_text для тендеров с docs_indexed_at > 48ч. MinIO файлы остаются. parse_status=CLEANED |
| `cleanup_old_documents` | воскресенье 03:00 | Nuclear: MinIO + записи TenderDocument для тендеров старше 730 дней |

**Переиндексация**: `POST /api/v1/tenders/{id}/reindex-docs/` — если parsed_text есть → re-embed, если очищен → re-parse из MinIO

## Инвалидация

- ai_summary сбрасывается при новом документе (post_save сигнал)
- ai_summary НЕ удаляется при TTL-очистке
- docs_indexed_at ставится при index_document_chunks, сбрасывается при TTL-очистке
