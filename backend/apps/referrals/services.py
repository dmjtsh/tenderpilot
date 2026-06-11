from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.conf import settings
from django.utils import timezone

if TYPE_CHECKING:
    from apps.users.models import User

logger = logging.getLogger(__name__)


def get_or_create_code(user: "User") -> str:
    from .models import ReferralCode

    rc, _ = ReferralCode.objects.get_or_create(user=user)
    return rc.code


def get_referral_link(user: "User") -> str:
    from .models import ReferralCode

    rc, _ = ReferralCode.objects.get_or_create(user=user)
    base = getattr(settings, "FRONTEND_BASE_URL", "https://tenderoll.ru")
    return f"{base}/login?ref={rc.code}"


def register_referral(referred_user: "User", ref_code: str) -> None:
    from .models import Referral, ReferralCode

    try:
        rc = ReferralCode.objects.select_related("user").get(code=ref_code.upper())
    except ReferralCode.DoesNotExist:
        logger.info("Unknown referral code: %s", ref_code)
        return

    if rc.user_id == referred_user.pk:
        return

    if Referral.objects.filter(referred_user=referred_user).exists():
        return

    Referral.objects.create(
        referrer=rc.user,
        referred_user=referred_user,
        code=rc,
    )
    logger.info("Referral registered: referrer=%s referred=%s", rc.user_id, referred_user.pk)


def get_pending_discount(user: "User") -> int:
    """Returns discount percent if user was referred and hasn't paid yet, else 0."""
    from .models import Referral

    referral = Referral.objects.filter(
        referred_user=user,
        discount_applied=False,
        status=Referral.Status.REGISTERED,
    ).first()
    return referral.discount_percent if referral else 0


def mark_converted(user: "User") -> None:
    from .models import Referral

    updated = Referral.objects.filter(
        referred_user=user,
        discount_applied=False,
        status=Referral.Status.REGISTERED,
    ).update(
        status=Referral.Status.CONVERTED,
        discount_applied=True,
        converted_at=timezone.now(),
    )
    if updated:
        logger.info("Referral converted: user=%s", user.pk)


def get_stats(user: "User") -> dict:
    from .models import Referral

    qs = Referral.objects.filter(referrer=user)
    referrals = Referral.objects.filter(referrer=user).select_related("referred_user").order_by("-registered_at")

    def _mask_email(email: str) -> str:
        local, domain = email.split("@", 1)
        return local[:2] + "***@" + domain

    invited = [
        {
            "email": _mask_email(r.referred_user.email),
            "status": r.status,
            "registered_at": r.registered_at.isoformat(),
            "converted_at": r.converted_at.isoformat() if r.converted_at else None,
        }
        for r in referrals
    ]

    return {
        "invited_count": qs.count(),
        "converted_count": qs.filter(status=Referral.Status.CONVERTED).count(),
        "invited": invited,
    }
