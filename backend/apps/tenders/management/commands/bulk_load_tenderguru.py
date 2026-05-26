"""
One-time bulk loader for TenderGuru commercial tenders.

Usage:
    python manage.py bulk_load_tenderguru --limit=100 --delay=0.3
    python manage.py bulk_load_tenderguru --dry-run
    python manage.py bulk_load_tenderguru --limit=500 --no-embed --offset=5
"""
import time

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Bulk load commercial tenders from TenderGuru API"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0, help="Max tenders to load (0=all)")
        parser.add_argument("--delay", type=float, default=0.3, help="Delay between detail requests")
        parser.add_argument("--dry-run", action="store_true", help="Only count, don't save")
        parser.add_argument("--no-embed", action="store_true", help="Skip embedding")
        parser.add_argument("--offset", type=int, default=1, help="Start page (default=1)")
        parser.add_argument("--law", type=str, default="kom", help="Law filter: kom, 44, 223")
        parser.add_argument("--with-detail", action="store_true", default=True,
                            help="Fetch detail for each tender (default: True)")
        parser.add_argument("--no-detail", action="store_true", help="Skip detail fetch")

    def handle(self, **options):
        import requests as req
        from apps.tenders.models import Tender
        from apps.tenders.tenderguru_client import (
            search_tenders,
            fetch_tender_detail,
            parse_list_item,
            enrich_from_detail,
        )
        from apps.tenders.services import upsert_tender
        from apps.tenders.tasks import enrich_tender

        limit = options["limit"]
        delay = options["delay"]
        dry_run = options["dry_run"]
        no_embed = options["no_embed"]
        start_page = options["offset"]
        law = options["law"]
        fetch_detail = not options["no_detail"]

        existing_numbers = set(
            Tender.objects.filter(source=Tender.Source.TENDERGURU)
            .values_list("number", flat=True)
        )
        self.stdout.write(f"Existing TenderGuru tenders: {len(existing_numbers)}")

        session = req.Session()
        session.headers["User-Agent"] = "Tenderoll/1.0 (tender aggregator; support@tenderoll.ru)"

        stats = {"pages": 0, "fetched": 0, "new": 0, "skipped": 0, "errors": 0, "enriched": 0}
        consecutive_skip_pages = 0
        SKIP_STOP = 3

        for page in range(start_page, 5000):
            try:
                items = search_tenders(
                    page=page,
                    law_filter=law,
                    actual=True,
                    session=session,
                )
            except Exception as exc:
                self.stderr.write(f"Page {page} error: {exc}")
                stats["errors"] += 1
                break

            if not items:
                self.stdout.write(f"Page {page}: empty, stopping")
                break

            stats["pages"] = page

            for item in items:
                parsed = parse_list_item(item)
                if not parsed:
                    continue

                stats["fetched"] += 1

                if law == "kom" and parsed.get("law_type") != "b2b":
                    stats["skipped"] += 1
                    continue

                if parsed["number"] in existing_numbers:
                    stats["skipped"] += 1
                    continue

                if dry_run:
                    stats["new"] += 1
                    self.stdout.write(
                        f"  [DRY] {parsed['number']} | {parsed['title'][:60]} | "
                        f"₽{parsed.get('nmck', '—')} | {parsed['trading_platform'][:30]}"
                    )
                    if limit and stats["new"] >= limit:
                        break
                    continue

                if fetch_detail:
                    tg_id = item.get("ID")
                    detail = fetch_tender_detail(tg_id, session=session)
                    if detail:
                        parsed = enrich_from_detail(parsed, detail)
                        stats["enriched"] += 1
                    time.sleep(delay)

                try:
                    tender = upsert_tender(parsed)
                    Tender.objects.filter(pk=tender.pk).update(enriched_at=timezone.now())
                    existing_numbers.add(parsed["number"])
                    stats["new"] += 1

                    if not no_embed:
                        enrich_tender.apply_async(args=[tender.pk], countdown=5)

                    self.stdout.write(
                        f"  [{stats['new']}] {tender.number} | {tender.title[:50]} | "
                        f"₽{tender.nmck or '—'} | {tender.trading_platform[:30]}"
                    )
                except Exception as exc:
                    self.stderr.write(f"  Upsert error: {exc}")
                    stats["errors"] += 1

                if limit and stats["new"] >= limit:
                    break

            if limit and stats["new"] >= limit:
                self.stdout.write(f"Reached limit={limit}")
                break

            if len(items) < 20:
                self.stdout.write(f"Page {page}: {len(items)} items (last page)")
                break

            time.sleep(delay)

        self.stdout.write(self.style.SUCCESS(
            f"\nDone: pages={stats['pages']} fetched={stats['fetched']} "
            f"new={stats['new']} skipped={stats['skipped']} "
            f"enriched={stats['enriched']} errors={stats['errors']}"
        ))
