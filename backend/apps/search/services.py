from typing import Any
from django.conf import settings
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue, MatchAny, Range,
)


COLLECTION_TENDERS = "tenders"
COLLECTION_DOC_CHUNKS = "doc_chunks"
EMBEDDING_DIM = 1024  # multilingual-e5-large


class QdrantService:
    def __init__(self) -> None:
        self._client: QdrantClient | None = None

    @property
    def client(self) -> QdrantClient:
        if self._client is None:
            self._client = QdrantClient(url=settings.QDRANT_URL)
        return self._client

    def ensure_collections(self) -> None:
        existing = {c.name for c in self.client.get_collections().collections}
        for name in (COLLECTION_TENDERS, COLLECTION_DOC_CHUNKS):
            if name not in existing:
                self.client.create_collection(
                    collection_name=name,
                    vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
                )

    def upsert_tender(self, tender_id: int, vector: list[float], payload: dict[str, Any]) -> None:
        self.client.upsert(
            collection_name=COLLECTION_TENDERS,
            points=[PointStruct(id=tender_id, vector=vector, payload=payload)],
        )

    def upsert_tenders_batch(
        self, items: list[tuple[int, list[float], dict[str, Any]]]
    ) -> None:
        """Батчевый upsert — эффективнее для index_tenders."""
        points = [
            PointStruct(id=tid, vector=vec, payload=payload)
            for tid, vec, payload in items
        ]
        self.client.upsert(collection_name=COLLECTION_TENDERS, points=points)

    def search_tenders(
        self,
        vector: list[float],
        limit: int = 20,
        region: str | None = None,
        regions: list[str] | None = None,
        status: str | None = None,
        nmck_min: float | None = None,
        nmck_max: float | None = None,
    ) -> list[dict[str, Any]]:
        conditions = []
        if regions:
            conditions.append(FieldCondition(key="region", match=MatchAny(any=regions)))
        elif region:
            conditions.append(FieldCondition(key="region", match=MatchValue(value=region)))
        if status:
            conditions.append(FieldCondition(key="status", match=MatchValue(value=status)))
        if nmck_min is not None or nmck_max is not None:
            conditions.append(
                FieldCondition(key="nmck", range=Range(gte=nmck_min, lte=nmck_max))
            )

        query_filter = Filter(must=conditions) if conditions else None

        results = self.client.query_points(
            collection_name=COLLECTION_TENDERS,
            query=vector,
            limit=limit,
            with_payload=True,
            query_filter=query_filter,
        ).points
        return [{"id": r.id, "score": r.score, **r.payload} for r in results]

    def match_profile(self, profile: Any, limit: int = 20, direction_ids: list[int] | None = None) -> list[dict[str, Any]]:
        qs = profile.directions.filter(profile_vector__isnull=False)
        if direction_ids:
            qs = qs.filter(id__in=direction_ids)
        directions = list(qs)
        if not directions:
            return []

        all_results: dict[int, dict[str, Any]] = {}

        for direction in directions:
            conditions = []
            if direction.regions:
                conditions.append(
                    FieldCondition(key="region", match=MatchAny(any=direction.regions))
                )
            if direction.nmck_min is not None or direction.nmck_max is not None:
                conditions.append(
                    FieldCondition(key="nmck", range=Range(gte=direction.nmck_min, lte=direction.nmck_max))
                )
            if direction.law_types:
                conditions.append(
                    FieldCondition(key="law_type", match=MatchAny(any=direction.law_types))
                )

            results = self.client.query_points(
                collection_name=COLLECTION_TENDERS,
                query=direction.profile_vector,
                query_filter=Filter(must=conditions) if conditions else None,
                limit=100,
                with_payload=True,
            ).points

            for r in results:
                existing = all_results.get(r.id)
                if existing is None or r.score > existing["score"]:
                    all_results[r.id] = {
                        "id": r.id,
                        "score": r.score,
                        "matched_direction": direction.name,
                        **r.payload,
                    }

        sorted_results = sorted(all_results.values(), key=lambda x: x["score"], reverse=True)
        return sorted_results[:limit * 5]

    def delete_tender(self, tender_id: int) -> None:
        self.client.delete(
            collection_name=COLLECTION_TENDERS,
            points_selector=[tender_id],
        )


qdrant = QdrantService()
