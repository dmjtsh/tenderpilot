from rest_framework import viewsets, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from .models import Tender
from .serializers import TenderListSerializer, TenderDetailSerializer


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


class TenderViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["status", "region"]
    search_fields = ["title", "number"]
    ordering_fields = ["published_at", "deadline_at", "nmck"]
    ordering = ["-published_at"]

    def get_queryset(self):
        return Tender.objects.select_related("customer").all()

    def get_serializer_class(self):
        if self.action == "retrieve":
            return TenderDetailSerializer
        return TenderListSerializer
