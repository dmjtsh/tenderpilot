from django.contrib import admin
from .models import Customer, Tender


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ["inn", "name", "region", "created_at"]
    search_fields = ["inn", "name"]


@admin.register(Tender)
class TenderAdmin(admin.ModelAdmin):
    list_display = ["number", "title_short", "nmck", "status", "published_at", "region"]
    list_filter = ["status", "region"]
    search_fields = ["number", "title"]
    raw_id_fields = ["customer"]
    readonly_fields = ["created_at", "updated_at"]

    @admin.display(description="Название")
    def title_short(self, obj: Tender) -> str:
        return obj.title[:80]
