import logging

from rest_framework.views import exception_handler

logger = logging.getLogger("django.request")


def log_and_exception_handler(exc, context):
    """
    DRF exception handler wrapper that logs full tracebacks to stdout/stderr
    so platforms like Railway show the real cause of 500s.
    """
    request = context.get("request")
    path = getattr(request, "path", None)
    method = getattr(request, "method", None)

    logger.exception("Unhandled DRF exception", extra={"path": path, "method": method})

    return exception_handler(exc, context)
