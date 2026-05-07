from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/tenders/", include("apps.tenders.urls")),
    path("api/v1/experiments/", include("apps.tenders.experiment_urls")),
    path("api/v1/search/", include("apps.search.urls")),
    path("api/v1/users/", include("apps.users.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]
