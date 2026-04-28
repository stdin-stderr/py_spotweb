# py_spotweb — Spotnet Indexer

A Python-based Usenet spotnet indexer that scans Spotnet posts, extracts metadata and images, and provides a Newznab-compatible API for searching and downloading NZBs.

## Overview

This application indexes posts from Usenet's Spotnet community, assembles downloadable NZBs and thumbnail images, and exposes a Newznab API for integration with media center applications (Sonarr, Radarr, etc.).

### Spotnet Architecture

Spotnet posts are distributed across three Usenet groups with distinct roles:

| Group | Role |
|-------|------|
| `free.pt` | **Spot headers** — XML metadata (title, category, description) in `X-XML:` MIME headers |
| `free.usenet` | Comments — not scanned |
| `alt.binaries.ftd` | **Binary data** — NZB segments and image segments; fetched on demand by message-ID |

The scanner only scans `free.pt` for new posts. NZB and image bytes are assembled from segments posted in `alt.binaries.ftd` and stored in the database.

## Technology Stack

| Service | Technology |
|---------|-----------|
| Database | PostgreSQL 16 (Alpine) |
| Scanner | Python 3.12 |
| API | FastAPI + Uvicorn |
| NNTP Client | Python nntplib (with SSL) |
| Packaging | Docker Compose |

**Note**: You'll need access to an NNTP provider that carries the `free.pt` and `alt.binaries.ftd` groups.

## Quick Start

### Prerequisites

