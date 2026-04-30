from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TenderViewSet, RegionsListView, OkvedSearchView

router = DefaultRouter()
router.register(r"", TenderViewSet, basename="tenders")

urlpatterns = [
    path("regions/", RegionsListView.as_view(), name="tenders-regions"),
    path("okved/", OkvedSearchView.as_view(), name="tenders-okved"),
    path("", include(router.urls)),
]
