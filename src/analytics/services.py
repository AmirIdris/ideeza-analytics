"""
Analytics Service Module

Handles all analytics aggregation logic with caching support.
Provides both real-time and pre-calculated query methods.
"""
import hashlib
import json
import logging
from typing import List, Dict

from django.core.cache import cache
from django.db.models import Count, F, Q, Sum, Min, Max
from django.db.models.functions import TruncMonth, TruncWeek, TruncDay
from django.utils import timezone

from .models import BlogView, DailyAnalyticsSummary

logger = logging.getLogger(__name__)


class AnalyticsService:
    """
    Service class for analytics operations.
    
    Methods:
        get_grouped_analytics: Group views by country or user
        get_top_analytics: Get top 10 by views
        get_performance_analytics: Time-series with growth calculation
        get_grouped_analytics_fast: Pre-calculated version (faster)
    """
    
    CACHE_TIMEOUT = 60 * 15  # 15 minutes

    @classmethod
    def _generate_cache_key(cls, prefix: str, **kwargs) -> str:
        """Generate deterministic cache key from parameters."""
        payload = json.dumps(kwargs, sort_keys=True, default=str)
        return f"analytics:{prefix}:{hashlib.md5(payload.encode()).hexdigest()}"

    @classmethod
    def _build_blogview_filters(cls, filters: Dict) -> Q:
        """
        Build declarative Q object for BlogView queries.
        
        Note: This is separate from _build_summary_filters() because:
        - BlogView uses 'timestamp' field (DateTimeField)
        - DailyAnalyticsSummary uses 'date' field (DateField)
        - Different field names require different Q object construction
        
        PROBLEM SOLVER APPROACH:
        Instead of complex conditional filtering chains, we build a declarative
        query object that clearly expresses the filtering logic.
        """
        q_objects = Q()
        
        # Date filters (mutually exclusive: year OR date range)
        if year := filters.get('year'):
            q_objects &= Q(timestamp__year=year)
        else:
            if start_date := filters.get('start_date'):
                q_objects &= Q(timestamp__gte=start_date)
            if end_date := filters.get('end_date'):
                q_objects &= Q(timestamp__lte=end_date)
        
        # Country filters
        if country_codes := filters.get('country_codes'):
            q_objects &= Q(country__code__in=country_codes)
        if exclude_codes := filters.get('exclude_country_codes'):
            q_objects &= ~Q(country__code__in=exclude_codes)
        
        # Author and blog filters
        if author := filters.get('author_username'):
            q_objects &= Q(blog__author__username=author)
        if blog_id := filters.get('blog_id'):
            q_objects &= Q(blog_id=blog_id)
        
        return q_objects

    @classmethod
    def _apply_filters(cls, queryset, filters: Dict):
        """
        Apply filters to BlogView queryset using declarative Q objects.
        
        Supports:
            - year, start_date, end_date (time filters)
            - country_codes (OR logic)
            - exclude_country_codes (NOT logic)
            - author_username, blog_id (exact match)
        """
        query_filters = cls._build_blogview_filters(filters)
        return queryset.filter(query_filters)

    @classmethod
    def get_grouped_analytics(cls, object_type: str, filters: Dict) -> List[Dict]:
        """
        API #1: Group blogs and views by country or user.
        
        Args:
            object_type: 'country' or 'user'
            filters: Filter parameters
            
        Returns:
            List of {x: grouping_key, y: unique_blogs, z: total_views}
        """
        cache_key = cls._generate_cache_key("grouped", type=object_type, filters=filters)
        
        if cached := cache.get(cache_key):
            return cached

        queryset = BlogView.objects.select_related('blog', 'blog__author', 'country')
        queryset = cls._apply_filters(queryset, filters)

        group_field = 'country__code' if object_type == 'country' else 'blog__author__username'
        
        data = list(
            queryset
            .values(x=F(group_field))
            .annotate(y=Count('blog', distinct=True), z=Count('id'))
            .order_by('-z')
        )

        cache.set(cache_key, data, timeout=cls.CACHE_TIMEOUT)
        return data

    @classmethod
    def get_top_analytics(cls, top_type: str, filters: Dict) -> List[Dict]:
        """
        API #2: Get top 10 by total views.
        
        Args:
            top_type: 'blog', 'user', or 'country'
            filters: Filter parameters
            
        Returns:
            List of {x: name, y: total_views, z: unique_count}
        """
        cache_key = cls._generate_cache_key("top", type=top_type, filters=filters)
        
        if cached := cache.get(cache_key):
            return cached

        queryset = BlogView.objects.select_related('blog', 'blog__author', 'country')
        queryset = cls._apply_filters(queryset, filters)

        # Configuration dict: maps top_type to (grouping_field, z_metric)
        # This avoids repetitive if/elif chains and makes it easy to add new types
        config = {
            'blog': ('blog__title', Count('country', distinct=True)),
            'user': ('blog__author__username', Count('blog', distinct=True)),
            'country': ('country__code', Count('blog', distinct=True)),
        }
        
        group_field, z_metric = config[top_type]
        
        data = list(
            queryset
            .values(x=F(group_field))
            .annotate(y=Count('id'), z=z_metric)
            .order_by('-y')[:10]
        )

        cache.set(cache_key, data, timeout=cls.CACHE_TIMEOUT)
        return data

    @classmethod
    def get_performance_analytics(cls, filters: Dict) -> List[Dict]:
        """
        API #3: Time-series performance with growth calculation.
        
        Auto-selects granularity based on date range:
            - >365 days: Monthly
            - >30 days: Weekly
            - <=30 days: Daily
            
        Returns:
            List of {x: "date (N blogs)", y: views, z: growth_percent}
        """
        cache_key = cls._generate_cache_key("perf", filters=filters)
        
        if cached := cache.get(cache_key):
            return cached

        queryset = BlogView.objects.select_related('blog', 'blog__author', 'country')
        queryset = cls._apply_filters(queryset, filters)

        # Determine time granularity
        date_range = queryset.aggregate(min=Min('timestamp'), max=Max('timestamp'))
        min_date = date_range['min'] or timezone.now()
        max_date = date_range['max'] or timezone.now()
        days = (max_date - min_date).days

        if days > 365:
            trunc_func = TruncMonth('timestamp')
        elif days > 30:
            trunc_func = TruncWeek('timestamp')
        else:
            trunc_func = TruncDay('timestamp')

        # Aggregate by period
        raw_data = (
            queryset
            .annotate(period=trunc_func)
            .values('period')
            .annotate(views=Count('id'), blogs=Count('blog', distinct=True))
            .order_by('period')
        )

        # Calculate growth percentage for each period
        results = cls._calculate_growth_periods(raw_data)

        cache.set(cache_key, results, timeout=cls.CACHE_TIMEOUT)
        return results

    @classmethod
    def _calculate_growth_periods(cls, raw_data) -> List[Dict]:
        """
        Calculate growth percentage for time-series data.
        
        Args:
            raw_data: QuerySet results with 'period', 'views', 'blogs'
            
        Returns:
            List of {x: "date (N blogs)", y: views, z: growth_percent}
        """
        results = []
        prev_views = 0

        for entry in raw_data:
            views = entry['views']
            # Calculate growth: ((current - previous) / previous) * 100
            growth = ((views - prev_views) / prev_views * 100) if prev_views > 0 else 0.0
            
            results.append({
                "x": f"{entry['period'].strftime('%Y-%m-%d')} ({entry['blogs']} blogs)",
                "y": views,
                "z": round(growth, 2),
            })
            prev_views = views
        
        return results

    @classmethod
    def _build_summary_filters(cls, filters: Dict) -> Q:
        """
        Build declarative Q object for pre-calculated summary queries.
        
        PROBLEM SOLVER APPROACH:
        Instead of complex conditional filtering, we build a declarative query
        that leverages the pre-calculated data structure. This eliminates
        the need for complex filtering logic at query time.
        """
        q_objects = Q()
        
        # Date filters (mutually exclusive: year OR date range)
        if year := filters.get('year'):
            q_objects &= Q(date__year=year)
        else:
            # Handle both datetime and date objects
            if start_date := filters.get('start_date'):
                start_date_value = start_date.date() if hasattr(start_date, 'date') else start_date
                q_objects &= Q(date__gte=start_date_value)
            if end_date := filters.get('end_date'):
                end_date_value = end_date.date() if hasattr(end_date, 'date') else end_date
                q_objects &= Q(date__lte=end_date_value)
        
        # Country filters
        if country_codes := filters.get('country_codes'):
            q_objects &= Q(country__code__in=country_codes)
        if exclude_codes := filters.get('exclude_country_codes'):
            q_objects &= ~Q(country__code__in=exclude_codes)
        
        # Author filter
        if author := filters.get('author_username'):
            q_objects &= Q(author__username=author)
        
        return q_objects

    @classmethod
    def get_grouped_analytics_fast(cls, object_type: str, filters: Dict) -> List[Dict]:
        """
        API #1 using pre-calculated data - Problem Solver Approach.
        
        Instead of complex filtering on raw events, we:
        1. Query pre-calculated summaries (already aggregated)
        2. Apply simple declarative filters using Q objects
        3. Just SUM the pre-calculated values (no complex calculations)
        
        Requires: Run `python manage.py precalculate_stats` first.
        
        Performance: O(365 rows) instead of O(10,000 events)
        Query complexity: Simple SUM aggregation, no complex WHERE clauses
        """
        cache_key = cls._generate_cache_key("grouped_fast", type=object_type, filters=filters)
        
        if cached := cache.get(cache_key):
            return cached

        # Build declarative query - no complex conditional logic
        query_filters = cls._build_summary_filters(filters)
        group_field = 'country__code' if object_type == 'country' else 'author__username'
        
        # Simple aggregation on pre-calculated data
        data = list(
            DailyAnalyticsSummary.objects
            .filter(query_filters)
            .values(x=F(group_field))
            .annotate(y=Sum('unique_blogs'), z=Sum('total_views'))
            .order_by('-z')
        )

        cache.set(cache_key, data, timeout=cls.CACHE_TIMEOUT)
        return data
