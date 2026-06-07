from collections import Counter

from django.core.management.base import BaseCommand

from apps.tenders.models import Tender
from apps.tenders.services import classify_industry


class Command(BaseCommand):
    help = "Backfill industry field for all tenders based on OKPD2 codes, title keywords, and TenderGuru category"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--batch", type=int, default=1000)

    def handle(self, **options):
        dry_run = options["dry_run"]
        batch_size = options["batch"]

        qs = Tender.objects.all()
        total = qs.count()
        self.stdout.write(f"Total tenders: {total}")

        updated = 0
        stats: Counter[str] = Counter()
        source_stats: dict[str, Counter[str]] = {}
        to_update: list[Tender] = []

        for tender in qs.iterator(chunk_size=batch_size):
            tg_category = ""
            rj = tender.raw_json or {}
            if isinstance(rj, dict):
                inner = rj.get("raw_json", {})
                if isinstance(inner, dict):
                    tg_category = inner.get("category", "")

            industry = classify_industry(
                tender.okpd_codes or [],
                tender.title or "",
                tg_category,
            )

            if tender.industry != industry:
                tender.industry = industry
                to_update.append(tender)

                if len(to_update) >= batch_size:
                    if not dry_run:
                        Tender.objects.bulk_update(to_update, ["industry"])
                    updated += len(to_update)
                    self.stdout.write(f"  updated {updated}...")
                    to_update = []

            label = industry or "(empty)"
            stats[label] += 1
            src = tender.source or "unknown"
            if src not in source_stats:
                source_stats[src] = Counter()
            source_stats[src][label] += 1

        if to_update:
            if not dry_run:
                Tender.objects.bulk_update(to_update, ["industry"])
            updated += len(to_update)

        prefix = "[DRY RUN] " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(f"\n{prefix}Updated {updated}/{total} tenders"))

        self.stdout.write("\nOverall distribution:")
        for label, n in stats.most_common():
            self.stdout.write(f"  {n:6d}  {label}")

        for src in sorted(source_stats):
            self.stdout.write(f"\n{src}:")
            for label, n in source_stats[src].most_common():
                self.stdout.write(f"  {n:6d}  {label}")
