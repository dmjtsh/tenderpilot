"""
Одноразовая команда для первоначальной загрузки тендеров за N дней.

Стратегия:
- Однодневные чанки (один день = один запрос).
- ЕИС жёстко ограничивает выдачу 100 страницами (5000 записей) на запрос.
  При ~10к тендеров/день по 44-ФЗ обходим так:
  * 44-ФЗ: 4 прохода по ценовым диапазонам (каждый < 5000 записей)
  * 223-ФЗ: один проход (~3к/день — укладывается)
- Останов каждого прохода: N страниц подряд без новых тендеров.

Пример:
    python manage.py bulk_load_tenders --days=90
    python manage.py bulk_load_tenders --days=30 --no-enrich
"""
import time
from datetime import date, timedelta

from django.core.management.base import BaseCommand

from apps.tenders.eis_client import search_tenders
from apps.tenders.services import upsert_tender

DEFAULT_STOP_AFTER = 5
DEFAULT_MIN_PAGES = 10
# ЕИС выдаёт max 100 стр.; 110 — чтобы stop-after успел сработать
DEFAULT_MAX_PAGES = 110

# Ценовые диапазоны для 44-ФЗ (priceFromGeneral / priceToGeneral).
# Проверено на 30.04.2026: каждый диапазон < 5000 записей.
#   ≤100к: ~2300, 100к-1млн: ~4450, 1-5млн: ~2650, 5млн+: ~1400
FZ44_PRICE_RANGES: list[tuple[str, str | None, str | None]] = [
    ("≤100к",    None,        "100000"),
    ("100к-1млн","100001",    "1000000"),
    ("1-5млн",   "1000001",   "5000000"),
    ("5млн+",    "5000001",   None),
]


