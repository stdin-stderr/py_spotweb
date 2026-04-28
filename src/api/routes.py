"""FastAPI routes — Newznab API dispatcher and minimal search UI."""

from __future__ import annotations

import html
import logging
from datetime import datetime, timedelta, timezone

import psycopg
import psycopg.rows
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

from src.api.formatting import format_description
from src.api.newznab import caps_response, search_response
from src.api.nzb import get_nzb
from src.scanner.categories import cat2desc, cat2short_desc, subcat_description, head_cat2desc, HEAD_CATEGORIES, CATEGORIES, SUBCAT_DESCRIPTIONS

log = logging.getLogger(__name__)
router = APIRouter()

# Global cache for category counts (populated at startup)
_CATEGORY_COUNTS: dict[tuple[int, str, int], int] = {}


def _compute_category_counts(conn: psycopg.Connection) -> dict[tuple[int, str, int], int]:
    """Pre-compute counts for all category/subcategory combinations.

    Returns a dict mapping (hcat, letter, number) to count.
    Example: (0, 'a', 0) -> 1250 (1250 releases with DivX format)
    """
    counts: dict[tuple[int, str, int], int] = {}

    with conn.cursor() as cur:
        rows = cur.execute(
            "SELECT spotnet_category, spotnet_subcats FROM releases WHERE spotnet_category IS NOT NULL"
        ).fetchall()

    for row in rows:
        hcat = row[0]
        subcats_str = row[1] or ""

        # Parse pipe-separated subcats (e.g., "a0|b3|c1|d4|")
        for code in subcats_str.split("|"):
            if not code or len(code) < 2:
                continue

            letter = code[0]
            try:
                number = int(code[1:])
            except ValueError:
                continue

            key = (hcat, letter, number)
            counts[key] = counts.get(key, 0) + 1

    return counts


def _get_count(hcat: int, letter: str, number: int) -> int:
    """Get cached count for a category/subcategory, or 0 if not found."""
    return _CATEGORY_COUNTS.get((hcat, letter, number), 0)


def _compute_dynamic_counts(conn: psycopg.Connection, q: str, cat: str, active_subcats: list[str], maxage: int = 0) -> dict[tuple[int, str, int], int]:
    """Compute counts for all filters given current search/filter context.

    Builds the same WHERE clause as _do_search but counts all possible filter combinations.
    """
    from src.api.newznab import NEWZNAB_ID_MAP

    newznab_to_internal: dict[int, int] = {v: k for k, v in NEWZNAB_ID_MAP.items()}
    counts: dict[tuple[int, str, int], int] = {}

    # Build base conditions (same as _do_search, but without subcat)
    conditions = ["1=1"]
    params: list = []

    if q:
        conditions.append("search_vector @@ plainto_tsquery('english', %s)")
        params.append(q)

    if cat:
        cat_ids_newznab = [int(c.strip()) for c in cat.split(",") if c.strip().isdigit()]
        internal_ids = []
        for nid in cat_ids_newznab:
            if nid in newznab_to_internal:
                internal_ids.append(newznab_to_internal[nid])
            for iid, nzid in NEWZNAB_ID_MAP.items():
                if nzid // 1000 == nid // 1000:
                    internal_ids.append(iid)
        if internal_ids:
            conditions.append("category_id = ANY(%s)")
            params.append(list(set(internal_ids)))

    # Add active subcats (AND logic)
    for sc in active_subcats:
        conditions.append("spotnet_subcats LIKE %s")
        params.append(f"%{sc}|%")

    if maxage > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=maxage)
        conditions.append("posted_at >= %s")
        params.append(cutoff)

    where = " AND ".join(conditions)

    # Query to get all releases matching current filters
    with conn.cursor() as cur:
        rows = cur.execute(
            f"SELECT spotnet_category, spotnet_subcats FROM releases WHERE {where}",
            params,
        ).fetchall()

    # Parse subcats and count each code
    for row in rows:
        hcat = row[0]
        subcats_str = row[1] or ""

        for code in subcats_str.split("|"):
            if not code or len(code) < 2:
                continue

            letter = code[0]
            try:
                number = int(code[1:])
            except ValueError:
                continue

            key = (hcat, letter, number)
            counts[key] = counts.get(key, 0) + 1

    return counts


