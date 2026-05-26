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


class Subscription(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CANCELED = "canceled", "Canceled"
        EXPIRED = "expired", "Expired"
        PAYMENT_FAILED = "payment_failed", "Payment Failed"

    class Interval(models.TextChoices):
        MONTHLY = "monthly", "Monthly"
        HALFYEARLY = "halfyearly", "Half-Yearly"
        YEARLY = "yearly", "Yearly"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscription",
    )
    plan = models.CharField(max_length=20, choices=UserPlan.Plan.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    interval = models.CharField(max_length=10, choices=Interval.choices)
    payment_method_id = models.CharField(max_length=100, blank=True)
    current_period_start = models.DateTimeField()
    current_period_end = models.DateTimeField()
    canceled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Подписка"
        verbose_name_plural = "Подписки"

    def __str__(self) -> str:
        return f"{self.user} — {self.plan} ({self.interval}) [{self.status}]"


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCEEDED = "succeeded", "Succeeded"
        CANCELED = "canceled", "Canceled"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payments",
    )
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
    )
    yookassa_payment_id = models.CharField(max_length=100, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="RUB")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    is_recurring = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Платёж"
        verbose_name_plural = "Платежи"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.yookassa_payment_id} — {self.amount} {self.currency} [{self.status}]"
