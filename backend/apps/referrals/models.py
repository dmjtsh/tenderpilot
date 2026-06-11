from __future__ import annotations

import secrets
import string

from django.db import models


def _generate_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    while True:
        code = "".join(secrets.choice(alphabet) for _ in range(8))
        if not ReferralCode.objects.filter(code=code).exists():
            return code


class ReferralCode(models.Model):
    user = models.OneToOneField(
        "users.User", on_delete=models.CASCADE, related_name="referral_code"
    )
    code = models.CharField(max_length=8, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.code} ({self.user_id})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = _generate_code()
        super().save(*args, **kwargs)


class Referral(models.Model):
    class Status(models.TextChoices):
        REGISTERED = "registered", "Зарегистрировался"
        CONVERTED = "converted", "Оплатил"

    referrer = models.ForeignKey(
        "users.User", on_delete=models.CASCADE, related_name="referrals_sent"
    )
    referred_user = models.OneToOneField(
        "users.User", on_delete=models.CASCADE, related_name="referral_origin"
    )
    code = models.ForeignKey(
        ReferralCode, on_delete=models.CASCADE, related_name="referrals"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.REGISTERED
    )
    discount_percent = models.PositiveSmallIntegerField(default=20)
    discount_applied = models.BooleanField(default=False)
    registered_at = models.DateTimeField(auto_now_add=True)
    converted_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.referrer} → {self.referred_user} [{self.status}]"
