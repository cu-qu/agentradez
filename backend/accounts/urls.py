from django.urls import path

from .views import (
    MeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    ProfileView,
    RegisterView,
    ResendVerificationEmailView,
    TokenObtainPairViewCustom,
    TokenRefreshViewCustom,
    VerifyEmailView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="auth-register"),
    path("verify-email/", VerifyEmailView.as_view(), name="auth-verify-email"),
    path(
        "verify-email/resend/",
        ResendVerificationEmailView.as_view(),
        name="auth-verify-email-resend",
    ),
    path(
        "password-reset/",
        PasswordResetRequestView.as_view(),
        name="auth-password-reset-request",
    ),
    path(
        "password-reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="auth-password-reset-confirm",
    ),
    path("token/", TokenObtainPairViewCustom.as_view(), name="token_obtain_pair"),
    path("token/refresh/", TokenRefreshViewCustom.as_view(), name="token_refresh"),
    path("me/", MeView.as_view(), name="me"),
    path("profile/", ProfileView.as_view(), name="profile"),
]
