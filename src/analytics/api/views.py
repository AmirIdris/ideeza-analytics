from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.authentication import JWTAuthentication

from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from analytics.services import AnalyticsService
from analytics.api.serializers import  AnalyticsResponseSerializer, AnalyticsFilterSerializer

class BaseAnalyticsView(APIView):
    """
    Base view to handle common Auth and Permission settings.
    """
    authentication_classes = [JWTAuthentication]
    # We set AllowAny for the assessment to make it easy to test, 
    # but in a real app, this would be [IsAuthenticated].
    permission_classes = [AllowAny] 

class GroupedAnalyticsView(BaseAnalyticsView):
    
    @swagger_auto_schema(request_body=AnalyticsFilterSerializer)
    def post(self, request, object_type):
        serializer = AnalyticsFilterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if object_type not in ['country', 'user']:
            return Response({"error": "Invalid object_type"}, status=status.HTTP_400_BAD_REQUEST)
        data = AnalyticsService.get_grouped_analytics(object_type, serializer.validated_data)
        return Response(data, status=status.HTTP_200_OK)


class TopAnalyticsView(BaseAnalyticsView):

    @swagger_auto_schema(request_body=AnalyticsFilterSerializer)
    def post(self, request, top_type):
        serializer = AnalyticsFilterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if top_type not in ['blog', 'country', 'user']:
            return Response({"error": "Invalid top_type"}, status=status.HTTP_400_BAD_REQUEST)

        data = AnalyticsService.get_top_analytics(top_type, serializer.validated_data)
        return Response(data, status=status.HTTP_200_OK)


class PerformanceAnalyticsView(BaseAnalyticsView):

    @swagger_auto_schema(
        operation_description="Granularity is auto-calculated",
        request_body=AnalyticsFilterSerializer
    )
    def post(self, request):
        serializer = AnalyticsFilterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = AnalyticsService.get_performance_analytics(serializer.validated_data)
        return Response(data, status=status.HTTP_200_OK)