"""
Pre-calculation Management Command

PROBLEM SOLVER APPROACH:
Instead of complex filtering on every API call, we pre-calculate daily aggregates.
This transforms the query from:
    "Scan 10,000 events, filter, group, count" (O(n) per request)
To:
    "Query 365 pre-calculated rows" (O(days) per request)

Usage:
    python manage.py precalculate_stats           # Calculate all dates
    python manage.py precalculate_stats --days=7  # Last 7 days only

In production, schedule via cron:
    0 1 * * * python manage.py precalculate_stats --days=1
"""
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.contrib.auth.models import User

from analytics.models import BlogView, DailyAnalyticsSummary, Country


class Command(BaseCommand):
    help = 'Pre-calculates daily analytics summaries for faster queries'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=None,
            help='Number of days to calculate (default: all available data)'
        )

    def handle(self, *args, **options):
        self.stdout.write("🔄 Starting pre-calculation...")
        
        days = options.get('days')
        
        if days:
            start_date = timezone.now().date() - timedelta(days=days)
            self.stdout.write(f"   Calculating last {days} days (from {start_date})")
        else:
            # Get the earliest view date
            earliest = BlogView.objects.order_by('timestamp').first()
            if not earliest:
                self.stdout.write(self.style.WARNING("No BlogView data found."))
                return
            start_date = earliest.timestamp.date()
            self.stdout.write(f"   Calculating from {start_date} to today")
        
        # Clear existing summaries for the date range
        DailyAnalyticsSummary.objects.filter(date__gte=start_date).delete()
        
        # Aggregate by date + country + author
        aggregated = BlogView.objects.filter(
            timestamp__date__gte=start_date
        ).annotate(
            view_date=TruncDate('timestamp')
        ).values(
            'view_date', 'country', 'blog__author'
        ).annotate(
            total_views=Count('id'),
            unique_blogs=Count('blog', distinct=True)
        ).order_by('view_date')
        
        # Bulk create summaries
        summaries = []
        for row in aggregated:
            summaries.append(DailyAnalyticsSummary(
                date=row['view_date'],
                country_id=row['country'],
                author_id=row['blog__author'],
                total_views=row['total_views'],
                unique_blogs=row['unique_blogs']
            ))
        
        DailyAnalyticsSummary.objects.bulk_create(summaries, batch_size=1000)
        
        self.stdout.write(self.style.SUCCESS(
            f"✅ Created {len(summaries)} daily summary records"
        ))
        self.stdout.write(self.style.SUCCESS(
            "   API queries now use pre-calculated data instead of raw events!"
        ))

