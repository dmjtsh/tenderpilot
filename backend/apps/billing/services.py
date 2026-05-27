from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .exceptions import QuotaExceeded
from .models import Payment, Subscription, UserPlan

if TYPE_CHECKING:
    from apps.users.models import User

logger = logging.getLogger(__name__)

PLAN_LIMITS: dict[str, dict[str, int]] = {
    "free":     {"max_companies": 1, "ai_summaries": 2,   "rag_questions": 10},
    "standard": {"max_companies": 1, "ai_summaries": 60,  "rag_questions": 120},
    "premium":  {"max_companies": 10, "ai_summaries": 500, "rag_questions": 1000},
}


def get_price(plan: str, interval: str) -> int:
    prices = settings.PLAN_PRICES.get(plan)
    if not prices:
        raise ValueError(f"Unknown plan: {plan}")
    price = prices.get(interval)
    if price is None:
        raise ValueError(f"Unknown interval: {interval}")
    return price


def get_user_plan(user: "User") -> UserPlan:
    plan, created = UserPlan.objects.get_or_create(
        user=user,
        defaults={"reset_at": timezone.now() + timedelta(days=30)},
    )
    if not created:
        _maybe_reset_counters(plan)
    return plan


def _maybe_reset_counters(user_plan: UserPlan) -> None:
    if timezone.now() >= user_plan.reset_at:
        UserPlan.objects.filter(pk=user_plan.pk).update(
            ai_summaries_used=0,
            rag_questions_used=0,
            reset_at=timezone.now() + timedelta(days=30),
        )
        user_plan.ai_summaries_used = 0
        user_plan.rag_questions_used = 0
        user_plan.reset_at = timezone.now() + timedelta(days=30)


def check_and_increment(
    user: "User",
    resource: Literal["ai_summary", "rag_question"],
) -> None:
    with transaction.atomic():
        plan = UserPlan.objects.select_for_update().filter(user=user).first()
        if plan is None:
            plan = UserPlan.objects.create(
                user=user,
                reset_at=timezone.now() + timedelta(days=30),
            )

        if timezone.now() >= plan.reset_at:
            plan.ai_summaries_used = 0
            plan.rag_questions_used = 0
            plan.reset_at = timezone.now() + timedelta(days=30)

        limits = PLAN_LIMITS.get(plan.plan, PLAN_LIMITS["free"])

        if resource == "ai_summary":
            limit = limits["ai_summaries"]
            used = plan.ai_summaries_used
            if used >= limit:
                raise QuotaExceeded("ai_summary", used, limit, plan.plan)
            plan.ai_summaries_used = used + 1
        else:
            limit = limits["rag_questions"]
            used = plan.rag_questions_used
            if used >= limit:
                raise QuotaExceeded("rag_question", used, limit, plan.plan)
            plan.rag_questions_used = used + 1

        plan.save(update_fields=["ai_summaries_used", "rag_questions_used", "reset_at"])


def check_company_limit(user: "User") -> None:
    from apps.users.models import CompanyProfile

    plan = get_user_plan(user)
    limits = PLAN_LIMITS.get(plan.plan, PLAN_LIMITS["free"])
    max_companies = limits["max_companies"]
    current = CompanyProfile.objects.filter(user=user).count()
    if current >= max_companies:
        raise QuotaExceeded("companies", current, max_companies, plan.plan)


