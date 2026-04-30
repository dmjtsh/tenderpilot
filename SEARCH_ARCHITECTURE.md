# Search Architecture — Tender SaaS

## Текущее состояние (AS IS)

```
CompanyProfile (description + keywords + regions)
              ↓
        один dense вектор
        multilingual-e5-large
              ↓
     Qdrant cosine similarity
     (все тендеры, без фильтров)
              ↓
           топ-20
```

**Проблемы:**
- Один вектор на всю компанию — кровля и благоустройство смешаны
- Нет фильтра по НМЦ — компании с оборотом 1 млн показываются тендеры на 500 млн
- Нет фильтра по типу закупки (44/223/615)
- Нет фильтра по региону на уровне Qdrant
- Текст тендера бедный — только название + ОКПД коды без расшифровки
- ОКПД коды ("43.91") модель не понимает — нужны человеческие названия

---

## Целевая архитектура (TO BE)

```
CompanyDirection × N (отдельно на каждое направление)
  кровля: НМЦ 500к–5млн, 44/615, Самара
  благоустройство: НМЦ 1млн–20млн, 44/223, Самара
              ↓
    HyDE: GPT-4o-mini генерирует 3 текста
    в стиле тендера → усреднение векторов
    (один раз при сохранении, не при поиске)
              ↓
       dense вектор профиля
       (хранится в Postgres)
              ↓
   ┌── Qdrant payload фильтры ──┐
   │  nmck BETWEEN min AND max  │
   │  region IN [...]           │← до векторного поиска
   │  law_type IN [44, 615]     │  убирает нерелевантное
   └────────────────────────────┘
              ↓ ~500 кандидатов
     Dense поиск top-100
     multilingual-e5-large (не меняем)
              ↓
   Cross-encoder reranking (опционально)
   mmarco-mMiniLMv2 → top-20
              ↓
   Дедупликация по tender_id
   + matched_direction метка
```

---

## Компоненты

### 1. Справочник ОКВЭД — `apps/tenders/okved.py`

Переводит коды в человеческий текст перед embedding.
Модель понимает слова, не коды.

```python
OKVED_NAMES = {
    "43.91": "производство кровельных работ",
    "81.30": "производство посадочных работ и содержание зелёных насаждений",
    "42.11": "строительство автомобильных дорог",
    # ~1500 записей — загрузить из открытого справочника
}

def okved_to_text(codes: list[str]) -> str:
    names = []
    for code in codes:
        name = (
            OKVED_NAMES.get(code) or
            OKVED_NAMES.get(code[:4]) or  # группа
            OKVED_NAMES.get(code[:2]) or  # класс
            code                           # fallback
        )
        names.append(name)
    return ", ".join(names)
```

### 2. Обогащённый текст тендера — `apps/search/embedder.py`

```python
def tender_text(tender) -> str:
    from apps.tenders.okved import okved_to_text

    okpd_names = okved_to_text(tender.okpd_codes or [])
    desc = (tender.description or "")[:500]  # truncate — важно

    parts = [
        f"passage: {tender.title}.",
        desc,
        f"Вид работ: {okpd_names}." if okpd_names else "",
        f"Заказчик: {tender.customer.name}." if tender.customer_id else "",
        f"Регион: {tender.region}." if tender.region else "",
        f"Закон: {tender.law_type}." if tender.law_type else "",
    ]
    return " ".join(p for p in parts if p)
```

**Почему description[:500]:** при усреднении длинного текста важная информация
из начала теряется. 500 символов — оптимальный баланс.

### 3. Модель CompanyDirection — `apps/users/models.py`

```python
class CompanyDirection(models.Model):
    profile     = models.ForeignKey(CompanyProfile, related_name='directions',
                                    on_delete=models.CASCADE)
    name        = models.CharField(max_length=255)   # "кровельные работы"
    okved_codes = ArrayField(models.CharField(max_length=10), default=list)
    keywords    = ArrayField(models.CharField(max_length=100), default=list)

    # НМЦ per direction — кровля до 5 млн, благоустройство до 20 млн
    nmck_min    = models.BigIntegerField(null=True, blank=True)
    nmck_max    = models.BigIntegerField(null=True, blank=True)

    # Типы закупок
    law_types   = ArrayField(models.CharField(max_length=10), default=list)
    # ["44-ФЗ", "223-ФЗ", "615-ПП"]

    # HyDE кэш
    hyde_texts      = models.JSONField(null=True, blank=True)
    profile_vector  = ArrayField(models.FloatField(), size=1024,
                                 null=True, blank=True)
    content_hash    = models.CharField(max_length=16, blank=True)
    vector_updated_at = models.DateTimeField(null=True, blank=True)

    def compute_content_hash(self) -> str:
        import hashlib, json
        content = {
            "name": self.name,
            "okved_codes": sorted(self.okved_codes or []),
            "keywords": sorted(self.keywords or []),
            "nmck_min": self.nmck_min,
            "nmck_max": self.nmck_max,
            "law_types": sorted(self.law_types or []),
        }
        return hashlib.sha256(
            json.dumps(content, sort_keys=True).encode()
        ).hexdigest()[:16]

    def needs_reindex(self) -> bool:
        return self.compute_content_hash() != self.content_hash
```

