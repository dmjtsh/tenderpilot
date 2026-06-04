import logging
from datetime import timedelta

from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db.models import Q, F
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework import permissions

from apps.tenders.models import Tender
from apps.tenders.region_aliases import expand_regions
from apps.users.models import CompanyProfile
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

    customers = params.get("customer") or []
    if isinstance(customers, str):
        customers = [c.strip() for c in customers.split(",") if c.strip()]
    if customers:
        q = Q()
        for c in customers:
            q |= Q(customer__name__icontains=c) | Q(customer__inn__startswith=c)
        qs = qs.filter(q)

    platforms = params.get("platform") or []
    if platforms:
        q = Q()
        for p in platforms:
            q |= Q(trading_platform__icontains=p)
        qs = qs.filter(q)

    return qs


class TenderSearchView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = SearchQuerySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        params = serializer.validated_data

        query = params["query"].strip()
        if not query:
            return Response({"data": [], "error": None})

        want = params["limit"]
        now = timezone.now()

        # --- Регионы ---
        regions = params.get("regions") or []
        if not regions and params.get("region"):
            regions = [params["region"]]
        expanded_regions = expand_regions(regions) if regions else None

        # === Postgres FTS (BM25) ===
        pg_query = SearchQuery(query, config="russian")
        qs = (
            Tender.objects.filter(
                search_vector=pg_query,
                status=params.get("status") or "active",
                deadline_at__gt=now,
            )
            .exclude(title="")
            .annotate(rank=SearchRank(F("search_vector"), pg_query))
            .order_by("-rank")
            .select_related("customer")
        )
        if expanded_regions:
            qs = qs.filter(region__in=expanded_regions)
        if params.get("nmck_min") is not None:
            qs = qs.filter(nmck__gte=params["nmck_min"])
        if params.get("nmck_max") is not None:
            qs = qs.filter(nmck__lte=params["nmck_max"])
        if params.get("law_type"):
            qs = qs.filter(law_type__in=params["law_type"])
        if params.get("procedure_type"):
            qs = qs.filter(procedure_type__in=params["procedure_type"])
        qs = _apply_db_filters(qs, params)

        results = []
        for tender in qs[:want]:
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
            })

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
            # fallback: первый (последний созданный) профиль
            from apps.users.views import _get_first_profile
            profile = _get_first_profile(request.user)
        page_size = int(request.query_params.get("limit", 20))
        page = int(request.query_params.get("page", 1))

        direction_ids_raw = request.query_params.get("direction_ids", "")
        direction_ids = [int(x) for x in direction_ids_raw.split(",") if x.strip().isdigit()]

        has_directions = profile.directions.filter(profile_vector__isnull=False).exists()
        if not has_directions:
            pending = profile.directions.exists()
            if pending:
                return Response({"data": [], "error": "Направления индексируются, подождите ~30 секунд"})
            return Response({"data": [], "error": "Добавьте направления поиска в профиле"})

        raw_regions = self._csv_param(request, "region")
        extra_regions = expand_regions(raw_regions) or None
        extra_law_types = self._csv_param(request, "law_type") or None
        extra_proc_types = self._csv_param(request, "procedure_type") or None
        extra_nmck_min_raw = request.query_params.get("nmck_min")
        extra_nmck_max_raw = request.query_params.get("nmck_max")
        extra_nmck_min = float(extra_nmck_min_raw) if extra_nmck_min_raw else None
        extra_nmck_max = float(extra_nmck_max_raw) if extra_nmck_max_raw else None

        hits = qdrant.match_profile(
            profile, limit=page_size, direction_ids=direction_ids or None,
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

        from apps.tenders.models import TenderPipeline
        from .scoring import score_label

        pipeline_excluded = set(TenderPipeline.objects.filter(
            user=request.user,
            status__in=["studying", "preparing", "submitted"],
        ).values_list("tender_id", flat=True))

        now = timezone.now()
        qs = Tender.objects.filter(pk__in=hit_ids, deadline_at__gt=now).exclude(title="").select_related("customer")

        db_filters = {
            "deadline_days": request.query_params.get("deadline_days"),
            "deadline_days_min": request.query_params.get("deadline_days_min"),
            "okpd": self._csv_param(request, "okpd"),
            "customer": request.query_params.get("customer", ""),
            "platform": self._csv_param(request, "platform"),
        }
        qs = _apply_db_filters(qs, db_filters)
        tenders = {t.pk: t for t in qs}

        scored = []
        for hit_id in hit_ids:
            if hit_id in pipeline_excluded:
                continue
            tender = tenders.get(hit_id)
            if not tender:
                continue
            cosine = score_map[hit_id]
            scored.append({
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
                "score": round(cosine, 4),
                "score_label": score_label(cosine),
            })

        sort_by = request.query_params.get("sort", "score")
        far_future = timezone.now() + timedelta(days=36500)
        epoch = timezone.now() - timedelta(days=36500)
        sort_keys = {
            "score": lambda r: (-r["score"], r["id"]),
            "deadline": lambda r: (r["deadline_at"] or far_future, r["id"]),
            "published": lambda r: (-(r["published_at"] or epoch).timestamp(), r["id"]),
            "nmck_asc": lambda r: (r["nmck"] or 0, r["id"]),
            "nmck_desc": lambda r: (-(r["nmck"] or 0), r["id"]),
        }
        scored.sort(key=sort_keys.get(sort_by, sort_keys["score"]))

        start = (page - 1) * page_size
        end = start + page_size
        results = scored[start:end]
        has_more = end < len(scored)

        out = SearchResultItemSerializer(results, many=True)
        return Response({"data": out.data, "has_more": has_more, "error": None})
