"""Deliver NZB files from stored release data."""

from __future__ import annotations

import psycopg
from src.scanner.spotnet import assemble_nzb
from src.scanner.nntp import NNTPClient


def _find_release_row(identifier: str, conn: psycopg.Connection):
    """Look up a release by messageid first, then fall back to integer id.

    Returns the (nzb_raw, nzb_segments, title) row or None.
    """
    # Try messageid first
    row = conn.execute(
        "SELECT nzb_raw, nzb_segments, title FROM releases WHERE messageid = %s",
        (identifier,),
    ).fetchone()
    if row:
        return row

    # Fallback: try as integer id
    try:
        release_id = int(identifier)
    except (ValueError, TypeError):
        return None
    return conn.execute(
        "SELECT nzb_raw, nzb_segments, title FROM releases WHERE id = %s",
        (release_id,),
    ).fetchone()


def get_nzb(identifier: str, conn: psycopg.Connection, nntp_client: NNTPClient | None = None) -> bytes | None:
    """Return the pre-assembled NZB for a release.

    Args:
        identifier: messageid string (e.g. "WW8easrf810leHwaQt0ee@spot.net") or integer id as string.

    Returns None if the release doesn't exist or has no NZB data.
    """
    row = _find_release_row(identifier, conn)

    if not row:
        return None

    nzb_raw, nzb_segments_str, _title = row

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
