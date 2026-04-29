import logging
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

        hits = qdrant.search_tenders(
            vector=query_vector,
            limit=params["limit"],
            region=params.get("region") or None,
            status=params.get("status"),
            nmck_min=params.get("nmck_min"),
            nmck_max=params.get("nmck_max"),
        )

        if not hits:
            return Response({"data": [], "error": None})

        hit_ids = [h["id"] for h in hits]
        score_map = {h["id"]: h["score"] for h in hits}

        tenders = {
            t.pk: t
            for t in Tender.objects.filter(pk__in=hit_ids).select_related("customer")
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

        out = SearchResultItemSerializer(results, many=True)
        return Response({"data": out.data, "error": None})


class TenderMatchView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request) -> Response:
        profile, _ = CompanyProfile.objects.get_or_create(user=request.user)

        parts: list[str] = []
        if profile.description:
            parts.append(profile.description)
        if profile.keywords:
            parts.extend(profile.keywords)

        if not parts:
            return Response({"data": [], "error": "Заполните профиль компании: добавьте описание или ключевые слова"})

        query = " ".join(parts)
        query_vector = embedder.embed_query(query)
        limit = int(request.query_params.get("limit", 20))

        hits = qdrant.search_tenders(
            vector=query_vector,
            limit=limit,
            regions=profile.regions if profile.regions else None,
        )

        if not hits:
            return Response({"data": [], "error": None})

        hit_ids = [h["id"] for h in hits]
        score_map = {h["id"]: h["score"] for h in hits}

        tenders = {
            t.pk: t
            for t in Tender.objects.filter(pk__in=hit_ids).select_related("customer")
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

        out = SearchResultItemSerializer(results, many=True)
        return Response({"data": out.data, "error": None})
