# py_spotnet_index — Project Log

> **For Claude sessions**: This file is the canonical progress log.
> Read it at the start of every session and update it before finishing.
> Any session may edit this file freely to record progress, blockers, or next steps.

---

## Spotnet Architecture

Three groups, three roles:

| Group | Role |
|-------|------|
| `free.pt` | Spot headers — XML metadata (title, category, description, image/NZB segment IDs) in `X-XML:` MIME headers |
| `free.usenet` | Comments — not scanned |
| `alt.binaries.ftd` | Binary data — NZB segments AND image segments posted here; fetched on demand by message-ID |

Scanner only scans `free.pt`. NZB and image bytes are fetched from `alt.binaries.ftd` at scan time via message-IDs listed in the spot XML.

---

## Stack

| Service  | Image / command                        | Port  |
|----------|----------------------------------------|-------|
| db       | postgres:16-alpine, init from schema.sql | 5432 |
| scanner  | `python -m src.scanner.main`           | —     |
| api      | `uvicorn src.api.main:app`             | 8080  |

**Credentials** (`.env`):
- `DATABASE_URL=postgresql://indexer:secret@db:5432/usenet_index`
- `NNTP_HOST=<your-nntp-provider>` port=563 SSL=True
- `MAX_AGE_DAYS=3`

**Important**: no source volume mounts — always `docker compose build <service>` after code changes.

---

## What Works

- Docker Compose stack: db / scanner / api
- Scanner bisects `free.pt` on first run, then walks forward; sleeps 5s if not caught up, 300s when up to date
- Parses `X-XML:` headers, assembles NZB + image from `alt.binaries.ftd`, stores in DB
- FastAPI Newznab API at `http://localhost:8080` — `/api?t=caps`, `/api?t=search`, `/ui`
- `/image/<id>` — serves JPEG/PNG thumbnails; auto-detects format
- Newznab search results include `coverurl` attr and `<description>` with `<img>` tag
- `/ui` shows thumbnails, description snippet, correct size, category name
- NZB download filename uses spot title (e.g. `Bringing History to Life - Incredible Weapons, 2026.nzb`)
- Full Newznab category tree: Console/Movies/Audio/PC/TV/XXX/Other with all subcategories
- ~640 spots from the last 3 days on a fresh DB

---

## Completed This Session

### 1. Image support (`src/scanner/spotnet.py`)

- Added `image_segments: list[str]` to `SpotnetPost` dataclass
- `parse_spotnet_body()` extracts `<Image><Segment>` message-IDs from the spot XML
- Refactored: shared `_fetch_segments()` + `_decode_spotnet_binary()` helpers used by both NZB and image
- Added `assemble_image()` — identical path to `assemble_nzb()`, returns JPEG/PNG bytes

### 2. Store image + description (`src/scanner/main.py`, `src/db/schema.sql`)

- Added `image_raw BYTEA` and `description TEXT` columns to `releases`
- Scanner calls `assemble_image()` alongside `assemble_nzb()` and stores both

### 3. API image endpoint + Newznab metadata (`src/api/routes.py`, `src/api/newznab.py`)

- `GET /image/{release_id}` — streams `image_raw` bytes, auto-detects JPEG vs PNG
- Search SELECT includes `(image_raw IS NOT NULL) AS has_image` and `description`
- Newznab response includes `newznab:attr name="coverurl"` and `<description>` with `<img>` tag
- `/ui` shows `<img height="80">` thumbnails, description snippet, correct size, category name

### 4. Scanner reliability fixes (`src/scanner/main.py`, `src/scanner/nntp.py`)

- **Bisect bug**: `_bisect_cutoff` returned `hi` instead of `lo` — caused scanner to start from the very last article, missing the entire window. Fixed to return `lo`; main loop date-filters the converged range.
- **Typo**: `nntplib.NNTPTemporaryFailure` → `nntplib.NNTPTemporaryError` (caused bisect to crash silently)
- Scanner now logs per-article progress: fetching, NZB/image assembled, stored, parse failures
- `scan_spotnet_group()` returns `bool` (caught up?); main loop sleeps 5s if not caught up, 300s when done

### 5. Metadata fixes (`src/scanner/spotnet.py`, `src/api/routes.py`, `src/api/newznab.py`)

- **File size**: Spotnet uses `<Size>` not `<FileSize>` — fixed to try both
- **NZB filename**: uses sanitised spot title, not `release-N.nzb`

### 6. Correct Newznab category tree

Full category set matching the Newznab standard:

| Internal ID | Name | Newznab ID |
|-------------|------|------------|
| 3 | Audio | 3000 |
| 4 | Other | 7000 |
| 5 | Ebook | 7020 |
| 6 | PC/Apps | 4000 |
| 7 | XXX | 6000 |
| 10 | Movies HD | 2040 |
| 11 | Movies SD | 2030 |
| 20 | TV HD | 5040 |
| 21 | TV SD | 5030 |
| 30 | MP3 | 3010 |
| 31 | Lossless | 3040 |

Spotnet XML category codes: 0=Video, 1=Audio, 2=Image/Ebook, 3=Applications

### 7. Previous sessions

- NZB assembly fixed: `_unspecial_zip_str()` + `zlib.decompress(raw, -15)` (raw deflate)
- `b"".join(body_lines)` not `b"\n".join(...)` — NNTP line splits are transport artefacts

