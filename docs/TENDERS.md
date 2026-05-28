# Тендеры — apps/tenders

Дата обновления: 28 мая 2026

## Модели

### Tender
```python
source          CharField(EIS|BIDZAAR|KOMTENDER|TENDERGURU|OTHER, default=EIS)
number          CharField(50, db_index)
title           TextField
nmck            DecimalField(18,2, nullable)
customer        FK → Customer (nullable, related_name=tenders)
region          CharField(100, blank)
okpd_codes      JSONField(default=list)
published_at    DateTimeField(nullable, db_index)
deadline_at     DateTimeField(nullable)
auction_date    DateTimeField(nullable)
status          CharField(ACTIVE|FINISHED|CANCELLED, default=ACTIVE, db_index)
law_type        CharField(44-ФЗ|223-ФЗ|615-ПП|b2b, blank, db_index)
procedure_type  CharField(AUCTION|CONTEST|REQUEST_QUOTATIONS|REQUEST_PROPOSALS|SINGLE_SOURCE|OTHER, default=OTHER, db_index)
trading_platform     CharField(500, blank)
trading_platform_url URLField(500, blank)
bid_security_amount       DecimalField(nullable)
bid_security_required     BooleanField(nullable)
contract_security_amount  DecimalField(nullable)
contract_security_percent DecimalField(6,2, nullable)
source_url      URLField(1000, blank)
raw_json        JSONField(default=dict)
ai_summary      TextField(blank)
embedding_id    UUIDField(nullable)         # = tender.pk после индексации в Qdrant
docs_indexed_at DateTimeField(nullable)     # когда doc_chunks проиндексированы
enriched_at     DateTimeField(nullable)     # null = не обогащён
content_quality SmallIntegerField(default=0, db_index)  # 0=normal, -1=TG без доков
created_at      DateTimeField
updated_at      DateTimeField
# unique_together: (number, source)
```

### Customer
```python
inn       CharField(12, db_index, unique when non-empty)
name      CharField(500)
full_name CharField(1000, blank)
region    CharField(100, blank)
created_at DateTimeField
```

### TenderPipeline
```python
user      FK → User (related_name=pipeline_entries)
tender    FK → Tender (related_name=pipeline_entries)
profile   FK → CompanyProfile (nullable, related_name=pipeline_entries)
status    CharField(NEW|STUDYING|PREPARING|SUBMITTED|WON|LOST)
notes     TextField(blank)
created_at, updated_at DateTimeField
# unique_together: (user, tender)
```

### PipelineComment
```python
pipeline_entry  FK → TenderPipeline (related_name=comments)
user            FK → User (related_name=pipeline_comments)
text            TextField
created_at      DateTimeField
```

### PipelineActivity
```python
pipeline_entry  FK → TenderPipeline (related_name=activities)
user            FK → User (related_name=pipeline_activities)
action_type     CharField(CREATED|STATUS_CHANGED|COMMENT_ADDED)
old_value       CharField(100, blank)
new_value       CharField(100, blank)
created_at      DateTimeField
```

### TenderSummaryV2
```python
tender              FK → Tender (related_name=summaries_v2)
user                FK → User (nullable, related_name=summaries_v2)
summary             JSONField(default=dict)
step_metrics        JSONField(default=dict)
total_input_tokens  PositiveIntegerField(default=0)
total_output_tokens PositiveIntegerField(default=0)
total_cost_usd      DecimalField(10,4, default=0)
generation_time_ms  PositiveIntegerField(default=0)
model               CharField(50, default=deepseek-chat)
created_at, updated_at DateTimeField
# unique_together: (tender, user)
```

### PromptTemplate
```python
name            CharField(50)
version         PositiveIntegerField(default=1)
system_prompt   TextField(blank)
user_template   TextField
description     TextField(blank)
is_active       BooleanField(default=True)
created_at      DateTimeField
# unique_together: (name, version)
```

### Experiment
```python
name        CharField(200)
description TextField(blank)
status      CharField(DRAFT|RUNNING|COMPLETED, default=DRAFT)
tender_ids  JSONField(default=list)
variants    JSONField(default=list)
created_at  DateTimeField
completed_at DateTimeField(nullable)
```

### SummaryExperiment
```python
tender              FK → Tender (related_name=summary_experiments)
experiment          FK → Experiment (nullable, related_name=runs)
variant_label       CharField(5, blank)
variant_name        CharField(100, blank)
strategy            CharField(30)
model               CharField(50, default=gpt-4o-mini)
actual_model        CharField(50, blank)
prompt_template     FK → PromptTemplate (nullable)
params              JSONField(default=dict)
input_tokens        PositiveIntegerField(default=0)
output_tokens       PositiveIntegerField(default=0)
cost_usd            DecimalField(8,6, default=0)
duration_ms         PositiveIntegerField(default=0)
was_truncated       BooleanField(default=False)
truncated_reason    CharField(50, blank)
original_total_tokens PositiveIntegerField(default=0)
result              JSONField(default=dict)
created_at          DateTimeField
```

---

## Парсеры

### eis_client.py (zakupki.gov.ru)
- `search_tenders(date_from, date_to, page, fz44, fz223, price_from, price_to)` → list[dict]
- `fetch_tender_detail(purchase_number, fallback_url)` → dict
- `fetch_day_count(day, fz44, fz223)` → int | None
- 44-ФЗ: парсинг HTML карточек, обогащение из детальной страницы
- 223-ФЗ: отдельная логика (`_fetch_tender_detail_223`)
- **Не рефакторить** — работает стабильно

