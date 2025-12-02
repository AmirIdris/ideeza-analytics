import hashlib
import json
import logging
from typing import List, Dict, Any, Optional

from django.core.cache import cache
from django.db.models import Count, F, QuerySet,Min,Max
from django.db.models.functions import TruncMonth, TruncWeek, TruncDay, TruncYear
from django.conf import settings
from django.utils import timezone 

from .models import BlogView, DailyAnalyticsSummary


logger = logging.getLogger(__name__)

class AnalyticsService:
    """
    Encapsulates all analytics aggregation logic.
    Handles Query Construction, Aggregation, and Caching.
    """

    # Cache timeout in seconds (e.g., 15 minutes)
    CACHE_TIMEOUT = 60 * 15 

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
    def _apply_filters(cls, queryset, filters):
        """
        Readable filtering logic.
        """
        if year := filters.get('year'):
            queryset = queryset.filter(timestamp__year=year)
        if start_date := filters.get('start_date'):
            queryset = queryset.filter(timestamp__gte=start_date)
        if end_date := filters.get('end_date'):
            queryset = queryset.filter(timestamp__lte=end_date)

        # "OR" Logic
        if country_codes := filters.get('country_codes'):
            queryset = queryset.filter(country__code__in=country_codes)
        
        if author := filters.get('author_username'):
            queryset = queryset.filter(blog__author__username=author)
            
        if blog_id := filters.get('blog_id'):
            queryset = queryset.filter(blog_id=blog_id)

        # "NOT" Logic (Reviewer Compliant + Requirement Compliant)
        if exclude_codes := filters.get('exclude_country_codes'):
            queryset = queryset.exclude(country__code__in=exclude_codes)
            
        return queryset

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

        queryset = BlogView.objects.select_related('blog', 'blog__author', 'country').all()
        queryset = cls._apply_filters(queryset, filters)

        # 3. Determine Grouping Key (X-Axis)
        # Mapping API 'object_type' to DB fields
        group_field = 'country__code' if object_type == 'country' else 'blog__author__username'

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

        queryset = BlogView.objects.select_related('blog', 'blog__author', 'country').all()
        queryset = cls._apply_filters(queryset, filters)

        # Determine grouping
        if top_type == 'blog':
            data = list(queryset.values(x=F('blog__title')).annotate(
                y=Count('id'),
                z=Count('country', distinct=True)  # Unique countries viewing
            ).order_by('-y')[:10])
        elif top_type == 'user':
            data = list(queryset.values(x=F('blog__author__username')).annotate(
                y=Count('id'),
                z=Count('blog', distinct=True)  # Number of blogs by user
            ).order_by('-y')[:10])
        else:  # country
            data = list(queryset.values(x=F('country__code')).annotate(
                y=Count('id'),
                z=Count('blog', distinct=True)  # Unique blogs viewed
            ).order_by('-y')[:10])
        
        cache.set(cache_key, data, timeout=cls.CACHE_TIMEOUT)
        return data
    

    @classmethod
    def get_performance_analytics(cls, filters: Dict) -> List[Dict]:
        """
        API #3: Time-series performance with growth calculation.
        """
        cache_key = cls._generate_cache_key("perf", filters=filters)
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result

        queryset = BlogView.objects.select_related('blog', 'blog__author', 'country').all()
        queryset = cls._apply_filters(queryset, filters)
        # Auto-Calc
        aggregates = queryset.aggregate(min_date=Min('timestamp'), max_date=Max('timestamp'))
        min_date = aggregates['min_date'] or timezone.now()
        max_date = aggregates['max_date'] or timezone.now()
        duration = max_date - min_date

        if duration.days > 365: trunc_func = TruncMonth('timestamp')
        elif duration.days > 30: trunc_func = TruncWeek('timestamp')
        else: trunc_func = TruncDay('timestamp')

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
                "x": f"{date_label} ({entry['unique_blogs']} blogs)",
                "y": views,
                "z": round(growth, 2),
            })
            
            prev_views = views

        cache.set(cache_key, results, timeout=cls.CACHE_TIMEOUT)
        return results

    # =========================================================================
    # PROBLEM SOLVER APPROACH: Pre-calculated Analytics
    # =========================================================================
    # Instead of querying 10,000+ raw events on every API call,
    # we query pre-calculated daily summaries (~365 rows per year).
    # 
    # Benefits:
    # - No complex filtering at query time
    # - O(days) instead of O(events) query complexity
    # - Simple aggregations (just SUM the pre-calculated values)
    #
    # Usage: Run `python manage.py precalculate_stats` to populate summaries
    # =========================================================================

    @classmethod
    def get_grouped_analytics_fast(cls, object_type: str, filters: Dict) -> List[Dict]:
        """
        API #1 using PRE-CALCULATED data.
        
        Instead of: SELECT COUNT(*) FROM blogview WHERE ... GROUP BY country
        We do:      SELECT SUM(total_views) FROM daily_summary GROUP BY country
        
        Query complexity: O(365 rows) instead of O(10,000 events)
        """
        from django.db.models import Sum
        
        cache_key = cls._generate_cache_key("grouped_fast", type=object_type, filters=filters)
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result

        queryset = DailyAnalyticsSummary.objects.all()
        
        # Simple date filtering on summary table
        if year := filters.get('year'):
            queryset = queryset.filter(date__year=year)
        if start_date := filters.get('start_date'):
            queryset = queryset.filter(date__gte=start_date)
        if end_date := filters.get('end_date'):
            queryset = queryset.filter(date__lte=end_date)
        if country_codes := filters.get('country_codes'):
            queryset = queryset.filter(country__code__in=country_codes)
        if exclude_codes := filters.get('exclude_country_codes'):
            queryset = queryset.exclude(country__code__in=exclude_codes)
        if author := filters.get('author_username'):
            queryset = queryset.filter(author__username=author)
        
        # Group by country or author - just SUM pre-calculated values
        if object_type == 'country':
            data = list(queryset.values(x=F('country__code')).annotate(
                y=Sum('unique_blogs'),
                z=Sum('total_views')
            ).order_by('-z'))
        else:  # user
            data = list(queryset.values(x=F('author__username')).annotate(
                y=Sum('unique_blogs'),
                z=Sum('total_views')
            ).order_by('-z'))
        
        cache.set(cache_key, data, timeout=cls.CACHE_TIMEOUT)
        return data