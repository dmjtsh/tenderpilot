from django.core.management.base import BaseCommand

from apps.tenders.models import Tender
from apps.tenders.services import compute_content_quality
from apps.tenders.tenderguru_client import _parse_docs_from_html


class Command(BaseCommand):
    help = "Backfill doc_files from info_html and recompute content_quality"

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
        docs_added = 0
        to_update = []
        for tender in qs.iterator(chunk_size=batch_size):
            rj = tender.raw_json or {}
            nested = rj.get("raw_json", {})
            if not isinstance(nested, dict):
                continue

            changed = False

            existing_docs = nested.get("doc_files") or []
            real_docs = [
                d for d in existing_docs
                if not d.get("link", "").startswith("mailto:")
                and "подать" not in (d.get("title", "") or "").lower()
            ]

            if not real_docs:
                html_docs = _parse_docs_from_html(nested.get("info_html", ""))
                if html_docs:
                    nested["doc_files"] = html_docs
                    tender.raw_json = rj
                    changed = True
                    docs_added += 1
                elif existing_docs != real_docs:
                    nested["doc_files"] = []
                    tender.raw_json = rj
                    changed = True

            quality = compute_content_quality(rj, Tender.Source.TENDERGURU)
            if tender.content_quality != quality:
                tender.content_quality = quality
                changed = True

            if changed:
                to_update.append(tender)
                if len(to_update) >= batch_size:
                    if not dry_run:
                        Tender.objects.bulk_update(to_update, ["raw_json", "content_quality"])
                    updated += len(to_update)
                    self.stdout.write(f"  updated {updated}... (docs added: {docs_added})")
                    to_update = []

        if to_update:
            if not dry_run:
                Tender.objects.bulk_update(to_update, ["raw_json", "content_quality"])
            updated += len(to_update)

        prefix = "[DRY RUN] " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}Updated {updated}/{total} tenders, docs extracted from info_html: {docs_added}"
        ))
