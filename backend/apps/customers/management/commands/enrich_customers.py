import time

from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.customers.models import CustomerProfile
from apps.tenders.models import Customer


class Command(BaseCommand):
    help = "Batch-обогащение заказчиков (DaData + RusProfile)"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--delay", type=float, default=2.5, help="Задержка между запросами (сек)")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        limit = options["limit"]
        delay = options["delay"]
        dry_run = options["dry_run"]

        existing_inns = set(
            CustomerProfile.objects.filter(
                rusprofile_updated_at__isnull=False,
            ).values_list("inn", flat=True)
        )

        candidates = (
            Customer.objects.filter(~Q(inn=""))
            .exclude(inn__in=existing_inns)
            .values_list("inn", flat=True)
            .distinct()[:limit]
        )
        candidate_list = list(candidates)

        self.stdout.write(f"Всего заказчиков без профиля: {len(candidate_list)} (лимит {limit})")

        if dry_run:
            self.stdout.write("Dry run — выход.")
            return

        from apps.customers.services.enrichment import enrich_customer

        ok, fail = 0, 0
        for i, inn in enumerate(candidate_list, 1):
            try:
                profile = enrich_customer(inn)
                if profile and profile.rusprofile_updated_at:
                    ok += 1
                    self.stdout.write(f"[{i}/{len(candidate_list)}] {inn} → {profile.name} ✓")
                else:
                    fail += 1
                    self.stdout.write(f"[{i}/{len(candidate_list)}] {inn} → partial/fail")
            except Exception as e:
                fail += 1
                self.stderr.write(f"[{i}/{len(candidate_list)}] {inn} → ERROR: {e}")

            if i < len(candidate_list):
                time.sleep(delay)

        self.stdout.write(self.style.SUCCESS(f"\nГотово: {ok} ok, {fail} fail"))
