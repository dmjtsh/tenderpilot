from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import (
    RegisterView, MeView, ChangePasswordView, CompanyProfileView,
    CompanyDirectionListCreateView, CompanyDirectionDetailView,
    InnLookupView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="users-register"),
    path("me/", MeView.as_view(), name="users-me"),
    path("me/password/", ChangePasswordView.as_view(), name="users-change-password"),
    path("me/company/", CompanyProfileView.as_view(), name="users-company"),
    path("me/directions/", CompanyDirectionListCreateView.as_view(), name="users-directions"),
    path("me/directions/<int:pk>/", CompanyDirectionDetailView.as_view(), name="users-direction-detail"),
    path("lookup-inn/", InnLookupView.as_view(), name="users-lookup-inn"),
    path("auth/token/", TokenObtainPairView.as_view(), name="token-obtain"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
]
