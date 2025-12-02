from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _

# Create your models here.



class Country(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=5, unique=True, db_index=True)

    def __str__(self):
        return self.code



class Blog(models.Model):
    title = models.CharField(max_length=255)
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blogs')
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title
        

class BlogView(models.Model):
    """
    Fact Table for Analytics.
    Stores every single view event.
    """
    blog = models.ForeignKey(Blog, on_delete=models.CASCADE, related_name='views')
    
    # NORMALIZED: Linking to Country table instead of storing raw string
    country = models.ForeignKey(Country, on_delete=models.SET_NULL, null=True, related_name='views')
    
    # IP is useful for uniqueness checks, though not strictly required by the prompt's x,y,z
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    # Optional: If a registered user viewed it
    viewer = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='viewed_blogs')
    
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            # Compound Index: Speed up filtering by time AND country (Very common query)
            models.Index(fields=['timestamp', 'country']),
            # Speed up "How many views did this blog get?"
            models.Index(fields=['blog', 'timestamp']),
        ]

    def __str__(self):
        return f"{self.blog.title} viewed from {self.country}"


class DailyAnalyticsSummary(models.Model):
    """
    Pre-calculated daily aggregates for O(1) analytics queries.
    
    PROBLEM SOLVER APPROACH:
    Instead of querying 10,000+ raw BlogView events and filtering on every API call,
    we pre-calculate daily statistics. This reduces query complexity from O(n) to O(days).
    
    Example: 1 year of data = 365 rows instead of 10,000+ events.
    """
    date = models.DateField(db_index=True)
    country = models.ForeignKey(Country, on_delete=models.CASCADE, null=True, blank=True)
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Pre-calculated metrics (no need to COUNT at query time)
    total_views = models.IntegerField(default=0)
    unique_blogs = models.IntegerField(default=0)
    
    class Meta:
        unique_together = ['date', 'country', 'author']
        indexes = [
            models.Index(fields=['date', 'country']),
            models.Index(fields=['date', 'author']),
        ]
        verbose_name = "Daily Analytics Summary"
        verbose_name_plural = "Daily Analytics Summaries"

    def __str__(self):
        return f"{self.date} | {self.country} | {self.author} | {self.total_views} views"