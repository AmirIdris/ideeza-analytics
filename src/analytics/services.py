import hashlib
import json
import logging
from typing import List, Dict, Any, Optional

from django.core.cache import cache
from django.db.models import Count, F, QuerySet
from django.db.models.functions import TruncMonth, TruncWeek, TruncDay, TruncYear
from django.conf import settings

from .models import BlogView
from .utils import DynamicFilterBuilder

logger = logging.getLogger(__name__)

class AnalyticsService:
    """
    Encapsulates all analytics aggregation logic.
    Handles Query Construction, Aggregation, and Caching.
    """

    # Cache timeout in seconds (e.g., 15 minutes)
    CACHE_TIMEOUT = 60 * 15 
    
    # Allowed fields for filtering security
    ALLOWED_FILTER_FIELDS = [
        'country', 'timestamp', 'blog', 'blog__title', 
        'blog__author__username', 'ip_address'
    ]

    @classmethod
    def _generate_cache_key(cls, prefix: str, **kwargs) -> str:
        """
        Generates a deterministic cache key based on arguments.
        Example: analytics:grouped:md5hash_of_params
        """
        # Sort keys so {"a":1, "b":2} is same as {"b":2, "a":1}
        payload_str = json.dumps(kwargs, sort_keys=True, default=str)
        payload_hash = hashlib.md5(payload_str.encode('utf-8')).hexdigest()
        return f"analytics:{prefix}:{payload_hash}"

    @classmethod
    def get_grouped_analytics(cls, object_type: str, filters: Dict) -> List[Dict]:
        """
        API #1: Group blogs and views by object_type (country/user).
        """
        # 1. Check Cache
        cache_key = cls._generate_cache_key("grouped", type=object_type, filters=filters)
        cached_result = cache.get(cache_key)
        if cached_result:
            logger.info(f"Cache HIT for {cache_key}")
            return cached_result

        logger.info(f"Cache MISS for {cache_key} - Running DB Query")

        # 2. Build Query
        builder = DynamicFilterBuilder(allowed_fields=cls.ALLOWED_FILTER_FIELDS)
        q_filters = builder.build(filters)
        queryset = BlogView.objects.filter(q_filters)

        # 3. Determine Grouping Key (X-Axis)
        # Mapping API 'object_type' to DB fields
        group_field = 'country' if object_type == 'country' else 'blog__author__username'

        # 4. Aggregation
        # values() acts as GROUP BY
        data = list(queryset.values(x=F(group_field)).annotate(
            y=Count('blog', distinct=True), # Unique blogs
            z=Count('id')                   # Total Views
        ).order_by('-z'))

        # 5. Set Cache
        cache.set(cache_key, data, timeout=cls.CACHE_TIMEOUT)
        return data

    @classmethod
    def get_top_analytics(cls, top_type: str, filters: Dict) -> List[Dict]:
        """
        API #2: Top 10 based on total views.
        """
        cache_key = cls._generate_cache_key("top", type=top_type, filters=filters)
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result

        builder = DynamicFilterBuilder(allowed_fields=cls.ALLOWED_FILTER_FIELDS)
        queryset = BlogView.objects.filter(builder.build(filters))

        # Determine grouping
        if top_type == 'blog':
            group_field = 'blog__title'
        elif top_type == 'user':
            group_field = 'blog__author__username'
        else: # country
            group_field = 'country'

        # Aggregation + Limit 10
        data = list(queryset.values(x=F(group_field)).annotate(
            y=Count('id') # Total views (Used as primary metric for sorting)
        ).order_by('-y')[:10])

        # Note: Assessment asks for x,y,z. We have x,y. 
        # Z is ambiguous for 'Top' unless it's growth, but usually Top lists are 2D.
        # We can add a dummy z or derived metric if clarified. 
        # For now, x=Name, y=Views is standard.

        cache.set(cache_key, data, timeout=cls.CACHE_TIMEOUT)
        return data

    @classmethod
    def get_performance_analytics(cls, period: str, filters: Dict) -> List[Dict]:
        """
        API #3: Time-series performance with growth calculation.
        """
        cache_key = cls._generate_cache_key("perf", period=period, filters=filters)
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result

        builder = DynamicFilterBuilder(allowed_fields=cls.ALLOWED_FILTER_FIELDS)
        queryset = BlogView.objects.filter(builder.build(filters))

        # 1. Truncate Date
        trunc_func = {
            'year': TruncYear('timestamp'),
            'month': TruncMonth('timestamp'),
            'week': TruncWeek('timestamp'),
            'day': TruncDay('timestamp')
        }.get(period, TruncMonth('timestamp'))

        # 2. Group By Period
        # We must order by period for the growth calculation to make sense
        raw_data = queryset.annotate(period_label=trunc_func)\
            .values('period_label')\
            .annotate(
                total_views=Count('id'),
                unique_blogs=Count('blog', distinct=True)
            ).order_by('period_label')

        # 3. Post-Processing (Calculate Growth %)
        # Doing this in Python is acceptable for aggregated result sets (usually < 365 rows)
        # Doing it in SQL requires Window Functions (Lag), which is complex to make database-agnostic.
        
        results = []
        prev_views = 0

        for entry in raw_data:
            views = entry['total_views']
            
            growth = 0.0
            if prev_views > 0:
                growth = ((views - prev_views) / prev_views) * 100
            
            # Format X-axis label nicely
            date_label = entry['period_label'].strftime("%Y-%m-%d")
            
            results.append({
                "x": date_label,
                "y": views,
                "z": round(growth, 2), # Growth Percentage
                # Extra metadata if needed: "blogs_created": entry['unique_blogs']
            })
            
            prev_views = views

        cache.set(cache_key, results, timeout=cls.CACHE_TIMEOUT)
        return results