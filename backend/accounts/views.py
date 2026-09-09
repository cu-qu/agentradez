from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .models import UserProfile
from .serializers import (
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    UserProfileSerializer,
    UserSerializer,
)
from .services import send_password_reset_email, send_verification_email

User = get_user_model()


@extend_schema(
    tags=["Auth"],
    summary="Register",
    description=(
        "Creates the account and returns JWT tokens. Sends a **verification email** "
        "(best-effort; registration still succeeds if sending fails). "
        "Confirm with `GET /api/auth/verify-email/?token=`."
    ),
)
class RegisterView(generics.CreateAPIView):
    permission_classes = [AllowAny]
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        send_verification_email(user)
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "user": UserSerializer(user).data,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["Auth"], summary="Obtain JWT token pair")
class TokenObtainPairViewCustom(TokenObtainPairView):
    permission_classes = [AllowAny]


@extend_schema(tags=["Auth"], summary="Refresh JWT access token")
class TokenRefreshViewCustom(TokenRefreshView):
    pass


@extend_schema(tags=["Auth"], summary="Current user (me)")
class MeView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


@extend_schema(
    tags=["Profile"],
    summary="Get or update my profile",
    description="Returns or updates profile fields such as preferred_language.",
)
class ProfileView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserProfileSerializer

    def get_object(self):
        profile, _ = UserProfile.objects.get_or_create(
            user=self.request.user,
            defaults={"preferred_language": self.request.user.preferred_language},
        )
        return profile


@extend_schema(
    tags=["Auth"],
    summary="Verify email",
    description="Confirm the account email using the token from the verification link.",
    parameters=[
        OpenApiParameter(
            name="token",
            type=str,
            location=OpenApiParameter.QUERY,
            required=True,
            description="Verification token from the email link.",
        ),
    ],
)
class VerifyEmailView(APIView):
    permission_classes = [AllowAny]
    serializer_class = None

    def get(self, request):
        token = (request.query_params.get("token") or "").strip()
        if not token:
            return Response(
                {"detail": "Missing token.", "token": ["This field is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        updated = User.objects.filter(
            email_verification_token=token, email_verified=False
        ).update(email_verified=True, email_verification_token="")
        if updated:
            return Response({"detail": "Email verified.", "email_verified": True})
        return Response(
            {"detail": "Invalid or expired verification token."},
            status=status.HTTP_400_BAD_REQUEST,
        )


@extend_schema(
    tags=["Auth"],
    summary="Resend verification email",
    description="Sends a new verification email to the authenticated user's address.",
)
class ResendVerificationEmailView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = None

    def post(self, request):
        user = request.user
        if user.email_verified:
            return Response(
                {"detail": "Email is already verified."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        send_verification_email(user)
        return Response(
            {"detail": "If your account needs verification, a new email has been sent."},
            status=status.HTTP_200_OK,
        )


@extend_schema(
    tags=["Auth"],
    summary="Request password reset",
    description=(
        "Sends a password-reset email if an account exists for the given address. "
        "Always returns the same success message (no email enumeration)."
    ),
    request=PasswordResetRequestSerializer,
)
class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    serializer_class = PasswordResetRequestSerializer

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip()
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if user is not None:
            send_password_reset_email(user)
        return Response(
            {
                "detail": "If an account exists for that email, you will receive reset instructions.",
            },
            status=status.HTTP_200_OK,
        )


@extend_schema(
    tags=["Auth"],
    summary="Confirm password reset",
    description=(
        "Sets a new password using **uid** and **token** from the reset email link "
        "(same encoding as Django's PasswordResetTokenGenerator)."
    ),
    request=PasswordResetConfirmSerializer,
)
class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    serializer_class = PasswordResetConfirmSerializer

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        uid_b64 = serializer.validated_data["uid"]
        token = serializer.validated_data["token"]
        new_password = serializer.validated_data["new_password"]
        try:
            uid = force_str(urlsafe_base64_decode(uid_b64))
            user = User.objects.get(pk=uid, is_active=True)
        except (User.DoesNotExist, ValueError, TypeError, OverflowError):
            return Response(
                {"detail": "Invalid or expired reset link."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not default_token_generator.check_token(user, token):
            return Response(
                {"detail": "Invalid or expired reset link."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.set_password(new_password)
        user.save(update_fields=["password"])
        return Response(
            {"detail": "Password has been reset. You can sign in with your new password."},
            status=status.HTTP_200_OK,
        )
