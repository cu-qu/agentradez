import os
import sys
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")


def env_list(name, default=""):
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def railway_allowed_hosts():
    """ALLOWED_HOSTS plus hosts Railway uses for routing and health checks."""
    hosts = env_list("ALLOWED_HOSTS")
    for host in (
        os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip(),
        os.environ.get("RAILWAY_PRIVATE_DOMAIN", "").strip(),
        "healthcheck.railway.app",
        ".railway.internal",
        ".up.railway.app",
    ):
        if host and host not in hosts:
            hosts.append(host)
    return hosts


def is_loopback_url(url):
    host = (urlsplit(url).hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def resolve_public_api_url():
    """Public API origin for OAuth callbacks and OpenAPI servers.

    Local defaults to localhost. On Railway, skip a loopback override and use
    RAILWAY_PUBLIC_DOMAIN so OAuth does not redirect to the developer's machine.
    """
    configured = os.environ.get("PUBLIC_API_URL", "").strip().rstrip("/")
    railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
    if configured and not is_loopback_url(configured):
        return configured
    if railway_domain:
        return f"https://{railway_domain}"
    return configured or "http://localhost:8001"


def _env_first(*names):
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def with_redis_auth(url=""):
    """Ensure a Redis URL includes ACL credentials (Railway requires AUTH)."""
    url = (url or "").strip()
    password = _env_first("REDIS_PASSWORD", "REDISPASSWORD")
    user = _env_first("REDIS_USER", "REDISUSER") or "default"
    if not url:
        host = _env_first("REDIS_HOST", "REDISHOST")
        port = _env_first("REDIS_PORT", "REDISPORT") or "6379"
        if not host:
            return ""
        url = f"redis://{host}:{port}/0"
    parsed = urlsplit(url)
    if parsed.password:
        return url
    if not password:
        return url
    host = parsed.hostname
    if not host:
        return url
    username = parsed.username or user
    netloc = f"{quote(username, safe='')}:{quote(password, safe='')}@{host}"
    if parsed.port:
        netloc += f":{parsed.port}"
    return urlunsplit(
        (parsed.scheme or "redis", netloc, parsed.path or "/0", parsed.query, parsed.fragment)
    )


def resolve_redis_url():
    """Prefer CELERY_BROKER_URL, then REDIS_URL; inject REDIS_PASSWORD if needed."""
    candidates = [
        _env_first("CELERY_BROKER_URL"),
        _env_first("REDIS_URL"),
        _env_first("CELERY_RESULT_BACKEND"),
    ]
    for candidate in candidates:
        if candidate and urlsplit(candidate).password:
            return candidate
    for candidate in candidates:
        if candidate:
            return with_redis_auth(candidate)
    return with_redis_auth("")


SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

DEBUG = os.environ.get("DEBUG", "True").lower() in ("true", "1", "yes")

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "whitenoise.runserver_nostatic",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    "anymail",
    "core",
    "accounts",
    "billing",
    "trading",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DJANGO_DB_NAME", "agentradez"),
        "USER": os.environ.get("DJANGO_DB_USER", "postgres"),
        "PASSWORD": os.environ.get("DJANGO_DB_PASSWORD", ""),
        "HOST": os.environ.get("DJANGO_DB_HOST", "localhost"),
        "PORT": os.environ.get("DJANGO_DB_PORT", "5432"),
        "ATOMIC_REQUESTS": True,
    }
}

_db_url = os.environ.get("DATABASE_URL", "").strip()
if _db_url:
    import dj_database_url

    DATABASES["default"] = dj_database_url.parse(_db_url, conn_max_age=600)
    DATABASES["default"]["ATOMIC_REQUESTS"] = True

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en"
LANGUAGES = [
    ("en", "English"),
    ("es", "Spanish"),
]
LOCALE_PATHS = [BASE_DIR / "locale"]
USE_I18N = True
USE_L10N = True
USE_TZ = True
TIME_ZONE = "UTC"

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "mediafiles"

