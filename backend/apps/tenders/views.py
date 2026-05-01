from django.utils import timezone
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from .models import Tender
from .serializers import TenderListSerializer, TenderDetailSerializer
from .services import get_or_create_summary
from apps.documents.services import answer_question


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
    filterset_fields = ["status", "region"]
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
