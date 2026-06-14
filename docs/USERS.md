# Пользователи — apps/users

Дата обновления: 14 июня 2026

## Модели

### User (AbstractUser)
```python
email           EmailField(unique)  # USERNAME_FIELD
email_verified  BooleanField(default=False)  # подтверждение email при регистрации
username        CharField           # REQUIRED_FIELD (inherited)
```

### CompanyProfile
```python
user                     FK → User (related_name=company_profiles)
name                     CharField(255)
inn                      CharField(12, blank)
description              TextField(blank)                # НЕ используется в HyDE
okved_codes              JSONField(default=list)          # legacy
regions                  JSONField(default=list)          # legacy
keywords                 JSONField(default=list)          # legacy
contract_security_budget BigIntegerField(nullable)
has_bank_guarantee       BooleanField(default=False)
platforms                JSONField(default=list)          # legacy
won_tender_ids           ArrayField(IntegerField, default=list)  # для won-tender скоринга
created_at, updated_at   DateTimeField
```

UI профиля: только name + inn (описание/оквэд/регионы/ключевые слова — legacy, не в UI).

### CompanyDirection
```python
profile          FK → CompanyProfile (related_name=directions)
name             CharField(255)
okved_codes      ArrayField(CharField, default=list)
keywords         ArrayField(CharField, default=list)
exclude_keywords ArrayField(CharField, default=list)    # negative matching в поиске
regions          ArrayField(CharField, default=list)    # Qdrant MatchAny
nmck_min         BigIntegerField(nullable)
nmck_max         BigIntegerField(nullable)
law_types        ArrayField(CharField, default=list)    # Qdrant MatchAny
procedure_types  ArrayField(CharField, default=list)    # Qdrant MatchAny
description      TextField(blank)                       # НЕ используется в HyDE
hyde_texts       JSONField(nullable)                    # 5 синтетических текстов от DeepSeek
profile_vector   ArrayField(FloatField, size=1024, nullable)  # multilingual-e5-large
content_hash     CharField(16, blank)                   # SHA256[:16] для debounce
vector_updated_at DateTimeField(nullable)
created_at, updated_at DateTimeField
```

### Direction → Vector Pipeline
1. User saves direction → post_save signal
2. `rebuild_direction_vector` Celery task (countdown=30, фиксированный task_id = debounce)
3. `needs_reindex()` проверяет content_hash (name + okved + keywords + regions + nmck + law_types + procedure_types)
4. HyDE: DeepSeek → 5 текстов → усреднение эмбеддингов → profile_vector

**НЕ добавлять description в HyDE** — проверено, размывает вектора.

## DaData (dadata.py)

- `enrich_company_by_inn(inn)` → CompanyInfo | None (name, full_name, inn, region, okved_main, okved_list)
- `find_inn_by_name(name)` → str | None
- Примечание: okveds в DaData часто пустой, только основной ОКВЭД

## API Endpoints

```
POST /api/v1/users/register/                — регистрация (отправляет verification email, НЕ выдаёт токены)
POST /api/v1/users/verify-email/            — подтверждение email (uid + token → access + refresh)
POST /api/v1/users/resend-verification/     — повторная отправка письма верификации
POST /api/v1/users/auth/token/              — JWT (email + password → access + refresh, проверяет email_verified)
POST /api/v1/users/auth/token/refresh/      — refresh token
GET  /api/v1/users/me/                      — текущий юзер
PATCH /api/v1/users/me/                     — обновление
POST /api/v1/users/me/password/             — смена пароля

# Компании (multi-company)
GET/POST /api/v1/users/me/companies/
GET/PATCH/DELETE /api/v1/users/me/companies/{id}/

# Направления (scoped + backward-compat)
GET/POST /api/v1/users/me/companies/{profile_pk}/directions/
GET/PATCH/DELETE /api/v1/users/me/companies/{profile_pk}/directions/{id}/
GET/POST /api/v1/users/me/directions/       — backward-compat (first profile)
GET/PATCH/DELETE /api/v1/users/me/directions/{id}/

POST /api/v1/users/lookup-inn/              — DaData enrichment по ИНН
```
