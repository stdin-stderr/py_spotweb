"""Build NZB XML from stored release data."""

from __future__ import annotations

from xml.etree.ElementTree import Element, SubElement, tostring

import psycopg


def get_nzb(release_id: int, conn: psycopg.Connection) -> bytes | None:
    """Return the NZB for a release.

    Spotnet releases have a pre-assembled NZB stored in nzb_raw.
    Binary releases have their article segments stored in file_articles.
    Returns None if the release doesn't exist or has no NZB data.
    """
    row = conn.execute(
        "SELECT source, nzb_raw FROM releases WHERE id = %s",
        (release_id,),
    ).fetchone()

    if not row:
        return None

    source, nzb_raw = row[0], row[1]

    if source == "spotnet":
        if nzb_raw:
            return bytes(nzb_raw)
        return None

    return _build_nzb_from_articles(release_id, conn)


def _build_nzb_from_articles(release_id: int, conn: psycopg.Connection) -> bytes:
    rows = conn.execute(
        """
        SELECT a.message_id, a.bytes, g.name AS group_name,
               f.normalized_name, fa.part_num
        FROM file_articles fa
        JOIN articles a    ON a.id = fa.article_id
        JOIN files f       ON f.id = fa.file_id
        JOIN newsgroups g  ON g.id = a.group_id
        WHERE f.release_id = %s
        ORDER BY f.normalized_name, fa.part_num
        """,
        (release_id,),
    ).fetchall()

    nzb = Element("nzb", xmlns="http://www.newzbin.com/DTD/2003/nzb")
    current_fname: str | None = None
    segments_el: Element | None = None

    for msg_id, size, group_name, fname, part in rows:
        if fname != current_fname:
            current_fname = fname
            file_el = SubElement(nzb, "file", subject=fname or "", poster="", date="0")
            groups_el = SubElement(file_el, "groups")
            SubElement(groups_el, "group").text = group_name or ""
            segments_el = SubElement(file_el, "segments")

        seg = SubElement(
            segments_el,  # type: ignore[arg-type]
            "segment",
            bytes=str(size or 0),
            number=str(part or 1),
        )
        seg.text = (msg_id or "").strip("<>")

    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(nzb, encoding="unicode").encode()
