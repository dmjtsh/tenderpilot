from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import (
    RegisterView, MeView, ChangePasswordView,
    CompanyProfileView, CompanyProfileListCreateView, CompanyProfileDetailView, CompanyProfileActivateView,
    CompanyDirectionListCreateView, CompanyDirectionDetailView,
    InnLookupView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="users-register"),
    path("me/", MeView.as_view(), name="users-me"),
    path("me/password/", ChangePasswordView.as_view(), name="users-change-password"),

    # backward-compat: работает с активным профилем
    path("me/company/", CompanyProfileView.as_view(), name="users-company"),
    path("me/directions/", CompanyDirectionListCreateView.as_view(), name="users-directions"),
    path("me/directions/<int:pk>/", CompanyDirectionDetailView.as_view(), name="users-direction-detail"),

    # multi-company CRUD
    path("me/companies/", CompanyProfileListCreateView.as_view(), name="users-companies"),
    path("me/companies/<int:pk>/", CompanyProfileDetailView.as_view(), name="users-company-detail"),
    path("me/companies/<int:pk>/activate/", CompanyProfileActivateView.as_view(), name="users-company-activate"),

    # directions scoped to a specific profile
    path("me/companies/<int:profile_pk>/directions/", CompanyDirectionListCreateView.as_view(), name="users-company-directions"),
    path("me/companies/<int:profile_pk>/directions/<int:pk>/", CompanyDirectionDetailView.as_view(), name="users-company-direction-detail"),

    path("lookup-inn/", InnLookupView.as_view(), name="users-lookup-inn"),
    path("auth/token/", TokenObtainPairView.as_view(), name="token-obtain"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
]
