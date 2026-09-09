from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User, UserProfile


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = [UserProfileInline]
    list_display = (
        "id",
        "username",
        "email",
        "email_verified",
        "preferred_language",
        "is_staff",
    )
    list_filter = ("email_verified", "is_staff", "is_superuser", "is_deleted")
    readonly_fields = ("email_verification_sent_at",)
    fieldsets = BaseUserAdmin.fieldsets + (
        (
            "Locale & verification",
            {
                "fields": (
                    "preferred_language",
                    "email_verified",
                    "email_verification_sent_at",
                )
            },
        ),
        ("Soft delete", {"fields": ("is_deleted", "deleted_at")}),
    )


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "preferred_language")
