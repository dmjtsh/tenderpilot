# Tender SaaS — Claude Code Instructions

## Project overview
AI-powered tender discovery platform for Russian public procurement (44-ФЗ, 223-ФЗ, 615-ПП).
Stack: Django 5 + DRF · Next.js 14 · Postgres · Qdrant · MinIO · Celery + Redis · OpenAI API

## Architecture
```
/backend
  /apps
    /tenders      — парсинг ЕИС, модели тендеров, справочник ОКВЭД, pipeline
    /search       — embedding, Qdrant, HyDE, матчинг
    /documents    — PDF парсинг, RAG, очистка (см. DOCUMENTS_ARCHITECTURE.md)
    /users        — авторизация, CompanyProfile, CompanyDirection
    /billing      — тарифы, ЮКасса (не реализовано)
    /alerts       — мониторинг пайплайна, Telegram алерты, PipelineRun
  /config         — settings, urls, celery
/frontend
  /app            — Next.js App Router pages
  /components     — UI компоненты
  /lib            — API клиент, типы
  /b_cTFNgcyL3L3  — лендинг (старая копия, не трогать)
/infra            — docker-compose, nginx, .env.example
```

---

## Что сделано

### Бэкенд

- **Парсер ЕИС** (`apps/tenders/eis_client.py`)
  - `search_tenders()` — список тендеров: `--days`, `--fz`, `--query`, `--max-pages`
  - `fetch_tender_detail()` — детальное обогащение одного тендера
  - Команда: `python manage.py parse_eis --days=30 --query="кровля" --enrich`
  - **Важно**: фильтрация по региону через GET НЕ РАБОТАЕТ (AJAX-виджет). Обход: `--query` с ключевым словом региона.

- **Справочник ОКВЭД** (`apps/tenders/okved.py`)
  - `OKVED_NAMES` — dict 2773 кодов
  - `okved_to_text(codes)` — коды → читаемые названия через запятую

- **Семантический поиск** (`apps/search/`)
  - Embedding: `multilingual-e5-large` через fastembed (ONNX, CPU, ~450MB, singleton)
  - `tender_text(tender)` — ТОЛЬКО title + ОКВЭД названия (чистая семантика, без метаданных)
  - Архитектура: вектор = семантика (title + ОКПД). Всё остальное (регион, закон, НМЦ, площадка, дедлайн) = Qdrant payload фильтры + DB фильтры
  - Ранжирование: чистый cosine similarity, без Smart Score
  - Qdrant коллекция `tenders`, cosine similarity
  - `POST /api/v1/search/` — семантический поиск
  - `GET /api/v1/search/match/` — матчинг под профиль
  - `GET /api/v1/tenders/customers/?q=` — поиск заказчиков (name icontains / INN startswith)

- **HyDE** (`apps/search/hyde.py`)
  - DeepSeek → 5 синтетических текстов в формате tender_text ("Title. Вид работ: ОКПД.")
  - Усреднение эмбеддингов → profile_vector
  - GPT может возвращать JSON в ```json``` блоке — парсинг обходит это

- **CompanyDirection** (`apps/users/models.py`)
  - okved_codes, keywords, regions, nmck_min/max, law_types, procedure_types
  - content_hash + needs_reindex() для debounce
  - post_save → Celery task rebuild_direction_vector (countdown=30, фиксированный task_id)
  - **Важно**: CompanyProfile.description НЕ используется в HyDE — откачено, размывает специфику направлений

- **match_profile** (`apps/search/services.py`)
  - Итерирует по направлениям с profile_vector
  - Payload-фильтры Qdrant: region, nmck, law_type, procedure_type, status, deadline_at_ts
  - Берёт max score среди направлений, поддерживает direction_ids
  - limit=100 per direction, возвращает до limit*10 для пагинации

- **Scoring** (`apps/search/scoring.py`)
  - Только `score_label(cosine)` — конвертирует cosine в текстовую метку
  - "Отличное совпадение" (≥0.82), "Хорошее" (≥0.75), "Среднее" (≥0.65), "Слабое" (<0.65)
  - Smart Score удалён — чистый cosine достаточен при правильных фильтрах

- **Pipeline exclusion** (views.py TenderMatchView)
  - Тендеры в статусах studying/preparing/submitted исключаются из "Для вас"

- **Backfill Qdrant payload** (`apps/search/management/commands/reindex_payloads.py`)
  - Добавляет procedure_type + deadline_at_ts в payload без пересчёта вектора
  - `python manage.py reindex_payloads [--dry-run] [--batch=1000] [--limit=N]`

