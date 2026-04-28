-- Groups to scan
CREATE TABLE IF NOT EXISTS newsgroups (
    id             SERIAL PRIMARY KEY,
    name           TEXT NOT NULL UNIQUE,
    low_watermark  BIGINT DEFAULT 0,
    high_watermark BIGINT DEFAULT 0,
    last_scanned   BIGINT DEFAULT 0,
    enabled        BOOLEAN DEFAULT TRUE,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

-- Raw NNTP overview records — never modified after insert
CREATE TABLE IF NOT EXISTS articles (
    id          BIGSERIAL PRIMARY KEY,
    group_id    INTEGER NOT NULL REFERENCES newsgroups(id),
    article_num BIGINT NOT NULL,
    message_id  TEXT NOT NULL UNIQUE,
    subject     TEXT NOT NULL,
    poster      TEXT,
    posted_at   TIMESTAMPTZ,
    bytes       BIGINT DEFAULT 0,
    lines       INTEGER DEFAULT 0,
    refs        TEXT,
    processed   BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS articles_group_processed ON articles(group_id, processed);
CREATE INDEX IF NOT EXISTS articles_message_id ON articles(message_id);
CREATE INDEX IF NOT EXISTS articles_posted_at ON articles(posted_at);

-- A file = one logical binary (e.g. movie.part01.rar) made of N article segments
CREATE TABLE IF NOT EXISTS files (
    id              BIGSERIAL PRIMARY KEY,
    release_id      BIGINT,
    normalized_name TEXT NOT NULL,
    total_parts     INTEGER NOT NULL,
    found_parts     INTEGER NOT NULL DEFAULT 0,
    total_bytes     BIGINT DEFAULT 0,
    is_rar          BOOLEAN DEFAULT FALSE,
    is_par2         BOOLEAN DEFAULT FALSE,
    is_nfo          BOOLEAN DEFAULT FALSE,
    is_sfv          BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS files_release_id ON files(release_id);

-- Many-to-many: articles belong to files
CREATE TABLE IF NOT EXISTS file_articles (
    file_id    BIGINT NOT NULL REFERENCES files(id),
    article_id BIGINT NOT NULL REFERENCES articles(id),
    part_num   INTEGER,
    PRIMARY KEY (file_id, article_id)
);

-- A release = one logical item (album, movie, series episode, etc.)
CREATE TABLE IF NOT EXISTS releases (
    id             BIGSERIAL PRIMARY KEY,
    title          TEXT NOT NULL,
    search_title   TEXT NOT NULL,
    category_id    INTEGER NOT NULL,
    newsgroup_id   INTEGER REFERENCES newsgroups(id),
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
    source         TEXT NOT NULL DEFAULT 'binary',  -- 'binary' or 'spotnet'
    nzb_raw        BYTEA,                           -- pre-assembled NZB for Spotnet releases
    image_raw      BYTEA,                           -- thumbnail image bytes (JPEG/PNG) from alt.binaries.ftd
    description    TEXT,                            -- release description from Spotnet XML
    created_at     TIMESTAMPTZ DEFAULT NOW()
);
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

-- Operational: track scanner progress per group
CREATE TABLE IF NOT EXISTS scan_state (
    group_id     INTEGER PRIMARY KEY REFERENCES newsgroups(id),
    last_article BIGINT DEFAULT 0,
    updated_at   TIMESTAMPTZ DEFAULT NOW()
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

-- Migrations — idempotent, run on every startup via init_db()
ALTER TABLE releases ADD COLUMN IF NOT EXISTS image_raw         BYTEA;
ALTER TABLE releases ADD COLUMN IF NOT EXISTS description       TEXT;
ALTER TABLE releases ADD COLUMN IF NOT EXISTS spotnet_category  INTEGER;
ALTER TABLE releases ADD COLUMN IF NOT EXISTS spotnet_subcats   TEXT;

-- Remove junk binary releases (Spotnet-only going forward)
DELETE FROM releases WHERE source = 'binary';
