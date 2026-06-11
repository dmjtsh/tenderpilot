from django.contrib import admin
from .models import Referral, ReferralCode


@admin.register(ReferralCode)
class ReferralCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "user_email", "created_at")
    search_fields = ("code", "user__email")
    readonly_fields = ("code", "created_at")

    @admin.display(description="Email")
    def user_email(self, obj):
        return obj.user.email


@admin.register(Referral)
class ReferralAdmin(admin.ModelAdmin):
    list_display = (
        "referrer_email", "referred_email", "status",
        "discount_percent", "discount_applied", "registered_at", "converted_at",
    )
    list_filter = ("status", "discount_applied")
    search_fields = ("referrer__email", "referred_user__email", "code__code")
    readonly_fields = ("registered_at", "converted_at")

    @admin.display(description="Реферер")
    def referrer_email(self, obj):
        return obj.referrer.email

    @admin.display(description="Приглашённый")
    def referred_email(self, obj):
        return obj.referred_user.email