- **DaData** (`apps/users/dadata.py`)
  - `enrich_company_by_inn(inn)` → name, region, okved_main, okved_list
  - `POST /api/v1/users/lookup-inn/`
  - Примечание: okveds в DaData часто пустой, только основной ОКВЭД

- **ОКВЭД поиск**: `GET /api/v1/tenders/okved/?q=` — до 20 результатов

- **Авторизация**: JWT, `/api/v1/users/auth/token/`, `/api/v1/users/register/`

- **Модуль documents** (`apps/documents/`) — см. DOCUMENTS_ARCHITECTURE.md
  - TenderDocument модель — хранение файлов, статусы парсинга
  - MinIO интеграция — upload/download/delete
  - Парсеры: pymupdf (PDF), python-docx (DOCX), rarfile/zipfile (архивы)
  - Celery pipeline: download → parse → classify → index → invalidate
  - get_summary_context() — RAG выборка через Qdrant для AI резюме
  - classify_documents_priority() — GPT определяет приоритет по имени файла
  - **TTL-очистка doc_chunks** (`cleanup_doc_chunks`) — каждый час, удаляет чанки из Qdrant + parsed_text из Postgres для тендеров где `docs_indexed_at` старше 48ч (`DOC_CHUNKS_TTL_HOURS=48`)
  - cleanup_old_documents() — Celery beat каждое воскресенье (nuclear: 730 дней, MinIO + записи)
  - **Переиндексация**: `POST /api/v1/tenders/{id}/reindex-docs/` — если parsed_text есть → re-embed, если очищен → re-parse из MinIO

- **AI резюме v2** (`apps/tenders/summary_v2/pipeline.py`) — v1 удалён
  - `generate_tender_summary_v2(tender_id)` — 6 параллельных LLM шагов (financial, timeline, requirements, work, customer, risks)
  - `get_or_create_summary_v2(tender)` — кэш в TenderSummaryV2, требует документы
  - Данные заказчика: RusProfile (через прокси) + DaData → hardcode в customer_analysis
  - Числовые значения копировать ТОЧНО как в документах (не конвертировать)
  - `GET /api/v1/tenders/{id}/summary/`
  - **Экспорт PDF/DOCX** (`apps/tenders/summary_export.py`)
    - `render_summary_pdf(tender, summary)` — reportlab + DejaVuSans TTF (кириллица)
    - `render_summary_docx(tender, summary)` — python-docx
    - `_sections(summary)` — общий обход JSON, items = `(label, str)` или `(label, list[str])` для буллетов
    - Подзаголовки для списков (Состав работ, Результаты, Оборудование, ПО, Допуск, Документы, Ограничения, Риски по категориям)
    - `GET /api/v1/tenders/{id}/summary/export/?type=pdf|docx`
    - **Важно**: параметр `type`, не `format` — DRF перехватывает `format` для content negotiation

- **A/B эксперименты** (`apps/tenders/`)
  - Модели: PromptTemplate, Experiment, SummaryExperiment
  - get_llm_client(model) — роутинг OpenAI/DeepSeek по префиксу модели
  - generate_summary_with_variant(tender, variant) — universal experiment runner
  - run_experiment_batch(experiment) — batch runner с txt отчётами
  - `python manage.py run_experiment --config=*.yaml [--tender-ids=1,2,3]`
  - API: `GET /api/v1/experiments/`, `GET /api/v1/experiments/{id}/runs/`
  - Reasoning модели (gpt-5, o-series): max_completion_tokens=16384, temperature=1

- **RAG вопросы** (`apps/documents/services.py`)
  - answer_question(tender_id, question) — поиск в doc_chunks + GPT
  - Возвращает полный текст чанков + document_id для цитирования
  - `needs_reindex: true` если доки есть но чанки очищены (TTL) — фронтенд показывает кнопку переиндексации
  - `POST /api/v1/tenders/{id}/ask/`

- **Мониторинг пайплайна** (`apps/alerts/`)
  - `PipelineRun` модель — лог каждого запуска задачи (task_name, status, stats JSON, duration_ms)
  - `send_telegram()` — отправка через requests.post к Telegram Bot API
  - `log_pipeline_run()` — создаёт PipelineRun + проверяет critical alerts
  - `check_critical_alerts()` — sync failure, 0 new 3 раза подряд, 5 enrich failures, truncation
  - Дедупликация алертов: `_should_alert(key)` с cooldown 1 час
  - `check_pipeline_health` — каждые 15 мин, алерт если sync не запускался >2ч
  - `send_morning_digest` — 09:00 MSK, сводка за 24ч: sync/enrich/БД/покрытие ЕИС/recover
  - `recover_failed_tenders` — 04:00 MSK, подбирает необогащённые (≤500) и без embedding (≤1000)

