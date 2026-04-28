"""Deliver NZB files from stored release data."""

from __future__ import annotations

import psycopg


def get_nzb(release_id: int, conn: psycopg.Connection) -> bytes | None:
    """Return the pre-assembled NZB for a release.

    Returns None if the release doesn't exist or has no NZB data.
    """
    row = conn.execute(
        "SELECT nzb_raw FROM releases WHERE id = %s",
        (release_id,),
    ).fetchone()

    if not row or not row[0]:
        return None

    return bytes(row[0])
