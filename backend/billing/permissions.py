from rest_framework.exceptions import APIException
from rest_framework.permissions import BasePermission

from billing.constants import FEATURE_TRADING
from billing.services.entitlements import user_has_feature


class SubscriptionRequired(APIException):
    status_code = 402
    default_detail = "An active paid subscription is required."
    default_code = "subscription_required"


class HasFeature(BasePermission):
    feature = FEATURE_TRADING
    message = "An active paid subscription is required."

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return False
        if user_has_feature(user, self.feature):
            return True
        raise SubscriptionRequired(
            {
                "detail": self.message,
                "code": "subscription_required",
                "required_feature": self.feature,
            }
        )


class HasTradingAccess(HasFeature):
    feature = FEATURE_TRADING
