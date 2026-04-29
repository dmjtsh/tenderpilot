import uuid
from django.db import models
from django.db.models import Q


class Customer(models.Model):
    inn = models.CharField(max_length=12, blank=True, db_index=True)
    name = models.CharField(max_length=500)
    full_name = models.CharField(max_length=1000, blank=True)
    region = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Заказчик"
        verbose_name_plural = "Заказчики"
        # INN уникален только когда непустой (частичный индекс Postgres)
        constraints = [
            models.UniqueConstraint(
                fields=["inn"],
                condition=~Q(inn=""),
                name="unique_non_empty_inn",
            )
        ]

    def __str__(self) -> str:
        return self.name


class Tender(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Активный"
        FINISHED = "finished", "Завершён"
        CANCELLED = "cancelled", "Отменён"

    class LawType(models.TextChoices):
        FZ44 = "44-ФЗ", "44-ФЗ"
        FZ223 = "223-ФЗ", "223-ФЗ"
        PP615 = "615-ПП", "615-ПП"

    number = models.CharField(max_length=50, unique=True, db_index=True)
    title = models.TextField()
    nmck = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tenders",
    )
    region = models.CharField(max_length=100, blank=True)
    okpd_codes = models.JSONField(default=list)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    deadline_at = models.DateTimeField(null=True, blank=True)
    auction_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    law_type = models.CharField(max_length=10, choices=LawType.choices, blank=True, db_index=True)
    trading_platform = models.CharField(max_length=500, blank=True)
    trading_platform_url = models.URLField(max_length=500, blank=True)
    bid_security_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    bid_security_required = models.BooleanField(null=True, blank=True)
    contract_security_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    contract_security_percent = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    source_url = models.URLField(max_length=1000, blank=True)
    raw_json = models.JSONField(default=dict)
    ai_summary = models.TextField(blank=True)
    embedding_id = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Тендер"
        verbose_name_plural = "Тендеры"
        ordering = ["-published_at"]

    def __str__(self) -> str:
        return f"{self.number}: {self.title[:80]}"
