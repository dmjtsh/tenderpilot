from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TenderViewSet, RegionsListView

router = DefaultRouter()
router.register(r"", TenderViewSet, basename="tenders")

urlpatterns = [
    path("regions/", RegionsListView.as_view(), name="tenders-regions"),
    path("", include(router.urls)),
]
