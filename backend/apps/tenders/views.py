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
            data = get_or_create_summary(tender)
            return Response({"data": data, "error": None})
        except Exception as e:
            return Response({"data": None, "error": str(e)}, status=500)
