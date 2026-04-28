"""FastAPI routes — Newznab API dispatcher and minimal search UI."""

from __future__ import annotations

import html
import logging
from datetime import datetime, timedelta, timezone

import psycopg
import psycopg.rows
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response

from src.api.newznab import caps_response, search_response
from src.api.nzb import get_nzb

log = logging.getLogger(__name__)
router = APIRouter()


def get_conn(request: Request) -> psycopg.Connection:
    return request.app.state.db_conn


@router.get("/api")
async def api_endpoint(
    request: Request,
    t: str = Query(..., description="Newznab function"),
    q: str = Query("", description="Search query"),
    cat: str = Query("", description="Category filter (comma-separated newznab IDs)"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    maxage: int = Query(0, ge=0, description="Max age in days (0=no limit)"),
    id: str = Query("", description="Release ID for get/details"),
    season: str = Query(""),
    ep: str = Query(""),
    imdbid: str = Query(""),
    tvdbid: str = Query(""),
    rid: str = Query(""),
) -> Response:
    base_url = request.app.state.base_url

    if t == "caps":
        return Response(content=caps_response(base_url), media_type="text/xml")

    conn: psycopg.Connection = request.app.state.db_conn

    if t == "get":
        if not id:
            raise HTTPException(400, "id parameter required")
        try:
            release_id = int(id)
        except ValueError:
            raise HTTPException(400, "id must be an integer")
        nzb = get_nzb(release_id, conn)
        if nzb is None:
            raise HTTPException(404, "NZB not available for this release")
        title_row = conn.execute("SELECT title FROM releases WHERE id = %s", (release_id,)).fetchone()
        raw_title = (title_row[0] if title_row else None) or f"release-{release_id}"
        safe_title = "".join(c if c.isalnum() or c in " .-_()" else "_" for c in raw_title).strip()
        return Response(
            content=nzb,
            media_type="application/x-nzb",
            headers={"Content-Disposition": f'attachment; filename="{safe_title}.nzb"'},
        )

    if t in ("search", "tvsearch", "movie", "audio"):
        releases, total = _do_search(conn, t, q, cat, limit, offset, maxage, season, ep, imdbid, tvdbid or rid)
        return Response(content=search_response(releases, base_url, total), media_type="text/xml")

    raise HTTPException(400, f"Unknown function: {t}")


@router.get("/image/{release_id}")
async def image_endpoint(release_id: int, request: Request) -> Response:
    conn: psycopg.Connection = request.app.state.db_conn
    row = conn.execute(
        "SELECT image_raw FROM releases WHERE id = %s", (release_id,)
    ).fetchone()
    if not row or not row[0]:
        raise HTTPException(404, "No image available for this release")
    data = bytes(row[0])
    media_type = "image/jpeg" if data[:2] == b"\xff\xd8" else "image/png"
    return Response(content=data, media_type=media_type)


def _do_search(
    conn: psycopg.Connection,
    t: str,
    q: str,
    cat: str,
    limit: int,
    offset: int,
    maxage: int,
    season: str,
    ep: str,
    imdbid: str,
    tvdbid: str,
) -> tuple[list[dict], int]:
    from src.api.newznab import NEWZNAB_ID_MAP

    # Reverse map: newznab_id → internal category_id
    newznab_to_internal: dict[int, int] = {v: k for k, v in NEWZNAB_ID_MAP.items()}

    conditions = ["1=1"]
    params: list = []

    if q:
        conditions.append("search_vector @@ plainto_tsquery('english', %s)")
        params.append(q)

    if cat:
        cat_ids_newznab = [int(c.strip()) for c in cat.split(",") if c.strip().isdigit()]
        internal_ids = []
        for nid in cat_ids_newznab:
            # include parent and sub-categories
            if nid in newznab_to_internal:
                internal_ids.append(newznab_to_internal[nid])
            # include sub-categories of parent (e.g. 2000 → 10, 11)
            for iid, nzid in NEWZNAB_ID_MAP.items():
                if nzid // 1000 == nid // 1000:
                    internal_ids.append(iid)
        if internal_ids:
            conditions.append("category_id = ANY(%s)")
            params.append(list(set(internal_ids)))

    if maxage > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=maxage)
        conditions.append("posted_at >= %s")
        params.append(cutoff)

    if t == "tvsearch":
        if season:
            conditions.append("title ILIKE %s")
            params.append(f"%S{season.zfill(2)}%")
        if ep:
            conditions.append("title ILIKE %s")
            params.append(f"%E{ep.zfill(2)}%")

    if t == "movie" and imdbid:
        conditions.append("title ILIKE %s")
        params.append(f"%{imdbid}%")

    where = " AND ".join(conditions)

    total_row = conn.execute(
        f"SELECT COUNT(*) FROM releases WHERE {where}", params
    ).fetchone()
    total = total_row[0] if total_row else 0

    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        rows = cur.execute(
            f"""
            SELECT id, title, category_id, poster, posted_at, total_bytes, file_count,
                   completion_pct, description,
                   (image_raw IS NOT NULL) AS has_image,
                   spotnet_category, spotnet_subcats
            FROM releases
            WHERE {where}
            ORDER BY posted_at DESC NULLS LAST
            LIMIT %s OFFSET %s
            """,
            params + [limit, offset],
        ).fetchall()

    return list(rows), total