- **Обогащение тендеров** (`apps/tenders/tasks.py`)
  - `enrich_tender` — Celery task, max_retries=3, delay=60с. При финальном провале ставит enriched_at
  - `enrich_missing` — management команда для batch бэкфилла (sync, не async)
  - `upsert_tender` — защита от затирания: enrichment fields не перезаписываются пустыми значениями
  - `enriched_at` на модели Tender — null значит не обогащён

- **Sync с ценовыми диапазонами** (`apps/tenders/tasks.py`)
  - `sync_active_tenders` — каждый час, итерирует по дням × ценовым диапазонам
  - 44-ФЗ: 5 диапазонов (≤100к, 100к-500к, 500к-1млн, 1-5млн, 5млн+)
  - 223-ФЗ: 1 проход без ценового фильтра
  - Smart stopping: STOP_AFTER=3 consecutive pages с 0 new
  - Truncation alert если проход ≥100 страниц (лимит ЕИС)
  - DAYS_LOOKBACK=5, time_limit=1800

- **Bulk load** (`apps/tenders/management/commands/bulk_load_tenders.py`)
  - Одноразовая загрузка за N дней с разбивкой по ценам
  - `python manage.py bulk_load_tenders --days=90 --delay=0.5`

### Фронтенд

#### Дизайн-система
- **Лендинг** (`/frontend/components/landing/`): белая тема, Stripe/Minerva стиль
- **Приложение** (`/app`): светлая тема, Linear.app стиль
- Tailwind v3 (не v4 — shadcn генерирует v4-синтаксис)
- **Логотип**: `pilot_logo.png` → `/frontend/public/logo.png` + `/frontend/app/icon.png` (favicon с закруглёнными углами через PIL)
- Все логотипы используют `<Image src="/logo.png" className="rounded-xl">` (28x28 основные, 26x26 логин)

#### Цветовая схема приложения
```
Background:  white / gray-50 (#FAFAFA)
Cards:       white, border gray-200
Accent:      violet-600 (#7C3AED) — score, direction badges, кнопки фильтров
Text:        gray-900 (#111827) primary, gray-500 secondary
Direction buttons active: bg-violet-100 border-violet-300 text-violet-800
"Все" button active: bg-[#111827] text-white
```

#### Цветовая схема лендинга (светлая)
```
Background:  white (#FFFFFF)
Cards:       gray-50 (#F9FAFB), border gray-200
Accent:      black (#111827) для кнопок
Text:        gray-900 (primary), gray-500 (secondary)
Highlight:   violet-600 — только для акцентов, не доминирует
```

#### Страницы приложения
- `/login` — авторизация + регистрация
- `/tenders` — лента (табы: Все / Для вас), фильтр по направлениям с violet-кнопками
- `/tenders/[id]` — детальная страница тендера с AI-резюме, документами, RAG-чатом с цитатами
- `/profile` — профиль компании с направлениями, анимация fade-in
- `/pipeline` — kanban-доска тендеров со статусами участия (новый/изучаю/готовлю/подал/выиграл/проиграл)

#### Лендинг (`/frontend/components/landing/`)
- `Navbar` — auth-aware (показывает "Личный кабинет" когда авторизован), breakpoint sm
- `Hero` — staggered `animate-hero` анимации, `hero.png` справа + статистика столбиком слева
- `Features` — scroll-анимации (left/right чередование) через IntersectionObserver
- `FAQ` — оригинальная 2x2 сетка карточек (не стандартный аккордеон), `grid-rows-[1fr]/[0fr]` анимация
- `CTA` — скрывается когда пользователь авторизован
- `Footer` — логотип + ссылки

#### Компоненты
- `TenderCard` — карточка тендера, cosine score + score_label, фиксированные колонки с "—" fallback
- `OkvedCombobox` — топ-20 популярных при открытии, поиск без минимума
- `InnSuggestPanel` — автозаполнение по ИНН + чекбоксы направлений
- `DirectionCard` — форма направления (ОКВЭД, НМЦ presets, 44/223/615)
- `DocumentsBlock` — загрузка документов, polling статусов
- `AiSummaryBlock` — резюме с прогрессом, бейдж "На основе документов", кнопки экспорта PDF (красная) / DOCX (синяя)
- `TenderChat` — RAG чат, история в сессии (не в БД)
- `SourceCitation` — цитата из документа в RAG-ответе (expand/collapse, violet border-left)
- `PipelineStatusButtons` — кнопки статусов на странице тендера
- `PipelineKanban` — kanban-доска на странице /pipeline
- `useScrollAnimation` hook — IntersectionObserver для scroll-анимаций лендинга

