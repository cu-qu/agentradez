"""Pull company headlines from Google News RSS and optional IR feeds."""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus, urlparse
from xml.etree import ElementTree as ET

import requests

from trading.constants import GENERIC_NEWS_KEYWORDS

logger = logging.getLogger(__name__)

HTTP_TIMEOUT = 15
USER_AGENT = "Mozilla/5.0 (compatible; AgenticTrading/1.0; research-breakthrough)"
GOOGLE_NEWS_RSS = (
    "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
)


@dataclass(frozen=True)
class FeedItem:
    external_id: str
    headline: str
    summary: str
    url: str
    published_at: datetime | None
    source: str


def _get_xml(url: str) -> str:
    response = requests.get(
        url,
        timeout=HTTP_TIMEOUT,
        headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml"},
    )
    response.raise_for_status()
    return response.text


def _parse_datetime(raw: str | None) -> datetime | None:
    value = (raw or "").strip()
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        parsed = None
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _text(node: ET.Element | None) -> str:
    if node is None or node.text is None:
        return ""
    return re.sub(r"\s+", " ", node.text).strip()


def _child(node: ET.Element, *names: str) -> ET.Element | None:
    for name in names:
        found = node.find(name)
        if found is not None:
            return found
        if "}" in (node.tag or ""):
            ns = node.tag.split("}")[0] + "}"
            found = node.find(ns + name.split("}")[-1])
            if found is not None:
                return found
    return None


def _item_id(guid: str, url: str, headline: str) -> str:
    raw = (guid or url or headline).strip()
    if raw:
        parsed = urlparse(raw)
        if parsed.scheme and parsed.netloc:
            raw = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if len(raw) <= 120:
            return raw[:128]
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    return digest


def parse_rss(xml_text: str, source: str) -> list[FeedItem]:
    if not xml_text or not xml_text.strip():
        return []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        logger.warning("Failed to parse RSS from %s", source)
        return []

    items: list[FeedItem] = []
    nodes = root.findall(".//item")
    if not nodes:
        nodes = root.findall(".//{http://www.w3.org/2005/Atom}entry")
    for node in nodes:
        title = _text(_child(node, "title"))
        link_node = _child(node, "link")
        link = _text(link_node)
        if not link and link_node is not None:
            link = (link_node.attrib.get("href") or "").strip()
        guid = _text(_child(node, "guid", "id"))
        summary = _text(_child(node, "description", "summary"))
        published = _parse_datetime(
            _text(_child(node, "pubDate", "published", "updated"))
        )
        if not title:
            continue
        items.append(
            FeedItem(
                external_id=_item_id(guid, link, title),
                headline=title[:512],
                summary=re.sub(r"<[^>]+>", " ", summary)[:4000],
                url=link[:1024],
                published_at=published,
                source=source,
            )
        )
    return items


def catalyst_query(keywords: list[str] | None = None) -> str:
    terms = [item.strip() for item in (keywords or []) if item and str(item).strip()]
    if not terms:
        terms = list(GENERIC_NEWS_KEYWORDS)
    parts = []
    for term in terms:
        if any(ch in term for ch in " \""):
            parts.append(f'"{term.strip("\"")}"')
        else:
            parts.append(term)
    return "(" + " OR ".join(parts) + ")"


def google_news_url(
    ticker: str,
    name: str,
    lookback_hours: int = 24,
    keywords: list[str] | None = None,
) -> str:
    window = "1d" if lookback_hours <= 36 else "7d"
    name_q = f'"{name}"' if name else ticker
    query = f"({ticker} OR {name_q}) {catalyst_query(keywords)} when:{window}"
    return GOOGLE_NEWS_RSS.format(query=quote_plus(query))


def fetch_google_news(
    ticker: str,
    name: str,
    lookback_hours: int = 24,
    keywords: list[str] | None = None,
) -> list[FeedItem]:
    url = google_news_url(ticker, name, lookback_hours=lookback_hours, keywords=keywords)
    xml_text = _get_xml(url)
    return parse_rss(xml_text, source="google_news")


def fetch_rss(url: str, source: str = "rss") -> list[FeedItem]:
    xml_text = _get_xml(url)
    return parse_rss(xml_text, source=source)
