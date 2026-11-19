from decimal import Decimal

MARKET_OPTIONS = "options"
MARKET_EQUITY = "equity"
MARKET_KALSHI = "kalshi"
MARKET_COINBASE = "coinbase"
MARKET_CHOICES = (
    (MARKET_OPTIONS, "Options"),
    (MARKET_EQUITY, "Equity"),
    (MARKET_KALSHI, "Kalshi"),
    (MARKET_COINBASE, "Coinbase"),
)

SIDE_BUY = "buy"
SIDE_SELL = "sell"
SIDE_CHOICES = (
    (SIDE_BUY, "Buy"),
    (SIDE_SELL, "Sell"),
)

SIGNAL_PENDING = "pending"
SIGNAL_WORKING_ENTRY = "working_entry"
SIGNAL_OPEN = "open"
SIGNAL_CLOSED = "closed"
SIGNAL_CANCELLED = "cancelled"
SIGNAL_EXPIRED = "expired"
SIGNAL_REJECTED = "rejected"
SIGNAL_STATUS_CHOICES = (
    (SIGNAL_PENDING, "Pending"),
    (SIGNAL_WORKING_ENTRY, "Working entry"),
    (SIGNAL_OPEN, "Open"),
    (SIGNAL_CLOSED, "Closed"),
    (SIGNAL_CANCELLED, "Cancelled"),
    (SIGNAL_EXPIRED, "Expired"),
    (SIGNAL_REJECTED, "Rejected"),
)

POSITION_OPEN = "open"
POSITION_CLOSED = "closed"

ORDER_ENTRY = "entry"
ORDER_EXIT = "exit"
ORDER_WORKING = "working"
ORDER_FILLED = "filled"
ORDER_CANCELLED = "cancelled"

DEFAULT_MAX_OPEN_POSITIONS = 5
DEFAULT_MAX_EXPOSURE_USD = Decimal("25000")
DEFAULT_MAX_LOSS_PER_POSITION_USD = Decimal("500")
