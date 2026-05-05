from rest_framework import serializers
from .models import Customer, Tender, TenderPipeline


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


class TenderDetailSerializer(serializers.ModelSerializer):
    customer = CustomerSerializer(read_only=True)

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
        ]


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

    class Meta:
        model = TenderPipeline
        fields = [
            "id", "tender", "profile", "status", "notes",
            "tender_title", "tender_number", "tender_nmck",
            "tender_region", "tender_deadline_at", "tender_customer_name",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
