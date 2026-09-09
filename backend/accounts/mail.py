from anymail.message import AnymailMessage
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


def send_transactional_mail(
    *,
    subject: str,
    text_template: str,
    html_template: str,
    context: dict,
    to_email: str,
    tags: list[str] | None = None,
) -> None:
    """
    Render Django templates and send via configured EMAIL_BACKEND
    (Resend via Anymail in production; console locally).
    """
    text_body = render_to_string(text_template, context)
    html_body = render_to_string(html_template, context)
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None)
    if not from_email:
        raise RuntimeError("DEFAULT_FROM_EMAIL must be configured to send email.")

    if getattr(settings, "EMAIL_USE_ANYMAIL_TAGS", True):
        msg: EmailMultiAlternatives = AnymailMessage(
            subject=subject,
            body=text_body,
            from_email=from_email,
            to=[to_email],
        )
        if tags:
            msg.tags = tags
    else:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=from_email,
            to=[to_email],
        )
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=False)
