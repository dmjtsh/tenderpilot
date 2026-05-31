from datetime import timedelta

import django_filters
from django.db.models import Count, Q, Sum
from django.http import StreamingHttpResponse
from django.utils import timezone
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from .models import Customer, Experiment, PipelineActivity, SummaryExperiment, Tender, TenderPipeline
from .region_aliases import CANONICAL_REGIONS, expand_regions
from .serializers import (
    PipelineCommentSerializer,
    TenderListSerializer,
    TenderDetailSerializer,
    TenderPipelineSerializer,
)
from .services import get_or_create_summary_v2
from apps.documents.services import answer_question


class TenderFilterSet(django_filters.FilterSet):
    procedure_type = django_filters.CharFilter(method="filter_procedure_type")
    law_type = django_filters.CharFilter(method="filter_law_type")
    source = django_filters.CharFilter(method="filter_source")
    nmck_min = django_filters.NumberFilter(field_name="nmck", lookup_expr="gte")
    nmck_max = django_filters.NumberFilter(field_name="nmck", lookup_expr="lte")
    region = django_filters.CharFilter(method="filter_region")
    deadline_after = django_filters.DateFilter(field_name="deadline_at", lookup_expr="gte")
    deadline_before = django_filters.DateFilter(field_name="deadline_at", lookup_expr="lte")
    deadline_days = django_filters.NumberFilter(method="filter_deadline_days")
    deadline_days_min = django_filters.NumberFilter(method="filter_deadline_days_min")
    okpd = django_filters.CharFilter(method="filter_okpd")
    customer = django_filters.CharFilter(method="filter_customer")
    platform = django_filters.CharFilter(method="filter_platform")

    class Meta:
        model = Tender
        fields = []

    def filter_procedure_type(self, queryset, name, value):
        vals = [v.strip() for v in value.split(",") if v.strip()]
        return queryset.filter(procedure_type__in=vals) if vals else queryset

    def filter_law_type(self, queryset, name, value):
        vals = [v.strip() for v in value.split(",") if v.strip()]
        return queryset.filter(law_type__in=vals) if vals else queryset

    def filter_source(self, queryset, name, value):
        vals = [v.strip() for v in value.split(",") if v.strip()]
        return queryset.filter(source__in=vals) if vals else queryset

    def filter_region(self, queryset, name, value):
        vals = [v.strip() for v in value.split(",") if v.strip()]
        expanded = expand_regions(vals)
        return queryset.filter(region__in=expanded) if expanded else queryset

    def filter_deadline_days(self, queryset, name, value):
        if value is None:
            return queryset
        cutoff = timezone.now() + timedelta(days=int(value))
        return queryset.filter(deadline_at__lte=cutoff)

    def filter_deadline_days_min(self, queryset, name, value):
        if value is None:
            return queryset
        cutoff = timezone.now() + timedelta(days=int(value))
        return queryset.filter(deadline_at__gte=cutoff)

    def filter_okpd(self, queryset, name, value):
        codes = [v.strip() for v in value.split(",") if v.strip()]
        if not codes:
            return queryset
        q = Q()
        for code in codes:
            q |= Q(okpd_codes__contains=[code])
        return queryset.filter(q)

    def filter_customer(self, queryset, name, value):
        value = value.strip()
        if not value:
            return queryset
        return queryset.filter(
            Q(customer__name__icontains=value) | Q(customer__inn__startswith=value)
        )

    def filter_platform(self, queryset, name, value):
        vals = [v.strip() for v in value.split(",") if v.strip()]
        if not vals:
            return queryset
        q = Q()
        for p in vals:
            q |= Q(trading_platform__icontains=p)
        return queryset.filter(q)


class RegionsListView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({"data": CANONICAL_REGIONS, "error": None})


class OkvedSearchView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        from .okved import OKVED_NAMES
        q = request.query_params.get("q", "").strip().lower()
        if not q:
            return Response({"data": [], "error": None})

        results = []
        for code, name in OKVED_NAMES.items():
            if q in code.lower() or q in name:
                results.append({"code": code, "name": name})
            if len(results) >= 20:
                break

        return Response({"data": results, "error": None})


