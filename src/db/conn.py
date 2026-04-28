"""psycopg3 connection helpers."""

from __future__ import annotations

from pathlib import Path

import psycopg

_SCHEMA = Path(__file__).parent / "schema.sql"


def init_db(dsn: str) -> None:
    """Apply schema.sql — safe to run on every startup (all DDL is IF NOT EXISTS)."""
    sql = _SCHEMA.read_text()
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(sql)
