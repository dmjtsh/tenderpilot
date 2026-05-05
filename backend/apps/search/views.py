import logging
from datetime import timedelta

from django.db.models import Q
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


def _apply_db_filters(qs, params: dict):
    deadline_days = params.get("deadline_days")
    if deadline_days:
        qs = qs.filter(deadline_at__lte=timezone.now() + timedelta(days=int(deadline_days)))

    deadline_days_min = params.get("deadline_days_min")
    if deadline_days_min:
        qs = qs.filter(deadline_at__gte=timezone.now() + timedelta(days=int(deadline_days_min)))

    okpd = params.get("okpd") or []
    if okpd:
        q = Q()
        for code in okpd:
            q |= Q(okpd_codes__contains=[code])
        qs = qs.filter(q)

    customer = (params.get("customer") or "").strip()
    if customer:
        qs = qs.filter(Q(customer__name__icontains=customer) | Q(customer__inn__startswith=customer))

    return qs


class TenderSearchView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = SearchQuerySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        params = serializer.validated_data

        query_vector = embedder.embed_query(params["query"])

        qdrant_regions = params.get("regions") or []
        if not qdrant_regions and params.get("region"):
            qdrant_regions = [params["region"]]

        want = params["limit"]
        hits = qdrant.search_tenders(
            vector=query_vector,
            limit=want * 5,
            regions=qdrant_regions or None,
            status=params.get("status"),
            nmck_min=params.get("nmck_min"),
            nmck_max=params.get("nmck_max"),
            law_types=params.get("law_type") or None,
            procedure_types=params.get("procedure_type") or None,
        )

        if not hits:
            return Response({"data": [], "error": None})

        hit_ids = [h["id"] for h in hits]
        score_map = {h["id"]: h["score"] for h in hits}

        now = timezone.now()
        qs = Tender.objects.filter(pk__in=hit_ids, deadline_at__gt=now).select_related("customer")
        qs = _apply_db_filters(qs, params)
        tenders = {t.pk: t for t in qs}

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
                "deadline_at": tender.deadline_at,
                "law_type": tender.law_type,
                "status": tender.status,
                "source_url": tender.source_url,
                "trading_platform": tender.trading_platform,
                "auction_date": tender.auction_date,
                "procedure_type": tender.procedure_type,
                "score": round(score_map[hit_id], 4),
            })
            if len(results) >= want:
                break

        out = SearchResultItemSerializer(results, many=True)
        return Response({"data": out.data, "error": None})


class TenderMatchView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _csv_param(self, request, name: str) -> list[str]:
        raw = request.query_params.get(name, "")
        return [v.strip() for v in raw.split(",") if v.strip()]

    def get(self, request: Request) -> Response:
        profile_id_raw = request.query_params.get("profile_id")
        if profile_id_raw and profile_id_raw.isdigit():
            try:
                profile = CompanyProfile.objects.get(pk=int(profile_id_raw), user=request.user)
            except CompanyProfile.DoesNotExist:
                return Response({"data": [], "error": "Профиль не найден"}, status=404)
        else:
            # fallback: активный или последний
            from apps.users.views import _get_active_profile
            profile = _get_active_profile(request.user)
        want = int(request.query_params.get("limit", 20))

        direction_ids_raw = request.query_params.get("direction_ids", "")
        direction_ids = [int(x) for x in direction_ids_raw.split(",") if x.strip().isdigit()]

        has_directions = profile.directions.filter(profile_vector__isnull=False).exists()
        if not has_directions:
            pending = profile.directions.exists()
            if pending:
                return Response({"data": [], "error": "Направления индексируются, подождите ~30 секунд"})
            return Response({"data": [], "error": "Добавьте направления поиска в профиле"})

        extra_regions = self._csv_param(request, "region") or None
        extra_law_types = self._csv_param(request, "law_type") or None
        extra_proc_types = self._csv_param(request, "procedure_type") or None
        extra_nmck_min_raw = request.query_params.get("nmck_min")
        extra_nmck_max_raw = request.query_params.get("nmck_max")
        extra_nmck_min = float(extra_nmck_min_raw) if extra_nmck_min_raw else None
        extra_nmck_max = float(extra_nmck_max_raw) if extra_nmck_max_raw else None

        hits = qdrant.match_profile(
            profile, limit=want, direction_ids=direction_ids or None,
            extra_regions=extra_regions,
            extra_nmck_min=extra_nmck_min,
            extra_nmck_max=extra_nmck_max,
            extra_law_types=extra_law_types,
            extra_procedure_types=extra_proc_types,
        )

        if not hits:
            return Response({"data": [], "error": None})

        hit_ids = [h["id"] for h in hits]
        score_map = {h["id"]: h["score"] for h in hits}
        direction_map = {h["id"]: h.get("matched_direction") for h in hits}

        now = timezone.now()
        qs = Tender.objects.filter(pk__in=hit_ids, deadline_at__gt=now).select_related("customer")

        db_filters = {
            "deadline_days": request.query_params.get("deadline_days"),
            "deadline_days_min": request.query_params.get("deadline_days_min"),
            "okpd": self._csv_param(request, "okpd"),
            "customer": request.query_params.get("customer", ""),
        }
        qs = _apply_db_filters(qs, db_filters)
        tenders = {t.pk: t for t in qs}

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
                "deadline_at": tender.deadline_at,
                "law_type": tender.law_type,
                "status": tender.status,
                "source_url": tender.source_url,
                "trading_platform": tender.trading_platform,
                "auction_date": tender.auction_date,
                "procedure_type": tender.procedure_type,
                "score": round(score_map[hit_id], 4),
                "matched_direction": direction_map.get(hit_id),
            })
            if len(results) >= want:
                break

        out = SearchResultItemSerializer(results, many=True)
        return Response({"data": out.data, "error": None})
