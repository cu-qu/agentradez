from decimal import Decimal
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

CONTRACT_MULTIPLIER = Decimal("100")

BROKER_ALPACA = "alpaca"
BROKER_ROBINHOOD = "robinhood"
BROKER_CHOICES = (
    (BROKER_ALPACA, "Alpaca"),
    (BROKER_ROBINHOOD, "Robinhood"),
)

OPTION_CALL = "call"
OPTION_PUT = "put"
OPTION_TYPE_CHOICES = (
    (OPTION_CALL, "Call"),
    (OPTION_PUT, "Put"),
)

PERIOD_DAILY = "daily"
PERIOD_WEEKLY = "weekly"
PERIOD_LIFETIME = "lifetime"
PERIOD_TYPE_CHOICES = (
    (PERIOD_DAILY, "Daily"),
    (PERIOD_WEEKLY, "Weekly"),
    (PERIOD_LIFETIME, "Lifetime"),
)

STRATEGY_COPY_TRADE = "copy-trade"
STRATEGY_RESEARCH_BREAKTHROUGH = "research-breakthrough"
STRATEGY_TYPE_COPY_TRADE = "copy_trade"
STRATEGY_TYPE_RESEARCH_BREAKTHROUGH = "research_breakthrough"
STRATEGY_TYPE_CHOICES = (
    (STRATEGY_TYPE_COPY_TRADE, "Copy Trade"),
    (STRATEGY_TYPE_RESEARCH_BREAKTHROUGH, "Research / Breakthrough"),
)
X_POLL_INTERVAL_SECONDS_MIN = 15
X_POLL_INTERVAL_SECONDS_DEFAULT = 60
X_POLL_INTERVAL_SECONDS_MAX = 86_400
RESEARCH_POLL_INTERVAL_SECONDS_MIN = 15
RESEARCH_POLL_INTERVAL_SECONDS_DEFAULT = 60
RESEARCH_POLL_INTERVAL_SECONDS_MAX = 86_400
RESEARCH_MIN_CATALYST_SCORE_DEFAULT = 70
RESEARCH_OTM_PCT_DEFAULT = "5.00"
RESEARCH_MIN_DTE_DEFAULT = 14
RESEARCH_MAX_DTE_DEFAULT = 45
RESEARCH_SIGNAL_COOLDOWN_HOURS_DEFAULT = 6

STRATEGY_VISIBILITY_PUBLIC = "public"
STRATEGY_VISIBILITY_RESTRICTED = "restricted"
STRATEGY_VISIBILITY_CHOICES = (
    (STRATEGY_VISIBILITY_PUBLIC, "Public"),
    (STRATEGY_VISIBILITY_RESTRICTED, "Restricted"),
)

SOURCE_X = "x"
SOURCE_CHAT_GROUP = "chat_group"
SOURCE_RESEARCH = "research"
SOURCE_GOOGLE_NEWS = "google_news"
SOURCE_RSS = "rss"
SOURCE_MANUAL = "manual"
SIGNAL_SOURCE_X = SOURCE_X
SIGNAL_SOURCE_CHAT_GROUP = SOURCE_CHAT_GROUP
COPY_TRADE_SIGNAL_SOURCE_CHOICES = (
    (SIGNAL_SOURCE_X, "X"),
    (SIGNAL_SOURCE_CHAT_GROUP, "Chat group"),
)
COPY_TRADE_SIGNAL_SOURCE_CATALOG = [
    {
        "value": SIGNAL_SOURCE_X,
        "label": "X",
        "description": "Pull option trades posted by a watched X account.",
        "config_fields": ["x_source"],
        "available": True,
    },
    {
        "value": SIGNAL_SOURCE_CHAT_GROUP,
        "label": "Chat group",
        "description": "Pull option trades from a chat group. Coming soon.",
        "config_fields": [],
        "available": False,
    },
]

PARSE_PENDING = "pending"
PARSE_PARSED = "parsed"
PARSE_NO_TRADE = "no_trade"
PARSE_SKIPPED = "skipped"
PARSE_ERROR = "error"
PARSE_STATUS_CHOICES = (
    (PARSE_PENDING, "Pending"),
    (PARSE_PARSED, "Parsed"),
    (PARSE_NO_TRADE, "No trade"),
    (PARSE_SKIPPED, "Skipped"),
    (PARSE_ERROR, "Error"),
)

RESEARCH_PENDING = "pending"
RESEARCH_CATALYST = "catalyst"
RESEARCH_NOISE = "noise"
RESEARCH_SKIPPED = "skipped"
RESEARCH_ERROR = "error"
RESEARCH_STATUS_CHOICES = (
    (RESEARCH_PENDING, "Pending"),
    (RESEARCH_CATALYST, "Catalyst"),
    (RESEARCH_NOISE, "Noise"),
    (RESEARCH_SKIPPED, "Skipped"),
    (RESEARCH_ERROR, "Error"),
)

