"""
Одноразовая команда для первоначальной загрузки тендеров за N дней.

Стратегия: разбиваем диапазон на чанки по CHUNK_DAYS дней и обходим каждый.
Это обходит ограничение ЕИС на количество страниц пагинации (~50 стр. стабильно).

Пример:
    python manage.py bulk_load_tenders --days=90
    python manage.py bulk_load_tenders --days=30 --chunk=3 --max-pages=200
"""
import time
from datetime import date, timedelta

from django.core.management.base import BaseCommand

from apps.tenders.eis_client import search_tenders
from apps.tenders.services import upsert_tender


class Command(BaseCommand):
    help = "Первоначальная загрузка тендеров за N дней чанками"

    def add_arguments(self, parser) -> None:
        parser.add_argument("--days", type=int, default=90, help="Сколько дней назад охватить")
        parser.add_argument("--chunk", type=int, default=7, help="Размер чанка в днях")
        parser.add_argument("--max-pages", type=int, default=100, help="Макс. страниц на чанк")
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
                f"макс. {max_pages} стр/чанк)"
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
                    break

                for data in results:
                    try:
                        is_new = data["number"] not in existing_numbers
                        data["raw_json"] = data.copy()
                        tender = upsert_tender(data)
                        chunk_fetched += 1

                        if is_new:
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
                    # Последняя страница — записей меньше чем per_page
                    break

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
