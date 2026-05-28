# Заказчики — apps/customers

Дата обновления: 28 мая 2026

## Модель CustomerProfile

```python
inn                       CharField(12, unique, db_index)
# DaData
name                      CharField(500, blank)
full_name                 CharField(1000, blank)
region                    CharField(200, blank)
okved_main                CharField(20, blank)
okved_list                JSONField(default=list)
status                    CharField(50, blank)
director_name             CharField(300, blank)
# RusProfile — финансы
revenue_rub               BigIntegerField(nullable)
profit_rub                BigIntegerField(nullable)
revenue_year              IntegerField(nullable)
employees_count           IntegerField(nullable)
founded_date              DateField(nullable)
# RusProfile — лицензии
licenses_count            IntegerField(default=0)
licenses_summary          TextField(blank)
# RusProfile — закупки
purchases_customer_count  IntegerField(default=0)
purchases_customer_amount BigIntegerField(default=0)
purchases_supplier_count  IntegerField(default=0)
# RusProfile — риски
arbitration_count         IntegerField(default=0)
fssp_count                IntegerField(default=0)
risk_indicators           JSONField(default=dict)
# Метаданные
rusprofile_id             IntegerField(nullable)
dadata_updated_at         DateTimeField(nullable)
rusprofile_updated_at     DateTimeField(nullable)
rusprofile_failed         BooleanField(default=False)
last_error                TextField(blank)
created_at, updated_at    DateTimeField
```

## Enrichment Pipeline (services/enrichment.py)

1. `enrich_customer(inn)` → CustomerProfile | None
2. DaData enrichment → basic info (name, region, okved)
3. RusProfile enrichment → financial, risk, license data (через прокси)
4. Freshness check: `_rusprofile_fresh(profile)` — пропускает если недавно обновлялось
5. Cooldown: `_rusprofile_cooldown(profile)` — пропускает если failed недавно

## RusProfile (services/rusprofile.py)

- Скрапинг через HTTP прокси (`RUSPROFILE_PROXY_URL`)
- Извлечение: выручка, прибыль, сотрудники, лицензии, арбитраж, ФССП
- **Не рефакторить** — работает через прокси (обход бана продового IP)

## Celery Tasks

- `enrich_customer_task(inn)` — вызывает enrich_customer()

## Management Commands

| Команда | Назначение |
|---------|-----------|
| `enrich_customers --limit=N --delay=SEC` | Batch обогащение заказчиков |
| `test_rusprofile` | Тест RusProfile API |

## Использование

CustomerProfile обогащается при генерации AI-резюме (summary_v2 context):
- `get_customer_profile(tender)` → ищет ИНН → enrich_customer → данные в промпт customer_analysis
- Если ИНН пуст, пробует `find_inn_by_name()` через DaData