### 4. HyDE — `apps/search/hyde.py`

**Идея:** вместо эмбеддинга описания компании ("занимаемся кровлей")
генерируем 3 гипотетических тендера через GPT-4o-mini и усредняем их векторы.
Гипотетические тендеры написаны на языке госзакупок → лучшее совпадение
с реальными тендерами в векторном пространстве.

**Когда вызывается:** один раз при сохранении/изменении направления,
НЕ при каждом поиске. Результат кэшируется в `profile_vector`.

```python
from openai import OpenAI
import numpy as np

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

HYDE_PROMPT = """
Ты эксперт по госзакупкам России.

Компания: {name}
ОКВЭД: {okved_text}
Ключевые слова: {keywords}
НМЦ: от {nmck_min} до {nmck_max} ₽
Типы закупок: {law_types}

Напиши {n} разных описания тендеров (2-3 предложения каждый),
которые идеально подошли бы этой компании.
Используй официальный язык госзакупок.
Верни ТОЛЬКО JSON массив строк без пояснений.
"""

def generate_hyde_texts(direction, n: int = 3) -> list[str]:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": HYDE_PROMPT.format(
            name=direction.name,
            okved_text=okved_to_text(direction.okved_codes or []),
            keywords=", ".join(direction.keywords or []) or "не указаны",
            nmck_min=f"{direction.nmck_min:,}" if direction.nmck_min else "не ограничен",
            nmck_max=f"{direction.nmck_max:,}" if direction.nmck_max else "не ограничен",
            law_types=", ".join(direction.law_types or ["44-ФЗ", "223-ФЗ", "615-ПП"]),
            n=n,
        )}],
        max_tokens=600,
        temperature=0.7,
    )
    return json.loads(response.choices[0].message.content.strip())


def build_direction_vector(direction) -> list[float]:
    hyde_texts = generate_hyde_texts(direction, n=3)

    embedder = Embedder()
    vectors = embedder.embed_passages(
        [f"passage: {t}" for t in hyde_texts]
    )
    # усредняем — итоговый вектор профиля
    return np.mean(vectors, axis=0).tolist(), hyde_texts
```

### 5. Celery task с debounce — `apps/search/tasks.py`

**Защита от API спама:**
- Фиксированный `task_id` = при повторном вызове старая задача
  перезаписывается в очереди → 10 сохранений за 30 сек = 1 вызов API
- Double-check hash перед генерацией

```python
@shared_task(bind=True)
def rebuild_direction_vector(self, direction_id: int):
    direction = CompanyDirection.objects.get(id=direction_id)

    new_hash = direction.compute_content_hash()
    if new_hash == direction.content_hash and direction.profile_vector:
        return "skip: already up to date"

    final_vector, hyde_texts = build_direction_vector(direction)

    CompanyDirection.objects.filter(id=direction_id).update(
        hyde_texts=hyde_texts,
        profile_vector=final_vector,
        content_hash=new_hash,
        vector_updated_at=timezone.now(),
    )
```

**Signal с debounce — `apps/users/signals.py`:**

```python
@receiver(post_save, sender=CompanyDirection)
def schedule_vector_rebuild(sender, instance, **kwargs):
    if not instance.needs_reindex():
        return
    rebuild_direction_vector.apply_async(
        args=[instance.id],
        countdown=30,                               # ждём 30 сек
        task_id=f"direction-vector-{instance.id}"  # ключевой трюк
    )
```

### 6. Поиск с фильтрами — `apps/search/services.py`