#### CSS-анимации (`globals.css`)
- `scroll-hidden` / `scroll-visible` — fade-up при скролле
- `scroll-hidden-left` / `scroll-hidden-right` — directional slide-in
- `scroll-hidden-scale` — scale-up при скролле
- `.stagger-1..6` — задержки для каскадных анимаций
- `.animate-hero` — entrance для hero секции
- `.btn-hover-lift` — подъём кнопок при hover
- Глобальный `cursor: pointer` для button/a/[role="button"] (Tailwind v3 preflight fix)
- `@media (prefers-reduced-motion: reduce)` — accessibility

#### Ключевые фиксы — не трогать
- `frontend/app/providers.tsx` — `useState(() => new QueryClient())` намеренно
- `frontend/components/Shell.tsx` — `mounted` state намеренный (hydration fix)
- 401 interceptor только при наличии токена
- Таб "Для вас" персистится в URL (`?tab=match`)
- Cursor pointer через global CSS — Tailwind v3 preflight ставит `cursor: default` на кнопки

### Данные (прод, 16 мая 2026)
- ~133k тендеров (active: 58.9k 44-ФЗ + 15k 223-ФЗ ≈ 74k active)
- 100% обогащены (enriched_at IS NOT NULL для всех active)
- Embedded: 32% (44-ФЗ), 19% (223-ФЗ) — Qdrant содержит ~24k векторов active
- Sync покрывает ~100% ЕИС (ценовые диапазоны)
- Bidzaar отключён (239 тендеров, не обогащаются)

### Покрытие полей (прод, active тендеры)
| Поле | 44-ФЗ (58.9k) | 223-ФЗ (15k) |
|------|---------------|---------------|
| НМЦ | 100% | 99.3% |
| Регион | 100% | 99.4% |
| ОКПД | 100% | 0% (!) |
| Дедлайн | 100% | 98.9% |
| Тип процедуры (не other) | 100% | 85.1% |
| Площадка | 100% | 96.4% |
| Обеспечение заявки (bool) | 66.4% | 0% |
| Обеспечение заявки (сумма) | 47.4% | 0% |
| Обеспечение контракта (%) | 89.8% | 0% |
| Обеспечение контракта (сумма) | 33.5% | 0% |
| Дата аукциона | 65.6% | 96.6% |
| Заказчик | 100% | 100% |

**Не парсится с ЕИС**: аванс, срок выполнения, преференции СМП/СОНО, антидемпинг, тип заказчика

---

## Не трогать — работает
- `apps/tenders/eis_client.py` — не рефакторить
- `apps/search/embedder.py` — singleton намеренный (модель ~450MB)
- `apps/tenders/services.py:MODEL_PRICING` — обновлять только при изменении тарифов провайдеров
- `apps/customers/services/rusprofile.py` — работает через прокси (RUSPROFILE_PROXY_URL)
- `frontend/app/providers.tsx` — см. выше
- `frontend/components/Shell.tsx` — см. выше
- Tailwind v3 — не обновлять

---

## MCP Tools

### postgres-mcp ✓
Использовать перед любым ORM запросом — проверить реальную схему.

### qdrant ✓
http://localhost:6333
Коллекции:
- `tenders` — векторы тендеров для матчинга
  payload: {number, title, nmck, customer_name, region, law_type, status, published_at, procedure_type, deadline_at_ts}
  фильтры в match_profile: status=active, deadline_at_ts>now, region MatchAny, nmck Range, law_type MatchAny, procedure_type MatchAny
- `doc_chunks` — RAG чанки документов
  payload: {tender_id, document_id, chunk_index, text, filename, content_priority}
- **mmap включён** для обеих коллекций (memmap_threshold=10000, on_disk HNSW) — векторы на диске, ОС кеширует в RAM

### sequential-thinking ✓
Обязательно для проектирования, архитектурных решений, сложных багов.
Вызов: "Используй sequential thinking. Задача: ..."

### filesystem ✓
`/Users/dmitriyshutov/Desktop/tender_pilot`
Всегда читать файл перед редактированием.

### memory ✓
Сохранять важные архитектурные решения между сессиями.

### fetch (опционально)
Чтение внешних URL — документация, API specs.

---

## Celery beat расписание

| Задача | Расписание | Описание |
|--------|-----------|----------|
| `sync_active_tenders` | каждый час :00 | Парсинг ЕИС по дням × ценовым диапазонам |
| `check_pipeline_health` | каждые 15 мин | Алерт если sync не запускался >2ч |
| `cleanup_doc_chunks` | каждый час | TTL-очистка чанков документов (48ч) |
| `recover_failed_tenders` | 04:00 MSK | Ночной подбор упавших enrich/embed |
| `send_morning_digest` | 09:00 MSK | Telegram сводка за 24ч |
| `cleanup_old_documents` | воскресенье 03:00 | Удаление документов старше 730 дней |