# WhiteNoise serves /static/ (Django admin CSS, etc.) from gunicorn on Railway.
# USE_FINDERS / AUTOREFRESH default to DEBUG, so runserver does not need
# collectstatic. Production uses the files collectstatic writes to STATIC_ROOT.
WHITENOISE_MANIFEST_STRICT = False

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {"location": str(MEDIA_ROOT)},
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

# Optional S3/R2 media storage. Static files always use WhiteNoise so the API
# boots on Railway without an object-storage bucket.
_r2_access_key = os.environ.get("R2_ACCESS_KEY_ID", "").strip()
_r2_secret_key = os.environ.get("R2_SECRET_ACCESS_KEY", "").strip()
_r2_account_id = os.environ.get("R2_ACCOUNT_ID", "").strip()
_r2_bucket = os.environ.get("R2_BUCKET_NAME", "").strip()
_r2_custom_domain = os.environ.get("R2_CUSTOM_DOMAIN", "").strip()
_r2_configured = all([_r2_access_key, _r2_secret_key, _r2_account_id, _r2_bucket])

if _r2_configured:
    _r2_storage_options = {
        "access_key": _r2_access_key,
        "secret_key": _r2_secret_key,
        "bucket_name": _r2_bucket,
        "endpoint_url": f"https://{_r2_account_id}.r2.cloudflarestorage.com",
        "region_name": "auto",
        "signature_version": "s3v4",
        "default_acl": "public-read",
        "object_parameters": {"CacheControl": "max-age=86400"},
        "querystring_auth": False,
    }
    if _r2_custom_domain:
        _r2_storage_options["custom_domain"] = _r2_custom_domain
        MEDIA_URL = f"https://{_r2_custom_domain}/"
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        "OPTIONS": _r2_storage_options,
    }

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
    },
    "EXCEPTION_HANDLER": "core.exceptions.log_and_exception_handler",
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler", "stream": sys.stdout},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
        "django.server": {"handlers": ["console"], "level": "ERROR", "propagate": False},
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.environ.get("JWT_ACCESS_LIFETIME_MINUTES", 60))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(os.environ.get("JWT_REFRESH_DAYS", 7))),
}

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")
PUBLIC_API_URL = resolve_public_api_url()

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "").strip()
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "").strip()
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
STRIPE_PRICE_MONTHLY = os.environ.get("STRIPE_PRICE_MONTHLY", "").strip()
STRIPE_PRICE_YEARLY = os.environ.get("STRIPE_PRICE_YEARLY", "").strip()
STRIPE_SUCCESS_URL = os.environ.get(
    "STRIPE_SUCCESS_URL",
    f"{FRONTEND_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
).strip()
STRIPE_CANCEL_URL = os.environ.get(
    "STRIPE_CANCEL_URL",
    f"{FRONTEND_URL}/billing/cancel",
).strip()
STRIPE_PORTAL_RETURN_URL = os.environ.get(
    "STRIPE_PORTAL_RETURN_URL",
    f"{FRONTEND_URL}/billing",
).strip()
ROBINHOOD_MCP_URL = os.environ.get(
    "ROBINHOOD_MCP_URL", "https://agent.robinhood.com/mcp/trading"
).strip()
ROBINHOOD_CLIENT_ID = os.environ.get("ROBINHOOD_CLIENT_ID", "").strip()
ROBINHOOD_OAUTH_REDIRECT_URI = os.environ.get("ROBINHOOD_OAUTH_REDIRECT_URI", "").strip()

_resend_key = os.environ.get("RESEND_API_KEY", "").strip()
if os.environ.get("EMAIL_BACKEND", "").strip():
    EMAIL_BACKEND = os.environ["EMAIL_BACKEND"].strip()
elif _resend_key:
    EMAIL_BACKEND = "anymail.backends.resend.EmailBackend"
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

ANYMAIL = {
    "RESEND_API_KEY": _resend_key,
}

DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL",
    "Agentradez <noreply@example.com>",
).strip()
SERVER_EMAIL = os.environ.get("SERVER_EMAIL", DEFAULT_FROM_EMAIL)

EMAIL_USE_ANYMAIL_TAGS = os.environ.get("EMAIL_USE_ANYMAIL_TAGS", "True").lower() in (
    "true",
    "1",
    "yes",
)

