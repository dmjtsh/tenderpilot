from django.core.management.base import BaseCommand

from apps.tenders.models import Tender
from apps.tenders.services import compute_content_quality


class Command(BaseCommand):
    help = "Backfill content_quality for existing TenderGuru tenders"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--batch", type=int, default=500)

    def handle(self, **options):
        dry_run = options["dry_run"]
        batch_size = options["batch"]

        qs = Tender.objects.filter(source=Tender.Source.TENDERGURU)
        total = qs.count()
        self.stdout.write(f"TenderGuru tenders: {total}")

        updated = 0
        to_update = []
        for tender in qs.iterator(chunk_size=batch_size):
            rj = tender.raw_json or {}
            nested = rj.get("raw_json", {})
            quality = compute_content_quality(rj, Tender.Source.TENDERGURU)
            if tender.content_quality != quality:
                tender.content_quality = quality
                to_update.append(tender)
                if len(to_update) >= batch_size:
                    if not dry_run:
                        Tender.objects.bulk_update(to_update, ["content_quality"])
                    updated += len(to_update)
                    self.stdout.write(f"  updated {updated}...")
                    to_update = []

        if to_update:
            if not dry_run:
                Tender.objects.bulk_update(to_update, ["content_quality"])
            updated += len(to_update)

        prefix = "[DRY RUN] " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(f"{prefix}Updated {updated}/{total} tenders"))
