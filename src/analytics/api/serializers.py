from rest_framework import serializers

class FilterConditionSerializer(serializers.Serializer):
    field = serializers.CharField(required=True, help_text="Field to filter by (e.g., country)")
    op = serializers.CharField(required=False, default="eq", help_text="Operator: eq, gt, lt, contains")
    value = serializers.JSONField(required=True, help_text="Value to match")

class FilterPayloadSerializer(serializers.Serializer):
    operator = serializers.ChoiceField(choices=["and", "or", "not"], default="and")
    conditions = serializers.ListField(
        child=serializers.DictField(), # recursive definition is hard in basic DRF, keeping simple
        help_text="List of conditions or nested groups"
    )

class AnalyticsResponseSerializer(serializers.Serializer):
    x = serializers.CharField(help_text="Grouping Key")
    y = serializers.IntegerField(help_text="Primary Metric")
    z = serializers.FloatField(help_text="Secondary Metric")