def _build_filter_tree(counts: dict[tuple[int, str, int], int] | None = None) -> list[dict]:
    """Build hierarchical filter tree for sidebar rendering.

    Args:
        counts: Optional dynamic counts dict. If None, uses cached _CATEGORY_COUNTS.

    Returns a list of head categories, each with sections (grouped by letter/label),
    and items within each section (each with letter, number, name, count, label).
    """
    if counts is None:
        counts = _CATEGORY_COUNTS

    filter_tree = []

    for hcat in range(4):
        head_cat_name = HEAD_CATEGORIES.get(hcat, "Unknown")
        sections = []

        # Get all letters for this head category (a, b, c, d, z)
        cat_data = CATEGORIES.get(hcat, {})
        letters = sorted(cat_data.keys(), key=lambda x: ["z", "a", "b", "c", "d"].index(x) if x in ["z", "a", "b", "c", "d"] else 999)

        for letter in letters:
            items_dict = cat_data.get(letter, {})
            if not items_dict:
                continue

            label = SUBCAT_DESCRIPTIONS.get(hcat, {}).get(letter, "Unknown")
            if label == "-":
                continue

            items = []
            for number in sorted(items_dict.keys()):
                entry = items_dict[number]
                if isinstance(entry, list):
                    name = entry[0]
                else:
                    name = str(entry)

                # Skip empty/dash entries
                if not name or name == "-":
                    continue

                count = counts.get((hcat, letter, number), 0)
                if count > 0:  # Only include items that exist in current results
                    items.append({
                        "letter": letter,
                        "number": number,
                        "name": name,
                        "count": count,
                    })

            if items:
                sections.append({
                    "letter": letter,
                    "label": label,
                    "items": items,
                })

        if sections:
            filter_tree.append({
                "hcat": hcat,
                "name": head_cat_name,
                "sections": sections,
            })

    return filter_tree


def decode_spotnet_metadata(spotnet_category, spotnet_subcats: str) -> dict:
    """Decode spotnet subcategories into human-readable metadata.

    Args:
        spotnet_category: Raw category from XML (0-3) or None
        spotnet_subcats: Pipe-separated codes like "a0|b3|c1|d4" or None

    Returns:
        Dict of {label: value} pairs, only including non-empty values
    """
    metadata = {}

    if spotnet_category is None or spotnet_subcats is None:
        return metadata

    try:
        hcat = int(spotnet_category)
    except (ValueError, TypeError):
        return metadata

    for code in spotnet_subcats.split("|"):
        if not code or len(code) < 2:
            continue

        cat_type = code[0]
        desc_label = subcat_description(hcat, cat_type)
        if desc_label == "-":
            continue

        desc_value = cat2desc(hcat, code)
        if desc_value and desc_value != "-":
            metadata[desc_label] = desc_value

    return metadata


def get_genre_from_subcats(spotnet_category: int | None, spotnet_subcats: str | None) -> str:
    """Extract genre (d-code) from spotnet subcategories.

    Args:
        spotnet_category: Raw category from XML (0-3) or None
        spotnet_subcats: Pipe-separated codes like "a0|b3|c1|d4" or None

    Returns:
        Human-readable genre name or empty string if not found
    """
    if spotnet_category is None or spotnet_subcats is None:
        return ""

    try:
        hcat = int(spotnet_category)
    except (ValueError, TypeError):
        return ""

    for code in spotnet_subcats.split("|"):
        if code.startswith("d"):
            return cat2desc(hcat, code)

    return ""


