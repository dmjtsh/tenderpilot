"""
Первоначальная загрузка коммерческих тендеров с komtender.ru.

Стратегия: sitemap → filter existing → parse pages → upsert → embed.
82k тендеров × 0.5s ≈ 11.4 часов. Запускать в tmux.

Пример:
    python manage.py bulk_load_komtender --limit=50
    python manage.py bulk_load_komtender --dry-run
    python manage.py bulk_load_komtender --no-embed --delay=0.3
"""
import time

import requests
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.tenders.komtender_client import fetch_sitemap_urls, parse_tender_page
from apps.tenders.models import Tender
from apps.tenders.services import upsert_tender


class Command(BaseCommand):
    help = "Первоначальная загрузка коммерческих тендеров с komtender.ru"

    def add_arguments(self, parser) -> None:
        parser.add_argument("--limit", type=int, default=0, help="Max тендеров (0 = все)")
        parser.add_argument("--delay", type=float, default=0.5, help="Пауза между запросами (сек)")
        parser.add_argument("--dry-run", action="store_true", help="Только подсчёт URLs")
        parser.add_argument("--no-embed", action="store_true", help="Не ставить в очередь embed")
        parser.add_argument("--offset", type=int, default=0, help="Пропустить первые N URLs")

    def handle(self, *args, **options) -> None:
        limit: int = options["limit"]
        delay: float = options["delay"]
        dry_run: bool = options["dry_run"]
        no_embed: bool = options["no_embed"]
        offset: int = options["offset"]

        self.stdout.write(self.style.NOTICE("Загружаем sitemap URLs..."))
        urls = fetch_sitemap_urls(since=None)
        self.stdout.write(f"Всего URLs в sitemap: {len(urls)}")

        existing_numbers = set(
            Tender.objects.filter(source=Tender.Source.KOMTENDER)
            .values_list("number", flat=True)
        )
        self.stdout.write(f"Уже в БД: {len(existing_numbers)}")

        new_urls = [u for u in urls if u["komtender_id"] not in existing_numbers]
        self.stdout.write(f"Новых: {len(new_urls)}")

        if dry_run:
            self.stdout.write(self.style.SUCCESS("Dry run — выход."))
            return

        if offset > 0:
            new_urls = new_urls[offset:]
            self.stdout.write(f"После offset={offset}: {len(new_urls)}")

        if limit > 0:
            new_urls = new_urls[:limit]
            self.stdout.write(f"С лимитом: {len(new_urls)}")

        session = requests.Session()
        session.headers["User-Agent"] = "Tenderoll/1.0 (tender aggregator; support@tenderoll.ru)"

        parsed = 0
        errors = 0

        for i, item in enumerate(new_urls, 1):
            try:
                data = parse_tender_page(item["url"], session=session)
                if not data:
                    errors += 1
                    self.stdout.write(self.style.WARNING(f"  [{i}/{len(new_urls)}] SKIP {item['url']}"))
                    time.sleep(delay)
                    continue

                tender = upsert_tender(data)
                Tender.objects.filter(pk=tender.pk).update(enriched_at=timezone.now())
                parsed += 1

                if not no_embed:
                    from apps.tenders.tasks import enrich_tender
                    enrich_tender.apply_async(args=[tender.pk], countdown=5)

                if i % 50 == 0 or i == len(new_urls):
                    self.stdout.write(f"  [{i}/{len(new_urls)}] parsed={parsed} errors={errors}")

            except Exception as exc:
                errors += 1
                self.stdout.write(self.style.WARNING(f"  [{i}/{len(new_urls)}] ERROR {item['url']}: {exc}"))

            time.sleep(delay)

        self.stdout.write(
            self.style.SUCCESS(f"\nГотово: parsed={parsed}, errors={errors}")
        )
        if not no_embed and parsed > 0:
            self.stdout.write(f"  {parsed} тендеров поставлены в очередь на embed через enrich_tender.")
