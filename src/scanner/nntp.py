"""Thin wrapper around nntplib.NNTP_SSL with reconnect logic."""

from __future__ import annotations

import logging
import nntplib
import socket
import time
from dataclasses import dataclass
from typing import Iterator

log = logging.getLogger(__name__)

_BACKOFF = [1, 2, 4, 8, 15, 30]


@dataclass
class GroupInfo:
    name: str
    count: int
    low: int
    high: int


@dataclass
class Article:
    article_num: int
    subject: str
    poster: str
    date: str
    message_id: str
    references: str
    bytes: int
    lines: int


class NNTPClient:
    def __init__(self, host: str, port: int, ssl: bool, username: str, password: str):
        self.host = host
        self.port = port
        self.ssl = ssl
        self.username = username
        self.password = password
        self._conn: nntplib.NNTP_SSL | nntplib.NNTP | None = None

    def connect(self) -> None:
        for attempt, delay in enumerate([0] + _BACKOFF):
            if delay:
                log.info("Reconnecting in %ds (attempt %d)", delay, attempt)
                time.sleep(delay)
            try:
                if self.ssl:
                    self._conn = nntplib.NNTP_SSL(self.host, port=self.port, user=self.username, password=self.password)
                else:
                    self._conn = nntplib.NNTP(self.host, port=self.port, user=self.username, password=self.password)
                log.info("Connected to %s:%d", self.host, self.port)
                return
            except (OSError, nntplib.NNTPError) as exc:
                log.warning("Connect failed: %s", exc)
        raise RuntimeError(f"Could not connect to {self.host} after retries")

    def _ensure_connected(self) -> None:
        if self._conn is None:
            self.connect()

    def quit(self) -> None:
        if self._conn:
            try:
                self._conn.quit()
            except Exception:
                pass
            self._conn = None

    def list_groups(self, pattern: str = "alt.binaries.*") -> list[GroupInfo]:
        self._ensure_connected()
        _, groups = self._conn.descriptions(pattern)  # type: ignore[union-attr]
        return [GroupInfo(name=name, count=0, low=0, high=0) for name, _ in groups.items()]

    def group_info(self, name: str) -> GroupInfo:
        self._ensure_connected()
        resp, count, low, high, _ = self._conn.group(name)  # type: ignore[union-attr]
        return GroupInfo(name=name, count=int(count), low=int(low), high=int(high))

    def xover(self, low: int, high: int) -> list[Article]:
        """Fetch overview records for article range [low, high] (inclusive)."""
        self._ensure_connected()
        try:
            _, overview = self._conn.over((low, high))  # type: ignore[union-attr]
        except nntplib.NNTPTemporaryError:
            return []

        articles = []
        for num, info in overview:
            try:
                articles.append(_parse_overview(int(num), info))
            except Exception as exc:
                log.debug("Skip article %s: %s", num, exc)
        return articles

    def fetch_article(self, message_id: str) -> list[bytes] | None:
        """Download a full article (headers + body) by message-ID. Returns raw lines."""
        self._ensure_connected()
        mid = f"<{message_id.strip('<>')}>"
        try:
            _, info = self._conn.article(mid)  # type: ignore[union-attr]
            return [l if isinstance(l, bytes) else l.encode("latin-1") for l in info.lines]
        except Exception as exc:
            log.debug("fetch_article %s failed: %s", message_id, exc)
            return None

    def xover_batched(self, low: int, high: int, batch_size: int = 5000) -> Iterator[list[Article]]:
        """Yield batches of Article objects across [low, high]."""
        pos = low
        while pos <= high:
            end = min(pos + batch_size - 1, high)
            try:
                batch = self.xover(pos, end)
            except (EOFError, socket.timeout, nntplib.NNTPError) as exc:
                log.warning("XOVER error at %d-%d: %s — reconnecting", pos, end, exc)
                self._conn = None
                self.connect()
                batch = self.xover(pos, end)
            yield batch
            pos = end + 1


def _parse_overview(num: int, info: dict) -> Article:
    def _int(v: str | bytes | None, default: int = 0) -> int:
        if v is None:
            return default
        try:
            return int(str(v).strip())
        except (ValueError, TypeError):
            return default

    def _str(v: str | bytes | None) -> str:
        if v is None:
            return ""
        return v.decode() if isinstance(v, bytes) else str(v)

    return Article(
        article_num=num,
        subject=_str(info.get("subject")),
        poster=_str(info.get("from")),
        date=_str(info.get("date")),
        message_id=_str(info.get("message-id")).strip("<>"),
        references=_str(info.get("references")),
        bytes=_int(info.get(":bytes")),
        lines=_int(info.get(":lines")),
    )
