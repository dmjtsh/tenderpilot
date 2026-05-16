import logging
import time

from django.core.management.base import BaseCommand

from apps.tenders.models import Tender
from apps.search.services import qdrant

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Backfill Qdrant payload with procedure_type and deadline_at_ts (no re-embedding)"

    def add_arguments(self, parser):
        parser.add_argument("--batch", type=int, default=1000)
        parser.add_argument("--limit", type=int, default=0, help="Max tenders to process (0=all)")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, **options):
        batch_size = options["batch"]
        max_limit = options["limit"]
        dry_run = options["dry_run"]

        qs = Tender.objects.filter(
            status=Tender.Status.ACTIVE,
            embedding_id__isnull=False,
        ).select_related("customer").order_by("pk")

        if max_limit:
            qs = qs[:max_limit]

        total = 0
        updated = 0
        errors = 0

        for tender in qs.iterator(chunk_size=batch_size):
            total += 1
            payload_patch = {
                "procedure_type": tender.procedure_type or "",
                "deadline_at_ts": int(tender.deadline_at.timestamp()) if tender.deadline_at else 0,
            }

            if dry_run:
                if total <= 3:
                    self.stdout.write(f"  [dry-run] tender {tender.pk}: {payload_patch}")
                continue

            try:
                qdrant.client.set_payload(
                    collection_name="tenders",
                    payload=payload_patch,
                    points=[tender.pk],
                )
                updated += 1
            except Exception as exc:
                errors += 1
                if errors <= 5:
                    logger.error("Failed to update tender %d: %s", tender.pk, exc)

            if total % batch_size == 0:
                self.stdout.write(f"  processed {total}...")
                time.sleep(0.1)

        self.stdout.write(self.style.SUCCESS(
            f"Done: total={total}, updated={updated}, errors={errors}"
            + (" [DRY RUN]" if dry_run else "")
        ))