def get_billing_info(user: "User") -> dict:
    from apps.users.models import CompanyProfile

    plan = get_user_plan(user)
    sub = Subscription.objects.filter(user=user).first()

    if (
        sub
        and sub.status == Subscription.Status.ACTIVE
        and sub.current_period_end > timezone.now()
        and plan.plan == UserPlan.Plan.FREE
    ):
        plan.plan = sub.plan
        plan.expires_at = sub.current_period_end
        plan.save(update_fields=["plan", "expires_at", "updated_at"])
        logger.warning("Auto-fixed UserPlan desync: user=%s plan=%s", user.id, sub.plan)

    limits = PLAN_LIMITS.get(plan.plan, PLAN_LIMITS["free"])
    companies_used = CompanyProfile.objects.filter(user=user).count()
    subscription_data = None
    if sub:
        subscription_data = {
            "status": sub.status,
            "interval": sub.interval,
            "current_period_end": sub.current_period_end.isoformat(),
            "canceled_at": sub.canceled_at.isoformat() if sub.canceled_at else None,
        }

    return {
        "plan": plan.plan,
        "expires_at": plan.expires_at.isoformat() if plan.expires_at else None,
        "subscription": subscription_data,
        "ai_summaries": {
            "used": plan.ai_summaries_used,
            "limit": limits["ai_summaries"],
        },
        "rag_questions": {
            "used": plan.rag_questions_used,
            "limit": limits["rag_questions"],
        },
        "companies": {
            "used": companies_used,
            "limit": limits["max_companies"],
        },
        "reset_at": plan.reset_at.isoformat(),
    }


# ─── Checkout & Payment Handling ──────────────────────────────────────────────


def create_checkout(user: "User", plan: str, interval: str) -> dict:
    if plan not in ("standard", "premium"):
        raise ValueError("Invalid plan")
    if interval not in ("monthly", "halfyearly", "yearly"):
        raise ValueError("Invalid interval")

    if not settings.YOOKASSA_SHOP_ID:
        raise RuntimeError("YooKassa is not configured")

    from .yookassa_client import create_first_payment

    amount = get_price(plan, interval)
    return_url = settings.YOOKASSA_RETURN_URL

    yoo_payment = create_first_payment(
        amount=amount,
        plan=plan,
        interval=interval,
        user_id=user.id,
        return_url=return_url,
    )

    Payment.objects.create(
        user=user,
        yookassa_payment_id=yoo_payment.id,
        amount=Decimal(str(amount)),
        status=Payment.Status.PENDING,
        metadata={"plan": plan, "interval": interval},
    )

    confirmation_url = yoo_payment.confirmation.confirmation_url
    return {"confirmation_url": confirmation_url}


def _period_end(start, interval: str):
    if interval == "yearly":
        return start + timedelta(days=365)
    if interval == "halfyearly":
        return start + timedelta(days=182)
    return start + timedelta(days=30)


def handle_payment_succeeded(yookassa_payment_id: str, yoo_data: dict) -> None:
    with transaction.atomic():
        payment = Payment.objects.select_for_update().filter(
            yookassa_payment_id=yookassa_payment_id,
        ).first()
        if not payment:
            logger.warning("Payment not found: %s", yookassa_payment_id)
            return
        if payment.status == Payment.Status.SUCCEEDED:
            return

        payment.status = Payment.Status.SUCCEEDED
        payment.save(update_fields=["status", "updated_at"])

        user = payment.user
        meta = payment.metadata
        plan = meta.get("plan", "standard")
        interval = meta.get("interval", "monthly")
        now = timezone.now()

        payment_method = yoo_data.get("payment_method", {})
        payment_method_id = payment_method.get("id", "")

        sub, created = Subscription.objects.select_for_update().get_or_create(
            user=user,
            defaults={
                "plan": plan,
                "interval": interval,
                "status": Subscription.Status.ACTIVE,
                "payment_method_id": payment_method_id,
                "current_period_start": now,
                "current_period_end": _period_end(now, interval),
            },
        )

        if not created:
            sub.plan = plan
            sub.interval = interval
            sub.status = Subscription.Status.ACTIVE
            sub.canceled_at = None
            if payment_method_id:
                sub.payment_method_id = payment_method_id
            if payment.is_recurring:
                sub.current_period_start = sub.current_period_end
                sub.current_period_end = _period_end(sub.current_period_end, interval)
            else:
                sub.current_period_start = now
                sub.current_period_end = _period_end(now, interval)
            sub.save()

        payment.subscription = sub
        payment.save(update_fields=["subscription", "updated_at"])

        user_plan = get_user_plan(user)
        user_plan.plan = plan
        user_plan.expires_at = sub.current_period_end
        user_plan.ai_summaries_used = 0
        user_plan.rag_questions_used = 0
        user_plan.reset_at = timezone.now() + timedelta(days=30)
        user_plan.save(update_fields=["plan", "expires_at", "ai_summaries_used", "rag_questions_used", "reset_at", "updated_at"])

        logger.info("Payment succeeded: user=%s plan=%s interval=%s", user.id, plan, interval)


