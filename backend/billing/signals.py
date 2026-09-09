from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts.models import User
from billing.services.entitlements import claim_grants_for_user


@receiver(post_save, sender=User)
def apply_pending_subscription_grants(sender, instance, created, **kwargs):
    if created:
        claim_grants_for_user(instance)
