"""
Бэкфилл обогащения тендеров — универсальная команда для 44-ФЗ и 223-ФЗ.

Примеры:
  # Сначала посмотреть сколько тендеров нужно обогатить
  python manage.py enrich_missing --dry-run

  # Только 223-ФЗ, лимит 100
  python manage.py enrich_missing --law-type=223 --limit=100

  # Полный бэкфилл без embed (для прода)
  python manage.py enrich_missing --delay=0.5

  # С embed (после бэкфилла, или для малых объёмов)
  python manage.py enrich_missing --limit=50 --no-skip-embed
"""
import time
import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Обогащает тендеры без enriched_at (пропускает Bidzaar)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--law-type",
            choices=["44", "223", "all"],
            default="all",
            help="Тип закона (default: all)",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Максимальное количество (0 = все)",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=0.5,
            help="Пауза между запросами к ЕИС (default: 0.5с)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Показать счётчики, не запускать обогащение",
        )
        parser.add_argument(
            "--no-skip-embed",
            action="store_true",
            help="Ставить embed_tender в очередь (по умолчанию пропускается)",
        )

    def handle(self, *args, **options):
        from apps.tenders.models import Tender

        qs = Tender.objects.filter(enriched_at__isnull=True).exclude(
            source=Tender.Source.BIDZAAR,
        )

        law_type = options["law_type"]
        if law_type == "44":
            qs = qs.filter(law_type="44-ФЗ")
        elif law_type == "223":
            qs = qs.filter(law_type="223-ФЗ")

        qs = qs.order_by("id")
        total = qs.count()
        limit = options["limit"]
        if limit:
            qs = qs[:limit]
            total = min(total, limit)

        self.stdout.write(f"Тендеров для обогащения: {total}")

        if law_type == "all":
            for lt in ["44-ФЗ", "223-ФЗ", "b2b", ""]:
                cnt = Tender.objects.filter(
                    enriched_at__isnull=True, law_type=lt,
                ).exclude(source=Tender.Source.BIDZAAR).count()
                if cnt:
                    self.stdout.write(f"  {lt or '(пусто)'}: {cnt}")

        bidzaar_skip = Tender.objects.filter(
            enriched_at__isnull=True, source=Tender.Source.BIDZAAR,
        ).count()
        if bidzaar_skip:
            self.stdout.write(f"  Bidzaar (пропущено): {bidzaar_skip}")

        if options["dry_run"] or total == 0:
            return

        skip_embed = not options["no_skip_embed"]
        delay = options["delay"]

        self._run(qs, total, delay, skip_embed)

    def _run(self, qs, total: int, delay: float, skip_embed: bool) -> None:
        from apps.tenders.eis_client import fetch_tender_detail
        from apps.tenders.services import upsert_tender

        ok = 0
        failed = 0
        skipped = 0
        start_time = time.time()

        for i, tender in enumerate(qs.iterator(chunk_size=100), 1):
            try:
                detail = fetch_tender_detail(tender.number, tender.source_url)
                if detail:
                    detail["raw_json"] = detail.copy()
                    upsert_tender(detail)
                    tender.enriched_at = timezone.now()
                    tender.save(update_fields=["enriched_at"])
                    ok += 1

                    if not skip_embed:
                        from apps.search.tasks import embed_tender
                        embed_tender.delay(tender.pk)

                    if detail.get("region"):
                        self.stdout.write(
                            f"  [{i}/{total}] {tender.number} → {detail['region']}"
                        )
                    else:
                        self.stdout.write(
                            f"  [{i}/{total}] {tender.number} → обогащён (нет региона на ЕИС)"
                        )
                else:
                    tender.enriched_at = timezone.now()
                    tender.save(update_fields=["enriched_at"])
                    skipped += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f"  [{i}/{total}] {tender.number} → нет данных на ЕИС"
                        )
                    )
            except Exception as exc:
                failed += 1
                logger.error("enrich_missing: %s: %s", tender.number, exc)
                self.stdout.write(
                    self.style.ERROR(
                        f"  [{i}/{total}] {tender.number} → ошибка: {exc}"
                    )
                )

            if delay and i < total:
                time.sleep(delay)

            if i % 100 == 0:
                elapsed = time.time() - start_time
                rate = i / elapsed if elapsed > 0 else 0
                eta = (total - i) / rate if rate > 0 else 0
                self.stdout.write(
                    f"  --- Прогресс: {i}/{total} | "
                    f"ok={ok} failed={failed} skipped={skipped} | "
                    f"ETA: {eta/60:.0f} мин ---"
                )

        elapsed = time.time() - start_time
        self.stdout.write(
            self.style.SUCCESS(
                f"\nГотово за {elapsed/60:.1f} мин: "
                f"ok={ok}, skipped={skipped}, failed={failed}"
            )
        )