EMAIL_VERIFICATION_FRONTEND_PATH = os.environ.get(
    "EMAIL_VERIFICATION_FRONTEND_PATH", "/verify-email"
)
EMAIL_VERIFICATION_SUBJECT = os.environ.get(
    "EMAIL_VERIFICATION_SUBJECT", "Agentradez: Confirm your email address"
)
PASSWORD_RESET_FRONTEND_PATH = os.environ.get(
    "PASSWORD_RESET_FRONTEND_PATH", "/reset-password"
)
EMAIL_PASSWORD_RESET_SUBJECT = os.environ.get(
    "EMAIL_PASSWORD_RESET_SUBJECT", "Reset your password"
)

CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173",
)
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-language",
    "authorization",
    "content-type",
    "origin",
    "x-requested-with",
]
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "http://localhost:8000")

CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
CELERY_TASK_DEFAULT_QUEUE = os.environ.get("CELERY_TASK_DEFAULT_QUEUE", "celery")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

SPECTACULAR_SETTINGS = {
    "TITLE": "Agentradez API",
    "DESCRIPTION": """
REST API for **Agentradez**.

Users connect a brokerage account, pick one Strategy and one Investment Tier for a single brokerage account, then the platform runs automatically.

- **Auth** — Register (sends a verification email via **django-anymail** / **Resend** when `RESEND_API_KEY` is set; otherwise the console backend), login (JWT), refresh token, current user (`GET/PATCH /api/auth/me/`, includes `subscription`), `GET /api/auth/verify-email/?token=`, `POST /api/auth/verify-email/resend/`, `POST /api/auth/password-reset/`, `POST /api/auth/password-reset/confirm/`
- **Profile** — `GET/PATCH /api/auth/profile/` (preferred language)
- **Billing** — Plans (`GET /api/billing/plans/`), current entitlement (`GET /api/billing/subscription/`), Stripe Checkout (`POST /api/billing/checkout/`), Customer Portal (`POST /api/billing/portal/`), Stripe webhook (`POST /api/billing/webhooks/stripe/`). Trading APIs require the `trading` feature (monthly, yearly, or a complimentary grant). Staff can grant access with `POST /api/admin/billing/grants/` or `python manage.py grant_subscription friend@example.com --plan yearly`.
- **Broker** — Connect Alpaca with API keys (`POST /api/broker-connections/`) or Robinhood via OAuth (`POST /api/broker-connections/robinhood/oauth/start/`, paste the localhost callback URL to `POST /api/broker-connections/robinhood/oauth/complete/`, optional GET callback `GET /api/broker-connections/robinhood/oauth/callback/`). List/select Agentic accounts (`GET /api/broker-connections/{id}/accounts/`, `GET /api/broker-connections/{id}/accounts/{account_number}/`, `POST /api/broker-connections/{id}/select-account/`). List Robinhood agent MCP tools (`GET /api/broker-connections/{id}/agent-tools/`). Disconnect (`POST /api/broker-connections/{id}/disconnect/`).
- **Strategies** — List strategies this account can pick (`GET /api/strategies/`; public plus any restricted grants). Parsed signals for a strategy (`GET /api/strategies/{id}/signals/`)
- **Tiers** — List investment tiers (`GET /api/investment-tiers/`)
- **Assignment** — Select Strategy + Investment Tier for one brokerage account (`GET/PUT /api/assignment/`; `broker_account_id` binds it to a Robinhood Agentic account)
- **Positions** — Open positions (`GET /api/positions/`; optional `broker_account_id`)
- **Trades** — Trade history including pending working orders and cancelled unfilled orders (`GET /api/trades/`, `GET /api/trades/{id}/`; optional `broker_account_id`)
- **Decisions** — Paper trail of how the assigned strategy processed signals and exits (`GET /api/decisions/`, `GET /api/decisions/{id}/`; optional `action`, `outcome`, `ticker`, `broker_account_id`)
- **Performance** — Personal metrics including lifetime P&L (`GET /api/performance/`)
- **Notifications** — Entry / skip / take-profit / exit notices, each linked to a decision when available (`GET /api/notifications/`, `POST /api/notifications/{id}/read/`, `POST /api/notifications/read-all/`; optional `broker_account_id`)
- **Admin** — Staff JWT (`is_staff`): create/configure strategies (including Copy Trade `signal_source` plus nested X watcher with `poll_interval_seconds`, Research / Breakthrough watchlists, and visibility / user-group access), list tweets/signals/research events per strategy, look back N days on an X copy-trade account (`POST /api/admin/strategies/{id}/lookback/`), ingest a research headline (`POST /api/admin/strategies/{id}/research-ingest/`), user groups, tiers, users/assignments, Copy Trade ingest, trades / positions, platform P&L (`/api/admin/...`). Built for a frontend admin page; Django admin is not required.
- **Reference** — Service health check: `GET /api/health/`
""",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
    "SERVE_AUTHENTICATION": None,
    "SCHEMA_PATH_PREFIX": r"/api",
    "COMPONENT_SPLIT_REQUEST": True,
    "SERVERS": [
        {
            "url": PUBLIC_API_URL,
            "description": "API",
        },
    ],
    "SWAGGER_UI_SETTINGS": {
        "persistAuthorization": True,
        "displayRequestDuration": True,
        "filter": True,
        "tryItOutEnabled": True,
    },
    "TAGS": [
        {"name": "Auth", "description": "Registration, JWT token, refresh, current user, email verify, password reset"},
        {"name": "Profile", "description": "User profile (preferred language)"},
        {"name": "Billing", "description": "Free / monthly / yearly plans, Stripe checkout and portal, current entitlements"},
        {"name": "Broker", "description": "Connect Alpaca with keys or Robinhood with OAuth (start + paste complete), list Agentic accounts, account detail, list agent tools, disconnect"},
        {"name": "Strategies", "description": "Available automated strategies and their parsed signals"},
        {
            "name": "Tiers",
            "description": (
                "Investment tier rule sets. Position size uses each tier's risk "
                "percent of equity, with a 1-contract floor when that would round "
                "to zero and the option premium is affordable."
            ),
        },
        {"name": "Assignment", "description": "User strategy and tier selection, optionally bound to one brokerage account"},
        {"name": "Positions", "description": "Currently open positions"},
        {"name": "Trades", "description": "Trade history, pending working orders, unfilled/cancelled orders, partial closes, and realized P&L"},
        {"name": "Decisions", "description": "Paper trail of strategy signal evaluations, skips, entries, and exits"},
        {"name": "Performance", "description": "Personal daily, weekly, and lifetime P&L"},
        {"name": "Notifications", "description": "Entry, skip, take-profit, and exit notifications linked to decisions"},
        {"name": "Admin", "description": "Staff frontend: strategies, visibility/groups, X watchers, research watchlists, lookback parse, tiers, users, billing grants/plans/features, signals, trades, platform stats"},
        {"name": "Reference", "description": "Service health check"},
    ],
}

