from .base import *  # noqa: F401,F403

DEBUG = True

LOGGING = {
    **LOGGING,
    "loggers": {
        **LOGGING["loggers"],
        "django.server": {
            **LOGGING["loggers"]["django.server"],
            "level": "INFO",
        },
    },
}

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "*"]

CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173",
)
CORS_ALLOW_ALL_ORIGINS = os.environ.get("CORS_ALLOW_ALL_ORIGINS", "false").lower() in (
    "true",
    "1",
    "yes",
)

STORAGES = {
    **STORAGES,
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        "OPTIONS": {"location": str(STATIC_ROOT)},
    },
}