@router.get("/ui", response_class=HTMLResponse)
@router.get("/ui/", response_class=HTMLResponse)
async def search_ui(
    request: Request,
    q: str = Query(""),
    cat: str = Query(""),
    page: int = Query(1, ge=1),
) -> HTMLResponse:
    limit = 50
    offset = (page - 1) * limit
    conn: psycopg.Connection = request.app.state.db_conn
    releases, total = _do_search(conn, "search", q, cat, limit, offset, 0, "", "", "", "")
    pages = max(1, (total + limit - 1) // limit)

    from src.api.newznab import NEWZNAB_ID_MAP
    CAT_NAMES = {
        3: "Audio", 4: "Other", 5: "Ebook", 6: "PC/Apps", 7: "XXX",
        10: "Movies HD", 11: "Movies SD", 20: "TV HD", 21: "TV SD",
        30: "MP3", 31: "Lossless",
    }

    rows_html = ""
    for r in releases:
        size_bytes = r.get("total_bytes") or 0
        size_str = f"{size_bytes / (1024*1024):.1f} MB" if size_bytes else "?"
        date_str = r.get("posted_at").strftime("%Y-%m-%d %H:%M") if r.get("posted_at") else ""
        nzb_url = f"/api?t=get&id={r['id']}"
        thumb = f'<img src="/image/{r["id"]}" height="80" style="vertical-align:top;border-radius:3px">' if r.get("has_image") else ""
        title_escaped = html.escape(r.get("title") or "")
        cat_name = CAT_NAMES.get(r.get("category_id"), str(r.get("category_id", "")))
        desc_escaped = html.escape((r.get("description") or "")[:300])
        desc_html = f'<br><small style="color:#666">{desc_escaped}</small>' if desc_escaped else ""
        rows_html += f"""
        <tr>
          <td style="width:90px">{thumb}</td>
          <td><a href="{nzb_url}">{title_escaped}</a>{desc_html}</td>
          <td>{cat_name}</td>
          <td>{size_str}</td>
          <td>{date_str}</td>
          <td><a href="{nzb_url}">NZB</a></td>
        </tr>"""

    pagination = " ".join(
        f'<a href="?q={q}&cat={cat}&page={p}">[{p}]</a>' for p in range(1, min(pages + 1, 20))
    )

    q_escaped = html.escape(q)
    cat_escaped = html.escape(cat)
    html_doc = f"""<!DOCTYPE html>
<html>
<head><title>Spotnet Index</title>
<style>
  body {{ font-family: monospace; padding: 1em; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ccc; padding: 4px 8px; text-align: left; vertical-align: middle; }}
  tr:nth-child(even) {{ background: #f5f5f5; }}
  input, select {{ margin-right: 0.5em; }}
  img {{ border-radius: 2px; }}
</style>
</head>
<body>
<h2>Spotnet Index</h2>
<form method="get" action="/ui/">
  <input name="q" value="{q_escaped}" placeholder="Search..." />
  <input name="cat" value="{cat_escaped}" placeholder="Category ID" size="6"/>
  <button type="submit">Search</button>
</form>
<p>{total} results &mdash; page {page}/{pages}</p>
<table>
  <tr><th></th><th>Title</th><th>Cat</th><th>Size</th><th>Date</th><th>Download</th></tr>
  {rows_html}
</table>
<p>{pagination}</p>
</body>
</html>"""
    return HTMLResponse(html_doc)