class CustomerSearchView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        q = request.query_params.get("q", "").strip()
        if len(q) < 2:
            return Response({"data": [], "error": None})

        qs = Customer.objects.filter(
            Q(name__icontains=q) | Q(inn__startswith=q)
        ).values("inn", "name")[:15]

        return Response({"data": list(qs), "error": None})


class TenderViewSet(viewsets.ReadOnlyModelViewSet):
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = TenderFilterSet
    search_fields = ["title", "number"]
    ordering_fields = ["published_at", "deadline_at", "nmck"]
    ordering = ["-content_quality", "-published_at"]

    def get_queryset(self):
        now = timezone.now()
        return (
            Tender.objects.select_related("customer")
            .filter(
                Q(deadline_at__gt=now) | Q(deadline_at__isnull=True),
                status=Tender.Status.ACTIVE,
            )
            .exclude(title="")
            .order_by("-content_quality", "-published_at")
        )

    def get_permissions(self):
        if self.action in ("list", "retrieve", "similar", "docs"):
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return TenderDetailSerializer
        return TenderListSerializer

    @action(detail=True, methods=["get"], url_path="similar")
    def similar(self, request, pk=None):
        from apps.search.services import qdrant
        from apps.search.scoring import score_label

        tender = self.get_object()
        limit = min(int(request.query_params.get("limit", 3)), 20)

        vector = qdrant.get_tender_vector(tender.id)
        if vector is None:
            return Response({"data": [], "has_more": False, "error": None})

        results = qdrant.search_tenders(
            vector=vector,
            limit=limit + 1,
            status="active",
            exclude_ids=[tender.id],
        )

        has_more = len(results) > limit
        results = results[:limit]

        tender_ids = [r["id"] for r in results]
        tenders_db = {
            t.id: t
            for t in Tender.objects.select_related("customer").filter(id__in=tender_ids)
        }

        is_anon = not request.user.is_authenticated
        if not is_anon:
            from apps.billing.models import UserPlan
            user_plan = UserPlan.objects.filter(user=request.user).values_list("plan", flat=True).first() or "free"
        else:
            user_plan = None
        data = []
        for r in results:
            t = tenders_db.get(r["id"])
            if not t:
                continue
            mask_b2b = t.law_type == "b2b" and (is_anon or user_plan == "free")
            data.append({
                "id": t.id,
                "number": t.number,
                "title": t.title,
                "nmck": float(t.nmck) if t.nmck else None,
                "customer_name": None if mask_b2b else (t.customer.name if t.customer else r.get("customer_name", "")),
                "region": t.region or "",
                "law_type": t.law_type or "",
                "procedure_type": t.procedure_type or "",
                "deadline_at": t.deadline_at.isoformat() if t.deadline_at else None,
                "auction_date": t.auction_date.isoformat() if t.auction_date else None,
                "published_at": t.published_at.isoformat() if t.published_at else None,
                "trading_platform": t.trading_platform or "",
                "source_url": None if mask_b2b else (t.source_url or ""),
                "status": t.status,
                "score": round(r["score"] * 100),
                "score_label": score_label(r["score"]),
                "is_restricted": mask_b2b,
            })

        return Response({"data": data, "has_more": has_more, "error": None})

    @action(detail=True, methods=["get"], url_path="summary")
    def summary(self, request, pk=None):
        from apps.billing.services import check_and_increment
        from apps.billing.exceptions import QuotaExceeded

        tender = self.get_object()
        is_refresh = request.query_params.get("refresh") == "true"
        generate = request.query_params.get("generate") == "true"

        from apps.tenders.models import TenderSummaryV2
        user = request.user

        if not is_refresh and not generate:
            cached = TenderSummaryV2.objects.filter(tender=tender, user=user).first()
            if cached:
                return Response({"data": cached.summary, "error": None})
            return Response({"data": None, "error": None})

        needs_generation = is_refresh or not TenderSummaryV2.objects.filter(tender=tender, user=user).exists()

        if needs_generation:
            from apps.documents.models import TenderDocument
            has_docs = TenderDocument.objects.filter(
                tender=tender,
                parse_status="done",
            ).exists()
            if not has_docs:
                still_processing = TenderDocument.objects.filter(
                    tender=tender,
                    parse_status__in=["pending", "processing"],
                ).exists()
                if still_processing:
                    return Response(
                        {"data": None, "error": "docs_processing"},
                        status=409,
                    )
                any_docs = TenderDocument.objects.filter(tender=tender).exists()
                if any_docs:
                    msg = "Документы не содержат извлекаемого текста (сканы или пустые файлы)"
                else:
                    msg = "Загрузите документы тендера, чтобы сгенерировать AI-резюме"
                return Response({"data": None, "error": msg}, status=400)
            try:
                check_and_increment(user, "ai_summary")
            except QuotaExceeded as e:
                return Response({"data": None, "error": e.detail}, status=402)

        try:
            if is_refresh:
                TenderSummaryV2.objects.filter(tender=tender, user=user).delete()
            data = get_or_create_summary_v2(tender, user=user)
            return Response({"data": data, "error": None})
        except Exception as e:
            return Response({"data": None, "error": str(e)}, status=500)

    @action(detail=True, methods=["get"], url_path="summary/export")
    def summary_export(self, request, pk=None):
        from django.http import HttpResponse
        from apps.tenders.models import TenderSummaryV2
        from apps.tenders.summary_export import render_summary_pdf, render_summary_docx

        tender = self.get_object()
        obj = TenderSummaryV2.objects.filter(tender=tender, user=request.user).first()
        if not obj:
            obj = TenderSummaryV2.objects.filter(tender=tender).first()
        if not obj:
            return Response({"data": None, "error": "Резюме не найдено"}, status=404)

        fmt = request.query_params.get("type", "pdf")
        summary = obj.summary

        if fmt == "docx":
            buf = render_summary_docx(tender, summary)
            content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ext = "docx"
        else:
            buf = render_summary_pdf(tender, summary)
            content_type = "application/pdf"
            ext = "pdf"

        filename = f"summary_{tender.number}.{ext}"
        response = HttpResponse(buf.getvalue(), content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    @action(detail=True, methods=["get"], url_path="docs")
    def docs(self, request, pk=None):
        from apps.documents.models import TenderDocument
        tender = self.get_object()
        if tender.law_type == "b2b":
            if not request.user.is_authenticated:
                return Response({"data": [], "error": None})
            from apps.billing.models import UserPlan
            plan = UserPlan.objects.filter(user=request.user).values_list("plan", flat=True).first() or "free"
            if plan == "free":
                return Response({"data": [], "error": None})
        top_level = TenderDocument.objects.filter(
            tender=tender, parent_document__isnull=True,
        ).order_by("content_priority", "filename")

        result: list[dict] = []
        for d in top_level:
            children = list(d.children.order_by("content_priority", "filename"))
            if children:
                for child in children:
                    if child.parse_status == TenderDocument.ParseStatus.SKIPPED:
                        continue
                    result.append(self._doc_to_dict(child, archive_name=d.filename))
                # If all children were skipped, show parent archive so user sees the file
                if not any(
                    c.parse_status != TenderDocument.ParseStatus.SKIPPED
                    for c in children
                ):
                    result.append(self._doc_to_dict(d))
            else:
                # Always show top-level docs without children, including skipped
                # (user should see the file even if we couldn't parse its content)
                result.append(self._doc_to_dict(d))
        return Response({
            "data": result,
            "docs_download_status": tender.docs_download_status,
            "error": None,
        })

    @staticmethod
    def _doc_to_dict(d, archive_name: str = "") -> dict:
        return {
            "id": d.id,
            "filename": d.filename,
            "file_type": d.file_type,
            "parse_status": d.parse_status,
            "file_size": d.file_size,
            "is_scanned": d.is_scanned,
            "content_priority": d.content_priority,
            "archive_name": archive_name,
        }

    @action(detail=True, methods=["get"], url_path=r"docs/(?P<doc_id>\d+)/download")
    def download_doc(self, request, pk=None, doc_id=None):
        from django.http import HttpResponse
        from apps.documents.models import TenderDocument
        from apps.documents.storage import download_file
        tender = self.get_object()
        try:
            doc = TenderDocument.objects.get(id=doc_id, tender=tender)
        except TenderDocument.DoesNotExist:
            return Response({"data": None, "error": "not found"}, status=404)
        data = download_file(doc.s3_key)
        response = HttpResponse(data, content_type="application/octet-stream")
        response["Content-Disposition"] = f'attachment; filename="{doc.filename}"'
        return response

    @action(detail=True, methods=["post"], url_path="chat/v1")
    def chat_v1(self, request, pk=None):
        from apps.billing.services import check_and_increment
        from apps.billing.exceptions import QuotaExceeded

        tender = self.get_object()
        question = (request.data.get("question") or "").strip()
        if not question:
            return Response({"data": None, "error": "Вопрос не может быть пустым"}, status=400)
        if len(question) > 500:
            return Response({"data": None, "error": "Вопрос слишком длинный (макс. 500 символов)"}, status=400)
        try:
            check_and_increment(request.user, "rag_question")
        except QuotaExceeded as e:
            return Response({"data": None, "error": e.detail}, status=402)
        try:
            result = answer_question(tender.id, question)
            return Response({"data": result, "error": None})
        except Exception as e:
            return Response({"data": None, "error": str(e)}, status=500)

    @action(detail=True, methods=["post"], url_path="chat")
    def chat(self, request, pk=None):
        import json as _json
        from apps.billing.services import check_and_increment
        from apps.billing.exceptions import QuotaExceeded
        from apps.tenders.chat_service import chat_with_tender_full_context

        tender = self.get_object()
        body = request.data
        message = (body.get("message") or "").strip()
        if not message:
            return Response({"data": None, "error": "Сообщение не может быть пустым"}, status=400)
        if len(message) > 500:
            return Response({"data": None, "error": "Сообщение слишком длинное (макс. 500 символов)"}, status=400)
        try:
            check_and_increment(request.user, "rag_question")
        except QuotaExceeded as e:
            return Response({"data": None, "error": e.detail}, status=402)

        history = body.get("history", [])

        def event_stream():
            try:
                for chunk in chat_with_tender_full_context(
                    tender.id, message, history
                ):
                    yield f"data: {_json.dumps({'chunk': chunk})}\n\n"
                yield f"data: {_json.dumps({'done': True})}\n\n"
            except Exception as exc:
                yield f"data: {_json.dumps({'error': str(exc)})}\n\n"

        response = StreamingHttpResponse(
            event_stream(),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response

    @action(detail=True, methods=["post"], url_path="download-docs")
    def download_docs(self, request, pk=None):
        from apps.documents.tasks import (
            download_and_parse_documents,
            _komtender_doc_links,
            _tenderguru_doc_links,
        )
        from apps.documents.eis_docs import fetch_document_links

        tender = self.get_object()

        if tender.source == tender.Source.KOMTENDER:
            has_links = bool(_komtender_doc_links(tender))
        elif tender.source == tender.Source.TENDERGURU:
            has_links = bool(_tenderguru_doc_links(tender))
        else:
            has_links = True

        if not has_links:
            tender.docs_download_status = Tender.DocsDownloadStatus.NO_DOCS
            tender.save(update_fields=["docs_download_status"])
            return Response({"data": {"started": False, "no_docs": True}, "error": None})

        tender.docs_download_status = Tender.DocsDownloadStatus.DOWNLOADING
        tender.save(update_fields=["docs_download_status"])
        download_and_parse_documents.delay(tender.id)
        return Response({"data": {"started": True}, "error": None})

    @action(detail=True, methods=["post"], url_path="reindex-docs")
    def reindex_docs(self, request, pk=None):
        from apps.documents.models import TenderDocument
        from apps.documents.tasks import parse_document, index_document_chunks

        tender = self.get_object()

        docs_with_text = TenderDocument.objects.filter(
            tender=tender, parse_status=TenderDocument.ParseStatus.DONE,
        ).exclude(parsed_text="")

        if docs_with_text.exists():
            for doc in docs_with_text:
                index_document_chunks.delay(doc.id)
            return Response({"data": {"action": "reindex", "count": docs_with_text.count()}, "error": None})

        docs_to_reparse = TenderDocument.objects.filter(
            tender=tender, parse_status__in=[
                TenderDocument.ParseStatus.DONE,
                TenderDocument.ParseStatus.CLEANED,
            ],
        ).filter(parsed_text="")

        count = 0
        for doc in docs_to_reparse:
            doc.parse_status = TenderDocument.ParseStatus.PENDING
            doc.save(update_fields=["parse_status"])
            parse_document.delay(doc.id)
            count += 1

        return Response({"data": {"action": "reparse", "count": count}, "error": None})

    @action(detail=True, methods=["post"], url_path="summary/experiment",
            permission_classes=[permissions.IsAdminUser])
    def summary_experiment(self, request, pk=None):
        from .models import SummaryExperiment
        from .services import generate_experiment_summary

        tender = self.get_object()
        strategy = request.data.get("strategy", "full")
        if strategy not in ("rag", "full"):
            return Response({"data": None, "error": "strategy must be 'rag' or 'full'"}, status=400)

        try:
            result = generate_experiment_summary(tender, strategy=strategy)
            exp = SummaryExperiment.objects.create(
                tender=tender,
                strategy=result["metrics"]["strategy"],
                model=result["metrics"]["model"],
                input_tokens=result["metrics"]["input_tokens"],
                output_tokens=result["metrics"]["output_tokens"],
                cost_usd=result["metrics"]["cost_usd"],
                duration_ms=result["metrics"]["duration_ms"],
                was_truncated=result["metrics"]["was_truncated"],
                truncated_reason=result["metrics"]["truncated_reason"],
                original_total_tokens=result["metrics"]["original_total_tokens"],
                result=result["summary"],
            )
            return Response({"data": {
                "id": exp.id,
                "strategy": exp.strategy,
                "model": exp.model,
                "input_tokens": exp.input_tokens,
                "output_tokens": exp.output_tokens,
                "cost_usd": float(exp.cost_usd),
                "duration_ms": exp.duration_ms,
                "was_truncated": exp.was_truncated,
                "truncated_reason": exp.truncated_reason,
                "original_total_tokens": exp.original_total_tokens,
                "result": exp.result,
                "created_at": exp.created_at.isoformat(),
            }, "error": None})
        except Exception as e:
            return Response({"data": None, "error": str(e)}, status=500)

    @action(detail=True, methods=["get"], url_path="summary/experiments",
            permission_classes=[permissions.IsAdminUser])
    def summary_experiments(self, request, pk=None):
        from .models import SummaryExperiment

        tender = self.get_object()
        experiments = SummaryExperiment.objects.filter(tender=tender)[:10]
        data = [{
            "id": e.id,
            "strategy": e.strategy,
            "model": e.model,
            "input_tokens": e.input_tokens,
            "output_tokens": e.output_tokens,
            "cost_usd": float(e.cost_usd),
            "duration_ms": e.duration_ms,
            "was_truncated": e.was_truncated,
            "truncated_reason": e.truncated_reason,
            "original_total_tokens": e.original_total_tokens,
            "result": e.result,
            "created_at": e.created_at.isoformat(),
        } for e in experiments]
        return Response({"data": data, "error": None})


    @action(detail=False, methods=["get"], url_path="search-won-candidates")
    def search_won_candidates(self, request):
        from urllib.parse import urlparse, parse_qs
        from .eis_client import fetch_tender_detail
        from .services import upsert_tender as _upsert
        import logging
        log = logging.getLogger(__name__)

        q = (request.query_params.get("q") or "").strip()
        if not q:
            return Response({"data": [], "error": None})

        # Try to extract regNumber from EIS URL
        try:
            parsed = urlparse(q)
            if parsed.scheme in ("http", "https") and "zakupki.gov.ru" not in parsed.netloc:
                return Response({"data": [], "error": "Принимаются только ссылки с zakupki.gov.ru"})
            if parsed.scheme in ("http", "https") and "zakupki.gov.ru" in parsed.netloc:
                params = parse_qs(parsed.query)
                reg_number = (params.get("regNumber") or params.get("regnum") or [""])[0].strip()
                if not reg_number:
                    return Response({"data": [], "error": "Не удалось извлечь номер тендера из ссылки"})
                if not reg_number.isdigit():
                    return Response({"data": [], "error": "Некорректный номер тендера в ссылке"})

                tender = Tender.objects.filter(number=reg_number).only("id", "number", "title").first()
                if tender:
                    return Response({"data": [{"id": tender.id, "number": tender.number, "title": tender.title}], "error": None})

                # Not in DB — fetch from EIS and import
                try:
                    detail = fetch_tender_detail(reg_number, fallback_url=q)
                except Exception as exc:
                    log.warning("EIS fetch failed for %s: %s", reg_number, exc)
                    detail = {}

                if not detail or not detail.get("number") or not detail.get("title", "").strip():
                    return Response({"data": [], "error": "Тендер не найден ни в базе, ни на ЕИС"})

                try:
                    tender = _upsert(detail)
                except Exception as exc:
                    log.error("upsert failed for %s: %s", reg_number, exc)
                    return Response({"data": [], "error": "Ошибка при сохранении тендера"})

                return Response({"data": [{"id": tender.id, "number": tender.number, "title": tender.title}], "error": None})
        except Exception:
            pass

        if len(q) < 2:
            return Response({"data": [], "error": None})
        qs = Tender.objects.filter(
            Q(number__icontains=q) | Q(title__icontains=q)
        ).only("id", "number", "title")[:10]
        data = [{"id": t.id, "number": t.number, "title": t.title[:100]} for t in qs]
        return Response({"data": data, "error": None})


class TenderPipelineViewSet(viewsets.ModelViewSet):
    serializer_class = TenderPipelineSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = TenderPipeline.objects.filter(
            user=self.request.user
        ).select_related("tender", "tender__customer")
        profile_id = self.request.query_params.get("profile_id")
        if profile_id:
            qs = qs.filter(profile_id=profile_id)
        return qs

    def list(self, request, *args, **kwargs):
        entries = list(self.get_queryset())
        tender_ids = [e.tender_id for e in entries]

        risk_map: dict[int, str | None] = {}
        if tender_ids:
            from .models import TenderSummaryV2
            for s in TenderSummaryV2.objects.filter(tender_id__in=tender_ids).values("tender_id", "summary"):
                risks = (s["summary"] or {}).get("risks") or {}
                risk_map[s["tender_id"]] = risks.get("overall_risk")

            from apps.documents.models import TenderDocument
            # Count docs the same way the docs API lists them:
            # top-level without children + non-skipped children (archives expand)
            parents_with_children = set(
                TenderDocument.objects.filter(
                    tender_id__in=tender_ids,
                    parent_document__isnull=False,
                ).values_list("parent_document_id", flat=True)
            )
            doc_qs = TenderDocument.objects.filter(tender_id__in=tender_ids).exclude(
                id__in=parents_with_children
            ).exclude(
                parent_document__isnull=False, parse_status="skipped"
            )
            doc_stats = doc_qs.values("tender_id").annotate(
                total=Count("id"),
                done=Count("id", filter=Q(parse_status="done"))
            )
            doc_map = {d["tender_id"]: (d["total"], d["done"]) for d in doc_stats}
        else:
            doc_map = {}

        for e in entries:
            e._summary_risk = risk_map.get(e.tender_id)
            e.tender_docs_total = doc_map.get(e.tender_id, (0, 0))[0]
            e.tender_docs_done = doc_map.get(e.tender_id, (0, 0))[1]

        serializer = self.get_serializer(entries, many=True)
        return Response({"data": serializer.data, "error": None})

    def perform_create(self, serializer: TenderPipelineSerializer) -> None:
        profile_id = self.request.data.get("profile")
        entry = serializer.save(user=self.request.user, profile_id=profile_id or None)
        PipelineActivity.objects.create(
            pipeline_entry=entry, user=self.request.user,
            action_type="created", new_value=entry.status,
        )

    def perform_update(self, serializer: TenderPipelineSerializer) -> None:
        old_status = serializer.instance.status
        entry = serializer.save()
        if entry.status != old_status:
            PipelineActivity.objects.create(
                pipeline_entry=entry, user=self.request.user,
                action_type="status_changed", old_value=old_status, new_value=entry.status,
            )

    @action(detail=False, methods=["get"])
    def summary(self, request):
        qs = self.get_queryset()
        in_work = qs.filter(status__in=["new", "studying", "preparing", "submitted"])
        won = qs.filter(status="won")
        lost = qs.filter(status="lost")
        return Response({"data": {
            "in_work_count": in_work.count(),
            "in_work_sum": in_work.aggregate(s=Sum("tender__nmck"))["s"] or 0,
            "won_count": won.count(),
            "won_sum": won.aggregate(s=Sum("tender__nmck"))["s"] or 0,
            "lost_count": lost.count(),
            "lost_sum": lost.aggregate(s=Sum("tender__nmck"))["s"] or 0,
        }, "error": None})

    @action(detail=False, methods=["get"], url_path=r"by-tender/(?P<tender_id>[0-9]+)")
    def by_tender(self, request, tender_id=None):
        entry = self.get_queryset().filter(tender_id=tender_id).first()
        if not entry:
            return Response({"data": None, "error": None})
        return Response({"data": TenderPipelineSerializer(entry).data, "error": None})

    @action(detail=True, methods=["get", "post"], url_path="comments")
    def comments(self, request, pk=None):
        entry = self.get_object()
        if request.method == "GET":
            qs = entry.comments.select_related("user").all()
            serializer = PipelineCommentSerializer(qs, many=True)
            return Response({"data": serializer.data, "error": None})
        serializer = PipelineCommentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = serializer.save(pipeline_entry=entry, user=request.user)
        PipelineActivity.objects.create(
            pipeline_entry=entry, user=request.user,
            action_type="comment_added", new_value=comment.text[:100],
        )
        return Response(
            {"data": PipelineCommentSerializer(comment).data, "error": None},
            status=201,
        )

    @action(detail=True, methods=["get"], url_path="activity")
    def activity(self, request, pk=None):
        entry = self.get_object()
        activities = entry.activities.select_related("user").all()[:50]
        data = [
            {
                "id": a.id,
                "action_type": a.action_type,
                "old_value": a.old_value,
                "new_value": a.new_value,
                "user_name": a.user.get_full_name() or a.user.email,
                "created_at": a.created_at.isoformat(),
            }
            for a in activities
        ]
        return Response({"data": data, "error": None})


class ExperimentViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Experiment.objects.all()
        tender_id = self.request.query_params.get("tender_id")
        if tender_id:
            qs = qs.filter(tender_ids__contains=[int(tender_id)])
        return qs

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        data = [{
            "id": e.id,
            "name": e.name,
            "status": e.status,
            "variants": e.variants,
            "completed_at": e.completed_at.isoformat() if e.completed_at else None,
        } for e in qs[:20]]
        return Response({"data": data, "error": None})

    def retrieve(self, request, *args, **kwargs):
        exp = self.get_object()
        return Response({"data": {
            "id": exp.id,
            "name": exp.name,
            "description": exp.description,
            "status": exp.status,
            "tender_ids": exp.tender_ids,
            "variants": exp.variants,
            "created_at": exp.created_at.isoformat(),
            "completed_at": exp.completed_at.isoformat() if exp.completed_at else None,
        }, "error": None})

    @action(detail=True, methods=["get"])
    def runs(self, request, pk=None):
        exp = self.get_object()
        tender_id = request.query_params.get("tender_id")
        qs = SummaryExperiment.objects.filter(experiment=exp)
        if tender_id:
            qs = qs.filter(tender_id=int(tender_id))
        data = [{
            "id": r.id,
            "variant_label": r.variant_label,
            "variant_name": r.variant_name,
            "strategy": r.strategy,
            "model": r.model,
            "actual_model": r.actual_model,
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
            "cost_usd": float(r.cost_usd),
            "duration_ms": r.duration_ms,
            "was_truncated": r.was_truncated,
            "truncated_reason": r.truncated_reason,
            "result": r.result,
            "created_at": r.created_at.isoformat(),
        } for r in qs]
        return Response({"data": data, "error": None})

    @action(detail=True, methods=["post"], url_path="run", permission_classes=[permissions.IsAdminUser])
    def run_experiment(self, request, pk=None):
        from .services import run_experiment_batch

        exp = self.get_object()
        if exp.status == Experiment.Status.RUNNING:
            return Response({"data": None, "error": "Experiment is already running"}, status=400)

        exp.status = Experiment.Status.DRAFT
        exp.completed_at = None
        exp.save(update_fields=["status", "completed_at"])
        SummaryExperiment.objects.filter(experiment=exp).delete()

        run_experiment_batch(exp)
        return Response({"data": {"status": exp.status}, "error": None})