SUPPORTED_LANGUAGES = ["en", "es"]

# Copy-trade X (Twitter) watcher. Bearer token is required to poll; ingest/parse
# admin endpoints work without it. Prefer the Pullcalls app credentials.
# How often to pull is per XAccountSource.poll_interval_seconds (default 60).
X_PULLCALLS_API_CONSUMER_KEY = os.environ.get("X_PULLCALLS_API_CONSUMER_KEY", "").strip()
X_PULLCALLS_API_SECRET = os.environ.get("X_PULLCALLS_API_SECRET", "").strip()
X_PULLCALLS_BEARER_TOKEN = unquote(os.environ.get("X_PULLCALLS_BEARER_TOKEN", "").strip())
X_BEARER_TOKEN = os.environ.get("X_BEARER_TOKEN", "").strip() or X_PULLCALLS_BEARER_TOKEN
X_API_BASE_URL = os.environ.get("X_API_BASE_URL", "https://api.x.com/2").strip()
X_COPY_TRADE_HANDLE = os.environ.get("X_COPY_TRADE_HANDLE", "").strip()

# Research / Breakthrough polls Google News RSS per watched company. No API key.
# How often to pull is per ResearchWatchConfig.poll_interval_seconds (default 60).

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": CELERY_BROKER_URL,
    }
}