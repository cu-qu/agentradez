from drf_spectacular.renderers import OpenApiJsonRenderer, OpenApiYamlRenderer
from drf_spectacular.utils import extend_schema
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthCheckSerializer(serializers.Serializer):
    status = serializers.CharField()


@extend_schema(
    tags=["Reference"],
    summary="Health check",
    description="Lightweight service health check for monitoring.",
    responses={200: HealthCheckSerializer},
)
class HealthCheckView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({"status": "ok"}, status=status.HTTP_200_OK)


class PublicSchemaView(SpectacularAPIView):
    """OpenAPI 3 document. JSON is the default so web clients can `fetch` it."""

    permission_classes = [AllowAny]
    authentication_classes = []
    renderer_classes = [OpenApiJsonRenderer, OpenApiYamlRenderer]


class PublicSwaggerView(SpectacularSwaggerView):
    permission_classes = [AllowAny]
    authentication_classes = []


class PublicRedocView(SpectacularRedocView):
    permission_classes = [AllowAny]
    authentication_classes = []
