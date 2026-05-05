import time

from django.core.management.base import BaseCommand

from apps.tenders.bidzaar_client import fetch_tender_detail, search_tenders
from apps.tenders.services import upsert_tender


class Command(BaseCommand):
    help = "Парсинг тендеров из Bidzaar (bidzaar.com)"

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--days", type=int, default=7,
            help="За сколько дней парсить (по дате публикации)",
        )
        parser.add_argument(
            "--query", type=str, default="",
            help="Ключевые слова для поиска, напр. 'кровля'",
        )
        parser.add_argument(
            "--max-pages", type=int, default=40,
            help="Лимит страниц пагинации (25 тендеров/страница)",
        )
        parser.add_argument(
            "--enrich", action="store_true",
            help="Обогатить каждый тендер детальным запросом (бюджет, ОКПД)",
        )
        parser.add_argument(
            "--all-statuses", action="store_true",
            help="Парсить все статусы (по умолчанию только активные)",
        )
        parser.add_argument(
            "--delay", type=float, default=0.4,
            help="Пауза между страницами (сек)",
        )

    def handle(self, *args, **options) -> None:
        days: int = options["days"]
        query: str = options["query"]
        max_pages: int = options["max_pages"]
        do_enrich: bool = options["enrich"]
        active_only: bool = not options["all_statuses"]
        delay: float = options["delay"]

        self.stdout.write(
            self.style.NOTICE(
                f"Парсинг Bidzaar: последние {days} дн., "
                f"запрос={query or 'все'}, "
                f"только активные={active_only}, "
                f"обогащение={do_enrich}"
            )
        )

        items = search_tenders(
            days=days,
            query=query,
            max_pages=max_pages,
            active_only=active_only,
        )

        self.stdout.write(f"Найдено: {len(items)} тендеров")

        saved = 0
        enriched = 0
        errors = 0

        for data in items:
            bidzaar_id: str = data.pop("bidzaar_id", "")

            if do_enrich and bidzaar_id:
                detail = fetch_tender_detail(bidzaar_id)
                if detail:
                    data["nmck"] = detail["nmck"]
                    data["okpd_codes"] = detail["okpd_codes"]
                    if detail["customer_inn"]:
                        data["customer_inn"] = detail["customer_inn"]
                    # Сохраним сырой ответ детали в raw_json
                    data["raw_detail"] = detail.get("raw_detail", {})
                    enriched += 1
                time.sleep(0.3)

            try:
                data["raw_json"] = {k: v for k, v in data.items() if k != "raw_json"}
                upsert_tender(data)
                saved += 1
            except Exception as exc:
                errors += 1
                self.stdout.write(
                    self.style.ERROR(f"Ошибка сохранения {data.get('number')}: {exc}")
                )

        msg = f"Готово: сохранено {saved}"
        if do_enrich:
            msg += f", обогащено {enriched}"
        if errors:
            msg += f", ошибок {errors}"
        self.stdout.write(self.style.SUCCESS(msg))
