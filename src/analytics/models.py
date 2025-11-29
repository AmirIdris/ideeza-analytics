from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _

# Create your models here.
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
    
    # We store country codes (e.g., 'US', 'ET') directly for fast grouping
    country = models.CharField(max_length=5, db_index=True)
    
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