from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from billing.services.entitlements import entitlement_payload

from .models import UserProfile

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ("username", "email", "password")

    def create(self, validated_data):
        return User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password"],
        )


class UserSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)
    preferred_language = serializers.CharField(required=False)
    subscription = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "email_verified",
            "is_staff",
            "preferred_language",
            "date_joined",
            "subscription",
        )
        read_only_fields = (
            "id",
            "username",
            "email",
            "email_verified",
            "is_staff",
            "date_joined",
            "subscription",
        )

    def get_subscription(self, obj) -> dict:
        return entitlement_payload(obj)

    def update(self, instance, validated_data):
        pref_lang = validated_data.pop("preferred_language", None)
        if pref_lang is not None:
            instance.preferred_language = pref_lang
            instance.save(update_fields=["preferred_language"])
            if hasattr(instance, "profile") and instance.profile:
                instance.profile.preferred_language = pref_lang
                instance.profile.save(update_fields=["preferred_language"])
        return instance


class UserProfileSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)

    class Meta:
        model = UserProfile
        fields = (
            "id",
            "preferred_language",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_new_password(self, value):
        validate_password(value)
        return value
