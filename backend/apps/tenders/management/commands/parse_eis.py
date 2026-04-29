import time
from datetime import date, timedelta

from django.core.management.base import BaseCommand

from apps.tenders.eis_client import search_tenders
from apps.tenders.services import upsert_tender


class Command(BaseCommand):
    help = "Парсинг тендеров из ЕИС (zakupki.gov.ru)"

    def add_arguments(self, parser) -> None:
        parser.add_argument("--days", type=int, default=7, help="За сколько дней парсить")
        parser.add_argument("--fz", choices=["44", "223", "all"], default="all")
        parser.add_argument("--max-pages", type=int, default=50, help="Лимит страниц пагинации")
        parser.add_argument("--delay", type=float, default=0.5, help="Пауза между страницами (сек)")
        parser.add_argument("--enrich", action="store_true", help="Запустить детальное обогащение через Celery")

    def handle(self, *args, **options) -> None:
        days: int = options["days"]
        fz: str = options["fz"]
        max_pages: int = options["max_pages"]
        delay: float = options["delay"]
        do_enrich: bool = options["enrich"]

        fz44 = fz in ("44", "all")
        fz223 = fz in ("223", "all")

        date_to = date.today()
        date_from = date_to - timedelta(days=days)

        self.stdout.write(
            self.style.NOTICE(
                f"Парсинг ЕИС: {date_from} → {date_to}, "
                f"44-ФЗ={fz44}, 223-ФЗ={fz223}"
            )
        )

        total_saved = 0
        total_new = 0

        for page in range(1, max_pages + 1):
            self.stdout.write(f"  Страница {page}...", ending=" ")
            self.stdout.flush()

            results = search_tenders(date_from, date_to, page, fz44, fz223)
            if not results:
                self.stdout.write("пусто, стоп.")
                break

            self.stdout.write(f"{len(results)} тендеров")

            for data in results:
                data["raw_json"] = data.copy()
                tender = upsert_tender(data)
                total_saved += 1

                if do_enrich:
                    from apps.tenders.tasks import enrich_tender
                    enrich_tender.delay(tender.pk)
                    total_new += 1

            if len(results) < 50:
                break

            if page < max_pages:
                time.sleep(delay)

        self.stdout.write(
            self.style.SUCCESS(
                f"\nГотово: сохранено {total_saved} тендеров"
                + (f", поставлено в очередь {total_new} задач обогащения" if do_enrich else "")
            )
        )