Автоматическая цепочка: sync → enrich_tender (countdown=5) → embed_tender

---

## Продакшн

- Сервер: Ubuntu 22.04, `root@147.45.141.195`
- Путь: `/opt/tenderpilot` (venv в `/opt/tenderpilot/venv/`, не в backend/)
- Деплой: `./deploy.sh` (git pull, pip install, migrate, build, systemd restart)
- Сервисы: gunicorn, celery worker, celery beat, next.js (systemd)
- Долгие задачи: tmux (`tmux new -s bulk`, `tmux attach -t bulk`)
- Django shell на проде: `cd /opt/tenderpilot/backend && python manage.py shell` (после `source ../venv/bin/activate`)
- psql НЕ установлен — SQL только через Django `connection.cursor()`
- **Важно**: `ROUND(PERCENTILE_CONT(...)::numeric, N)` — нужен cast, иначе ошибка на psycopg3

### Деплой с переиндексацией (май 2026)

После архитектурных изменений (tender_text, HyDE, scoring) нужна полная переиндексация:

```bash
# 1. Деплой кода
./deploy.sh  # git pull, pip install, migrate, npm build, restart

# 2. Переиндексация тендеров в Qdrant (tmux!)
tmux new -s reindex
cd /opt/tenderpilot/backend && source ../venv/bin/activate
python manage.py index_tenders
# ~18.6k active с embedding, ~450/мин ≈ 40 минут

# 3. Переиндексация направлений (HyDE промпт изменился)
python manage.py shell -c "
from apps.search.tasks import rebuild_direction_vector
from apps.users.models import CompanyDirection
for d in CompanyDirection.objects.all():
    rebuild_direction_vector(d.id)
    print(f'rebuilt {d.id} {d.name}')
"
# ~5 направлений × 15 сек = ~1 мин

# 4. Проверка
# - GET /api/v1/search/match/?profile_id=X → data не пустой
# - Qdrant scroll → проверить deadline_at_ts в payload
```

---

## Critical rules

### Перед кодом
1. Прочитай файл через filesystem
2. Проверь схему через postgres-mcp
3. Для сложных задач — sequential thinking сначала

### Django
- API только через DRF
- Модели только в `apps/*/models.py`
- Бизнес-логика только в `services.py`
- Celery tasks только в `tasks.py`
- Секреты через `django.conf.settings`
- Миграции только через `makemigrations`
- Type hints везде
- venv: `backend/.venv/bin/python`

### API
- Endpoints: `/api/v1/...`
- Ответ: `{data: ..., error: null}` или `{data: null, error: "..."}`
- Пагинация: page_size=20
- Auth: JWT Bearer token

### AI / ML
- HyDE вызовы через `apps/search/hyde.py`
- GPT JSON — всегда зачищать ```json``` блок перед json.loads
- LLM результаты кэшировать в Postgres
- Embedding: `multilingual-e5-large` через fastembed (не менять)
- Debounce векторов: countdown=30, фиксированный task_id
- **НЕ добавлять description в HyDE** — проверено, размывает вектора (компания описывает ВСЕ направления, а вектор для ОДНОГО)

### Documents (полная архитектура в DOCUMENTS_ARCHITECTURE.md)
- Документы качаются ТОЛЬКО по явному запросу пользователя
- Режим А (резюме): get_summary_context() → RAG через Qdrant doc_chunks
- Режим Б (вопросы): answer_question() → RAG с filter(tender_id)
- SUMMARY_QUERIES универсальные — без привязки к сфере
- document_id в каждом Qdrant payload — для точечного удаления
- Инвалидация ai_summary при новом документе (post_save сигнал)
- ai_summary НЕ удалять при очистке
- **TTL-очистка (48ч)**: cleanup_doc_chunks каждый час — Qdrant doc_chunks + parsed_text. MinIO файлы остаются для re-parse
- **Nuclear-очистка (730 дней)**: cleanup_old_documents — MinIO + записи TenderDocument
- `docs_indexed_at` на Tender — ставится при index_document_chunks, сбрасывается при TTL-очистке

### AI резюме промпт
- Структурированный JSON v2: customer_analysis, work_description, key_risks, required_documents
- Числовые значения ТОЧНО как в документах — не конвертировать
- Тип тендера LLM определяет сам
- Обеспечение > 15% → financial_risks с точным процентом
- source="none" → предупреждение что только метаданные
- Промпт хранится в PromptTemplate "summary_v1" в БД

