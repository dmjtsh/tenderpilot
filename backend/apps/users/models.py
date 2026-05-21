import hashlib
import json

from django.contrib.auth.models import AbstractUser
from django.contrib.postgres.fields import ArrayField
from django.db import models


class User(AbstractUser):
    email = models.EmailField(unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"

    def __str__(self) -> str:
        return self.email


class CompanyProfile(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="company_profiles")
    name = models.CharField(max_length=255)
    inn = models.CharField(max_length=12, blank=True)
    description = models.TextField(blank=True)
    okved_codes = models.JSONField(default=list)
    regions = models.JSONField(default=list)
    keywords = models.JSONField(default=list)
    contract_security_budget = models.BigIntegerField(null=True, blank=True)
    has_bank_guarantee = models.BooleanField(default=False)
    platforms = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Профиль компании"
        verbose_name_plural = "Профили компаний"

    def __str__(self) -> str:
        return self.name


class CompanyDirection(models.Model):
    profile = models.ForeignKey(CompanyProfile, related_name="directions", on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    okved_codes = ArrayField(models.CharField(max_length=10), default=list, blank=True)
    keywords = ArrayField(models.CharField(max_length=100), default=list, blank=True)
    exclude_keywords = ArrayField(models.CharField(max_length=100), default=list, blank=True)
    regions = ArrayField(models.CharField(max_length=100), default=list, blank=True)
    nmck_min = models.BigIntegerField(null=True, blank=True)
    nmck_max = models.BigIntegerField(null=True, blank=True)
    law_types = ArrayField(models.CharField(max_length=10), default=list, blank=True)
    procedure_types = ArrayField(models.CharField(max_length=25), default=list, blank=True)
    description = models.TextField(blank=True)
    won_tender_ids = ArrayField(models.IntegerField(), default=list, blank=True)
    hyde_texts = models.JSONField(null=True, blank=True)
    profile_vector = ArrayField(models.FloatField(), size=1024, null=True, blank=True)
    content_hash = models.CharField(max_length=16, blank=True)
    vector_updated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Направление компании"
        verbose_name_plural = "Направления компании"

    def __str__(self) -> str:
        return f"{self.profile.name} — {self.name}"

    def compute_content_hash(self) -> str:
        content = {
            "name": self.name,
            "description": (self.description or "")[:500],
            "okved_codes": sorted(self.okved_codes or []),
            "keywords": sorted(self.keywords or []),
            "regions": sorted(self.regions or []),
            "nmck_min": self.nmck_min,
            "nmck_max": self.nmck_max,
            "law_types": sorted(self.law_types or []),
            "procedure_types": sorted(self.procedure_types or []),
        }
        return hashlib.sha256(
            json.dumps(content, sort_keys=True).encode()
        ).hexdigest()[:16]

    def needs_reindex(self) -> bool:
        return self.compute_content_hash() != self.content_hash