def get_row_background_color(spotnet_category: int | None, spotnet_subcats: str | None) -> str:
    """Get background color for a row based on spotnet category and type.

    Color mapping:
    - Books (z2): Grey (#f5f5f5)
    - Erotica (z3): Purple (#f3e5f5)
    - Other Image (category 0): Blue (#e3f2fd)
    - Sound (category 1): Yellow (#fffde7)
    - Games (category 2): Green (#e8f5e9)
    - Applications (category 3): Coral (#ffccbc)
    """
    if spotnet_category is None:
        return ""

    try:
        cat = int(spotnet_category)
    except (ValueError, TypeError):
        return ""

    # For Image category (0), check Type (z-codes) first
    if cat == 0:
        if spotnet_subcats:
            # Check for Book (z2) or Erotica (z3)
            codes = spotnet_subcats.split("|")
            for code in codes:
                if code.startswith("z2"):
                    return "#f5f5f5"  # Grey for Books
                if code.startswith("z3"):
                    return "#f3e5f5"  # Purple for Erotica
        return "#e3f2fd"  # Blue for other Image
    elif cat == 1:
        return "#fffde7"  # Yellow for Sound
    elif cat == 2:
        return "#e8f5e9"  # Green for Games
    elif cat == 3:
        return "#ffccbc"  # Coral for Applications

    return ""


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


@router.get("/ui/release/{release_id}")
async def release_detail(release_id: int, request: Request):
    conn: psycopg.Connection = request.app.state.db_conn
    templates: Jinja2Templates = request.app.state.templates

    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        row = cur.execute(
            """
            SELECT id, title, poster, posted_at, total_bytes, file_count,
                   completion_pct, description, has_nfo, has_par2, is_passworded,
                   image_raw, spotnet_category, spotnet_subcats, category_id
            FROM releases
            WHERE id = %s
            """,
            (release_id,),
        ).fetchone()

    if not row:
        raise HTTPException(404, f"Release {release_id} not found")

    # Decode metadata
    metadata = decode_spotnet_metadata(row["spotnet_category"], row["spotnet_subcats"])

    # Add category from internal category_id
    from src.api.newznab import NEWZNAB_ID_MAP
    CAT_NAMES = {
        3: "Audio", 4: "Other", 5: "Ebook", 6: "PC/Apps", 7: "XXX",
        10: "Movies HD", 11: "Movies SD", 20: "TV HD", 21: "TV SD",
        30: "MP3", 31: "Lossless",
    }
    category_name = CAT_NAMES.get(row.get("category_id"), str(row.get("category_id", "Unknown")))

    # Format description
    description_raw = row.get("description") or ""
    description_formatted = format_description(description_raw) if description_raw else ""

    # Render template directly
    template = templates.get_template("release_detail.html")
    context = {
        "request": request,
        "release_id": release_id,
        "title": row.get("title") or "",
        "poster": row.get("poster") or "Unknown",
        "posted_at": row.get("posted_at"),
        "total_bytes": row.get("total_bytes"),
        "file_count": row.get("file_count"),
        "completion": row.get("completion_pct"),
        "image_raw": row.get("image_raw"),
        "description": description_formatted,
        "metadata": metadata,
        "nfo_raw": row.get("has_nfo"),
        "par2_raw": row.get("has_par2"),
        "password_protected": row.get("is_passworded"),
    }
    html_content = template.render(context)
    return HTMLResponse(html_content)


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
    subcat: str = "",
    subcats: list[str] | None = None,
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

    # Handle multiple subcats (from list) or single subcat (backward compatible)
    if subcats is None:
        subcats = []
    if subcat:
        subcats = [subcat] + subcats

    if subcats:
        # Build condition for all subcats: spotnet_subcats LIKE '%a0|%' AND spotnet_subcats LIKE '%d0|%'
        for sc in subcats:
            conditions.append("spotnet_subcats LIKE %s")
            params.append(f"%{sc}|%")

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


def is_filter_active(active_subcats: list[str], letter: str, number: int) -> bool:
    """Check if a specific filter (letter, number) is active."""
    code = f"{letter}{number}"
    return code in active_subcats


