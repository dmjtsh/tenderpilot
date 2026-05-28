import time
from datetime import date, timedelta

from django.core.management.base import BaseCommand

from apps.tenders.eis_client import search_tenders, REGION_CODES
from apps.tenders.services import upsert_tender


class Command(BaseCommand):
    help = "Парсинг тендеров из ЕИС (zakupki.gov.ru)"

    def add_arguments(self, parser) -> None:
        parser.add_argument("--days", type=int, default=7, help="За сколько дней парсить (игнорируется если указан --date-from)")
        parser.add_argument("--date-from", type=str, default="", help="Начало диапазона YYYY-MM-DD (включительно)")
        parser.add_argument("--date-to", type=str, default="", help="Конец диапазона YYYY-MM-DD (включительно, по умолчанию сегодня)")
        parser.add_argument("--fz", choices=["44", "223", "all"], default="all")
        parser.add_argument("--max-pages", type=int, default=50, help="Лимит страниц пагинации")
        parser.add_argument("--delay", type=float, default=0.5, help="Пауза между страницами (сек)")
        parser.add_argument("--enrich", action="store_true", help="Запустить детальное обогащение через Celery")
        parser.add_argument(
            "--regions", type=str, default="",
            help="Коды регионов через запятую (63,73,58) или названия (Самарская область,...)"
        )
        parser.add_argument(
            "--query", type=str, default="",
            help="Ключевые слова для поиска (напр. 'кровля' или 'благоустройство')"
        )

    def handle(self, *args, **options) -> None:
        days: int = options["days"]
        fz: str = options["fz"]
        max_pages: int = options["max_pages"]
        delay: float = options["delay"]
        do_enrich: bool = options["enrich"]
        regions_raw: str = options["regions"]
        query: str = options["query"]

        fz44 = fz in ("44", "all")
        fz223 = fz in ("223", "all")

        date_to = date.fromisoformat(options["date_to"]) if options["date_to"] else date.today()
        if options["date_from"]:
            date_from = date.fromisoformat(options["date_from"])
        else:
            date_from = date_to - timedelta(days=days)

        # Разбираем коды регионов
        region_codes: list[str] = []
        if regions_raw:
            for r in regions_raw.split(","):
                r = r.strip()
                if r.isdigit():
                    region_codes.append(r)
                elif r in REGION_CODES:
                    region_codes.append(REGION_CODES[r])
                else:
                    self.stdout.write(self.style.WARNING(f"Регион не найден: {r}"))

        runs = region_codes if region_codes else [None]

        self.stdout.write(
            self.style.NOTICE(
                f"Парсинг ЕИС: {date_from} → {date_to}, "
                f"44-ФЗ={fz44}, 223-ФЗ={fz223}, "
                f"регионы={region_codes or 'все'}, "
                f"запрос={query or 'все'}"
            )
        )

        total_saved = 0
        total_new = 0

        for region_code in runs:
            if region_code:
                region_name = next((k for k, v in REGION_CODES.items() if v == region_code), region_code)
                self.stdout.write(f"\n--- Регион: {region_name} ---")

            for page in range(1, max_pages + 1):
                self.stdout.write(f"  Страница {page}...", ending=" ")
                self.stdout.flush()

                results = search_tenders(date_from, date_to, page, fz44, fz223, region_code, query or None)
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
