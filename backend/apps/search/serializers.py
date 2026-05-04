from rest_framework import serializers


class SearchQuerySerializer(serializers.Serializer):
    query = serializers.CharField(max_length=500)
    limit = serializers.IntegerField(default=20, min_value=1, max_value=100)
    region = serializers.CharField(required=False, allow_blank=True)
    status = serializers.CharField(required=False, default="active")
    nmck_max = serializers.FloatField(required=False, allow_null=True)
    nmck_min = serializers.FloatField(required=False, allow_null=True)


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
    score = serializers.FloatField()
    matched_direction = serializers.CharField(allow_null=True, required=False)
