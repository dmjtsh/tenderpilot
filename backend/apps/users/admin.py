from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, CompanyProfile


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["email", "username", "is_staff", "date_joined"]
    ordering = ["-date_joined"]


@admin.register(CompanyProfile)
class CompanyProfileAdmin(admin.ModelAdmin):
    list_display = ["name", "inn", "user"]
    search_fields = ["name", "inn"]