EVENT_CLINICAL = "clinical_result"
EVENT_FDA = "fda_decision"
EVENT_BREAKTHROUGH = "breakthrough"
EVENT_PARTNERSHIP = "partnership"
EVENT_ACQUISITION = "acquisition"
EVENT_PRODUCT = "product_launch"
EVENT_CONTRACT = "contract_win"
EVENT_EARNINGS = "earnings"
EVENT_OTHER = "other"
EVENT_TYPE_CHOICES = (
    (EVENT_CLINICAL, "Clinical / trial result"),
    (EVENT_FDA, "Regulatory decision"),
    (EVENT_BREAKTHROUGH, "Research breakthrough"),
    (EVENT_PARTNERSHIP, "Partnership / license"),
    (EVENT_ACQUISITION, "Acquisition / deal"),
    (EVENT_PRODUCT, "Product launch"),
    (EVENT_CONTRACT, "Contract / award"),
    (EVENT_EARNINGS, "Earnings / guidance"),
    (EVENT_OTHER, "Other"),
)
EVENT_TYPE_VALUES = [value for value, _label in EVENT_TYPE_CHOICES if value != EVENT_OTHER]

EVENT_NEWS_KEYWORDS = {
    EVENT_CLINICAL: ["trial", "phase 3", "phase III", "endpoint", "study"],
    EVENT_FDA: ["FDA", "EMA", "FCC", "approval", "regulator"],
    EVENT_BREAKTHROUGH: ["breakthrough", "discovery", "research"],
    EVENT_PARTNERSHIP: ["partnership", "collaboration", "licensing"],
    EVENT_ACQUISITION: ["acquisition", "acquire", "merger"],
    EVENT_PRODUCT: ["launch", "unveils", "release"],
    EVENT_CONTRACT: ["contract", "awarded", "selected"],
    EVENT_EARNINGS: ["earnings", "guidance"],
}

GENERIC_NEWS_KEYWORDS = [
    "announces",
    "press release",
    "breakthrough",
    "approval",
    "acquisition",
    "partnership",
    "launch",
]


def news_keywords_for_event_types(event_types: list | None = None) -> list[str]:
    selected = [str(item).strip() for item in (event_types or []) if str(item).strip()]
    if not selected:
        return list(GENERIC_NEWS_KEYWORDS)
    seen: list[str] = []
    for event_type in selected:
        for word in EVENT_NEWS_KEYWORDS.get(event_type, []):
            if word not in seen:
                seen.append(word)
    return seen or list(GENERIC_NEWS_KEYWORDS)


RESEARCH_STRATEGY_PRESETS = [
    {
        "id": "any",
        "label": "Any sector",
        "description": "Trade confirmed catalysts across whatever companies you add.",
        "sectors": [],
        "enabled_event_types": [],
        "news_keywords": list(GENERIC_NEWS_KEYWORDS),
    },
    {
        "id": "healthcare",
        "label": "Healthcare",
        "description": "Trial results, regulatory decisions, vaccines/therapies, and deals.",
        "sectors": ["healthcare", "biotech", "pharma"],
        "enabled_event_types": [
            EVENT_CLINICAL,
            EVENT_FDA,
            EVENT_BREAKTHROUGH,
            EVENT_PARTNERSHIP,
            EVENT_ACQUISITION,
        ],
        "news_keywords": news_keywords_for_event_types(
            [EVENT_CLINICAL, EVENT_FDA, EVENT_BREAKTHROUGH, EVENT_PARTNERSHIP, EVENT_ACQUISITION]
        ),
    },
    {
        "id": "technology",
        "label": "Technology",
        "description": "Product launches, research breakthroughs, partnerships, and M&A.",
        "sectors": ["tech", "software", "semiconductor"],
        "enabled_event_types": [
            EVENT_BREAKTHROUGH,
            EVENT_PRODUCT,
            EVENT_PARTNERSHIP,
            EVENT_ACQUISITION,
            EVENT_CONTRACT,
        ],
        "news_keywords": news_keywords_for_event_types(
            [EVENT_BREAKTHROUGH, EVENT_PRODUCT, EVENT_PARTNERSHIP, EVENT_ACQUISITION, EVENT_CONTRACT]
        ),
    },
    {
        "id": "deals",
        "label": "Deals only",
        "description": "Announced acquisitions, partnerships, and major contract wins.",
        "sectors": [],
        "enabled_event_types": [EVENT_ACQUISITION, EVENT_PARTNERSHIP, EVENT_CONTRACT],
        "news_keywords": news_keywords_for_event_types(
            [EVENT_ACQUISITION, EVENT_PARTNERSHIP, EVENT_CONTRACT]
        ),
    },
]

STRATEGY_TYPE_CATALOG = [
    {
        "value": STRATEGY_TYPE_COPY_TRADE,
        "label": "Copy Trade",
        "description": (
            "Copies option trades from a configured source and distributes "
            "them as signals. X is available now; chat groups can be added later. "
            "When the source is X, set poll_interval_seconds on x_source for how "
            "often to pull new posts."
        ),
        "config_fields": ["signal_source", "x_source"],
        "signal_sources": COPY_TRADE_SIGNAL_SOURCE_CATALOG,
    },
    {
        "value": STRATEGY_TYPE_RESEARCH_BREAKTHROUGH,
        "label": "Research / Breakthrough",
        "description": (
            "Generic catalyst strategy: watch a company universe you configure, "
            "score confirmed research/results, product news, and announced deals, "
            "then select an options contract. Sector, keywords, and event types "
            "are inputs — not hardcoded. Does not copy another trader."
        ),
        "config_fields": ["research_config", "watched_companies"],
        "presets": RESEARCH_STRATEGY_PRESETS,
    },
]

DIR_BULLISH = "bullish"
DIR_BEARISH = "bearish"
DIR_UNKNOWN = "unknown"
DIRECTION_CHOICES = (
    (DIR_BULLISH, "Bullish"),
    (DIR_BEARISH, "Bearish"),
    (DIR_UNKNOWN, "Unknown"),
)
