from django.db import models


class CustomerProfile(models.Model):
    inn = models.CharField(max_length=12, unique=True, db_index=True)

    # DaData
    name = models.CharField(max_length=512, blank=True)
    full_name = models.CharField(max_length=1000, blank=True)
    region = models.CharField(max_length=200, blank=True)
    okved_main = models.CharField(max_length=20, blank=True)
    okved_list = models.JSONField(default=list)
    status = models.CharField(max_length=64, blank=True)
    director_name = models.CharField(max_length=256, blank=True)

    # RusProfile — финансы
    revenue_rub = models.BigIntegerField(null=True, blank=True)
    profit_rub = models.BigIntegerField(null=True, blank=True)
    revenue_year = models.IntegerField(null=True, blank=True)
    employees_count = models.IntegerField(null=True, blank=True)
    founded_date = models.CharField(max_length=32, blank=True)

    # RusProfile — лицензии
    licenses_count = models.IntegerField(null=True, blank=True)
    licenses_summary = models.TextField(blank=True)

    # RusProfile — госзакупки
    purchases_customer_count = models.IntegerField(null=True, blank=True)
    purchases_customer_amount = models.BigIntegerField(null=True, blank=True)
    purchases_supplier_count = models.IntegerField(null=True, blank=True)

    # RusProfile — риски
    arbitration_count = models.IntegerField(null=True, blank=True)
    fssp_count = models.IntegerField(null=True, blank=True)
    risk_indicators = models.JSONField(default=dict)

    # Мета
    rusprofile_id = models.BigIntegerField(null=True, blank=True)
    dadata_updated_at = models.DateTimeField(null=True, blank=True)
    rusprofile_updated_at = models.DateTimeField(null=True, blank=True)
    rusprofile_failed = models.BooleanField(default=False)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Профиль заказчика"
        verbose_name_plural = "Профили заказчиков"
        indexes = [
            models.Index(fields=["rusprofile_updated_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.inn})"
