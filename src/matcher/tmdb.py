"""Synchronous TMDB API client."""

from __future__ import annotations

import collections
import difflib
import logging
import time

import httpx

log = logging.getLogger(__name__)

_BASE = "https://api.themoviedb.org/3"
_TIMEOUT = 10.0
_MIN_SIMILARITY = 0.6  # SequenceMatcher ratio threshold for accepting a match


class _RateLimiter:
    """Sliding-window rate limiter — blocks until a request slot is available."""

    def __init__(self, max_per_second: int) -> None:
        self._max = max_per_second
        self._times: collections.deque[float] = collections.deque()

    def wait(self) -> None:
        now = time.monotonic()
        # Drop timestamps older than 1 second
        while self._times and now - self._times[0] >= 1.0:
            self._times.popleft()
        if len(self._times) >= self._max:
            sleep_for = 1.0 - (now - self._times[0])
            if sleep_for > 0:
                time.sleep(sleep_for)
            now = time.monotonic()
            while self._times and now - self._times[0] >= 1.0:
                self._times.popleft()
        self._times.append(time.monotonic())


class TmdbClient:
    def __init__(self, api_key: str, max_requests_per_second: int = 10) -> None:
        # JWT access tokens (start with "eyJ") use Bearer auth; short hex strings use ?api_key=
        if api_key.startswith("eyJ"):
            headers = {"Authorization": f"Bearer {api_key}"}
            self._key_param: dict = {}
        else:
            headers = {}
            self._key_param = {"api_key": api_key}
        self._http = httpx.Client(timeout=_TIMEOUT, headers=headers)
        self._limiter = _RateLimiter(max_requests_per_second)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> TmdbClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _get(self, path: str, **params: object) -> dict:
        self._limiter.wait()
        resp = self._http.get(
            f"{_BASE}{path}",
            params={**self._key_param, **params},
        )
        resp.raise_for_status()
        return resp.json()

    def _best_match(self, results: list[dict], query: str, title_key: str) -> dict | None:
        if not results:
            return None
        query_lower = query.lower()
        best: dict | None = None
        best_score = 0.0
        for item in results[:5]:
            candidate = (item.get(title_key) or "").lower()
            score = difflib.SequenceMatcher(None, query_lower, candidate).ratio()
            if score > best_score:
                best_score = score
                best = item
        if best_score >= _MIN_SIMILARITY:
            return best
        log.info("no confident match for %r — best: %r (score=%.2f)", query, best.get(title_key) if best else None, best_score)
        return None

    def search_movie(self, query: str, year: int | None = None) -> dict | None:
        params: dict = {"query": query, "language": "en-US"}
        if year:
            params["year"] = year
        data = self._get("/search/movie", **params)
        result = self._best_match(data.get("results", []), query, "title")
        if result is None and year:
            # retry without year constraint
            data = self._get("/search/movie", query=query, language="en-US")
            result = self._best_match(data.get("results", []), query, "title")
        return result

    def search_tv(self, query: str, year: int | None = None) -> dict | None:
        params: dict = {"query": query, "language": "en-US"}
        if year:
            params["first_air_date_year"] = year
        data = self._get("/search/tv", **params)
        result = self._best_match(data.get("results", []), query, "name")
        if result is None and year:
            data = self._get("/search/tv", query=query, language="en-US")
            result = self._best_match(data.get("results", []), query, "name")
        return result

    def _year_from_date(self, date_str: str | None) -> int | None:
        if date_str and len(date_str) >= 4:
            try:
                return int(date_str[:4])
            except ValueError:
                pass
        return None

    def to_metadata_row(self, result: dict, tmdb_type: str) -> dict:
        """Normalise a raw TMDB search result into a tmdb_metadata dict."""
        if tmdb_type == "movie":
            title = result.get("title") or result.get("original_title", "")
            date = result.get("release_date")
        else:
            title = result.get("name") or result.get("original_name", "")
            date = result.get("first_air_date")
        return {
            "tmdb_id": result["id"],
            "tmdb_type": tmdb_type,
            "title": title,
            "original_title": result.get("original_title") or result.get("original_name"),
            "overview": result.get("overview"),
            "poster_path": result.get("poster_path"),
            "release_year": self._year_from_date(date),
            "rating": result.get("vote_average"),
            "vote_count": result.get("vote_count"),
        }
