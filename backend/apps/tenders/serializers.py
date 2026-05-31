from rest_framework import serializers
from .models import Customer, Tender, TenderPipeline, PipelineComment


def _b2b_restriction(request, instance) -> tuple[bool, str | None]:
    """Returns (is_restricted, restriction_reason) for B2B tenders."""
    if instance.law_type != "b2b":
        return False, None
    is_anon = not (request and request.user and request.user.is_authenticated)
    if is_anon:
        return True, "anon"
    from apps.billing.models import UserPlan
    plan = UserPlan.objects.filter(user=request.user).values_list("plan", flat=True).first() or "free"
    if plan == "free":
        return True, "free_plan"
    return False, None


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ["id", "inn", "name", "full_name", "region"]


class TenderListSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)

    class Meta:
        model = Tender
        fields = [
            "id", "number", "title", "nmck", "customer_name",
            "region", "okpd_codes", "published_at", "deadline_at", "auction_date",
            "status", "law_type", "procedure_type",
            "trading_platform", "trading_platform_url",
            "bid_security_amount", "bid_security_required",
            "contract_security_amount", "contract_security_percent",
            "source_url", "source",
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        restricted, reason = _b2b_restriction(request, instance)
        data["is_restricted"] = restricted
        data["restriction_reason"] = reason
        if restricted:
            data["customer_name"] = None
            data["trading_platform_url"] = None
            data["source_url"] = None
        return data


class TenderDetailSerializer(serializers.ModelSerializer):
    customer = CustomerSerializer(read_only=True)
    has_info_html = serializers.SerializerMethodField()
    info_html_text = serializers.SerializerMethodField()
    products = serializers.SerializerMethodField()

    class Meta:
        model = Tender
        fields = [
            "id", "number", "title", "nmck", "customer",
            "region", "okpd_codes", "published_at", "deadline_at", "auction_date",
            "status", "law_type", "procedure_type",
            "trading_platform", "trading_platform_url",
            "bid_security_amount", "bid_security_required",
            "contract_security_amount", "contract_security_percent",
            "source_url", "ai_summary", "source", "created_at", "updated_at",
            "has_info_html", "info_html_text", "products",
        ]

    def get_products(self, obj) -> list[dict] | None:
        rj = obj.raw_json or {}
        nested = rj.get("raw_json", {})
        products = (nested.get("products", []) if isinstance(nested, dict) else []) or rj.get("products", [])
        return products if products else None

    def get_has_info_html(self, obj) -> bool:
        rj = obj.raw_json or {}
        nested = rj.get("raw_json", {})
        raw = (nested.get("info_html", "") if isinstance(nested, dict) else "") or rj.get("info_html", "")
        return bool(raw and len(raw) > 50)

    def get_info_html_text(self, obj) -> str | None:
        from apps.tenders.summary_v2.context import _get_info_html_sanitized
        html = _get_info_html_sanitized(obj)
        return html if html else None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        restricted, reason = _b2b_restriction(request, instance)
        data["is_restricted"] = restricted
        data["restriction_reason"] = reason
        if restricted:
            data["customer"] = {"id": None, "inn": None, "name": None, "full_name": None, "region": instance.region}
            data["trading_platform_url"] = None
            data["source_url"] = None
        return data


class TenderPipelineSerializer(serializers.ModelSerializer):
    tender_title = serializers.CharField(source="tender.title", read_only=True)
    tender_number = serializers.CharField(source="tender.number", read_only=True)
    tender_nmck = serializers.DecimalField(
        source="tender.nmck", max_digits=18, decimal_places=2, read_only=True
    )
    tender_region = serializers.CharField(source="tender.region", read_only=True)
    tender_deadline_at = serializers.DateTimeField(source="tender.deadline_at", read_only=True)
    tender_customer_name = serializers.CharField(
        source="tender.customer.name", read_only=True, default=""
    )
    tender_law_type = serializers.CharField(source="tender.law_type", read_only=True)
    tender_overall_risk = serializers.SerializerMethodField()
    tender_docs_total = serializers.IntegerField(read_only=True, default=0)
    tender_docs_done = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = TenderPipeline
        fields = [
            "id", "tender", "profile", "status", "notes",
            "tender_title", "tender_number", "tender_nmck",
            "tender_region", "tender_deadline_at", "tender_customer_name",
            "tender_law_type", "tender_overall_risk",
            "tender_docs_total", "tender_docs_done",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_tender_overall_risk(self, obj) -> str | None:
        return getattr(obj, "_summary_risk", None)


class PipelineCommentSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = PipelineComment
        fields = ["id", "text", "user_name", "created_at"]
        read_only_fields = ["id", "created_at"]

    def get_user_name(self, obj) -> str:
        return obj.user.get_full_name() or obj.user.email
