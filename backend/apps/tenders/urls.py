from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TenderViewSet, TenderPipelineViewSet, RegionsListView, OkvedSearchView, CustomerSearchView, TenderSitemapView

router = DefaultRouter()
router.register(r"pipeline", TenderPipelineViewSet, basename="pipeline")
router.register(r"", TenderViewSet, basename="tenders")

urlpatterns = [
    path("sitemap/", TenderSitemapView.as_view(), name="tenders-sitemap"),
    path("regions/", RegionsListView.as_view(), name="tenders-regions"),
    path("okved/", OkvedSearchView.as_view(), name="tenders-okved"),
    path("customers/", CustomerSearchView.as_view(), name="tenders-customers"),
    path("", include(router.urls)),
]
