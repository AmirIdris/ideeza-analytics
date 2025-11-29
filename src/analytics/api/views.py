from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.authentication import JWTAuthentication

from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from analytics.services import AnalyticsService
from analytics.api.serializers import FilterPayloadSerializer, AnalyticsResponseSerializer

class BaseAnalyticsView(APIView):
    """
    Base view to handle common Auth and Permission settings.
    """
    authentication_classes = [JWTAuthentication]
    # We set AllowAny for the assessment to make it easy to test, 
    # but in a real app, this would be [IsAuthenticated].
    permission_classes = [AllowAny] 

class GroupedAnalyticsView(BaseAnalyticsView):
    
    @swagger_auto_schema(
        operation_summary="Get Grouped Analytics (API #1)",
        operation_description="Group blogs and views by Object Type (country or user).",
        request_body=FilterPayloadSerializer,
        responses={200: AnalyticsResponseSerializer(many=True)},
        manual_parameters=[
            openapi.Parameter('object_type', openapi.IN_PATH, description="country OR user", type=openapi.TYPE_STRING)
        ]
    )
    def post(self, request, object_type):
        if object_type not in ['country', 'user']:
            return Response({"error": "Invalid object_type"}, status=status.HTTP_400_BAD_REQUEST)
        
        filters = request.data
        data = AnalyticsService.get_grouped_analytics(object_type, filters)
        return Response(data, status=status.HTTP_200_OK)


class TopAnalyticsView(BaseAnalyticsView):

    @swagger_auto_schema(
        operation_summary="Get Top Performers (API #2)",
        operation_description="Returns Top 10 users, countries, or blogs based on views.",
        request_body=FilterPayloadSerializer,
        responses={200: AnalyticsResponseSerializer(many=True)},
        manual_parameters=[
            openapi.Parameter('top_type', openapi.IN_PATH, description="blog, country, or user", type=openapi.TYPE_STRING)
        ]
    )
    def post(self, request, top_type):
        if top_type not in ['blog', 'country', 'user']:
            return Response({"error": "Invalid top_type"}, status=status.HTTP_400_BAD_REQUEST)

        filters = request.data
        data = AnalyticsService.get_top_analytics(top_type, filters)
        return Response(data, status=status.HTTP_200_OK)


class PerformanceAnalyticsView(BaseAnalyticsView):

    @swagger_auto_schema(
        operation_summary="Get Time-Series Performance (API #3)",
        operation_description="Shows views and growth % over time.",
        request_body=FilterPayloadSerializer,
        responses={200: AnalyticsResponseSerializer(many=True)},
        manual_parameters=[
            openapi.Parameter('compare', openapi.IN_QUERY, description="Period: month, week, day, year", type=openapi.TYPE_STRING, default='month')
        ]
    )
    def post(self, request):
        period = request.query_params.get('compare', 'month')
        filters = request.data
        data = AnalyticsService.get_performance_analytics(period, filters)
        return Response(data, status=status.HTTP_200_OK)