### tenderguru_client.py (TenderGuru API v2.3)
- `search_tenders(f, price1, price2, actual, page)` → list[dict]
- `fetch_tender_detail(tg_id)` → dict (docsXML, productsXML, Info HTML)
- `parse_list_item(item)` → dict
- `enrich_from_detail(base, detail)` → dict
- **3-tier doc fallback**: docsXML → linksTenderXML → `_parse_docs_from_html(info_html)`
- `_parse_info_html(raw)` → dict (delivery_place, security_amount, procedure_type)
- `_parse_products(products_xml)` → list[dict]
- Junk filter: mailto ссылки, "подать предложение"
- Procedure type detection: title keywords → searchFragmentXML → Info HTML → TenderType

### komtender_client.py (komtender.ru)
- `fetch_sitemap_urls(base_url, max_pages)` → list[str]
- `parse_tender_page(url, komtender_id)` → dict | None
- Извлечение документов из JS: `_extract_documents_from_js(html, komtender_id)`

---

## Services (services.py)

- `upsert_tender(data)` → Tender — smart update, не перезаписывает enrichment fields пустыми значениями
- `compute_content_quality(data, source)` → int — EIS=0, TG с doc_files=0, TG без doc_files=-1
- `get_or_create_summary_v2(tender, user)` → dict — кэш в TenderSummaryV2
- `get_llm_client(model)` → OpenAI client — роутинг DeepSeek/OpenAI, circuit breaker
- `_CircuitBreaker` — fallback DeepSeek → gpt-4o-mini (3 failures / 60s window / 300s cooldown)
- `calculate_cost(model, input_tokens, output_tokens)` → Decimal
- `detect_procedure_type(source_url)` → ProcedureType

## Summary v2 Pipeline (summary_v2/)

- `generate_tender_summary_v2(tender_id, model, user)` → TenderSummaryV2
- 6 шагов: financial, timeline, requirements, work, customer (параллельно) + risks (последовательно, зависит от остальных)
- Контекст: `get_step_context(tender, step)` — приоритетная выборка документов по шагу (80k токенов макс)
- Дедупликация документов по имени (v1/v2, даты)
- Info HTML добавляется как доп. контекст если есть место

---

## Celery Tasks (tasks.py)

| Task | Расписание | Описание |
|------|-----------|----------|
| `enrich_tender` | countdown=5 после sync | max_retries=3, delay=60с. При финальном провале ставит enriched_at |
| `sync_active_tenders` | каждый час :00 | ЕИС по дням × ценовым диапазонам, time_limit=1800 |
| `sync_tenderguru` | каждые 2ч :15 | 5000/run, time_limit=7200 |
| `sync_komtender` | каждые 30 мин | Коммерческие тендеры с komtender.ru |
| `cleanup_finished_tenders` | воскресенье 04:00 | Помечает старые завершённые тендеры |

Автоцепочка: sync → enrich_tender (countdown=5) → embed_tender

---

## Management Commands

| Команда | Назначение |
|---------|-----------|
| `parse_eis --days=N --query=X --max-pages=M --enrich` | Одноразовый парсинг ЕИС |
| `bulk_load_tenders --days=N --delay=SEC --no-enrich` | Batch загрузка ЕИС |
| `bulk_load_tenderguru --limit=N --delay=SEC --dry-run --law=44` | Batch загрузка TenderGuru |
| `bulk_load_komtender` | Batch загрузка Komtender |
| `enrich_missing --dry-run --delay=SEC --limit=N` | Бэкфилл обогащения |
| `backfill_content_quality --dry-run --batch=500` | Пересчёт content_quality + извлечение доков из info_html |
| `run_experiment --config=*.yaml --tender-ids=1,2,3 --count=N` | A/B эксперименты |
| `normalize_regions` | Стандартизация регионов |
| `fix_customer_inns` | Валидация ИНН заказчиков |
| `reenrich_223` | Переобогащение 223-ФЗ |

---

## API Endpoints

```
GET    /api/v1/tenders/                        — список (фильтры, пагинация, сортировка)
GET    /api/v1/tenders/{id}/                   — детали
GET    /api/v1/tenders/{id}/similar/           — похожие тендеры
GET    /api/v1/tenders/{id}/summary/           — AI резюме (generate=true для генерации)
GET    /api/v1/tenders/{id}/summary/export/?type=pdf|docx
GET    /api/v1/tenders/{id}/docs/              — список документов
GET    /api/v1/tenders/{id}/download-doc/{doc_id}/
POST   /api/v1/tenders/{id}/download-docs/     — запуск загрузки
POST   /api/v1/tenders/{id}/reindex-docs/      — переиндексация
GET    /api/v1/tenders/{id}/chat/              — SSE RAG чат
GET    /api/v1/tenders/regions/                — список регионов
GET    /api/v1/tenders/okved/?q=               — поиск ОКВЭД
GET    /api/v1/tenders/customers/?q=           — поиск заказчиков
GET    /api/v1/tenders/search-won-candidates/  — аналитика побед

# Pipeline
GET    /api/v1/tenders/pipeline/               — список записей
POST   /api/v1/tenders/pipeline/               — создать
PATCH  /api/v1/tenders/pipeline/{id}/          — обновить
DELETE /api/v1/tenders/pipeline/{id}/          — удалить
GET    /api/v1/tenders/pipeline/summary/       — статистика
POST   /api/v1/tenders/pipeline/{id}/comments/ — комментарии
GET    /api/v1/tenders/pipeline/{id}/activity/ — лог активности

# Experiments
GET    /api/v1/experiments/                    — список экспериментов
GET    /api/v1/experiments/{id}/runs/          — результаты
```