### Pipeline
- Один статус на пару (user, tender) — unique_together
- Статусы: new / studying / preparing / submitted / won / lost
- Pipeline показывается на странице тендера и на отдельной /pipeline
- Метрика "сумма в работе" — sum НМЦ для статусов studying/preparing/submitted
- Метрика "выиграно" — sum НМЦ для статуса won (для дашборда инвесторов)

### Frontend — дизайн
- Лендинг (`/frontend/components/landing/`): светлая тема, Stripe/Minerva стиль
- Приложение (`/app`): светлая тема, Linear стиль
- При редизайне — брать токены из светлой схемы (white/gray-50/gray-200/violet-600)
- React Query v5: `isLoading = isPending && isFetching`
- Типы из `frontend/lib/api.ts`
- DRF ListCreateAPIView: `r.data.results ?? r.data`
- DocumentsBlock и AiSummaryBlock: один React Query ключ для /docs/

### Никогда
- Бизнес-логику в views
- Синхронные HTTP в Celery tasks
- PDF локально — только MinIO
- N+1 запросы — select_related/prefetch_related
- Коммитить .env
- Писать код не прочитав файл
- Автоматически качать документы при парсинге ЕИС
- Менять тему лендинга на тёмную
- Менять тему приложения на тёмную

---

## Key models

```python
Tender: id, number, title, nmck, customer, region, okpd_codes,
        published_at, deadline_at, auction_date, status,
        law_type, procedure_type, trading_platform, trading_platform_url,
        bid_security_amount, bid_security_required,
        contract_security_amount, contract_security_percent,
        source_url, raw_json, ai_summary, embedding_id,
        docs_indexed_at, enriched_at
        # enriched_at — когда обогащён (null = не обогащён)
        # embedding_id — UUID после индексации в Qdrant (null = не проиндексирован)
        # unique_together: (number, source)

Customer: id, inn, name, region, full_name

CompanyProfile: id, user, name, inn, description, okved_codes, regions, keywords
                # UI профиля: только name + inn (описание/оквэд/регионы/ключевые слова — legacy, не в UI)

CompanyDirection: id, profile, name, okved_codes, keywords,
                  regions, nmck_min, nmck_max, law_types, procedure_types,
                  hyde_texts, profile_vector, content_hash,
                  vector_updated_at, created_at, updated_at
                  # regions: ArrayField — фильтр Qdrant MatchAny
                  # procedure_types: ArrayField — фильтр Qdrant MatchAny (добавлен май 2026)
                  # profile_vector: 1024-dim, multilingual-e5-large
                  # content_hash: SHA256[:16] от {name, okved, keywords, regions, nmck, law_types, procedure_types}

TenderDocument: id, tender, filename, file_type, s3_key, file_size,
                parent_document (FK self, nullable), archive_path,
                parsed_text, is_scanned, file_hash,
                parse_status (pending/processing/done/failed/skipped/cleaned),
                parse_error, content_priority (0-99),
                created_at, parsed_at

TenderPipeline: id, user, tender, status, notes,
                created_at, updated_at
                # status: new / studying / preparing / submitted / won / lost
                # unique_together: (user, tender)

PromptTemplate: id, name, version, system_prompt, user_template,
                description, is_active, created_at
                # unique_together: (name, version)

Experiment: id, name, description, status (draft/running/completed),
            tender_ids (JSONField), variants (JSONField),
            created_at, completed_at

SummaryExperiment: id, tender, experiment (nullable FK), variant_label,
                   variant_name, strategy, model, actual_model,
                   prompt_template (FK), params, input_tokens,
                   output_tokens, cost_usd, duration_ms,
                   was_truncated, truncated_reason,
                   original_total_tokens, result (JSONField),
                   created_at

PipelineRun: id, task_name, status (ok/partial/failed),
             started_at, finished_at, duration_ms,
             stats (JSONField), error_message
             # task_name: sync_active_tenders, enrich_tender,
             #   embed_tender, cleanup_doc_chunks,
             #   cleanup_old_documents, recover_failed_tenders

TenderMatch: id, profile, tender, score, notified_at
Subscription: id, user, plan (free/solo/team), expires_at
```

---

## LLM модели

Дефолтная модель для AI-резюме: **DeepSeek V4 Flash** (alias `deepseek-chat`, deprecation 24 июля 2026 — после этой даты использовать `deepseek-v4-flash`).

Цены (актуально на май 2026, $/1M токенов):
| Модель | Input | Output | Назначение |
|--------|-------|--------|------------|
| deepseek-chat / deepseek-v4-flash | $0.14 | $0.28 | AI-резюме (дефолт) |
| gpt-4o-mini | $0.15 | $0.60 | классификация документов, fallback |
| gpt-4o | $2.50 | $10.00 | резерв на премиум задачи |
| gpt-5-nano | $0.05 | $0.40 | reasoning, не подходит для extraction |

