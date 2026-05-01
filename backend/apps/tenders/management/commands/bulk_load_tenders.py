"""
Одноразовая команда для первоначальной загрузки тендеров за N дней.

Стратегия: разбиваем диапазон на чанки по CHUNK_DAYS дней и обходим каждый.
Это обходит ограничение ЕИС на количество страниц пагинации (~50 стр. стабильно).

ЕИС возвращает дубликаты после исчерпания уникальных записей, поэтому останов
происходит не по `len < 50`, а по `--stop-after` последовательных страниц без
новых тендеров.

Пример:
    python manage.py bulk_load_tenders --days=90
    python manage.py bulk_load_tenders --days=30 --chunk=3
"""
import time
from datetime import date, timedelta

from django.core.management.base import BaseCommand

from apps.tenders.eis_client import search_tenders
from apps.tenders.services import upsert_tender

# Сколько страниц подряд без новых тендеров означает «контент исчерпан»
DEFAULT_STOP_AFTER = 5
# Страховочный лимит на случай зависания (ЕИС не должен выдавать 5000+ стр. на 7 дней)
DEFAULT_MAX_PAGES = 500


class Command(BaseCommand):
    help = "Первоначальная загрузка тендеров за N дней чанками"

    def add_arguments(self, parser) -> None:
        parser.add_argument("--days", type=int, default=90, help="Сколько дней назад охватить")
        parser.add_argument("--chunk", type=int, default=7, help="Размер чанка в днях")
        parser.add_argument(
            "--max-pages", type=int, default=DEFAULT_MAX_PAGES,
            help=f"Страховочный лимит страниц на чанк (default: {DEFAULT_MAX_PAGES})"
        )
        parser.add_argument(
            "--stop-after", type=int, default=DEFAULT_STOP_AFTER,
            help=f"Стоп после N страниц подряд без новых тендеров (default: {DEFAULT_STOP_AFTER})"
        )
        parser.add_argument(
            "--min-pages", type=int, default=50,
            help="Минимум страниц на чанк (защита от раннего стопа при прерванном прогоне, default: 50)"
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
        chunk_days: int = options["chunk"]
        max_pages: int = options["max_pages"]
        stop_after: int = options["stop_after"]
        min_pages: int = options["min_pages"]
        delay: float = options["delay"]
        do_enrich: bool = options["enrich"]

        today = date.today()
        start_date = today - timedelta(days=days)

        # Строим список чанков от новых к старым
        chunks: list[tuple[date, date]] = []
        chunk_end = today
        while chunk_end > start_date:
            chunk_start = max(chunk_end - timedelta(days=chunk_days - 1), start_date)
            chunks.append((chunk_start, chunk_end))
            chunk_end = chunk_start - timedelta(days=1)

        total_chunks = len(chunks)
        self.stdout.write(
            self.style.NOTICE(
                f"Загрузка тендеров: {start_date} → {today} "
                f"({days} дней, {total_chunks} чанков по {chunk_days} дней, "
                f"лимит {max_pages} стр/чанк, стоп после {stop_after} пустых стр.)"
            )
        )

        total_fetched = 0
        total_new = 0
        total_updated = 0

        for chunk_idx, (date_from, date_to) in enumerate(chunks, 1):
            self.stdout.write(
                f"\n[{chunk_idx}/{total_chunks}] Чанк {date_from} → {date_to}"
            )

            chunk_fetched = 0
            chunk_new = 0
            consecutive_no_new = 0

            # Предзагружаем номера тендеров за этот период для определения новых
            from apps.tenders.models import Tender
            existing_numbers = set(
                Tender.objects.filter(
                    published_at__date__gte=date_from,
                    published_at__date__lte=date_to,
                ).values_list("number", flat=True)
            )

            for page in range(1, max_pages + 1):
                try:
                    results = search_tenders(
                        date_from=date_from,
                        date_to=date_to,
                        page=page,
                        fz44=True,
                        fz223=True,
                    )
                except Exception as exc:
                    self.stdout.write(
                        self.style.WARNING(f"  Страница {page}: ошибка — {exc}")
                    )
                    break

                if not results:
                    # ЕИС вернул пустую страницу — всё загружено
                    break

                page_new = 0
                for data in results:
                    try:
                        is_new = data["number"] not in existing_numbers
                        data["raw_json"] = data.copy()
                        tender = upsert_tender(data)
                        chunk_fetched += 1

                        if is_new:
                            page_new += 1
                            chunk_new += 1
                            existing_numbers.add(data["number"])
                            if do_enrich:
                                from apps.tenders.tasks import enrich_tender
                                enrich_tender.apply_async(
                                    args=[tender.pk],
                                    countdown=10,
                                )
                    except Exception as exc:
                        self.stdout.write(
                            self.style.WARNING(
                                f"  upsert error {data.get('number', '?')}: {exc}"
                            )
                        )

                self.stdout.write(
                    f"  стр.{page}: +{len(results)} (чанк итого: {chunk_fetched}, новых: {chunk_new})"
                )

                if len(results) < 50:
                    # Последняя страница ЕИС вернул меньше per_page записей
                    break

                # Отслеживаем страницы без новых тендеров (ЕИС отдаёт дубликаты).
                # Счётчик начинает считаться только после min_pages.
                if page == min_pages:
                    consecutive_no_new = 0
                elif page > min_pages:
                    if page_new == 0:
                        consecutive_no_new += 1
                        if consecutive_no_new >= stop_after:
                            self.stdout.write(
                                self.style.WARNING(
                                    f"  Стоп: {stop_after} страниц подряд без новых тендеров — "
                                    f"уникальный контент чанка исчерпан."
                                )
                            )
                            break
                    else:
                        consecutive_no_new = 0

                if page < max_pages:
                    time.sleep(delay)

            total_fetched += chunk_fetched
            total_new += chunk_new
            total_updated += chunk_fetched - chunk_new

        self.stdout.write(
            self.style.SUCCESS(
                f"\n✓ Готово: всего {total_fetched} тендеров "
                f"(новых: {total_new}, обновлено: {total_updated})"
            )
        )
        if do_enrich and total_new > 0:
            self.stdout.write(
                f"  {total_new} новых тендеров поставлены в очередь Celery на обогащение."
            )
        self.stdout.write(
            "  Запустите 'python manage.py index_tenders --only-new' для индексации в Qdrant."
        )
