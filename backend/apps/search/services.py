import time
from typing import Any
from django.conf import settings
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue, MatchAny, Range,
    HasIdCondition,
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

    def get_tender_vector(self, tender_id: int) -> list[float] | None:
        points = self.client.retrieve(
            collection_name=COLLECTION_TENDERS,
            ids=[tender_id],
            with_vectors=True,
        )
        if not points:
            return None
        return points[0].vector

    def search_tenders(
        self,
        vector: list[float],
        limit: int = 20,
        region: str | None = None,
        regions: list[str] | None = None,
        status: str | None = None,
        nmck_min: float | None = None,
        nmck_max: float | None = None,
        law_types: list[str] | None = None,
        procedure_types: list[str] | None = None,
        exclude_ids: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        conditions = []
        must_not = []
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
        if law_types:
            conditions.append(FieldCondition(key="law_type", match=MatchAny(any=law_types)))
        if procedure_types:
            conditions.append(FieldCondition(key="procedure_type", match=MatchAny(any=procedure_types)))
        if exclude_ids:
            must_not.append(HasIdCondition(has_id=exclude_ids))

        query_filter = Filter(
            must=conditions or None,
            must_not=must_not or None,
        ) if conditions or must_not else None

        results = self.client.query_points(
            collection_name=COLLECTION_TENDERS,
            query=vector,
            limit=limit,
            with_payload=True,
            query_filter=query_filter,
        ).points
        return [{"id": r.id, "score": r.score, **r.payload} for r in results]

    def match_profile(
        self,
        profile: Any,
        limit: int = 20,
        direction_ids: list[int] | None = None,
        extra_regions: list[str] | None = None,
        extra_nmck_min: float | None = None,
        extra_nmck_max: float | None = None,
        extra_law_types: list[str] | None = None,
        extra_procedure_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        qs = profile.directions.filter(profile_vector__isnull=False)
        if direction_ids:
            qs = qs.filter(id__in=direction_ids)
        directions = list(qs)
        if not directions:
            return []

        all_results: dict[int, dict[str, Any]] = {}

        # Pre-fetch won tender vectors once (shared across all directions)
        won_tender_ids = getattr(profile, "won_tender_ids", None) or []
        won_vectors: dict[int, list[float]] = {}
        for won_tid in won_tender_ids:
            vec = self.get_tender_vector(won_tid)
            if vec is not None:
                won_vectors[won_tid] = vec

        for direction in directions:
            conditions = [
                FieldCondition(key="status", match=MatchValue(value="active")),
                FieldCondition(key="deadline_at_ts", range=Range(gt=int(time.time()))),
            ]

            regions = list(set(direction.regions or []) & set(extra_regions)) if extra_regions and direction.regions else (extra_regions or direction.regions)
            if regions:
                conditions.append(
                    FieldCondition(key="region", match=MatchAny(any=regions))
                )

            eff_nmck_min = max(filter(None, [direction.nmck_min, extra_nmck_min]), default=None)
            eff_nmck_max = min(filter(None, [direction.nmck_max, extra_nmck_max]), default=None)
            if eff_nmck_min is not None or eff_nmck_max is not None:
                conditions.append(
                    FieldCondition(key="nmck", range=Range(gte=eff_nmck_min, lte=eff_nmck_max))
                )

            law_types = list(set(direction.law_types or []) & set(extra_law_types)) if extra_law_types and direction.law_types else (extra_law_types or direction.law_types)
            if law_types:
                conditions.append(
                    FieldCondition(key="law_type", match=MatchAny(any=law_types))
                )

            proc_types = list(set(direction.procedure_types or []) & set(extra_procedure_types)) if extra_procedure_types and direction.procedure_types else (extra_procedure_types or direction.procedure_types)
            if proc_types:
                conditions.append(
                    FieldCondition(key="procedure_type", match=MatchAny(any=proc_types))
                )

            direction_filter = Filter(must=conditions) if conditions else None

            # 1. Hyde search
            hyde_results = self.client.query_points(
                collection_name=COLLECTION_TENDERS,
                query=direction.profile_vector,
                query_filter=direction_filter,
                limit=100,
                with_payload=True,
            ).points

            # 2. Won tender searches — separate queries, bring in new candidates
            # candidates: {id: {hyde: float, won: {tid: float}, payload: dict}}
            candidates: dict[int, dict] = {}
            for r in hyde_results:
                candidates[r.id] = {"hyde": r.score, "won": {}, "payload": r.payload}

            for won_tid, won_vec in won_vectors.items():
                won_hits = self.client.query_points(
                    collection_name=COLLECTION_TENDERS,
                    query=won_vec,
                    query_filter=direction_filter,
                    limit=50,
                    with_payload=True,
                ).points
                for r in won_hits:
                    if r.id not in candidates:
                        candidates[r.id] = {"hyde": 0.0, "won": {}, "payload": r.payload}
                    candidates[r.id]["won"][won_tid] = r.score

            # 3. Final score: 0.5*hyde + (0.5/N)*sum(won_i)  [N = total won vectors]
            N = len(won_vectors)
            exclude_kws = [kw.lower() for kw in (direction.exclude_keywords or [])]
            for cid, data in candidates.items():
                if exclude_kws:
                    title_lower = (data["payload"].get("title") or "").lower()
                    if any(kw in title_lower for kw in exclude_kws):
                        continue
                if N > 0:
                    won_total = sum(data["won"].get(tid, 0.0) for tid in won_vectors)
                    final = 0.5 * data["hyde"] + (0.5 / N) * won_total
                else:
                    final = data["hyde"]
                existing = all_results.get(cid)
                if existing is None or final > existing["score"]:
                    all_results[cid] = {
                        "id": cid,
                        "score": final,
                        "matched_direction": direction.name,
                        "matched_direction_id": direction.id,
                        **data["payload"],
                    }

        sorted_results = sorted(all_results.values(), key=lambda x: x["score"], reverse=True)
        return sorted_results[:limit * 10]

    def search_doc_chunks(
        self,
        vector: list[float],
        tender_id: int,
        limit: int = 2,
        score_threshold: float = 0.3,
    ) -> list[dict[str, Any]]:
        results = self.client.query_points(
            collection_name=COLLECTION_DOC_CHUNKS,
            query=vector,
            query_filter=Filter(must=[
                FieldCondition(key="tender_id", match=MatchValue(value=tender_id)),
            ]),
            limit=limit,
            score_threshold=score_threshold,
            with_payload=True,
        ).points
        return [{"score": r.score, **(r.payload or {})} for r in results]

    def upsert_doc_chunks(
        self, points: list[tuple[str, list[float], dict[str, Any]]],
    ) -> None:
        if not points:
            return
        self.client.upsert(
            collection_name=COLLECTION_DOC_CHUNKS,
            points=[
                PointStruct(id=pid, vector=vec, payload=payload)
                for pid, vec, payload in points
            ],
        )

    def scroll_doc_chunks(
        self,
        document_id: int,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        results, _ = self.client.scroll(
            collection_name=COLLECTION_DOC_CHUNKS,
            scroll_filter=Filter(must=[
                FieldCondition(key="document_id", match=MatchValue(value=document_id)),
            ]),
            limit=limit,
            with_payload=True,
        )
        return [{**(r.payload or {})} for r in results]

    def delete_doc_chunks(self, document_id: int) -> None:
        self.client.delete(
            collection_name=COLLECTION_DOC_CHUNKS,
            points_selector=Filter(must=[
                FieldCondition(key="document_id", match=MatchValue(value=document_id)),
            ]),
        )

    def delete_tender(self, tender_id: int) -> None:
        self.client.delete(
            collection_name=COLLECTION_TENDERS,
            points_selector=[tender_id],
        )


qdrant = QdrantService()