Стратегия контекста: **Full** (все документы целиком, truncation если >100k токенов по приоритетам 99→3→2→1).

### Результаты экспериментов (май 2026)

- **RAG vs Full**: Full побеждает на средних/больших тендерах (полнее извлекает риски, документы, условия). RAG теряет контекст. Выбран Full как дефолт.
- **DeepSeek V4 Flash vs GPT-4o-mini**: DeepSeek качественнее (детальнее, конкретные числа, ссылки на статьи закона). Output ~1090 vs ~280 токенов. Цена сравнима ($0.005 vs $0.002/запрос).
- **DeepSeek V4 Flash vs GPT-5 Nano**: Nano проигрывает по UX (47с vs 15с из-за reasoning tokens ~5000), пропускает риски, выдаёт общие формулировки. Reasoning модели не подходят для structured extraction.

### A/B платформа

Модели: `Experiment`, `SummaryExperiment`, `PromptTemplate` в `apps/tenders/models.py`.
Запуск: `python manage.py run_experiment --config=*.yaml [--tender-ids=1,2,3] [--count=10]`.
API: `GET /api/v1/experiments/` — доступ для is_authenticated, запуск (POST run) только для is_staff.
YAML конфиги в `backend/experiment_*.yaml`.

---

## Environment variables
```
DATABASE_URL=postgresql://tender_user:tender_pass@localhost:5432/tenders
QDRANT_URL=http://localhost:6333
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=tender_admin
MINIO_SECRET_KEY=tender_secret_123
REDIS_URL=redis://localhost:6379
OPENAI_API_KEY=...             # HyDE, классификация, fallback для резюме
DEEPSEEK_API_KEY=...           # AI-резюме (дефолт)
DADATA_TOKEN=...               # автозаполнение по ИНН
TELEGRAM_BOT_TOKEN=...         # Telegram bot для алертов
TELEGRAM_ADMIN_CHAT_ID=...     # chat_id для Telegram алертов
RUSPROFILE_PROXY_URL=...       # прокси для RusProfile (http://user:pass@host:port)
YUKASSA_SHOP_ID=...
YUKASSA_SECRET_KEY=...
```

---

## Commands

```bash
# Инфраструктура
docker compose up -d

# Бэкенд
cd backend
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver 8080
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/celery -A config worker -l info -Q celery,high_priority

# Фронтенд
cd frontend && npm run dev

# Парсинг
python manage.py parse_eis --days=30 --query="кровля" --max-pages=20 --enrich

# Bulk load (одноразовый, подтягивает все тендеры за N дней)
python manage.py bulk_load_tenders --days=90 --delay=0.5
python manage.py bulk_load_tenders --days=7 --no-enrich  # без обогащения

# Бэкфилл обогащения (необогащённые тендеры)
python manage.py enrich_missing --dry-run          # посмотреть счётчики
python manage.py enrich_missing --delay=0.5        # обогатить все
python manage.py enrich_missing --limit=100        # обогатить 100

# Индексация тендеров в Qdrant
python manage.py index_tenders
python manage.py index_tenders --only-new          # только без embedding_id

# Backfill Qdrant payload (procedure_type + deadline_at_ts без пересчёта вектора)
python manage.py reindex_payloads --dry-run
python manage.py reindex_payloads --batch=1000

# A/B эксперимент
python manage.py run_experiment --config=experiment_models.yaml --tender-ids=1082,1148,2458 --count=5

# Тест Telegram алертов
python manage.py shell -c "from apps.alerts.telegram import send_telegram; print(send_telegram('test'))"

# Тест утреннего дайджеста
python manage.py shell -c "from apps.alerts.tasks import send_morning_digest; send_morning_digest()"

# Принудительная переиндексация направлений
python manage.py shell -c "
from apps.search.tasks import rebuild_direction_vector
from apps.users.models import CompanyDirection
for d in CompanyDirection.objects.filter(profile_vector__isnull=True):
    rebuild_direction_vector(d.id)
    print(f'rebuilt {d.id} {d.name}')
"
```

---

## Custom commands (.claude/commands/)
```
/new-endpoint       — новый Django REST endpoint
/new-celery-task    — новая Celery задача
/debug              — отладка: логи + БД + очередь
/review             — code review на нарушения правил
```

---

## Roadmap

