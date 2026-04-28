"""Deliver NZB files from stored release data."""

from __future__ import annotations

import psycopg
from src.scanner.spotnet import assemble_nzb
from src.scanner.nntp import NNTPClient


def get_nzb(release_id: int, conn: psycopg.Connection, nntp_client: NNTPClient | None = None) -> bytes | None:
    """Return the pre-assembled NZB for a release.

    Returns None if the release doesn't exist or has no NZB data.
    """
    row = conn.execute(
        "SELECT nzb_raw, nzb_segments FROM releases WHERE id = %s",
        (release_id,),
    ).fetchone()

    if not row:
        return None

    nzb_raw, nzb_segments_str = row

    if nzb_raw:
        return bytes(nzb_raw)

    if nzb_segments_str and nntp_client:
        segments = [s for s in nzb_segments_str.split("|") if s]
        try:
            nntp_client.connect()
            # assemble_nzb expects the raw nntplib connection object which is in nntp_client._conn
            return assemble_nzb(nntp_client._conn, segments)
        except Exception:
            return None

    return None
