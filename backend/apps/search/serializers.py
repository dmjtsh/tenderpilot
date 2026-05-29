from rest_framework import serializers


class SearchQuerySerializer(serializers.Serializer):
    query = serializers.CharField(max_length=500)
    limit = serializers.IntegerField(default=20, min_value=1, max_value=100)
    region = serializers.CharField(required=False, allow_blank=True)
    status = serializers.CharField(required=False, default="active")
    nmck_max = serializers.FloatField(required=False, allow_null=True)
    nmck_min = serializers.FloatField(required=False, allow_null=True)
    law_type = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    procedure_type = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    regions = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    deadline_days = serializers.IntegerField(required=False, allow_null=True, default=None)
    deadline_days_min = serializers.IntegerField(required=False, allow_null=True, default=None)
    okpd = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    customer = serializers.CharField(required=False, allow_blank=True, default="")


class ExplanationSerializer(serializers.Serializer):
    icon = serializers.CharField()
    text = serializers.CharField()


class SearchResultItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    number = serializers.CharField()
    title = serializers.CharField()
    nmck = serializers.FloatField(allow_null=True)
    customer_name = serializers.CharField(allow_null=True)
    region = serializers.CharField()
    published_at = serializers.DateTimeField(allow_null=True)
    deadline_at = serializers.DateTimeField(allow_null=True, required=False)
    law_type = serializers.CharField(allow_null=True, required=False, allow_blank=True)
    status = serializers.CharField()
    source_url = serializers.CharField()
    trading_platform = serializers.CharField(allow_null=True, required=False, allow_blank=True)
    auction_date = serializers.DateTimeField(allow_null=True, required=False)
    procedure_type = serializers.CharField(allow_null=True, required=False, allow_blank=True)
    score = serializers.FloatField(required=False, allow_null=True)
    score_label = serializers.CharField(required=False, default="")
    explanations = ExplanationSerializer(many=True, required=False, default=list)
    matched_direction = serializers.CharField(allow_null=True, required=False)
