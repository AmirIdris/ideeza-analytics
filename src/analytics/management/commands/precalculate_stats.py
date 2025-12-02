"""
Pre-calculate Analytics Command

Usage:
    python manage.py precalculate_stats           # All data
    python manage.py precalculate_stats --days=7  # Last 7 days

Scheduled in production via cron:
    0 1 * * * python manage.py precalculate_stats --days=1
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone

from analytics.models import BlogView, DailyAnalyticsSummary, Country


class Command(BaseCommand):
    help = 'Pre-calculate daily analytics summaries'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=None,
            help='Days to calculate (default: all)'
        )

    def handle(self, *args, **options):
        self.stdout.write("Starting pre-calculation...")
        
        # Determine date range
        days = options.get('days')
        if days:
            start_date = timezone.now().date() - timedelta(days=days)
            self.stdout.write(f"  Range: last {days} days")
        else:
            earliest = BlogView.objects.order_by('timestamp').first()
            if not earliest:
                self.stdout.write(self.style.WARNING("No data found."))
                return
            start_date = earliest.timestamp.date()
            self.stdout.write(f"  Range: {start_date} to today")

        # Clear existing summaries
        DailyAnalyticsSummary.objects.filter(date__gte=start_date).delete()

        # Aggregate by day + country + author
        aggregated = (
            BlogView.objects
            .filter(timestamp__date__gte=start_date)
            .annotate(view_date=TruncDate('timestamp'))
            .values('view_date', 'country', 'blog__author')
            .annotate(
                total_views=Count('id'),
                unique_blogs=Count('blog', distinct=True)
            )
            .order_by('view_date')
        )

        # Bulk create summaries
        summaries = [
            DailyAnalyticsSummary(
                date=row['view_date'],
                country_id=row['country'],
                author_id=row['blog__author'],
                total_views=row['total_views'],
                unique_blogs=row['unique_blogs']
            )
            for row in aggregated
        ]
        
        DailyAnalyticsSummary.objects.bulk_create(summaries, batch_size=1000)

        self.stdout.write(self.style.SUCCESS(
            f"Created {len(summaries)} summary records"
        ))
