from rest_framework import serializers
from django.utils import timezone
from datetime import timedelta
class AnalyticsFilterSerializer(serializers.Serializer):
    """
    Explicit contract to prevent SQL/Logic Injection.
    """

    range = serializers.ChoiceField(
        choices=['day', 'week', 'month', 'year'],
        required=False,
        help_text="Quick date range filter"
    )

    # Date Range
    start_date = serializers.DateTimeField(required=False)
    end_date = serializers.DateTimeField(required=False)
    year = serializers.IntegerField(required=False, min_value=2000, max_value=2100)
    
    # Dimensions (Supports 'OR' Logic via Lists)
    country_codes = serializers.ListField(
        child=serializers.CharField(max_length=5), 
        required=False,
        help_text="List of country codes to include (OR logic)"
    )
    author_username = serializers.CharField(required=False)
    blog_id = serializers.IntegerField(required=False)

    # Supports 'NOT' Logic (Requirement Requirement)
    exclude_country_codes = serializers.ListField(
        child=serializers.CharField(max_length=5),
        required=False,
        help_text="List of country codes to EXCLUDE (NOT logic)"
    )
    
    def validate(self, data):
        # Convert 'range' to start_date/end_date
        if 'range' in data:
            now = timezone.now()
            if data['range'] == 'day':
                data['start_date'] = now - timedelta(days=1)
            elif data['range'] == 'week':
                data['start_date'] = now - timedelta(weeks=1)
            elif data['range'] == 'month':
                data['start_date'] = now - timedelta(days=30)
            elif data['range'] == 'year':
                data['start_date'] = now - timedelta(days=365)
            data['end_date'] = now
        return data


class AnalyticsResponseSerializer(serializers.Serializer):
    x = serializers.CharField(help_text="Grouping Key")
    y = serializers.IntegerField(help_text="Primary Metric")
    z = serializers.FloatField(help_text="Secondary Metric")