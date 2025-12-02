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
from django.db.models import Count, F, Sum, Min, Max
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
    def _apply_filters(cls, queryset, filters: Dict):
        """
        Apply filters to BlogView queryset.
        
        Supports:
            - year, start_date, end_date (time filters)
            - country_codes (OR logic)
            - exclude_country_codes (NOT logic)
            - author_username, blog_id (exact match)
        """
        if filters.get('year'):
            queryset = queryset.filter(timestamp__year=filters['year'])
        if filters.get('start_date'):
            queryset = queryset.filter(timestamp__gte=filters['start_date'])
        if filters.get('end_date'):
            queryset = queryset.filter(timestamp__lte=filters['end_date'])
        if filters.get('country_codes'):
            queryset = queryset.filter(country__code__in=filters['country_codes'])
        if filters.get('author_username'):
            queryset = queryset.filter(blog__author__username=filters['author_username'])
        if filters.get('blog_id'):
            queryset = queryset.filter(blog_id=filters['blog_id'])
        if filters.get('exclude_country_codes'):
            queryset = queryset.exclude(country__code__in=filters['exclude_country_codes'])
        
        return queryset

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

        # Calculate growth percentage
        results = []
        prev_views = 0

        for entry in raw_data:
            views = entry['views']
            growth = ((views - prev_views) / prev_views * 100) if prev_views > 0 else 0.0
            
            results.append({
                "x": f"{entry['period'].strftime('%Y-%m-%d')} ({entry['blogs']} blogs)",
                "y": views,
                "z": round(growth, 2),
            })
            prev_views = views

        cache.set(cache_key, results, timeout=cls.CACHE_TIMEOUT)
        return results

    @classmethod
    def get_grouped_analytics_fast(cls, object_type: str, filters: Dict) -> List[Dict]:
        """
        API #1 using pre-calculated data (faster for large datasets).
        
        Requires: Run `python manage.py precalculate_stats` first.
        
        Performance: O(365 rows) instead of O(10,000 events)
        """
        cache_key = cls._generate_cache_key("grouped_fast", type=object_type, filters=filters)
        
        if cached := cache.get(cache_key):
            return cached

        queryset = DailyAnalyticsSummary.objects.all()
        
        # Apply filters
        if filters.get('year'):
            queryset = queryset.filter(date__year=filters['year'])
        if filters.get('start_date'):
            queryset = queryset.filter(date__gte=filters['start_date'])
        if filters.get('end_date'):
            queryset = queryset.filter(date__lte=filters['end_date'])
        if filters.get('country_codes'):
            queryset = queryset.filter(country__code__in=filters['country_codes'])
        if filters.get('exclude_country_codes'):
            queryset = queryset.exclude(country__code__in=filters['exclude_country_codes'])
        if filters.get('author_username'):
            queryset = queryset.filter(author__username=filters['author_username'])

        group_field = 'country__code' if object_type == 'country' else 'author__username'
        
        data = list(
            queryset
            .values(x=F(group_field))
            .annotate(y=Sum('unique_blogs'), z=Sum('total_views'))
            .order_by('-z')
        )

        cache.set(cache_key, data, timeout=cls.CACHE_TIMEOUT)
        return data
