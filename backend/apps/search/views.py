import logging
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework import permissions, status

from apps.tenders.models import Tender
from apps.users.models import CompanyProfile
from .embedder import embedder
from .services import qdrant
from .serializers import SearchQuerySerializer, SearchResultItemSerializer

logger = logging.getLogger(__name__)


class TenderSearchView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = SearchQuerySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        params = serializer.validated_data

        query_vector = embedder.embed_query(params["query"])

        want = params["limit"]
        hits = qdrant.search_tenders(
            vector=query_vector,
            limit=want * 5,
            region=params.get("region") or None,
            status=params.get("status"),
            nmck_min=params.get("nmck_min"),
            nmck_max=params.get("nmck_max"),
        )

        if not hits:
            return Response({"data": [], "error": None})

        hit_ids = [h["id"] for h in hits]
        score_map = {h["id"]: h["score"] for h in hits}

        now = timezone.now()
        tenders = {
            t.pk: t
            for t in Tender.objects.filter(pk__in=hit_ids, deadline_at__gt=now).select_related("customer")
        }

        results = []
        for hit_id in hit_ids:
            tender = tenders.get(hit_id)
            if not tender:
                continue
            results.append({
                "id": tender.pk,
                "number": tender.number,
                "title": tender.title,
                "nmck": float(tender.nmck) if tender.nmck else None,
                "customer_name": tender.customer.name if tender.customer else None,
                "region": tender.region,
                "published_at": tender.published_at,
                "status": tender.status,
                "source_url": tender.source_url,
                "score": round(score_map[hit_id], 4),
            })
            if len(results) >= want:
                break

        out = SearchResultItemSerializer(results, many=True)
        return Response({"data": out.data, "error": None})


class TenderMatchView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request) -> Response:
        profile, _ = CompanyProfile.objects.get_or_create(user=request.user)
        want = int(request.query_params.get("limit", 20))

        direction_ids_raw = request.query_params.get("direction_ids", "")
        direction_ids = [int(x) for x in direction_ids_raw.split(",") if x.strip().isdigit()]

        has_directions = profile.directions.filter(profile_vector__isnull=False).exists()
        if not has_directions:
            pending = profile.directions.exists()
            if pending:
                return Response({"data": [], "error": "Направления индексируются, подождите ~30 секунд"})
            return Response({"data": [], "error": "Добавьте направления поиска в профиле"})

        hits = qdrant.match_profile(profile, limit=want, direction_ids=direction_ids or None)

        if not hits:
            return Response({"data": [], "error": None})

        hit_ids = [h["id"] for h in hits]
        score_map = {h["id"]: h["score"] for h in hits}
        direction_map = {h["id"]: h.get("matched_direction") for h in hits}

        now = timezone.now()
        tenders = {
            t.pk: t
            for t in Tender.objects.filter(pk__in=hit_ids, deadline_at__gt=now).select_related("customer")
        }

        results = []
        for hit_id in hit_ids:
            tender = tenders.get(hit_id)
            if not tender:
                continue
            results.append({
                "id": tender.pk,
                "number": tender.number,
                "title": tender.title,
                "nmck": float(tender.nmck) if tender.nmck else None,
                "customer_name": tender.customer.name if tender.customer else None,
                "region": tender.region,
                "published_at": tender.published_at,
                "status": tender.status,
                "source_url": tender.source_url,
                "score": round(score_map[hit_id], 4),
                "matched_direction": direction_map.get(hit_id),
            })
            if len(results) >= want:
                break

        out = SearchResultItemSerializer(results, many=True)
        return Response({"data": out.data, "error": None})
