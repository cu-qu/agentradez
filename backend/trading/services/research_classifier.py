"""Classify headlines into confirmed research / deal catalysts.

This is not a copy-trade parser. It scores whether a company confirmed a
material result, FDA action, or deal — then a separate selector picks the
option contract.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from trading.constants import (
    DIR_BEARISH,
    DIR_BULLISH,
    DIR_UNKNOWN,
    EVENT_ACQUISITION,
    EVENT_BREAKTHROUGH,
    EVENT_CLINICAL,
    EVENT_CONTRACT,
    EVENT_EARNINGS,
    EVENT_FDA,
    EVENT_OTHER,
    EVENT_PARTNERSHIP,
    EVENT_PRODUCT,
)

CONFIRM_RE = re.compile(
    r"\b(?:announces?|announced|reports?|reported|discloses?|disclosed|"
    r"confirms?|confirmed|press release|said today|published (?:results|data)|"
    r"fda (?:approves?|approved|grants?|granted)|receives? fda)\b",
    re.IGNORECASE,
)

RUMOR_RE = re.compile(
    r"\b(?:rumou?rs?|rumored|unconfirmed|sources say|people familiar|"
    r"considering|in talks|might acquire|could acquire|reportedly|"
    r"according to people|wsj reports that .* may)\b",
    re.IGNORECASE,
)

ANALYST_ONLY_RE = re.compile(
    r"\b(?:analyst|price target|upgrades?|downgrades?|initiates coverage|"
    r"overweight|underweight|outperform|underperform)\b",
    re.IGNORECASE,
)

# (regex, score, event_type, direction)
CATALYST_PATTERNS: list[tuple[re.Pattern, int, str, str]] = [
    (
        re.compile(
            r"\bfda\s+(?:fully\s+)?(?:approves?|approved|approval)\b|"
            r"\b(?:bla|nda|snda)\s+approv",
            re.IGNORECASE,
        ),
        42,
        EVENT_FDA,
        DIR_BULLISH,
    ),
    (
        re.compile(
            r"\b(?:accelerated approval|breakthrough therapy(?: designation)?|"
            r"fast[- ]track designation|priority review)\b",
            re.IGNORECASE,
        ),
        34,
        EVENT_FDA,
        DIR_BULLISH,
    ),
    (
        re.compile(
            r"\b(?:complete response letter|\bcrl\b|fda (?:rejects?|rejected|rejection))\b",
            re.IGNORECASE,
        ),
        42,
        EVENT_FDA,
        DIR_BEARISH,
    ),
    (
        re.compile(
            r"\b(?:clinical hold|partial clinical hold|boxed warning|black[- ]box)\b",
            re.IGNORECASE,
        ),
        36,
        EVENT_FDA,
        DIR_BEARISH,
    ),
    (
        re.compile(
            r"\b(?:cancer vaccine|individualized (?:cancer )?vaccine|"
            r"personalized cancer vaccine|mrna (?:cancer )?vaccine)\b",
            re.IGNORECASE,
        ),
        36,
        EVENT_BREAKTHROUGH,
        DIR_BULLISH,
    ),
    (
        re.compile(
            r"\b(?:phase\s*(?:3|iii)|pivotal)\b.{0,80}\b(?:success|succeed(?:ed|s)?|"
            r"positive|met (?:its |the )?primary endpoint|statistically significant)\b|"
            r"\b(?:success|succeed(?:ed|s)?|positive|met (?:its |the )?primary endpoint|"
            r"statistically significant)\b.{0,80}\b(?:phase\s*(?:3|iii)|pivotal)\b",
            re.IGNORECASE,
        ),
        38,
        EVENT_CLINICAL,
        DIR_BULLISH,
    ),
    (
        re.compile(
            r"\b(?:failed|missed|did not meet|didn't meet|does not meet)\b.{0,80}"
            r"\b(?:endpoint|trial|phase|study)\b|"
            r"\b(?:endpoint|trial|phase|study)\b.{0,80}"
            r"\b(?:failed|missed|did not meet|didn't meet)\b",
            re.IGNORECASE,
        ),
        38,
        EVENT_CLINICAL,
        DIR_BEARISH,
    ),
    (
        re.compile(
            r"\b(?:phase\s*(?:2|ii))\b.{0,80}\b(?:positive|success|met (?:its |the )?"
            r"primary endpoint)\b",
            re.IGNORECASE,
        ),
        22,
        EVENT_CLINICAL,
        DIR_BULLISH,
    ),
    (
        re.compile(
            r"\b(?:to acquire|will acquire|acquires|acquired|acquisition of|"
            r"definitive agreement to (?:acquire|be acquired)|buyout|takeover)\b",
            re.IGNORECASE,
        ),
        36,
        EVENT_ACQUISITION,
        DIR_BULLISH,
    ),
    (
        re.compile(
            r"\b(?:strategic )?(?:partnership|collaboration|licensing deal|"
            r"exclusive license|co-develop(?:ment)?|joint (?:venture|development))\b",
            re.IGNORECASE,
        ),
        28,
        EVENT_PARTNERSHIP,
        DIR_BULLISH,
    ),
    (
        re.compile(
            r"\b(?:unveils|unveiled|launch(?:es|ed|ing)?|now available|"
            r"general availability|releases? (?:a |its )?(?:new )?(?:product|model|"
            r"chip|device|platform))\b",
            re.IGNORECASE,
        ),
        30,
        EVENT_PRODUCT,
        DIR_BULLISH,
    ),
    (
        re.compile(
            r"\b(?:awarded|wins?|won|selected (?:as|by))\b.{0,50}\b(?:contract|deal|award)\b|"
            r"\b(?:multi[- ]year (?:agreement|contract))\b",
            re.IGNORECASE,
        ),
        32,
        EVENT_CONTRACT,
        DIR_BULLISH,
    ),
    (
        re.compile(
            r"\b(?:beats? (?:estimates|eps|revenue)|raises? (?:full[- ]year )?guidance)\b",
            re.IGNORECASE,
        ),
        26,
        EVENT_EARNINGS,
        DIR_BULLISH,
    ),
    (
        re.compile(
            r"\b(?:misses? (?:estimates|eps|revenue)|cuts? (?:full[- ]year )?guidance|"
            r"lowers guidance)\b",
            re.IGNORECASE,
        ),
        26,
        EVENT_EARNINGS,
        DIR_BEARISH,
    ),
]


@dataclass(frozen=True)
class CompanyRef:
    ticker: str
    name: str
    aliases: list[str]


@dataclass(frozen=True)
class Classification:
    is_catalyst: bool
    event_type: str
    direction: str
    score: int
    rationale: str
    ticker: str

    def as_dict(self) -> dict:
        return asdict(self)


def _labels(company: CompanyRef) -> list[str]:
    names = [company.name, *(company.aliases or [])]
    return [item.strip() for item in names if item and item.strip()]


def company_mentioned(text: str, company: CompanyRef) -> bool:
    if not text:
        return False
    ticker = (company.ticker or "").strip().upper()
    if ticker and re.search(rf"(?:\$|\b){re.escape(ticker)}\b", text, re.IGNORECASE):
        return True
    lowered = text.lower()
    return any(label.lower() in lowered for label in _labels(company))


def matching_companies(text: str, companies: list[CompanyRef]) -> list[CompanyRef]:
    return [company for company in companies if company_mentioned(text, company)]


def _clamp(score: int) -> int:
    return max(0, min(100, score))


def classify_text(
    headline: str,
    summary: str = "",
    companies: list[CompanyRef] | None = None,
    enabled_event_types: set[str] | list[str] | None = None,
    require_confirmation: bool = True,
) -> list[Classification]:
    """Score a headline against the watchlist. One result per matched company."""
    text = f"{headline or ''} {summary or ''}".strip()
    companies = companies or []
    enabled = set(enabled_event_types) if enabled_event_types else None
    matched = matching_companies(text, companies)
    if not matched:
        return [
            Classification(
                is_catalyst=False,
                event_type=EVENT_OTHER,
                direction=DIR_UNKNOWN,
                score=0,
                rationale="No watched company mentioned.",
                ticker="",
            )
        ]

    return [
        _classify_for_company(
            text,
            company,
            enabled_event_types=enabled,
            require_confirmation=require_confirmation,
        )
        for company in matched
    ]


def _classify_for_company(
    text: str,
    company: CompanyRef,
    enabled_event_types: set[str] | None = None,
    require_confirmation: bool = True,
) -> Classification:
    score = 20
    reasons = [f"Matched {company.ticker}"]
    event_type = EVENT_OTHER
    direction = DIR_UNKNOWN
    best_boost = 0

    confirmed = bool(CONFIRM_RE.search(text))
    rumor = bool(RUMOR_RE.search(text))
    analyst = bool(ANALYST_ONLY_RE.search(text))

    if confirmed:
        score += 18
        reasons.append("company/regulator confirmation language")
    if rumor and not confirmed:
        score -= 40
        reasons.append("rumor / unconfirmed language")
    if analyst and not confirmed:
        score -= 25
        reasons.append("analyst commentary without confirmation")

    for pattern, boost, etype, edir in CATALYST_PATTERNS:
        if enabled_event_types is not None and etype not in enabled_event_types:
            continue
        if pattern.search(text) and boost > best_boost:
            best_boost = boost
            event_type = etype
            direction = edir

    if best_boost:
        score += best_boost
        reasons.append(f"{event_type.replace('_', ' ')} ({direction})")
    else:
        score -= 10
        if enabled_event_types:
            reasons.append("no enabled catalyst pattern")
        else:
            reasons.append("no material catalyst pattern")

    if require_confirmation and not confirmed:
        score = min(score, 45)
        reasons.append("confirmation required")

    if direction == DIR_BULLISH and not confirmed and rumor:
        score = min(score, 35)
    if best_boost and confirmed:
        score += 8

    score = _clamp(score)
    is_catalyst = bool(best_boost) and score >= 50 and not (rumor and not confirmed)
    if require_confirmation and not confirmed:
        is_catalyst = False
    if analyst and not confirmed and not best_boost:
        is_catalyst = False
    rationale = "; ".join(reasons)[:255]
    return Classification(
        is_catalyst=is_catalyst,
        event_type=event_type,
        direction=direction,
        score=score,
        rationale=rationale,
        ticker=company.ticker.upper(),
    )