def _rebuild_params_with_filter(q: str, cat: str, active_subcats: list[str], letter: str, number: int) -> str:
    """Rebuild query string with a new filter added (radio-button style: replaces same letter)."""
    code = f"{letter}{number}"

    # Remove any existing filter with same letter (radio-button behavior)
    new_subcats = [sc for sc in active_subcats if sc[0] != letter]

    # Add new filter
    new_subcats.append(code)
    new_subcats.sort()

    # Build query string
    qs_parts = []
    if q:
        qs_parts.append(f"q={html.escape(q)}")
    if cat:
        qs_parts.append(f"cat={html.escape(cat)}")
    for sc in new_subcats:
        qs_parts.append(f"subcat={sc}")

    return "&".join(qs_parts)


def _remove_filter(q: str, cat: str, active_subcats: list[str], letter: str, number: int) -> str:
    """Rebuild query string with a specific filter removed."""
    code = f"{letter}{number}"
    new_subcats = [sc for sc in active_subcats if sc != code]

    # Build query string
    qs_parts = []
    if q:
        qs_parts.append(f"q={html.escape(q)}")
    if cat:
        qs_parts.append(f"cat={html.escape(cat)}")
    for sc in new_subcats:
        qs_parts.append(f"subcat={sc}")

    return "&".join(qs_parts)


@router.get("/ui")
@router.get("/ui/")
async def search_ui(
    request: Request,
    q: str = Query(""),
    cat: str = Query(""),
    subcat: str = Query(""),
    page: int = Query(1, ge=1),
):
    limit = 50
    offset = (page - 1) * limit
    conn: psycopg.Connection = request.app.state.db_conn
    templates: Jinja2Templates = request.app.state.templates

    # Parse multiple subcat parameters from query string
    active_subcats = request.query_params.getlist("subcat")
    releases, total = _do_search(conn, "search", q, cat, limit, offset, 0, "", "", "", "", subcat, active_subcats)
    pages = max(1, (total + limit - 1) // limit)

    from src.api.newznab import NEWZNAB_ID_MAP

    CAT_NAMES = {
        3: "Audio", 4: "Other", 5: "Ebook", 6: "PC/Apps", 7: "XXX",
        10: "Movies HD", 11: "Movies SD", 20: "TV HD", 21: "TV SD",
        30: "MP3", 31: "Lossless",
    }

    CAT_OPTIONS = [
        ("All categories", ""),
        ("── Movies", "2000"),
        ("   Movies HD", "2040"),
        ("   Movies SD", "2030"),
        ("── TV", "5000"),
        ("   TV HD", "5040"),
        ("   TV SD", "5030"),
        ("── Audio", "3000"),
        ("   MP3", "3010"),
        ("   Lossless", "3040"),
        ("── PC / Apps", "4000"),
        ("── XXX", "6000"),
        ("── Other", "7000"),
        ("   Ebook", "7020"),
    ]

    # Build sidebar filter tree with dynamic counts based on current filters
    dynamic_counts = _compute_dynamic_counts(conn, q, cat, active_subcats, 0)
    filter_tree = _build_filter_tree(dynamic_counts)

    # Render template directly to avoid Jinja2Templates caching issues
    template = templates.get_template("search_ui.html")
    context = {
        "request": request,
        "q": q,
        "cat": cat,
        "total": total,
        "page": page,
        "pages": pages,
        "filter_tree": filter_tree,
        "active_subcats": active_subcats,
        "releases": releases,
        "cat_names": CAT_NAMES,
        "cat_options": CAT_OPTIONS,
        "newznab_id_map": NEWZNAB_ID_MAP,
        "extract_genre": extract_genre_func,
    }
    html_content = template.render(context)
    return HTMLResponse(html_content)


def extract_genre_func(spotnet_cat: int, spotnet_subcats: str) -> str:
    """Extract genre (d-codes) from spotnet_subcats."""
    if not spotnet_subcats:
        return ""

    # Map Spotnet category to hcat (head category for tree lookup)
    spotnet_to_hcat = {0: 0, 1: 1, 2: 0, 3: 3}
    hcat = spotnet_to_hcat.get(spotnet_cat, 0)

    codes = spotnet_subcats.split("|")
    for code in codes:
        if code and code.startswith("d"):
            # Look up genre description using cat2desc
            return cat2desc(hcat, code) or ""
    return ""
