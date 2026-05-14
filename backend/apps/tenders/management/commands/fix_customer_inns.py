import time

from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.tenders.eis_client import fetch_tender_detail
from apps.tenders.models import Tender


class Command(BaseCommand):
    help = "Backfill empty customer INNs by re-fetching tender detail pages from EIS"

    def add_arguments(self, parser) -> None:
        parser.add_argument("--limit", type=int, default=0, help="Max tenders to process (0=all)")
        parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests (seconds)")
        parser.add_argument("--dry-run", action="store_true", help="Only show counts, don't fetch")
        parser.add_argument("--law-type", type=str, default="", help="Filter by law_type (e.g. '44-ФЗ')")

    def handle(self, *args, **options) -> None:
        limit: int = options["limit"]
        delay: float = options["delay"]
        dry_run: bool = options["dry_run"]
        law_type: str = options["law_type"]

        qs = (
            Tender.objects
            .select_related("customer")
            .filter(
                Q(customer__inn__isnull=True) | Q(customer__inn=""),
                enriched_at__isnull=False,
            )
        )
        if law_type:
            qs = qs.filter(law_type=law_type)

        total = qs.count()
        self.stdout.write(f"Enriched tenders with empty customer INN: {total}")

        if dry_run:
            law_types = qs.values_list("law_type", flat=True).distinct()
            for lt in law_types:
                c = qs.filter(law_type=lt).count()
                self.stdout.write(f"  {lt or '(empty)'}: {c}")
            return

        if limit:
            qs = qs[:limit]

        fixed = 0
        skipped = 0
        failed = 0

        for tender in qs.iterator(chunk_size=100):
            number = tender.number
            source_url = tender.source_url or ""

            try:
                detail = fetch_tender_detail(number, source_url)
            except Exception as exc:
                self.stderr.write(f"  FAIL {tender.id} {number}: {exc}")
                failed += 1
                time.sleep(delay)
                continue

            inn = detail.get("customer_inn", "")
            if not inn:
                skipped += 1
                if (fixed + skipped + failed) % 100 == 0:
                    self.stdout.write(f"  progress: fixed={fixed} skipped={skipped} failed={failed}")
                time.sleep(delay)
                continue

            customer = tender.customer
            if customer and not customer.inn:
                customer.inn = inn
                customer.full_name = detail.get("customer_name", "") or customer.full_name
                customer.save(update_fields=["inn", "full_name"])
                fixed += 1
                if fixed % 50 == 0:
                    self.stdout.write(f"  fixed {fixed} so far (skipped={skipped}, failed={failed})")
            else:
                skipped += 1

            time.sleep(delay)

        self.stdout.write(self.style.SUCCESS(
            f"Done. fixed={fixed}, skipped={skipped}, failed={failed}"
        ))
