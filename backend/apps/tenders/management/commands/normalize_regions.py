"""
Переопределяет регион для всех тендеров через FIAS-адрес с ЕИС.

Для каждого тендера:
  1. Заходит на страницу тендера на ЕИС
  2. Берёт поле "Место нахождения" (FIAS-адрес)
  3. Извлекает почтовый индекс
  4. Определяет субъект РФ через postal_region.json
  5. Обновляет Tender.region в БД

Использование:
    python manage.py normalize_regions --dry-run       # посчитать без изменений
    python manage.py normalize_regions                 # применить
    python manage.py normalize_regions --delay=0.5     # с паузой между запросами
    python manage.py normalize_regions --limit=100     # только первые 100
"""
from __future__ import annotations

import time

from django.core.management.base import BaseCommand

from apps.tenders.eis_client import fetch_tender_detail
from apps.tenders.models import Tender


class Command(BaseCommand):
    help = "Обновляет Tender.region через FIAS-адрес с ЕИС"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--delay", type=float, default=0.3, help="Пауза между запросами (сек)")
        parser.add_argument("--limit", type=int, default=None, help="Ограничить кол-во тендеров")

    def handle(self, *args, **options):
        dry_run: bool = options["dry_run"]
        delay: float = options["delay"]
        limit: int | None = options["limit"]

        qs = Tender.objects.filter(law_type="223-ФЗ").only("id", "number", "source_url", "region", "law_type")
        if limit:
            qs = qs[:limit]

        total = qs.count() if not limit else limit
        self.stdout.write(f"Тендеров к обработке: {total}")
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — изменения не применяются"))

        ok = skipped = failed = 0

        for tender in qs.iterator(chunk_size=100):
            try:
                data = fetch_tender_detail(tender.number, tender.source_url or "")
                new_region = data.get("region", "")

                if not new_region:
                    skipped += 1
                    continue

                if new_region != tender.region:
                    self.stdout.write(
                        f"  [{tender.number}] {tender.region!r} → {new_region!r}"
                    )
                    if not dry_run:
                        Tender.objects.filter(pk=tender.pk).update(region=new_region)

                ok += 1
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"  [{tender.number}] ошибка: {exc}"))
                failed += 1

            if delay:
                time.sleep(delay)

        self.stdout.write(
            self.style.SUCCESS(
                f"\nГотово: обработано {ok}, пропущено (нет региона) {skipped}, ошибок {failed}"
            )
        )
