from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Literal

from django.db import transaction
from django.utils import timezone

from .exceptions import QuotaExceeded
from .models import UserPlan

if TYPE_CHECKING:
    from apps.users.models import User

PLAN_LIMITS: dict[str, dict[str, int]] = {
    "free":     {"max_companies": 1, "ai_summaries": 2,   "rag_questions": 10},
    "standard": {"max_companies": 1, "ai_summaries": 60,  "rag_questions": 120},
    "premium":  {"max_companies": 10, "ai_summaries": 500, "rag_questions": 1000},
}


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
    limits = PLAN_LIMITS.get(plan.plan, PLAN_LIMITS["free"])
    companies_used = CompanyProfile.objects.filter(user=user).count()

    return {
        "plan": plan.plan,
        "expires_at": plan.expires_at.isoformat() if plan.expires_at else None,
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
