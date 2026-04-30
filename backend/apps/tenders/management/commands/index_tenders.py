import uuid
from django.core.management.base import BaseCommand

from apps.tenders.models import Tender
from apps.search.embedder import embedder, tender_text
from apps.search.services import qdrant


class Command(BaseCommand):
    help = "Переиндексировать тендеры в Qdrant"

    def add_arguments(self, parser) -> None:
        parser.add_argument("--limit", type=int, default=0, help="Макс. тендеров (0 = все)")
        parser.add_argument("--batch-size", type=int, default=32)
        parser.add_argument("--only-new", action="store_true", help="Только без embedding_id")

    def handle(self, *args, **options) -> None:
        limit: int = options["limit"]
        batch_size: int = options["batch_size"]
        only_new: bool = options["only_new"]

        qdrant.ensure_collections()

        qs = Tender.objects.select_related("customer").order_by("id")
        if only_new:
            qs = qs.filter(embedding_id__isnull=True)
        if limit:
            qs = qs[:limit]

        total = qs.count()
        self.stdout.write(f"Индексируем {total} тендеров (batch={batch_size})...")

        processed = 0
        batch_tenders: list[Tender] = []

        for tender in qs.iterator(chunk_size=batch_size):
            batch_tenders.append(tender)

            if len(batch_tenders) >= batch_size:
                processed += self._index_batch(batch_tenders)
                self.stdout.write(f"  {processed}/{total}")
                batch_tenders = []

        if batch_tenders:
            processed += self._index_batch(batch_tenders)

        self.stdout.write(self.style.SUCCESS(f"\nГотово: проиндексировано {processed} тендеров"))

    def _index_batch(self, tenders: list[Tender]) -> int:
        texts = [tender_text(t) for t in tenders]
        vectors = embedder.embed_passages(texts)

        items = []
        for t, vec in zip(tenders, vectors):
            payload = {
                "number": t.number,
                "title": t.title,
                "nmck": float(t.nmck) if t.nmck else None,
                "customer_name": t.customer.name if t.customer else "",
                "region": t.region,
                "law_type": t.law_type,
                "status": t.status,
                "published_at": t.published_at.isoformat() if t.published_at else None,
            }
            items.append((t.pk, vec, payload))

        qdrant.upsert_tenders_batch(items)

        # Отмечаем каждый тендер как проиндексированный (уникальный UUID)
        for t in tenders:
            Tender.objects.filter(pk=t.pk).update(embedding_id=uuid.uuid4())

        return len(tenders)