- Docker and Docker Compose
- `.env` file with credentials (see [Configuration](#configuration))

### Run the Stack

```bash
docker compose up --build
```

This starts:
- `db` — PostgreSQL database (port 5432)
- `scanner` — Scanner daemon continuously indexing new spots
- `api` — FastAPI Newznab endpoint (port 8080)

### Access the Application

- **Newznab API**: http://localhost:8080/api
- **Web UI**: http://localhost:8080/ui
- **Image endpoint**: http://localhost:8080/image/{release_id}

## Components

### Scanner (`src/scanner/`)

Continuously monitors `free.pt` for new spotnet posts and indexes them into the database.

**Process**:
1. **Bisect** — On first run, binary-searches the article range to find posts matching `MAX_AGE_DAYS`
2. **Scan** — Fetches article headers, parses Spotnet XML metadata from `X-XML:` MIME headers
3. **Assemble** — Fetches NZB and image segments from `alt.binaries.ftd` and decompresses them
4. **Store** — Inserts release metadata, NZB bytes, and image bytes into the database

**Key Files**:
- `main.py` — Main scan loop with bisect + forward walk
- `spotnet.py` — XML parsing and segment assembly logic
- `nntp.py` — NNTP client wrapper
- `categories.py` — Spotnet category decoder (maps Spotnet codes to Newznab categories)

**Configuration** (`config.toml`):
```toml
[nntp]
host = "your-nntp-provider.com"
port = 563
ssl = true

[scanner]
sleep_interval_active = 5      # seconds when catching up
sleep_interval_idle = 300      # seconds when up to date
```

### API (`src/api/`)

FastAPI application providing a Newznab-compatible search API and web UI.

**Endpoints**:

| Endpoint | Purpose |
|----------|---------|
| `GET /api?t=caps` | Newznab capabilities (supported categories) |
| `GET /api?t=search` | Search for spots by query or category |
| `GET /image/{release_id}` | Serve thumbnail image (auto-detects JPEG/PNG) |
| `GET /download/{release_id}` | Download NZB file |
| `GET /ui` | Web UI with thumbnail gallery and search |

**Example Search**:
```
GET /api?t=search&q=Breaking+Bad&cat=5030
```

Returns RSS feed with Newznab extensions:
- `newznab:attr name="coverurl"` — thumbnail URL
- `newznab:attr name="category"` — decoded category (e.g., "TV > SD")
- `<description>` — snippet with embedded thumbnail

**Key Files**:
- `routes.py` — FastAPI route handlers and database queries
- `newznab.py` — RSS/Newznab XML response builder
- `nzb.py` — NZB file delivery

### Database (`src/db/`)

PostgreSQL schema storing releases, segments, and metadata.

**Tables**:

- `releases` — Indexed spots with metadata, thumbnails, descriptions
  - `id` — Primary key
  - `title` — Spot title
  - `description` — Parsed description text
  - `category_id` — Newznab category (e.g., 2040 for Movies HD)
  - `spotnet_category` — Raw category from XML (0=Video, 1=Audio, 2=Image, 3=Apps)
  - `spotnet_subcats` — Pipe-separated subcategory codes (e.g., "a0|b3|c1|d4")
  - `image_raw` — JPEG/PNG thumbnail bytes (BYTEA)
  - `nzb_raw` — Assembled NZB bytes (BYTEA)
  - `size` — Total file size
  - `article_num` — Source article number in free.pt
  - `posted` — Timestamp

- `segments` — Individual NZB and image segments
  - `release_id` — Foreign key to releases
  - `message_id` — Usenet message-ID for fetching from alt.binaries.ftd
  - `segment_type` — "nzb" or "image"
  - `part_num` — Segment sequence number
  - `bytes` — Compressed segment data

## Configuration

### Environment Variables (`.env`)

```bash
# Database connection
DATABASE_URL=postgresql://indexer:secret@db:5432/usenet_index

# NNTP server
NNTP_HOST=your-nntp-provider.com
NNTP_PORT=563
NNTP_SSL=True

# Scanner max age for initial bisect
MAX_AGE_DAYS=3
```

### NNTP Server

Configure your NNTP provider:

1. Update `NNTP_HOST` in `.env` with your provider's hostname
2. Set `NNTP_PORT` and `NNTP_SSL` as needed
3. Ensure the server carries `free.pt` and `alt.binaries.ftd`
4. Rebuild: `docker compose build scanner`

## Key Features

✅ **Full Spotnet indexing** — Parses XML metadata, extracts categories and descriptions  
✅ **NZB assembly** — Fetches and decompresses multi-part segments with custom encoding  
✅ **Thumbnail extraction** — Auto-detects and serves JPEG or PNG images  
✅ **Newznab compliance** — Full category tree + coverurl metadata for Sonarr/Radarr  
✅ **Web UI** — Search with thumbnails, snippets, and download links  
✅ **Scalable scanning** — Bisect + forward walk design handles years of backlog  
✅ **Reliable NNTP** — Handles temporary failures, segment timeouts, parse errors  

## Known Gotchas

### Spotnet Encoding
- Segments use **custom escaping** (`=C/=B/=A/=D`), not yEnc
- Compression is **raw deflate** (no zlib header) — decompress with `zlib.decompress(data, -15)`
- Both NZB and image use identical encoding/decompression path

### Database
- Uses psycopg3 (not psycopg2) — `cursor()` from connection, not `conn.executemany()`
- Column `refs` is reserved keyword (not `references`)
- `row_factory` goes on `cursor()`, not on `execute()`

### Scanner
- `_bisect_cutoff()` returns `lo` (converged lower bound), not `hi`
- Main loop date-filters the converged range `[lo, hi]` to avoid duplicates
- Scanner sleeps 5s if catching up, 300s when up to date

### Categories
- Spotnet XML stores raw category codes: 0=Video, 1=Audio, 2=Image, 3=Applications
- Mapping to Newznab IDs (2000, 3000, 7000, 4000) happens in API layer
- Subcategories store as pipe-separated codes (e.g., "a0|b3") — decoded at query time

## Troubleshooting

### Scanner not progressing
- Check NNTP connectivity: `docker logs <container-id> scanner`
- Verify `MAX_AGE_DAYS` is set correctly in `.env`
- Confirm `free.pt` and `alt.binaries.ftd` groups exist on your NNTP server

### Missing images or NZBs
- Segments may have expired on the NNTP server (typical retention: 1000–2000 days)
- `nzb_raw` or `image_raw = NULL` indicates assembly failed; check scanner logs

### API returns no results
- Ensure scanner has completed initial bisect (check logs: "Bisect complete")
- Verify database connectivity: `docker logs <container-id> db`
- Check query parameters: `/api?t=search&q=<term>`

## Project Layout

```
py_spotweb/
├── src/
│   ├── scanner/
│   │   ├── main.py           # Scan loop, bisect, article processing
│   │   ├── spotnet.py        # XML parsing, segment assembly
│   │   ├── nntp.py           # NNTP client
│   │   └── categories.py     # Spotnet → Newznab category mapping
│   ├── api/
│   │   ├── main.py           # FastAPI app
│   │   ├── routes.py         # Endpoints: search, image, download, ui
│   │   ├── newznab.py        # RSS/Newznab XML builder
│   │   └── nzb.py            # NZB file delivery
│   ├── db/
│   │   ├── schema.sql        # PostgreSQL schema
│   │   └── migrations.sql    # Schema updates
│   └── config.py             # Config loader
├── docker-compose.yml        # Service definitions
├── Dockerfile                # Python image
├── config.toml              # NNTP + scanner config
├── pyproject.toml           # Python dependencies
├── .env                     # Credentials (not in git)
└── README.md               # This file
```

## Development

### Local Setup

```bash
# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r pyproject.toml

# Run tests
pytest

# Run scanner locally (requires .env + database)
python -m src.scanner.main

# Run API locally
uvicorn src.api.main:app --reload
```

### Rebuilding Services

After code changes, rebuild the affected service:

```bash
docker compose build scanner    # Rebuild scanner image
docker compose build api        # Rebuild API image
docker compose up               # Restart services
```

**Note**: No source volume mounts — always rebuild after code changes.

## References

- **Spotnet Reference**: [spotweb/spotweb](https://github.com/spotweb/spotweb) — Original PHP implementation
  - `Services_Nntp_SpotReading.php` — NNTP scanning logic
  - `Services_Format_Util.php` — Encoding/decoding utilities
  - `SpotCategories.php` — Category mapping (ported to `src/scanner/categories.py`)
- **Newznab Standard**: [Newznab API](https://www.newznab.com/wiki/index.php/API)
- **Python nntplib**: [nntplib documentation](https://docs.python.org/3/library/nntplib.html)

## License

See LICENSE file.