### Сделано
- [x] Справочник ОКВЭД (2773 кода)
- [x] Обогащённый tender_text()
- [x] CompanyDirection + HyDE + debounce
- [x] Payload фильтры Qdrant (НМЦ, регион, закон)
- [x] Фронт — направления, ОКВЭД combobox, НМЦ presets
- [x] DaData автозаполнение по ИНН
- [x] Фильтр по направлениям в "Для вас"
- [x] TenderDocument модель + MinIO + парсеры PDF/DOCX/RAR/ZIP
- [x] Celery pipeline: download → parse → classify → index → invalidate
- [x] AI резюме v2 (DeepSeek V4 Flash, Full context, structured JSON)
- [x] A/B эксперименты: платформа, YAML конфиги, side-by-side UI
- [x] DocumentsBlock + AiSummaryBlock на странице тендера
- [x] RAG чат по тендеру (TenderChat)
- [x] Очистка старых документов (Celery beat)
- [x] Лендинг белая тема (Stripe/Minerva стиль)
- [x] Редизайн фильтра направлений (violet кнопки, "Все" toggle)
- [x] Связка лендинг ↔ приложение (CTA → /login, auth-aware navbar)
- [x] Scroll-анимации лендинга
- [x] Hero, FAQ редизайн
- [x] RAG цитаты: SourceCitation
- [x] Логотип pilot_logo.png + favicon
- [x] TTL-очистка doc_chunks (48ч) + mmap для Qdrant
- [x] Эндпоинт переиндексации документов

### Приоритет 1 — до первых пользователей
- [x] Pipeline тендеров (kanban + статусы участия)
- [x] Telegram алерты (critical alerts + утренний дайджест + health check)
- [x] Мониторинг пайплайна (PipelineRun, логирование sync/enrich)
- [x] Sync с ценовыми диапазонами (покрытие ~100% ЕИС вместо ~37%)
- [x] Ночной recover_failed_tenders (автоподбор упавших)
- [x] Защита upsert_tender от затирания данных
- [x] Retry в enrich_tender (max_retries=3)
- [x] Smart Score → удалён, заменён на чистый cosine + score_label
- [x] Qdrant payload fix (procedure_type + deadline_at_ts + backfill команда)
- [x] Pipeline exclusion из "Для вас" (studying/preparing/submitted)
- [x] Пагинация матчинга (offset, has_more, "Показать ещё")
- [x] Сортировка (score/deadline/published/nmck_asc/nmck_desc)
- [x] Валидация направлений (name + okved/keywords обязательны, nmck range)
- [x] Фильтр по площадкам (icontains, 9 площадок)
- [x] Фильтр по заказчикам (multi-select + async поиск, CustomerSearchView)
- [x] Новая архитектура поиска: вектор = только семантика, остальное = фильтры
- [x] Экспорт AI-резюме в PDF/DOCX (структурированный, с подзаголовками и буллетами)
- [x] Похожие тендеры на странице тендера
- [x] Обратный отсчёт дедлайна в TenderCard (daysUntilDeadline)
- [x] Удаление v1 summary pipeline — только v2 (требует документы)
- [x] Фикс бесконечного спиннера AI-резюме (React Query вместо useEffect race condition)
- [x] Прокси для RusProfile (RUSPROFILE_PROXY_URL, обход бана продового IP)
- [ ] Интеграция ЗаЧестныйБизнес API (замена RusProfile) — ресерч готов, API ключ не куплен
- [ ] Монетизация (ЮКасса) — free/solo/team
- [ ] **Анализ рынка** — фича "Есть ли у меня шансы?": оценка конкурентности ниши, топ-победители, ценовая зона, соответствие профиля. Мокап: market_analysis_mockup (1).html

### Приоритет 2 — после первых платящих
- [ ] EIS Coverage Check (независимая проверка: наш count vs ЕИС count)
- [ ] Карточка заказчика (история победителей, бенчмарки) — данные из ЕИС
- [ ] Мониторинг изменений документов (file_hash + diff)
- [ ] Bidding outcomes tracking (расширение Pipeline для аналитики)
- [ ] Rate limiting на AI endpoints + Sentry
- [ ] Cross-encoder reranking
- [ ] OCR для сканированных PDF

### Приоритет 3 — по фидбеку
- [ ] Черновик заявки (LLM)
- [ ] Сохранённые поисковые запросы

### Отвергнутые идеи (не делать)
- ~~Description компании в HyDE промпт~~ — размывает направления, откачено (регрессия: "Кровля" начала матчить автотранспорт)
- ~~Smart Score (4-факторная формула)~~ — удалён. Чистый cosine + правильные фильтры дают лучший результат без лишней сложности
- ~~Метаданные в tender_text (ai_summary, region, law_type)~~ — загрязняют семантический вектор, мешают чистому матчингу по содержанию работ
