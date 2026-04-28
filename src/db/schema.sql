-- Drop unused tables from legacy Usenet indexing (safe: no data, replaced by Spotnet-only design)
DROP TABLE IF EXISTS file_articles CASCADE;
DROP TABLE IF EXISTS files CASCADE;
DROP TABLE IF EXISTS articles CASCADE;

-- Groups being scanned (Spotnet-only)
CREATE TABLE IF NOT EXISTS newsgroups (
    id             SERIAL PRIMARY KEY,
    name           TEXT NOT NULL UNIQUE,
    low_watermark  BIGINT DEFAULT 0,
    high_watermark BIGINT DEFAULT 0,
    last_scanned   BIGINT DEFAULT 0,
    enabled        BOOLEAN DEFAULT TRUE,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

-- Operational: track scanner progress per group
CREATE TABLE IF NOT EXISTS scan_state (
    group_id     INTEGER PRIMARY KEY REFERENCES newsgroups(id),
    last_article BIGINT DEFAULT 0,
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);

-- A release = one logical item (album, movie, series episode, etc.)
CREATE TABLE IF NOT EXISTS releases (
    id             BIGSERIAL PRIMARY KEY,
    messageid      TEXT UNIQUE,                     -- Usenet Message-ID for SpotWeb-compatible URLs
    title          TEXT NOT NULL,
    search_title   TEXT NOT NULL,
    category_id    INTEGER NOT NULL,
    poster         TEXT,
    posted_at      TIMESTAMPTZ,
    total_bytes    BIGINT DEFAULT 0,
    file_count     INTEGER DEFAULT 0,
    completion_pct NUMERIC(5,2) DEFAULT 0,
    has_nfo        BOOLEAN DEFAULT FALSE,
    has_par2       BOOLEAN DEFAULT FALSE,
    is_passworded  BOOLEAN DEFAULT FALSE,
    nfo_text       TEXT,
    search_vector  TSVECTOR,
    source         TEXT NOT NULL DEFAULT 'spotnet', -- Spotnet-only design
    nzb_raw        BYTEA,                           -- pre-assembled NZB from Spotnet XML
    image_raw      BYTEA,                           -- thumbnail image bytes (JPEG/PNG) from alt.binaries.ftd
    description    TEXT,                            -- release description from Spotnet XML
    spotnet_category INTEGER,
    spotnet_subcats  TEXT,
    nzb_segments     TEXT,
    image_segments   TEXT,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS releases_messageid ON releases(messageid);
CREATE INDEX IF NOT EXISTS releases_category ON releases(category_id);
CREATE INDEX IF NOT EXISTS releases_posted_at ON releases(posted_at DESC);
CREATE INDEX IF NOT EXISTS releases_search ON releases USING GIN(search_vector);

-- Categories
CREATE TABLE IF NOT EXISTS categories (
    id         INTEGER PRIMARY KEY,
    parent_id  INTEGER REFERENCES categories(id),
    name       TEXT NOT NULL,
    newznab_id INTEGER
);


-- Seed categories (idempotent)
-- Internal IDs match Spotnet scanner category_id values
INSERT INTO categories (id, parent_id, name, newznab_id) VALUES
  -- top-level buckets (scanner uses these as category_id)
  (3,  NULL, 'Audio',       3000),
  (4,  NULL, 'Other',       7000),
  (5,  NULL, 'Ebook',       7020),
  (6,  NULL, 'PC/Apps',     4000),
  (7,  NULL, 'XXX',         6000),
  -- video sub-types
  (10, NULL, 'Movies HD',   2040),
  (11, NULL, 'Movies SD',   2030),
  (20, NULL, 'TV HD',       5040),
  (21, NULL, 'TV SD',       5030),
  -- audio sub-types
  (30, 3,    'MP3',         3010),
  (31, 3,    'Lossless',    3040)
ON CONFLICT (id) DO NOTHING;

