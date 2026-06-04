"""
Заполняет search_vector для всех тендеров (одноразовый бэкфилл).

Использование:
    python manage.py backfill_search_vectors
    python manage.py backfill_search_vectors --batch=2000
    python manage.py backfill_search_vectors --only-null   # только пустые
"""
import time

from django.contrib.postgres.search import SearchVector
from django.core.management.base import BaseCommand

from apps.tenders.models import Tender


class Command(BaseCommand):
    help = "Backfill search_vector field for all tenders (BM25 / Postgres FTS)"

    def add_arguments(self, parser):
        parser.add_argument("--batch", type=int, default=1000)
        parser.add_argument(
            "--only-null",
            action="store_true",
            help="Обновлять только тендеры без search_vector",
        )

    def handle(self, *args, **options):
        batch_size: int = options["batch"]
        only_null: bool = options["only_null"]

        qs = Tender.objects.all()
        if only_null:
            qs = qs.filter(search_vector__isnull=True)

        total = qs.count()
        self.stdout.write(f"Тендеров для обработки: {total:,}")

        updated = 0
        ids = list(qs.values_list("id", flat=True).order_by("id"))

        for i in range(0, len(ids), batch_size):
            batch_ids = ids[i : i + batch_size]
            Tender.objects.filter(pk__in=batch_ids).update(
                search_vector=SearchVector("title", config="russian"),
            )
            updated += len(batch_ids)
            pct = updated / total * 100 if total else 0
            self.stdout.write(f"  {updated:,}/{total:,} ({pct:.1f}%)", ending="\r")
            self.stdout.flush()

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Готово. Обновлено: {updated:,} тендеров"))
