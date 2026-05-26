import json
import logging

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import (
    cancel_subscription,
    create_checkout,
    get_billing_info,
    handle_payment_failed,
    handle_payment_succeeded,
    verify_pending_payment,
)

logger = logging.getLogger(__name__)


class BillingInfoView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        data = get_billing_info(request.user)
        return Response({"data": data, "error": None})


class CheckoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        plan = request.data.get("plan")
        interval = request.data.get("interval", "monthly")

        if plan not in ("standard", "premium"):
            return Response(
                {"data": None, "error": "Выберите тариф: standard или premium"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if interval not in ("monthly", "halfyearly", "yearly"):
            return Response(
                {"data": None, "error": "Выберите период: monthly, halfyearly или yearly"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = create_checkout(request.user, plan, interval)
            return Response({"data": result, "error": None})
        except RuntimeError as e:
            return Response(
                {"data": None, "error": str(e)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception:
            logger.exception("Checkout error")
            return Response(
                {"data": None, "error": "Ошибка создания платежа"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class WebhookView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        try:
            body = request.data if isinstance(request.data, dict) else json.loads(request.body)
        except (json.JSONDecodeError, Exception):
            return Response(status=status.HTTP_400_BAD_REQUEST)

        event_type = body.get("event")
        payment_obj = body.get("object", {})
        payment_id = payment_obj.get("id")

        if not payment_id:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        if event_type == "payment.succeeded":
            handle_payment_succeeded(payment_id, payment_obj)
        elif event_type in ("payment.canceled", "payment.waiting_for_capture"):
            if event_type == "payment.canceled":
                handle_payment_failed(payment_id)
        else:
            logger.info("Unhandled webhook event: %s", event_type)

        return Response(status=status.HTTP_200_OK)


class VerifyPaymentView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        updated = verify_pending_payment(request.user)
        data = get_billing_info(request.user)
        return Response({"data": {**data, "updated": updated}, "error": None})


class CancelSubscriptionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            result = cancel_subscription(request.user)
            return Response({"data": result, "error": None})
        except ValueError as e:
            return Response(
                {"data": None, "error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
