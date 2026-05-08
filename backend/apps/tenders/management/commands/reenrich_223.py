"""
Переобогащение тендеров 223-ФЗ у которых нет дедлайна (deadline_at=NULL).

Примеры:
  # Запустить для всех (через Celery очередь, батчами по 500)
  python manage.py reenrich_223

  # Только активные
  python manage.py reenrich_223 --active-only

  # Лимит количества
  python manage.py reenrich_223 --limit 1000

  # Синхронно (без Celery, медленно но надёжно для теста)
  python manage.py reenrich_223 --sync --limit 10
"""
import time
import logging

from django.core.management.base import BaseCommand
from django.db.models import Q

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Переобогащает тендеры 223-ФЗ без дедлайна"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Максимальное количество тендеров (0 = все)",
        )
        parser.add_argument(
            "--active-only",
            action="store_true",
            help="Только активные тендеры (status=active)",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Все 223-ФЗ тендеры, включая уже обогащённые (для исправления регионов)",
        )
        parser.add_argument(
            "--sync",
            action="store_true",
            help="Выполнить синхронно (без Celery), полезно для отладки",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="Размер батча при постановке в очередь Celery (default: 500)",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=0.05,
            help="Задержка между задачами в сек при --sync (default: 0.05)",
        )

    def handle(self, *args, **options):
        from apps.tenders.models import Tender
        from apps.tenders.tasks import enrich_tender

        if options["all"]:
            qs = Tender.objects.filter(law_type="223-ФЗ")
        else:
            qs = Tender.objects.filter(law_type="223-ФЗ", deadline_at__isnull=True)
        if options["active_only"]:
            qs = qs.filter(status=Tender.Status.ACTIVE)

        qs = qs.order_by("id")
        total = qs.count()
        limit = options["limit"]
        if limit:
            qs = qs[:limit]
            total = min(total, limit)

        self.stdout.write(f"Найдено тендеров 223-ФЗ{'(все)' if options['all'] else ' без дедлайна'}: {total}")
        if total == 0:
            return

        if options["sync"]:
            self._run_sync(qs, total, options["delay"])
        else:
            self._run_async(qs, total, options["batch_size"])

    def _run_async(self, qs, total: int, batch_size: int) -> None:
        from apps.tenders.tasks import enrich_tender

        queued = 0
        batch = []
        for tender in qs.values_list("pk", flat=True).iterator(chunk_size=batch_size):
            batch.append(tender)
            if len(batch) >= batch_size:
                for pk in batch:
                    enrich_tender.apply_async(args=[pk], countdown=queued * 0.1)
                queued += len(batch)
                batch = []
                self.stdout.write(f"  В очереди: {queued}/{total}")

        # остаток
        for pk in batch:
            enrich_tender.apply_async(args=[pk], countdown=queued * 0.1)
        queued += len(batch)

        self.stdout.write(
            self.style.SUCCESS(f"Поставлено в очередь Celery: {queued} тендеров")
        )

    def _run_sync(self, qs, total: int, delay: float) -> None:
        from apps.tenders.eis_client import fetch_tender_detail
        from apps.tenders.services import upsert_tender

        ok = 0
        failed = 0
        for i, tender in enumerate(qs.iterator(chunk_size=100), 1):
            try:
                detail = fetch_tender_detail(tender.number, tender.source_url)
                if detail:
                    detail["raw_json"] = detail.copy()
                    upsert_tender(detail)
                    ok += 1
                    if detail.get("deadline_at"):
                        self.stdout.write(f"  [{i}/{total}] {tender.number} → deadline: {detail['deadline_at']}")
                    else:
                        self.stdout.write(f"  [{i}/{total}] {tender.number} → нет дедлайна на странице")
                else:
                    failed += 1
                    self.stdout.write(
                        self.style.WARNING(f"  [{i}/{total}] {tender.number} → нет данных")
                    )
            except Exception as exc:
                failed += 1
                logger.error("reenrich_223: error for %s: %s", tender.number, exc)
                self.stdout.write(
                    self.style.ERROR(f"  [{i}/{total}] {tender.number} → ошибка: {exc}")
                )
            if delay:
                time.sleep(delay)

        self.stdout.write(
            self.style.SUCCESS(f"Готово: успешно={ok}, ошибок={failed}")
        )
