from datetime import timedelta

import django_filters
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from .models import Tender, TenderPipeline
from .serializers import TenderListSerializer, TenderDetailSerializer, TenderPipelineSerializer
from .services import get_or_create_summary
from apps.documents.services import answer_question


class TenderFilterSet(django_filters.FilterSet):
    procedure_type = django_filters.CharFilter(method="filter_procedure_type")
    law_type = django_filters.CharFilter(method="filter_law_type")
    nmck_min = django_filters.NumberFilter(field_name="nmck", lookup_expr="gte")
    nmck_max = django_filters.NumberFilter(field_name="nmck", lookup_expr="lte")
    region = django_filters.CharFilter(method="filter_region")
    deadline_after = django_filters.DateFilter(field_name="deadline_at", lookup_expr="gte")
    deadline_before = django_filters.DateFilter(field_name="deadline_at", lookup_expr="lte")
    deadline_days = django_filters.NumberFilter(method="filter_deadline_days")
    okpd = django_filters.CharFilter(method="filter_okpd")
    customer = django_filters.CharFilter(method="filter_customer")

    class Meta:
        model = Tender
        fields = []

    def filter_procedure_type(self, queryset, name, value):
        vals = [v.strip() for v in value.split(",") if v.strip()]
        return queryset.filter(procedure_type__in=vals) if vals else queryset

    def filter_law_type(self, queryset, name, value):
        vals = [v.strip() for v in value.split(",") if v.strip()]
        return queryset.filter(law_type__in=vals) if vals else queryset

    def filter_region(self, queryset, name, value):
        vals = [v.strip() for v in value.split(",") if v.strip()]
        return queryset.filter(region__in=vals) if vals else queryset

    def filter_deadline_days(self, queryset, name, value):
        if value is None:
            return queryset
        cutoff = timezone.now() + timedelta(days=int(value))
        return queryset.filter(deadline_at__lte=cutoff)

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


class RegionsListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        regions = (
            Tender.objects.exclude(region="")
            .values_list("region", flat=True)
            .distinct()
            .order_by("region")
        )
        return Response({"data": list(regions), "error": None})


class OkvedSearchView(APIView):
    permission_classes = [permissions.IsAuthenticated]

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


class TenderViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = TenderFilterSet
    search_fields = ["title", "number"]
    ordering_fields = ["published_at", "deadline_at", "nmck"]
    ordering = ["-published_at"]

    def get_queryset(self):
        now = timezone.now()
        return Tender.objects.select_related("customer").filter(
            deadline_at__gt=now
        )

    def get_serializer_class(self):
        if self.action == "retrieve":
            return TenderDetailSerializer
        return TenderListSerializer

    @action(detail=True, methods=["get"], url_path="summary")
    def summary(self, request, pk=None):
        tender = self.get_object()
        try:
            if request.query_params.get("refresh") == "true":
                tender.ai_summary = ""
                tender.save(update_fields=["ai_summary"])
            data = get_or_create_summary(tender)
            return Response({"data": data, "error": None})
        except Exception as e:
            return Response({"data": None, "error": str(e)}, status=500)

    @action(detail=True, methods=["get"], url_path="docs")
    def docs(self, request, pk=None):
        from apps.documents.models import TenderDocument
        tender = self.get_object()
        top_level = TenderDocument.objects.filter(
            tender=tender, parent_document__isnull=True,
        ).order_by("content_priority", "filename")

        result: list[dict] = []
        for d in top_level:
            if d.parse_status == TenderDocument.ParseStatus.SKIPPED:
                continue
            children = list(d.children.order_by("content_priority", "filename"))
            if children:
                for child in children:
                    if child.parse_status == TenderDocument.ParseStatus.SKIPPED:
                        continue
                    result.append(self._doc_to_dict(child, archive_name=d.filename))
            else:
                result.append(self._doc_to_dict(d))
        return Response({"data": result, "error": None})

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

    @action(detail=True, methods=["post"], url_path="ask")
    def ask(self, request, pk=None):
        tender = self.get_object()
        question = (request.data.get("question") or "").strip()
        if not question:
            return Response({"data": None, "error": "Вопрос не может быть пустым"}, status=400)
        if len(question) > 500:
            return Response({"data": None, "error": "Вопрос слишком длинный (макс. 500 символов)"}, status=400)
        try:
            result = answer_question(tender.id, question)
            return Response({"data": result, "error": None})
        except Exception as e:
            return Response({"data": None, "error": str(e)}, status=500)

    @action(detail=True, methods=["post"], url_path="download-docs")
    def download_docs(self, request, pk=None):
        from apps.documents.tasks import download_and_parse_documents
        tender = self.get_object()
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


class TenderPipelineViewSet(viewsets.ModelViewSet):
    serializer_class = TenderPipelineSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return TenderPipeline.objects.filter(
            user=self.request.user
        ).select_related("tender", "tender__customer")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        qs = self.get_queryset()
        in_work = qs.filter(status__in=["studying", "preparing", "submitted"])
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
