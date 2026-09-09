"""Thin X API v2 client used by the copy-trade watcher."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import requests
from django.conf import settings
from django.utils.dateparse import parse_datetime
from django.utils.timezone import make_aware


class XApiError(Exception):
    pass


def format_x_api_error(exc: BaseException) -> str:
    text = str(exc)
    lower = text.lower()
    if "credits depleted" in lower or "x api 402" in lower:
        return (
            "X API credits are depleted. Add credits in the X developer portal, then retry."
        )
    if "x api 401" in lower or '"status": 401' in lower:
        return "X API unauthorized. The bearer token was rejected."
    if "x api 404" in lower:
        return "X API 404: user or tweets endpoint was not found."
    return text[:255]


@dataclass(frozen=True)
class XTweet:
    id: str
    text: str
    created_at: datetime | None


@dataclass(frozen=True)
class XUser:
    id: str
    username: str
    name: str


def _parse_created_at(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        return make_aware(parsed, timezone=timezone.utc)
    return parsed


class XClient:
    def __init__(
        self,
        bearer_token: str,
        consumer_key: str = "",
        consumer_secret: str = "",
        base_url: str | None = None,
    ):
        self.bearer_token = bearer_token
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.base_url = (base_url or getattr(settings, "X_API_BASE_URL", "")).rstrip("/")
        if not self.base_url:
            self.base_url = "https://api.x.com/2"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.bearer_token}"}

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self.base_url}{path}"
        try:
            response = requests.get(
                url, headers=self._headers(), params=params or {}, timeout=20
            )
        except requests.RequestException as exc:
            raise XApiError(str(exc)[:255]) from exc
        if response.status_code >= 400:
            detail = response.text[:200]
            raise XApiError(f"X API {response.status_code}: {detail}")
        try:
            return response.json()
        except ValueError as exc:
            raise XApiError("X API returned non-JSON") from exc

    def lookup_user(self, username: str) -> XUser:
        handle = username.lstrip("@").strip()
        payload = self._get(f"/users/by/username/{handle}")
        data = payload.get("data") or {}
        if not data.get("id"):
            raise XApiError(f"X user @{handle} not found")
        return XUser(
            id=str(data["id"]),
            username=data.get("username") or handle,
            name=data.get("name") or "",
        )

    def user_tweets(
        self,
        user_id: str,
        since_id: str | None = None,
        max_results: int = 20,
        start_time: datetime | None = None,
        pagination_token: str | None = None,
    ) -> list[XTweet]:
        tweets, _ = self._user_tweets_page(
            user_id,
            since_id=since_id,
            max_results=max_results,
            start_time=start_time,
            pagination_token=pagination_token,
        )
        return tweets

    def iter_user_tweets(
        self,
        user_id: str,
        start_time: datetime | None = None,
        max_results: int = 100,
        max_pages: int = 32,
    ):
        token = None
        for _ in range(max_pages):
            tweets, token = self._user_tweets_page(
                user_id,
                max_results=max_results,
                start_time=start_time,
                pagination_token=token,
            )
            yield from tweets
            if not token:
                return

    def _user_tweets_page(
        self,
        user_id: str,
        since_id: str | None = None,
        max_results: int = 20,
        start_time: datetime | None = None,
        pagination_token: str | None = None,
    ) -> tuple[list[XTweet], str | None]:
        params = {
            "max_results": max(5, min(int(max_results), 100)),
            "tweet.fields": "created_at,text,note_tweet",
            "exclude": "retweets,replies",
        }
        if since_id:
            params["since_id"] = since_id
        if start_time is not None:
            params["start_time"] = _rfc3339(start_time)
        if pagination_token:
            params["pagination_token"] = pagination_token
        payload = self._get(f"/users/{user_id}/tweets", params=params)
        tweets = []
        for item in payload.get("data") or []:
            note = (item.get("note_tweet") or {}).get("text")
            tweets.append(
                XTweet(
                    id=str(item["id"]),
                    text=note or item.get("text") or "",
                    created_at=_parse_created_at(item.get("created_at")),
                )
            )
        next_token = (payload.get("meta") or {}).get("next_token") or None
        return tweets, next_token


def _rfc3339(value: datetime) -> str:
    if value.tzinfo is None:
        value = make_aware(value, timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def get_x_client() -> XClient | None:
    token = (
        getattr(settings, "X_PULLCALLS_BEARER_TOKEN", "")
        or getattr(settings, "X_BEARER_TOKEN", "")
        or ""
    )
    if not token:
        return None
    return XClient(
        bearer_token=token,
        consumer_key=getattr(settings, "X_PULLCALLS_API_CONSUMER_KEY", "") or "",
        consumer_secret=getattr(settings, "X_PULLCALLS_API_SECRET", "") or "",
    )
