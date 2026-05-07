from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ExperimentViewSet

router = DefaultRouter()
router.register(r"", ExperimentViewSet, basename="experiments")

urlpatterns = [
    path("", include(router.urls)),
]
