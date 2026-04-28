"""TMDB matcher — polls for unmatched video releases and enriches them with TMDB data."""

from __future__ import annotations

import logging
import time

import psycopg
import psycopg.rows

from src.config import load as load_config
from src.db.conn import init_db
from src.matcher.title import clean_title
from src.matcher.tmdb import TmdbClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

_FETCH_SQL = """
    SELECT id, title, category_id
    FROM releases
    WHERE (
        (category_id IN (10, 11) AND spotnet_subcats LIKE '%%z0|%%')
        OR
        (category_id IN (20, 21) AND spotnet_subcats LIKE '%%z1|%%')
    )
      AND tmdb_matched_at IS NULL
      AND (tmdb_match_failed IS NULL OR tmdb_match_failed = FALSE)
    ORDER BY posted_at DESC
    LIMIT %(batch_size)s
"""

_UPSERT_METADATA = """
    INSERT INTO tmdb_metadata
        (tmdb_id, tmdb_type, title, original_title, overview, poster_path,
         release_year, rating, vote_count)
    VALUES
        (%(tmdb_id)s, %(tmdb_type)s, %(title)s, %(original_title)s, %(overview)s,
         %(poster_path)s, %(release_year)s, %(rating)s, %(vote_count)s)
    ON CONFLICT (tmdb_id) DO UPDATE SET
        title          = EXCLUDED.title,
        original_title = EXCLUDED.original_title,
        overview       = EXCLUDED.overview,
        poster_path    = EXCLUDED.poster_path,
        release_year   = EXCLUDED.release_year,
        rating         = EXCLUDED.rating,
        vote_count     = EXCLUDED.vote_count,
        fetched_at     = NOW()
"""

_MARK_MATCHED = """
    UPDATE releases
    SET tmdb_id         = %(tmdb_id)s,
        tmdb_year       = %(tmdb_year)s,
        tmdb_season     = %(season)s,
        tmdb_episode    = %(episode)s,
        tmdb_matched_at = NOW(),
        tmdb_match_failed = FALSE
    WHERE id = %(release_id)s
"""

_MARK_FAILED = """
    UPDATE releases
    SET tmdb_match_failed = TRUE
    WHERE id = %(release_id)s
"""


def _is_series(category_id: int) -> bool:
    return category_id in (20, 21)


def _process_batch(conn: psycopg.Connection, client: TmdbClient, batch_size: int) -> int:
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(_FETCH_SQL, {"batch_size": batch_size})
        rows = cur.fetchall()

    for row in rows:
        release_id = row["id"]
        raw_title: str = row["title"] or ""

        is_tv = _is_series(row["category_id"])
        tmdb_type = "tv" if is_tv else "movie"

        cleaned, year, season, episode = clean_title(raw_title)
        log.info("[search] %r → query=%r year=%s type=%s", raw_title, cleaned, year, tmdb_type)

        try:
            result = client.search_tv(cleaned, year) if is_tv else client.search_movie(cleaned, year)
        except Exception as exc:
            log.warning("[error] TMDB request failed for %r: %s", raw_title, exc)
            continue

        with conn.cursor() as cur:
            if result:
                meta = client.to_metadata_row(result, tmdb_type)
                cur.execute(_UPSERT_METADATA, meta)
                cur.execute(_MARK_MATCHED, {
                    "tmdb_id": meta["tmdb_id"],
                    "tmdb_year": meta["release_year"] or year,
                    "season": season,
                    "episode": episode,
                    "release_id": release_id,
                })
                log.info("[match] %r → %r (id=%s, %s)", raw_title, meta["title"], meta["tmdb_id"], tmdb_type)
            else:
                cur.execute(_MARK_FAILED, {"release_id": release_id})
                log.info("[no match] %r", raw_title)
        conn.commit()

    return len(rows)


def main() -> None:
    cfg = load_config()

    if not cfg.tmdb.api_key:
        raise RuntimeError("TMDB_API_KEY is not set — add it to .env or environment")

    log.info("applying schema migrations…")
    init_db(cfg.database.dsn)

    log.info("starting TMDB matcher (sleep=%.1fs, caught_up=%ds, batch=%d)",
             cfg.tmdb.sleep_between_requests, cfg.tmdb.sleep_when_caught_up, cfg.tmdb.batch_size)

    with TmdbClient(cfg.tmdb.api_key, max_requests_per_second=10) as client:
        with psycopg.connect(cfg.database.dsn) as conn:
            while True:
                processed = _process_batch(conn, client, cfg.tmdb.batch_size)
                if processed == 0:
                    log.info("caught up — sleeping %ds", cfg.tmdb.sleep_when_caught_up)
                    time.sleep(cfg.tmdb.sleep_when_caught_up)
                else:
                    time.sleep(cfg.tmdb.sleep_between_requests)


if __name__ == "__main__":
    main()
