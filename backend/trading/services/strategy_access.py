"""Who can see and select a strategy."""

from __future__ import annotations

from django.db.models import Q, QuerySet

from trading.constants import STRATEGY_VISIBILITY_PUBLIC
from trading.models import Strategy


def user_can_access_strategy(user, strategy: Strategy) -> bool:
    if not strategy.is_active:
        return False
    if getattr(user, "is_staff", False):
        return True
    if strategy.visibility == STRATEGY_VISIBILITY_PUBLIC:
        return True
    if strategy.allowed_users.filter(pk=user.pk).exists():
        return True
    return strategy.allowed_groups.filter(is_active=True, members=user).exists()


def strategies_visible_to(user) -> QuerySet[Strategy]:
    qs = Strategy.objects.filter(is_active=True)
    if getattr(user, "is_staff", False):
        return qs
    return qs.filter(
        Q(visibility=STRATEGY_VISIBILITY_PUBLIC)
        | Q(allowed_users=user)
        | Q(allowed_groups__is_active=True, allowed_groups__members=user)
    ).distinct()
