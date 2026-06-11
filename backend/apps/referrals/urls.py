from django.urls import path
from .views import ReferralMeView

urlpatterns = [
    path("me/", ReferralMeView.as_view(), name="referral-me"),
]
