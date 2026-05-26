from django.urls import path

from .views import BillingInfoView, CancelSubscriptionView, CheckoutView, VerifyPaymentView, WebhookView

urlpatterns = [
    path("me/", BillingInfoView.as_view(), name="billing-me"),
    path("checkout/", CheckoutView.as_view(), name="billing-checkout"),
    path("webhook/", WebhookView.as_view(), name="billing-webhook"),
    path("verify/", VerifyPaymentView.as_view(), name="billing-verify"),
    path("cancel/", CancelSubscriptionView.as_view(), name="billing-cancel"),
]
