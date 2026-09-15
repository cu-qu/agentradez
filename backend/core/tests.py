from unittest.mock import patch

from django.contrib.staticfiles.finders import find
from django.test import TestCase
from rest_framework.test import APIClient

from config.settings.base import MIDDLEWARE, resolve_redis_url, with_redis_auth


class HealthCheckTests(TestCase):
    def test_health_ok(self):
        resp = APIClient().get("/api/health/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok"})


class OpenApiAndCeleryTests(TestCase):
    def test_schema_and_docs_available(self):
        client = APIClient()
        schema = client.get("/api/schema/")
        self.assertEqual(schema.status_code, 200)
        docs = client.get("/api/docs/")
        self.assertEqual(docs.status_code, 200)
        redoc = client.get("/api/redoc/")
        self.assertEqual(redoc.status_code, 200)

    def test_schema_is_openapi_for_web_clients(self):
        client = APIClient()
        resp = client.get("/api/schema/", HTTP_ORIGIN="http://localhost:3000")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "http://localhost:3000")
        spec = resp.json()
        self.assertTrue(str(spec.get("openapi", "")).startswith("3."))
        paths = spec["paths"]
        for route in (
            "/api/auth/token/",
            "/api/auth/register/",
            "/api/strategies/",
            "/api/strategies/{id}/signals/",
            "/api/investment-tiers/",
            "/api/assignment/",
            "/api/broker-connections/",
            "/api/positions/",
            "/api/trades/",
            "/api/performance/",
            "/api/notifications/",
            "/api/notifications/read-all/",
            "/api/billing/plans/",
            "/api/billing/subscription/",
            "/api/billing/checkout/",
            "/api/admin/billing/grants/",
            "/api/admin/strategies/",
            "/api/admin/strategies/{id}/posts/",
            "/api/admin/strategies/{id}/signals/",
            "/api/admin/strategies/{id}/lookback/",
            "/api/admin/strategies/{id}/events/",
            "/api/admin/strategy-types/",
            "/api/admin/user-groups/",
            "/api/admin/users/",
            "/api/admin/x-sources/",
            "/api/admin/x-parse/",
            "/api/admin/watched-companies/",
            "/api/admin/research-parse/",
            "/api/admin/research-events/",
        ):
            self.assertIn(route, paths)
        self.assertIn("jwtAuth", spec.get("components", {}).get("securitySchemes", {}))

    def test_example_celery_task_is_registered(self):
        from config.celery import app

        app.autodiscover_tasks(force=True)
        self.assertIn("accounts.ping", app.tasks)
        self.assertIn("trading.poll_research_feeds", app.tasks)
        from accounts.tasks import ping

        self.assertEqual(ping.apply().get(), "pong")


class RedisUrlTests(TestCase):
    def test_broker_url_gets_password_injected(self):
        with patch.dict(
            "os.environ",
            {"REDIS_PASSWORD": "secret", "REDIS_USER": "default"},
            clear=False,
        ):
            url = with_redis_auth("redis://redis.railway.internal:6379/0")
        self.assertEqual(url, "redis://default:secret@redis.railway.internal:6379/0")

    def test_resolve_prefers_celery_broker_url(self):
        with patch.dict(
            "os.environ",
            {
                "CELERY_BROKER_URL": "redis://default:from-broker@redis.railway.internal:6379/0",
                "REDIS_URL": "redis://redis:6379/0",
            },
            clear=False,
        ):
            self.assertEqual(
                resolve_redis_url(),
                "redis://default:from-broker@redis.railway.internal:6379/0",
            )


class WhiteNoiseStaticTests(TestCase):
    def test_admin_css_is_on_the_staticfiles_path(self):
        self.assertTrue(find("admin/css/base.css"))

    def test_whitenoise_is_enabled_for_gunicorn(self):
        self.assertEqual(MIDDLEWARE[0], "django.middleware.security.SecurityMiddleware")
        self.assertEqual(MIDDLEWARE[1], "whitenoise.middleware.WhiteNoiseMiddleware")
