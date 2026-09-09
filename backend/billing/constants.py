FEATURE_TRADING = "trading"

PLAN_FREE = "free"
PLAN_MONTHLY = "monthly"
PLAN_YEARLY = "yearly"

INTERVAL_NONE = "none"
INTERVAL_MONTH = "month"
INTERVAL_YEAR = "year"
INTERVAL_CHOICES = (
    (INTERVAL_NONE, "None"),
    (INTERVAL_MONTH, "Monthly"),
    (INTERVAL_YEAR, "Yearly"),
)

VALUE_BOOLEAN = "boolean"
VALUE_INTEGER = "integer"
VALUE_TYPE_CHOICES = (
    (VALUE_BOOLEAN, "Boolean"),
    (VALUE_INTEGER, "Integer"),
)

SOURCE_FREE = "free"
SOURCE_STRIPE = "stripe"
SOURCE_GRANT = "grant"
SOURCE_CHOICES = (
    (SOURCE_FREE, "Free"),
    (SOURCE_STRIPE, "Stripe"),
    (SOURCE_GRANT, "Complimentary grant"),
)

STATUS_ACTIVE = "active"
STATUS_TRIALING = "trialing"
STATUS_PAST_DUE = "past_due"
STATUS_CANCELED = "canceled"
STATUS_UNPAID = "unpaid"
STATUS_INCOMPLETE = "incomplete"
STATUS_INCOMPLETE_EXPIRED = "incomplete_expired"
STATUS_PAUSED = "paused"
STATUS_EXPIRED = "expired"

SUBSCRIPTION_STATUS_CHOICES = (
    (STATUS_ACTIVE, "Active"),
    (STATUS_TRIALING, "Trialing"),
    (STATUS_PAST_DUE, "Past due"),
    (STATUS_CANCELED, "Canceled"),
    (STATUS_UNPAID, "Unpaid"),
    (STATUS_INCOMPLETE, "Incomplete"),
    (STATUS_INCOMPLETE_EXPIRED, "Incomplete expired"),
    (STATUS_PAUSED, "Paused"),
    (STATUS_EXPIRED, "Expired"),
)

# Stripe statuses that still unlock paid features.
STRIPE_LIVE_STATUSES = frozenset(
    {STATUS_ACTIVE, STATUS_TRIALING, STATUS_PAST_DUE}
)

DEFAULT_FEATURES = {
    PLAN_FREE: {FEATURE_TRADING: False},
    PLAN_MONTHLY: {FEATURE_TRADING: True},
    PLAN_YEARLY: {FEATURE_TRADING: True},
}
