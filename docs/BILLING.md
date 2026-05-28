# Биллинг — apps/billing

Дата обновления: 28 мая 2026

## Модели

### UserPlan
```python
user                OneToOneField → User (related_name=plan)
plan                CharField(FREE|STANDARD|PREMIUM, default=FREE)
expires_at          DateTimeField(nullable)            # null = free
ai_summaries_used   PositiveIntegerField(default=0)
rag_questions_used  PositiveIntegerField(default=0)
reset_at            DateTimeField                      # следующий сброс счётчиков (каждые 30 дней)
created_at, updated_at DateTimeField
```

### Subscription
```python
user                OneToOneField → User (related_name=subscription)
plan                CharField(FREE|STANDARD|PREMIUM)
status              CharField(ACTIVE|CANCELED|EXPIRED|PAYMENT_FAILED, default=ACTIVE)
interval            CharField(MONTHLY|HALFYEARLY|YEARLY)
payment_method_id   CharField(100, blank)              # для рекуррентных (ОТКЛЮЧЕНО)
current_period_start DateTimeField
current_period_end   DateTimeField
canceled_at         DateTimeField(nullable)
created_at, updated_at DateTimeField
```

### Payment
```python
user                FK → User (related_name=payments)
subscription        FK → Subscription (nullable, related_name=payments)
yookassa_payment_id CharField(100, unique)
amount              DecimalField(10,2)
currency            CharField(3, default=RUB)
status              CharField(PENDING|SUCCEEDED|CANCELED|FAILED, default=PENDING)
is_recurring        BooleanField(default=False)
metadata            JSONField(default=dict)            # {plan, interval}
created_at, updated_at DateTimeField
```

## Тарифы

### Лимиты (PLAN_LIMITS)
| План | Компании | AI резюме/мес | RAG вопросы/мес |
|------|----------|---------------|-----------------|
| free | 1 | 2 | 10 |
| standard | 1 | 60 | 120 |
| premium | 10 | 500 | 1000 |

### Цены (PLAN_PRICES, ₽)
| План | Месяц | Полгода (-1 мес) | Год (-3 мес) |
|------|-------|-----------------|--------------|
| standard | 2 990 | 14 950 | 26 910 |
| premium | 6 990 | 34 950 | 62 910 |

## Checkout Flow

1. `POST /billing/checkout/` {plan, interval} → create_first_payment() → ЮКасса
2. ЮКасса redirect → `YOOKASSA_RETURN_URL` (прод: `https://tenderoll.ru/plan?payment=success`)
3. Два пути подтверждения:
   - **Webhook**: `POST /billing/webhook/` — ЮКасса notification
   - **Verify**: `POST /billing/verify/` — fallback, poll ЮКасса API (когда webhook не доходит)
4. `handle_payment_succeeded()` → создаёт/обновляет Subscription + UserPlan, сбрасывает счётчики

## Lifecycle подписки

```
active → canceled (user cancel) → expired (Celery, после period_end) → free (downgrade UserPlan)
active → expired (Celery, process_renewals если period_end прошёл) → free
```

## Auto-fix desync

В `get_billing_info()`: если Subscription active + period_end > now, а UserPlan = free → автоматически синхронизирует.
Покрывает случай десинхрона при деплое между оплатой и первым визитом.

## Рекуррентные платежи

**ОТКЛЮЧЕНЫ**. ЮКасса требует согласование с менеджером для `save_payment_method`.
При необходимости: написать менеджеру ЮКасса, показать скриншот cancel flow, указать ожидаемый оборот.

## YooKassa Client (yookassa_client.py)

- `create_first_payment(amount, plan, interval, user_id, return_url)` → Payment
- `fetch_payment(payment_id)` → Payment
- `create_recurring_payment(...)` → Payment (ОТКЛЮЧЕНО)

## Celery Tasks

| Task | Расписание | Описание |
|------|-----------|----------|
| `process_renewals` | 03:00 daily | expired subs → free (не рекуррент) |
| `expire_canceled_subscriptions` | 03:30 daily | canceled + period_end прошёл → free |

## API Endpoints

```
GET  /api/v1/billing/me/       — billing info (plan, usage, subscription)
POST /api/v1/billing/checkout/ — создать платёж {plan, interval}
POST /api/v1/billing/webhook/  — ЮКасса callback (AllowAny)
POST /api/v1/billing/verify/   — poll pending payment
POST /api/v1/billing/cancel/   — отмена подписки
```

## Env переменные
```
YOOKASSA_SHOP_ID      # не YUKASSA_!
YOOKASSA_SECRET_KEY
YOOKASSA_RETURN_URL   # прод: https://tenderoll.ru/plan?payment=success
```
