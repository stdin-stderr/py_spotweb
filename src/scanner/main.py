"""Scanner: pull NNTP headers and store raw articles in PostgreSQL."""

from __future__ import annotations

import email.utils
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
import psycopg.rows

# Allow running as `python -m src.scanner.main` from project root
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config import load as load_config
from src.db.conn import init_db
from src.scanner.nntp import NNTPClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


def parse_date(raw: str) -> datetime | None:
    try:
        ts = email.utils.parsedate_to_datetime(raw)
        return ts.astimezone(timezone.utc)
    except Exception:
        return None


def ensure_group(conn: psycopg.Connection, name: str) -> int:
    row = conn.execute(
        "INSERT INTO newsgroups (name) VALUES (%s) ON CONFLICT (name) DO UPDATE SET name=EXCLUDED.name RETURNING id",
        (name,),
    ).fetchone()
    return row[0]  # type: ignore[index]


def get_watermark(conn: psycopg.Connection, group_id: int) -> int:
    row = conn.execute(
        "SELECT last_article FROM scan_state WHERE group_id = %s", (group_id,)
    ).fetchone()
    return row[0] if row else 0


def set_watermark(conn: psycopg.Connection, group_id: int, article_num: int) -> None:
    conn.execute(
        """
        INSERT INTO scan_state (group_id, last_article, updated_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (group_id) DO UPDATE
          SET last_article = EXCLUDED.last_article, updated_at = NOW()
        """,
        (group_id, article_num),
    )


def _bisect_cutoff(
    nntp: NNTPClient, low: int, high: int, cutoff: datetime, batch_size: int
) -> int:
    """Binary-search for the start of articles posted on or after cutoff.

    Invariant: lo is always before cutoff, hi is always at or after cutoff.
    Returns lo when converged so the caller scans [lo, high] and filters
    individual articles by date — this ensures no spots in the window are missed.
    """
    lo, hi = low, high
    while hi - lo > batch_size:
        mid = (lo + hi) // 2
        batch = nntp.xover(mid, min(mid + 200, hi))
        if not batch:
            lo = mid
            continue
        first_date = parse_date(batch[0].date)
        if not first_date or first_date < cutoff:
            lo = mid
        else:
            hi = mid
    log.info("Bisect converged: lo=%d hi=%d — starting scan from lo", lo, hi)
    return lo


