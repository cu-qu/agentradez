from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from django.urls import include, path

from core.views import HealthCheckView, PublicRedocView, PublicSchemaView, PublicSwaggerView

admin.site.site_header = "Agentradez"
admin.site.site_title = "Agentradez"
admin.site.index_title = "Administration"


def root(request):
    return JsonResponse(
        {
            "name": "Agentradez API",
            "docs": "/api/docs/",
            "redoc": "/api/redoc/",
            "schema": "/api/schema/",
            "health": "/api/health/",
        }
    )


urlpatterns = [
    path("", root),
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/", include("billing.urls")),
    path("api/", include("trading.urls")),
    path("api/health/", HealthCheckView.as_view(), name="health-check"),
    path("api/schema/", PublicSchemaView.as_view(), name="schema"),
    path("api/docs/", PublicSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", PublicRedocView.as_view(url_name="schema"), name="redoc"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
