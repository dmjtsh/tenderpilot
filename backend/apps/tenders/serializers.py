from rest_framework import serializers
from .models import Customer, Tender


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
            "status", "law_type", "trading_platform", "trading_platform_url",
            "bid_security_amount", "bid_security_required",
            "contract_security_amount", "contract_security_percent",
            "source_url",
        ]


class TenderDetailSerializer(serializers.ModelSerializer):
    customer = CustomerSerializer(read_only=True)

    class Meta:
        model = Tender
        fields = [
            "id", "number", "title", "nmck", "customer",
            "region", "okpd_codes", "published_at", "deadline_at", "auction_date",
            "status", "law_type", "trading_platform", "trading_platform_url",
            "bid_security_amount", "bid_security_required",
            "contract_security_amount", "contract_security_percent",
            "source_url", "ai_summary", "created_at", "updated_at",
        ]
