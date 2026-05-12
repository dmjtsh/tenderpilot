from django.urls import path
from .views import BillingInfoView

urlpatterns = [
    path("me/", BillingInfoView.as_view(), name="billing-me"),
]
