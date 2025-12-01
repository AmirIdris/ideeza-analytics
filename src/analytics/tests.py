# src/analytics/tests.py
from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from analytics.models import Country, Blog, BlogView
from analytics.services import AnalyticsService

class AnalyticsAPITest(TestCase):
    def setUp(self):
        # Create test data
        self.client = APIClient()
        self.user = User.objects.create_user('testuser', 'test@test.com')
        self.country_us = Country.objects.create(name='USA', code='US')
        self.country_uk = Country.objects.create(name='UK', code='UK')
        self.blog = Blog.objects.create(title='Test Blog', author=self.user, content='...')
        
        # Create views
        BlogView.objects.create(blog=self.blog, country=self.country_us)
        BlogView.objects.create(blog=self.blog, country=self.country_us)
        BlogView.objects.create(blog=self.blog, country=self.country_uk)
    
    def test_api1_grouped_by_country(self):
        """Test API #1: Group by country with filters"""
        response = self.client.post(
            '/api/analytics/blog-views/country/',
            {'country_codes': ['US']},
            format='json'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['x'], 'US')
        self.assertEqual(response.data[0]['z'], 2)  # 2 views
    
    def test_api2_top_blogs(self):
        """Test API #2: Top 10 blogs"""
        response = self.client.post(
            '/api/analytics/top/blog/',
            {},
            format='json'
        )
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(response.data), 10)
        self.assertIn('x', response.data[0])
        self.assertIn('y', response.data[0])
        self.assertIn('z', response.data[0])
    
    def test_api3_performance(self):
        """Test API #3: Performance over time"""
        response = self.client.post(
            '/api/analytics/performance/',
            {},
            format='json'
        )
        self.assertEqual(response.status_code, 200)
        if response.data:
            self.assertIn('blogs', response.data[0]['x'])
            self.assertIn('y', response.data[0])
            self.assertIn('z', response.data[0])
    
    def test_dynamic_filters_and_logic(self):
        """Test AND logic: multiple filters combine"""
        response = self.client.post(
            '/api/analytics/blog-views/country/',
            {
                'country_codes': ['US', 'UK'],
                'year': 2025
            },
            format='json'
        )
        self.assertEqual(response.status_code, 200)
    
    def test_dynamic_filters_not_logic(self):
        """Test NOT logic: exclude countries"""
        response = self.client.post(
            '/api/analytics/blog-views/country/',
            {'exclude_country_codes': ['SPAM']},
            format='json'
        )
        self.assertEqual(response.status_code, 200)