from django.contrib import admin

from .models import CustomerProfile


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ("inn", "name", "status", "licenses_count", "rusprofile_updated_at")
    list_filter = ("rusprofile_failed", "status")
    search_fields = ("inn", "name")
    readonly_fields = ("created_at", "updated_at")
