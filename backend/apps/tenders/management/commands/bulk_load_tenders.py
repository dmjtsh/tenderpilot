"""
Одноразовая команда для первоначальной загрузки тендеров за N дней.

Стратегия:
- Разбиваем диапазон на однодневные чанки (по умолчанию).
- Каждый день парсится ДВАЖДЫ: отдельно 44-ФЗ и отдельно 223-ФЗ.
  Это обходит жёсткий лимит ЕИС — 100 страниц (5000 записей) на запрос.
  При ~11к тендеров/день: 44-ФЗ ≈ 8к + 223-ФЗ ≈ 3к — каждый укладывается.
- Останов: N страниц подряд без новых тендеров (ЕИС отдаёт дубликаты после исчерпания).

Пример:
    python manage.py bulk_load_tenders --days=90
    python manage.py bulk_load_tenders --days=30 --no-enrich
"""
import time
from datetime import date, timedelta

from django.core.management.base import BaseCommand

from apps.tenders.eis_client import search_tenders
from apps.tenders.services import upsert_tender

# Сколько страниц подряд без новых тендеров означает «контент исчерпан»
DEFAULT_STOP_AFTER = 5
# Минимум страниц перед включением stop-after (защита при прерванном прогоне)
DEFAULT_MIN_PAGES = 20
# Страховочный лимит: ЕИС отдаёт max 100 стр., ставим 110 чтобы stop-after сработал
DEFAULT_MAX_PAGES = 110


class Command(BaseCommand):
    help = "Первоначальная загрузка тендеров за N дней (по 1 дню, fz44 и fz223 раздельно)"

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
        self.stdout.write(
            self.style.NOTICE(
                f"Загрузка тендеров: {start_date} → {today} "
                f"({days} дней, {total_days} однодневных чанков × 2 запроса (44+223), "
                f"лимит {max_pages} стр/запрос, стоп после {stop_after} пустых стр.)"
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

            # Два прохода: сначала 44-ФЗ, потом 223-ФЗ
            for fz_label, fz44, fz223 in [("44-ФЗ", True, False), ("223-ФЗ", False, True)]:
                self.stdout.write(f"  [{fz_label}]")
                pass_new = 0
                pass_fetched = 0
                consecutive_no_new = 0

                for page in range(1, max_pages + 1):
                    try:
                        results = search_tenders(
                            date_from=day,
                            date_to=day,
                            page=page,
                            fz44=fz44,
                            fz223=fz223,
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

                    if len(results) < 50:
                        break

                    # stop-after включается после min_pages
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

                day_fetched += pass_fetched
                day_new += pass_new

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

