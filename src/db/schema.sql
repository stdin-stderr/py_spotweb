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

-- TMDB metadata cache — one row per TMDB ID (movie or TV show)
CREATE TABLE IF NOT EXISTS tmdb_metadata (
    tmdb_id        INTEGER PRIMARY KEY,
    tmdb_type      TEXT NOT NULL,
    title          TEXT NOT NULL,
    original_title TEXT,
    overview       TEXT,
    poster_path    TEXT,
    release_year   INTEGER,
    rating         NUMERIC(3,1),
    vote_count     INTEGER,
    fetched_at     TIMESTAMPTZ DEFAULT NOW()
);

-- A release = one logical item (album, movie, series episode, etc.)
CREATE TABLE IF NOT EXISTS releases (
    id               BIGSERIAL PRIMARY KEY,
    messageid        TEXT UNIQUE,
    title            TEXT NOT NULL,
    search_title     TEXT NOT NULL,
    category_id      INTEGER NOT NULL,
    poster           TEXT,
    posted_at        TIMESTAMPTZ,
    total_bytes      BIGINT DEFAULT 0,
    file_count       INTEGER DEFAULT 0,
    completion_pct   NUMERIC(5,2) DEFAULT 0,
    has_nfo          BOOLEAN DEFAULT FALSE,
    has_par2         BOOLEAN DEFAULT FALSE,
    is_passworded    BOOLEAN DEFAULT FALSE,
    nfo_text         TEXT,
    search_vector    TSVECTOR,
    source           TEXT NOT NULL DEFAULT 'spotnet',
    nzb_raw          BYTEA,
    image_raw        BYTEA,
    description      TEXT,
    spotnet_category INTEGER,
    spotnet_subcats  TEXT,
    nzb_segments     TEXT,
    image_segments   TEXT,
    spotnet_key      INTEGER,
    spotnet_tag      TEXT,
    spotnet_created  INTEGER,
    spotnet_website  TEXT,
    spotnet_signature TEXT,
    spotnet_verified  BOOLEAN DEFAULT FALSE,
    spotnet_spotter_id TEXT,
    tmdb_id           INTEGER REFERENCES tmdb_metadata(tmdb_id),
    tmdb_year         INTEGER,
    tmdb_season       INTEGER,
    tmdb_episode      INTEGER,
    tmdb_matched_at   TIMESTAMPTZ,
    tmdb_match_failed BOOLEAN DEFAULT FALSE,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS releases_messageid    ON releases(messageid);
CREATE INDEX IF NOT EXISTS releases_category     ON releases(category_id);
CREATE INDEX IF NOT EXISTS releases_posted_at    ON releases(posted_at DESC);
CREATE INDEX IF NOT EXISTS releases_search       ON releases USING GIN(search_vector);
CREATE INDEX IF NOT EXISTS releases_tmdb_id      ON releases(tmdb_id) WHERE tmdb_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS releases_tmdb_unmatched
    ON releases(id)
    WHERE spotnet_category = 0
      AND tmdb_matched_at IS NULL
      AND (tmdb_match_failed IS NULL OR tmdb_match_failed = FALSE);

-- Categories
CREATE TABLE IF NOT EXISTS categories (
    id         INTEGER PRIMARY KEY,
    parent_id  INTEGER REFERENCES categories(id),
    name       TEXT NOT NULL,
    newznab_id INTEGER
);

-- Seed categories (idempotent)
INSERT INTO categories (id, parent_id, name, newznab_id) VALUES
  (3,  NULL, 'Audio',       3000),
  (4,  NULL, 'Other',       7000),
  (5,  NULL, 'Ebook',       7020),
  (6,  NULL, 'PC/Apps',     4000),
  (7,  NULL, 'XXX',         6000),
  (10, NULL, 'Movies HD',   2040),
  (11, NULL, 'Movies SD',   2030),
  (20, NULL, 'TV HD',       5040),
  (21, NULL, 'TV SD',       5030),
  (30, 3,    'MP3',         3010),
  (31, 3,    'Lossless',    3040)
ON CONFLICT (id) DO NOTHING;
