from django.conf import settings
from django.db import models


class UserPlan(models.Model):
    class Plan(models.TextChoices):
        FREE = "free", "Free"
        STANDARD = "standard", "Standard"
        PREMIUM = "premium", "Premium"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="plan",
    )
    plan = models.CharField(max_length=20, choices=Plan.choices, default=Plan.FREE)
    expires_at = models.DateTimeField(null=True, blank=True)

    ai_summaries_used = models.PositiveIntegerField(default=0)
    rag_questions_used = models.PositiveIntegerField(default=0)
    reset_at = models.DateTimeField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Тариф пользователя"
        verbose_name_plural = "Тарифы пользователей"

    def __str__(self) -> str:
        return f"{self.user} — {self.plan}"