```python
def match_tenders_for_profile(profile, limit: int = 20) -> list:
    directions = profile.directions.filter(
        profile_vector__isnull=False
    ).all()

    all_results = []

    for direction in directions:
        # Payload фильтры — применяются ДО векторного поиска
        must_conditions = []

        if direction.regions:
            must_conditions.append(
                FieldCondition(key="region",
                               match=MatchAny(any=direction.regions))
            )
        if direction.nmck_min or direction.nmck_max:
            must_conditions.append(
                FieldCondition(key="nmck",
                               range=Range(gte=direction.nmck_min,
                                           lte=direction.nmck_max))
            )
        if direction.law_types:
            must_conditions.append(
                FieldCondition(key="law_type",
                               match=MatchAny(any=direction.law_types))
            )

        results = self.client.search(
            collection_name="tenders",
            query_vector=direction.profile_vector,
            query_filter=Filter(must=must_conditions) if must_conditions else None,
            limit=100,  # берём 100, потом дедуплицируем
        )

        for r in results:
            r.matched_direction = direction.name
        all_results.extend(results)

    # Дедупликация — оставляем лучший score для каждого тендера
    seen: dict[int, Any] = {}
    for r in all_results:
        if r.id not in seen or r.score > seen[r.id].score:
            seen[r.id] = r

    return sorted(seen.values(), key=lambda x: x.score, reverse=True)[:limit]
```

---

## Почему НЕ меняем модель на BGE-M3

Текущая `multilingual-e5-large` через fastembed (ONNX) хорошо работает на CPU.
Смена на BGE-M3 (PyTorch) даёт sparse векторы но:
- Требует PyTorch (~2GB) вместо легкого ONNX (~50MB)
- Сложнее формировать sparse вектор запроса для профиля
- Обогащённый `tender_text()` с расшифровкой ОКВЭД решает ту же проблему
  что и sparse поиск (точные термины попадают в dense вектор)

Вернуться к вопросу о BGE-M3 после первых пользователей и измерения качества.

---

## Cross-encoder reranking — опционально

Добавлять ПОСЛЕ первых платящих пользователей.
Улучшает precision на 30-50% но добавляет ~200-300ms латентности.

```python
# Модель для русского языка
reranker = CrossEncoder('cross-encoder/mmarco-mMiniLMv2-L12-H384-v1')

def rerank(profile_text: str, candidates: list, top_k: int = 20) -> list:
    pairs = [(profile_text, c.payload['title']) for c in candidates]
    scores = reranker.predict(pairs)
    ranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
    return [c for c, _ in ranked[:top_k]]
```

---

## Стоимость GPT-4o-mini для HyDE

- 3 текста × ~200 токенов output = ~600 токенов на направление
- $0.60 / 1M output токенов = **$0.00036 за направление**
- 100 обновлений профилей в день = **~$0.036/день = ~$1/месяц**

---

## Порядок внедрения

### Шаг 1 — Обогащение текста (быстрый win, не меняет модель)
1. Создать `apps/tenders/okved.py` со справочником ОКВЭД
2. Обновить `tender_text()` в `apps/search/embedder.py`
3. Запустить `python manage.py index_tenders`
4. Проверить качество поиска руками на 10-20 запросах

### Шаг 2 — CompanyDirection + фильтры
5. Добавить `CompanyDirection` в `apps/users/models.py` + миграция
6. Обновить `QdrantService.match_profile()` — итерация по направлениям,
   payload фильтры, дедупликация, matched_direction
7. Обновить API `/api/v1/search/match/`

### Шаг 3 — HyDE
8. Создать `apps/search/hyde.py`
9. Создать Celery task `rebuild_direction_vector` с debounce
10. Добавить signal `post_save` на CompanyDirection
11. Добавить `OPENAI_API_KEY` в `.env`

### Шаг 4 — Фронт
12. Форма направлений с динамическим списком
13. НМЦ: radio кнопки (до 1 млн / 1-10 млн / 10-50 млн / 50-200 млн /
    свыше 200 млн / своё значение)
14. Чекбоксы 44-ФЗ / 223-ФЗ / 615-ПП per направление
15. Карточка тендера: показывать метку `matched_direction`

### Шаг 5 — Проверка качества
16. Протестировать 20+ реальных запросов
17. Сравнить результаты до/после

### Шаг 6 — Cross-encoder (после первых пользователей)
18. Добавить `sentence-transformers` в requirements
19. Инициализировать reranker один раз при старте Django
20. Добавить как опциональный слой поверх топ-100