class Command(BaseCommand):
    help = "Первоначальная загрузка тендеров за N дней (по 1 дню, 44-ФЗ×4 ценовых диапазона + 223-ФЗ)"

    def add_arguments(self, parser) -> None:
        parser.add_argument("--days", type=int, default=90, help="Сколько дней назад охватить")
        parser.add_argument(
            "--max-pages", type=int, default=DEFAULT_MAX_PAGES,
            help=f"Страховочный лимит страниц на запрос (default: {DEFAULT_MAX_PAGES})"
        )
        parser.add_argument(
            "--stop-after", type=int, default=DEFAULT_STOP_AFTER,
            help=f"Стоп после N страниц подряд без новых тендеров (default: {DEFAULT_STOP_AFTER})"
        )
        parser.add_argument(
            "--min-pages", type=int, default=DEFAULT_MIN_PAGES,
            help=f"Минимум страниц перед включением stop-after (default: {DEFAULT_MIN_PAGES})"
        )
        parser.add_argument("--delay", type=float, default=0.5, help="Пауза между страницами (сек)")
        parser.add_argument(
            "--enrich", action="store_true", default=True,
            help="Ставить новые тендеры в очередь на обогащение (по умолчанию включено)"
        )
        parser.add_argument(
            "--no-enrich", dest="enrich", action="store_false",
            help="Не обогащать (только базовые данные)"
        )

    def handle(self, *args, **options) -> None:
        days: int = options["days"]
        max_pages: int = options["max_pages"]
        stop_after: int = options["stop_after"]
        min_pages: int = options["min_pages"]
        delay: float = options["delay"]
        do_enrich: bool = options["enrich"]

        today = date.today()
        start_date = today - timedelta(days=days)

        # Однодневные чанки от новых к старым
        day_chunks: list[date] = []
        d = today
        while d >= start_date:
            day_chunks.append(d)
            d -= timedelta(days=1)

        total_days = len(day_chunks)
        passes_per_day = len(FZ44_PRICE_RANGES) + 1  # 4 ценовых + 1 для 223-ФЗ
        self.stdout.write(
            self.style.NOTICE(
                f"Загрузка тендеров: {start_date} → {today} "
                f"({days} дней, {total_days} однодневных чанков × {passes_per_day} проходов, "
                f"лимит {max_pages} стр/проход, стоп после {stop_after} пустых стр.)"
            )
        )

        total_new = 0
        total_updated = 0

        for day_idx, day in enumerate(day_chunks, 1):
            self.stdout.write(f"\n[{day_idx}/{total_days}] День {day}")

            from apps.tenders.models import Tender
            existing_numbers = set(
                Tender.objects.filter(
                    published_at__date=day,
                ).values_list("number", flat=True)
            )

            day_new = 0
            day_fetched = 0

            # 44-ФЗ: 4 прохода по ценовым диапазонам
            for range_label, price_from, price_to in FZ44_PRICE_RANGES:
                self.stdout.write(f"  [44-ФЗ / НМЦК {range_label}]")
                pass_new, pass_fetched = self._fetch_pass(
                    date_from=day, date_to=day,
                    fz44=True, fz223=False,
                    price_from=price_from, price_to=price_to,
                    existing_numbers=existing_numbers,
                    max_pages=max_pages, min_pages=min_pages,
                    stop_after=stop_after, delay=delay, do_enrich=do_enrich,
                )
                day_new += pass_new
                day_fetched += pass_fetched

            # 223-ФЗ: один проход (~3к/день — укладывается в лимит)
            self.stdout.write(f"  [223-ФЗ]")
            pass_new, pass_fetched = self._fetch_pass(
                date_from=day, date_to=day,
                fz44=False, fz223=True,
                price_from=None, price_to=None,
                existing_numbers=existing_numbers,
                max_pages=max_pages, min_pages=min_pages,
                stop_after=stop_after, delay=delay, do_enrich=do_enrich,
            )
            day_new += pass_new
            day_fetched += pass_fetched

            total_new += day_new
            total_updated += day_fetched - day_new
            self.stdout.write(f"  День итого: {day_fetched} тендеров, новых: {day_new}")

        self.stdout.write(
            self.style.SUCCESS(
                f"\n✓ Готово: новых: {total_new}, обновлено: {total_updated}"
            )
        )
        if do_enrich and total_new > 0:
            self.stdout.write(f"  {total_new} новых тендеров поставлены в очередь Celery на обогащение.")
        self.stdout.write(
            "  Запустите 'python manage.py index_tenders --only-new' для индексации в Qdrant."
        )

    def _fetch_pass(
        self,
        date_from: date,
        date_to: date,
        fz44: bool,
        fz223: bool,
        price_from: str | None,
        price_to: str | None,
        existing_numbers: set,
        max_pages: int,
        min_pages: int,
        stop_after: int,
        delay: float,
        do_enrich: bool,
    ) -> tuple[int, int]:
        """Один проход пагинации для заданных параметров. Возвращает (новых, всего)."""
        pass_new = 0
        pass_fetched = 0
        consecutive_no_new = 0

        for page in range(1, max_pages + 1):
            try:
                results = search_tenders(
                    date_from=date_from,
                    date_to=date_to,
                    page=page,
                    fz44=fz44,
                    fz223=fz223,
                    price_from=price_from,
                    price_to=price_to,
                )
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f"    стр.{page}: ошибка — {exc}"))
                break

            if not results:
                break

            page_new = 0
            for data in results:
                try:
                    is_new = data["number"] not in existing_numbers
                    data["raw_json"] = data.copy()
                    tender = upsert_tender(data)
                    pass_fetched += 1

                    if is_new:
                        page_new += 1
                        pass_new += 1
                        existing_numbers.add(data["number"])
                        if do_enrich:
                            from apps.tenders.tasks import enrich_tender
                            enrich_tender.apply_async(args=[tender.pk], countdown=10)
                except Exception as exc:
                    self.stdout.write(
                        self.style.WARNING(f"    upsert error {data.get('number', '?')}: {exc}")
                    )

            self.stdout.write(
                f"    стр.{page}: +{len(results)} (итого: {pass_fetched}, новых: {pass_new})"
            )

            if page == min_pages:
                consecutive_no_new = 0
            elif page > min_pages:
                if page_new == 0:
                    consecutive_no_new += 1
                    if consecutive_no_new >= stop_after:
                        self.stdout.write(
                            self.style.WARNING(
                                f"    Стоп: {stop_after} стр. подряд без новых — контент исчерпан."
                            )
                        )
                        break
                else:
                    consecutive_no_new = 0

            if page < max_pages:
                time.sleep(delay)

        return pass_new, pass_fetched