def scan_spotnet_group(
    nntp: NNTPClient,
    conn: psycopg.Connection,
    group_name: str,
    max_age_days: int,
    batch_size: int,
    retrieve_on_demand: bool = False,
) -> bool:
    """Scan a Spotnet group: download article bodies, parse XML, store releases directly.

    Returns True if the group was fully caught up (watermark reached high), False if more
    articles remain (caller should loop again without a long sleep).
    """
    from src.scanner.spotnet import assemble_image, assemble_nzb, parse_spotnet_body

    group_id = ensure_group(conn, group_name)
    conn.commit()

    try:
        info = nntp.group_info(group_name)
    except Exception as exc:
        log.warning("Could not select group %s: %s", group_name, exc)
        return True

    log.info("Spotnet %s: low=%d high=%d count=%d", group_name, info.low, info.high, info.count)

    watermark = get_watermark(conn, group_id)
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)

    if watermark == 0:
        start = _bisect_cutoff(nntp, info.low, info.high, cutoff, batch_size)
        log.info("Spotnet %s: bisect start=%d (high=%d)", group_name, start, info.high)
    else:
        start = watermark + 1

    if start > info.high:
        log.info("Spotnet %s: up to date", group_name)
        return True

    total_stored = 0
    total_skipped = 0
    total_failed = 0
    last_num = start - 1
    for batch in nntp.xover_batched(start, info.high, batch_size=batch_size):
        if not batch:
            continue

        log.info("Spotnet %s: processing batch of %d articles (articles %d–%d, up to %d)",
                 group_name, len(batch), batch[0].article_num, batch[-1].article_num, info.high)

        for i, art in enumerate(batch):
            posted_at = parse_date(art.date)
            if posted_at and posted_at < cutoff:
                total_skipped += 1
                continue

            # Will be reassigned after parsing to prefer spotnet_created if available
            posted_at_fallback = posted_at

            # Skip articles already stored
            if conn.execute(
                "SELECT 1 FROM releases WHERE source='spotnet' AND search_title=%s",
                (art.message_id,),
            ).fetchone():
                total_skipped += 1
                continue

            log.info("Spotnet %s: [%d/%d] fetching %s", group_name, i + 1, len(batch), art.message_id)
            lines = nntp.fetch_article(art.message_id)
            if not lines:
                log.info("Spotnet %s: no article body for %s", group_name, art.message_id)
                total_failed += 1
                continue

            post = parse_spotnet_body(lines)
            if not post:
                log.info("Spotnet %s: parse failed for %s (subject: %s)", group_name, art.message_id, art.subject[:80])
                total_failed += 1
                continue

            # Prefer spotnet_created timestamp over NNTP date if available
            if post.spotnet_created:
                posted_at = datetime.fromtimestamp(post.spotnet_created, tz=timezone.utc)
            else:
                posted_at = posted_at_fallback

            # Assemble NZB and image from segments listed in the XML
            nzb_bytes: bytes | None = None
            image_bytes: bytes | None = None
            nzb_segments_str: str | None = "|".join(post.nzb_segments) + "|" if post.nzb_segments else None
            image_segments_str: str | None = "|".join(post.image_segments) + "|" if post.image_segments else None

            if nntp._conn and not retrieve_on_demand:
                if post.nzb_segments:
                    try:
                        nzb_bytes = assemble_nzb(nntp._conn, post.nzb_segments)
                        log.info("Spotnet %s: NZB assembled (%d bytes) for %r", group_name, len(nzb_bytes) if nzb_bytes else 0, post.title)
                    except Exception as exc:
                        log.info("Spotnet %s: NZB assembly failed for %r: %s", group_name, post.title, exc)
                if post.image_segments:
                    try:
                        image_bytes = assemble_image(nntp._conn, post.image_segments)
                        log.info("Spotnet %s: image assembled (%d bytes) for %r", group_name, len(image_bytes) if image_bytes else 0, post.title)
                    except Exception as exc:
                        log.info("Spotnet %s: image assembly failed for %r: %s", group_name, post.title, exc)

            # Strip angle brackets to get clean message-ID for SpotWeb-compatible URLs
            clean_messageid = art.message_id.strip("<>")

            conn.execute(
                """
                INSERT INTO releases
                  (messageid, title, search_title, category_id, poster, posted_at,
                   total_bytes, file_count, completion_pct, search_vector,
                   source, nzb_raw, image_raw, description, spotnet_category, spotnet_subcats,
                   nzb_segments, image_segments, spotnet_key, spotnet_tag, spotnet_created, spotnet_website)
                VALUES (
                  %s, %s, %s, %s, %s, %s,
                  %s, 1, 100, to_tsvector('english', %s),
                  'spotnet', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT DO NOTHING
                """,
                (
                    clean_messageid,
                    post.title,
                    art.message_id,
                    post.category_id,
                    post.poster,
                    posted_at,
                    post.file_size,
                    post.title,
                    nzb_bytes,
                    image_bytes,
                    post.description or None,
                    post.spotnet_category,
                    post.spotnet_subcats or None,
                    nzb_segments_str,
                    image_segments_str,
                    post.spotnet_key,
                    post.spotnet_tag or None,
                    post.spotnet_created,
                    post.spotnet_website or None,
                ),
            )
            log.info("Spotnet %s: stored %r (%.1f MB, cat=%d)", group_name, post.title, post.file_size / 1024 / 1024, post.category_id)
            total_stored += 1
            conn.commit()  # commit each release immediately so the API sees it

        last_num = batch[-1].article_num
        set_watermark(conn, group_id, last_num)
        conn.commit()
        log.info("Spotnet %s: batch done — stored=%d skipped=%d failed=%d (watermark %d / %d)",
                 group_name, total_stored, total_skipped, total_failed, last_num, info.high)

    caught_up = last_num >= info.high
    log.info("Spotnet %s: scan complete — stored=%d skipped=%d failed=%d caught_up=%s",
             group_name, total_stored, total_skipped, total_failed, caught_up)
    return caught_up


def run_once(cfg) -> bool:
    """Run one scan cycle. Returns True if all groups are fully caught up."""
    init_db(cfg.database.dsn)
    nntp = NNTPClient(
        host=cfg.nntp.host,
        port=cfg.nntp.port,
        ssl=cfg.nntp.ssl,
        username=cfg.nntp.username,
        password=cfg.nntp.password,
    )
    nntp.connect()

    all_caught_up = True

    with psycopg.connect(cfg.database.dsn) as conn:
        for group_name in cfg.scanner.spotnet_groups:
            log.info("Scanning group: %s", group_name)
            try:
                caught_up = scan_spotnet_group(
                    nntp=nntp,
                    conn=conn,
                    group_name=group_name,
                    max_age_days=cfg.scanner.max_age_days,
                    batch_size=cfg.nntp.batch_size,
                    retrieve_on_demand=cfg.storage.retrieve_on_demand,
                )
                if not caught_up:
                    all_caught_up = False
            except Exception as exc:
                log.error("Error scanning %s: %s", group_name, exc, exc_info=True)

    nntp.quit()
    return all_caught_up


def main() -> None:
    cfg = load_config()
    log.info(
        "Scanner starting — host=%s max_age_days=%d spotnet_groups=%s",
        cfg.nntp.host,
        cfg.scanner.max_age_days,
        cfg.scanner.spotnet_groups,
    )
    while True:
        try:
            caught_up = run_once(cfg)
        except Exception as exc:
            log.error("Scanner cycle failed: %s", exc, exc_info=True)
            caught_up = True  # don't tight-loop on persistent errors
        delay = 300 if caught_up else 5
        log.info("Scan cycle complete — sleeping %ds", delay)
        time.sleep(delay)


if __name__ == "__main__":
    main()
