import random
from datetime import timedelta
from django.utils import timezone
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from analytics.models import Blog, BlogView
from faker import Faker

class Command(BaseCommand):
    help = 'Seeds the database with mock analytics data (Users, Blogs, Views)'

    def handle(self, *args, **kwargs):
        fake = Faker()
        self.stdout.write("🌱 Starting data seed...")

        # 1. Create Users
        self.stdout.write("Creating Users...")
        users = []
        for _ in range(10):
            username = fake.unique.user_name()
            email = fake.email()
            # Simple password for all
            user = User(username=username, email=email)
            user.set_password('password123')
            users.append(user)
        
        
        User.objects.bulk_create(users, ignore_conflicts=True)
        all_users = list(User.objects.all())

        # 2. Create Blogs
        self.stdout.write("Creating Blogs...")
        blogs = []
        for _ in range(50):
            blogs.append(Blog(
                title=fake.catch_phrase(),
                author=random.choice(all_users),
                content=fake.text(max_nb_chars=1000)
            ))
        Blog.objects.bulk_create(blogs)
        all_blogs = list(Blog.objects.all())

        # 3. Create Views (The Heavy Lifting)
        self.stdout.write("Creating 10,000 Views (distributed over 1 year)...")
        views = []
        countries = ['US', 'ET', 'DE', 'IN', 'GB', 'FR', 'CA', 'BR']
        
        # We want data over the last 365 days
        end_time = timezone.now()
        
        for _ in range(10000):
            # Random time in last year
            days_ago = random.randint(0, 365)
            # Random hour/minute
            seconds_ago = random.randint(0, 86400)
            view_time = end_time - timedelta(days=days_ago, seconds=seconds_ago)
            
            views.append(BlogView(
                blog=random.choice(all_blogs),
                country=random.choice(countries),
                timestamp=view_time,
                ip_address=fake.ipv4(),
                viewer=random.choice(all_users) if random.random() > 0.7 else None # 30% chance logged in
            ))

        # Bulk create in batches to be memory efficient
        BlogView.objects.bulk_create(views, batch_size=2000)
        
        # NOTE: bulk_create does not trigger 'auto_now_add' in Python, 
        # it relies on DB. But since we manually set 'timestamp' above, 
        # we need to make sure the DB respects it or we update it.

        self.stdout.write(self.style.SUCCESS(f'✅ Successfully created {len(views)} views!'))