### 8. Store categories as raw numbers; decode in API/UI

Created `src/scanner/categories.py` — full Python port of `spotweb/SpotCategories.php`:
- `HEAD_CATEGORIES`: 0=Image, 1=Sound, 2=Games, 3=Applications
- `CATEGORIES`: full tree mapping (hcat, type, number) → name for Format/Source/Language/Genre
- `SHORTCAT`: abbreviated display names (DivX, WMV, MPG, MP3, etc.)
- Functions: `cat2desc()`, `cat2short_desc()`, `create_subcat_z()` for z-category logic

Database schema extended (`src/db/schema.sql`):
- Added `spotnet_category INTEGER` — raw 0-3 from XML `<Category>` tag
- Added `spotnet_subcats TEXT` — pipe-separated codes like "a0|b3|c1|d4"

Scanner updated (`src/scanner/spotnet.py`, `src/scanner/main.py`):
- `SpotnetPost` dataclass includes `spotnet_category` and `spotnet_subcats` fields
- Parser extracts raw category integer and builds full subcat string from all `<SubCat>` elements
- INSERT statement includes both: `category_id` (high-level Newznab) + raw `spotnet_category`/`spotnet_subcats`
- Enables detailed category lookups in API layer without re-parsing XML

---

## In Progress

### 9. Category Decoding in Newznab Responses (WIP)

- Added `spotnet_to_newznab_categories(spotnet_cat, subcats)` — maps Spotnet XML categories to Newznab IDs
  - Spotnet XML: 0=Video, 1=Audio, 2=Image/Ebook, 3=Applications → Newznab: 2000, 3000, 7000, 4000
  - Checks subcategories for refinements (PDF → 7020 Ebook, FLAC → 3040 Lossless, etc.)
- Added `spotnet_category_path(spotnet_cat, subcats)` — builds human-readable paths like "Image > PDF"
- Updated search query (`src/api/routes.py`) to fetch spotnet_category and spotnet_subcats
- Updated Newznab response builder (`src/api/newznab.py`) to:
  - Output human-readable `<category>` element
  - Output multiple `<newznab:attr name="category">` attributes
  - Fallback to internal category_id if spotnet_category is NULL

**Blocker**: spotnet_category values appear incorrect or NULL:
- XXX/adult videos store as spotnet_category=1 (Audio) instead of expected 0 (Video)
- De Telegraaf (PDF) stores as spotnet_category=1 (Audio) instead of expected 2 (Image/Ebook)
- Some records have spotnet_category=NULL
- **Next**: Debug the XML parsing in `src/scanner/spotnet.py` to verify correct extraction of `<Category>` tag

## Next Steps

- Debug and fix spotnet_category parsing (may be NNTP source data issue or parser bug)
- XXX detection: flag spots with `spotnet_category=0` + erotica subcategory codes (d23–d26, d72–d89)
- UI: add subcategory display (Format, Source, Genre, etc.) to search results
- Consider: `/ui` pagination, filter/search by decoded category fields
- Consider: on-demand NZB assembly for expired segment windows (nzb_raw = NULL)

---

## Key Files

| File | Purpose |
|------|---------|
| `src/scanner/categories.py` | **NEW** — `SpotCategories` decoder (Python port from PHP); `cat2desc()`, `cat2short_desc()`, `create_subcat_z()` |
| `src/scanner/spotnet.py` | `parse_spotnet_body()`, `assemble_nzb()`, `assemble_image()`, shared helpers |
| `src/scanner/main.py` | `scan_spotnet_group()` — bisect, fetch, parse, assemble NZB + image |
| `src/scanner/nntp.py` | NNTP client — `xover()`, `fetch_article()`, `xover_batched()` |
| `src/api/routes.py` | Newznab dispatcher, `/image/<id>` endpoint, `/ui` with thumbnails |
| `src/api/newznab.py` | RSS/Newznab XML builder — full category tree, coverurl + description HTML |
| `src/api/nzb.py` | NZB delivery — spotnet returns `nzb_raw` |
| `src/db/schema.sql` | DB schema + idempotent migrations |
| `src/config.py` | Config loader — NNTP, database, scanner, API config |
| `docker-compose.yml` | Stack definition (db, scanner, api) |
| `config.toml` | NNTP + scanner config |
| `.env` | Credentials + `MAX_AGE_DAYS` override |

---

## Known Gotchas

- psycopg3 (not psycopg2): use `with conn.cursor() as cur: cur.executemany(...)` — no `conn.executemany()`
- `row_factory` goes on `cursor()`, not `execute()`
- Column is `refs` (not `references` — reserved keyword)
- Python 3.12, nntplib deprecated but functional
- Spotnet segment bodies: **no yEnc**, custom `=C/=B/=A/=D` escaping + raw deflate
- Image and NZB use **identical** encoding — same `_fetch_segments` + `_decode_spotnet_binary` path
- `_bisect_cutoff` returns `lo` (not `hi`) — the converged range [lo, hi] is date-filtered in the scan loop
- SpotWeb reference: `spotweb/spotweb` on GitHub — `Services_Nntp_SpotReading.php` + `Services_Format_Util.php`
