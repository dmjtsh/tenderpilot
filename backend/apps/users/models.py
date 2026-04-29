from django.contrib.auth.models import AbstractUser
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
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="company_profile")
    name = models.CharField(max_length=255)
    inn = models.CharField(max_length=12, blank=True)
    description = models.TextField(blank=True)
    okved_codes = models.JSONField(default=list)
    regions = models.JSONField(default=list)
    keywords = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Профиль компании"
        verbose_name_plural = "Профили компаний"

    def __str__(self) -> str:
        return self.name
