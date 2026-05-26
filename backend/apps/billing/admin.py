from django.contrib import admin

from .models import Payment, Subscription, UserPlan


@admin.register(UserPlan)
class UserPlanAdmin(admin.ModelAdmin):
    list_display = ["user", "plan", "ai_summaries_used", "rag_questions_used", "reset_at", "expires_at"]
    list_filter = ["plan"]
    search_fields = ["user__email"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ["user", "plan", "status", "interval", "current_period_end", "canceled_at"]
    list_filter = ["status", "plan", "interval"]
    search_fields = ["user__email"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["yookassa_payment_id", "user", "amount", "status", "is_recurring", "created_at"]
    list_filter = ["status", "is_recurring"]
    search_fields = ["user__email", "yookassa_payment_id"]
    readonly_fields = ["created_at", "updated_at"]
