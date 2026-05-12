from django.contrib import admin
from .models import UserPlan


@admin.register(UserPlan)
class UserPlanAdmin(admin.ModelAdmin):
    list_display = ["user", "plan", "ai_summaries_used", "rag_questions_used", "reset_at", "expires_at"]
    list_filter = ["plan"]
    search_fields = ["user__email"]
    readonly_fields = ["created_at", "updated_at"]