def handle_payment_failed(yookassa_payment_id: str) -> None:
    with transaction.atomic():
        payment = Payment.objects.select_for_update().filter(
            yookassa_payment_id=yookassa_payment_id,
        ).first()
        if not payment:
            return
        if payment.status in (Payment.Status.FAILED, Payment.Status.CANCELED):
            return

        payment.status = Payment.Status.FAILED
        payment.save(update_fields=["status", "updated_at"])

        sub = Subscription.objects.filter(user=payment.user, status=Subscription.Status.ACTIVE).first()
        if sub and payment.is_recurring:
            sub.status = Subscription.Status.PAYMENT_FAILED
            sub.save(update_fields=["status", "updated_at"])

        logger.warning("Payment failed: %s user=%s", yookassa_payment_id, payment.user_id)


def verify_pending_payment(user: "User") -> bool:
    payment = Payment.objects.filter(
        user=user, status=Payment.Status.PENDING,
    ).order_by("-created_at").first()
    if not payment:
        return False

    from .yookassa_client import fetch_payment
    try:
        yoo = fetch_payment(payment.yookassa_payment_id)
    except Exception:
        logger.exception("Failed to fetch payment %s", payment.yookassa_payment_id)
        return False

    if yoo.status == "succeeded":
        yoo_data = {}
        if hasattr(yoo, "payment_method") and yoo.payment_method:
            yoo_data["payment_method"] = {"id": getattr(yoo.payment_method, "id", "")}
        handle_payment_succeeded(payment.yookassa_payment_id, yoo_data)
        return True
    if yoo.status == "canceled":
        handle_payment_failed(payment.yookassa_payment_id)
    return False


def cancel_subscription(user: "User") -> dict:
    sub = Subscription.objects.filter(user=user).exclude(
        status__in=[Subscription.Status.EXPIRED],
    ).first()
    if not sub:
        raise ValueError("No active subscription")

    sub.status = Subscription.Status.CANCELED
    sub.canceled_at = timezone.now()
    sub.save(update_fields=["status", "canceled_at", "updated_at"])

    logger.info("Subscription canceled: user=%s active_until=%s", user.id, sub.current_period_end)
    return {
        "status": "canceled",
        "active_until": sub.current_period_end.isoformat(),
    }


def process_renewals() -> int:
    now = timezone.now()
    expired_subs = Subscription.objects.filter(
        status=Subscription.Status.ACTIVE,
        current_period_end__lte=now,
    ).select_related("user")

    count = 0
    for sub in expired_subs:
        with transaction.atomic():
            sub.status = Subscription.Status.EXPIRED
            sub.save(update_fields=["status", "updated_at"])

            user_plan = get_user_plan(sub.user)
            user_plan.plan = UserPlan.Plan.FREE
            user_plan.expires_at = None
            user_plan.save(update_fields=["plan", "expires_at", "updated_at"])
            count += 1

        logger.info("Subscription expired: user=%s plan=%s", sub.user_id, sub.plan)

    return count


def expire_canceled_subscriptions() -> int:
    now = timezone.now()
    expired = Subscription.objects.filter(
        status=Subscription.Status.CANCELED,
        current_period_end__lte=now,
    ).select_related("user")

    count = 0
    for sub in expired:
        with transaction.atomic():
            sub.status = Subscription.Status.EXPIRED
            sub.save(update_fields=["status", "updated_at"])

            user_plan = get_user_plan(sub.user)
            user_plan.plan = UserPlan.Plan.FREE
            user_plan.expires_at = None
            user_plan.save(update_fields=["plan", "expires_at", "updated_at"])
            count += 1

    return count
