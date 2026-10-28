PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    homepage TEXT NOT NULL,
    authority TEXT NOT NULL DEFAULT 'reference',
    license_name TEXT,
    license_url TEXT,
    redistribution TEXT NOT NULL DEFAULT 'unknown',
    access_method TEXT NOT NULL DEFAULT 'manual',
    formats TEXT NOT NULL DEFAULT '[]',
    release_date TEXT,
    last_checked TEXT,
    update_url TEXT,
    notes TEXT,
    active_release_id INTEGER,
    FOREIGN KEY(active_release_id) REFERENCES source_releases(id)
);

CREATE TABLE IF NOT EXISTS source_releases (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    version TEXT NOT NULL,
    release_date TEXT,
    acquired_at TEXT NOT NULL,
    checksum_sha256 TEXT,
    artifact_path TEXT,
    import_format TEXT NOT NULL,
    record_count INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(source_id, version, checksum_sha256)
);

CREATE TABLE IF NOT EXISTS concepts (
    id INTEGER PRIMARY KEY,
    release_id INTEGER NOT NULL REFERENCES source_releases(id) ON DELETE CASCADE,
    source_record_id TEXT,
    domain TEXT,
    subdomain TEXT,
    definition_en TEXT,
    definition_lv TEXT,
    status TEXT NOT NULL DEFAULT 'unverified'
        CHECK(status IN ('recommended','acceptable','deprecated','unverified')),
    approval TEXT,
    source_note TEXT,
    raw_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS concepts_release ON concepts(release_id);
CREATE INDEX IF NOT EXISTS concepts_domain ON concepts(domain);

CREATE TABLE IF NOT EXISTS terms (
    id INTEGER PRIMARY KEY,
    concept_id INTEGER NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    language TEXT NOT NULL CHECK(language IN ('en','lv')),
    text TEXT NOT NULL,
    normalized TEXT NOT NULL,
    is_preferred INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'unverified'
        CHECK(status IN ('recommended','acceptable','deprecated','unverified')),
    part_of_speech TEXT,
    grammatical_gender TEXT,
    grammatical_number TEXT,
    grammar_json TEXT NOT NULL DEFAULT '{}',
    usage_note TEXT
);

CREATE INDEX IF NOT EXISTS terms_normalized ON terms(language, normalized);
CREATE INDEX IF NOT EXISTS terms_concept ON terms(concept_id);

CREATE VIRTUAL TABLE IF NOT EXISTS terms_fts USING fts5(
    text,
    normalized,
    language UNINDEXED,
    content='terms',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 0'
);

CREATE TRIGGER IF NOT EXISTS terms_ai AFTER INSERT ON terms BEGIN
    INSERT INTO terms_fts(rowid,text,normalized,language)
    VALUES (new.id,new.text,new.normalized,new.language);
END;
CREATE TRIGGER IF NOT EXISTS terms_ad AFTER DELETE ON terms BEGIN
    INSERT INTO terms_fts(terms_fts,rowid,text,normalized,language)
    VALUES ('delete',old.id,old.text,old.normalized,old.language);
END;
CREATE TRIGGER IF NOT EXISTS terms_au AFTER UPDATE ON terms BEGIN
    INSERT INTO terms_fts(terms_fts,rowid,text,normalized,language)
    VALUES ('delete',old.id,old.text,old.normalized,old.language);
    INSERT INTO terms_fts(rowid,text,normalized,language)
    VALUES (new.id,new.text,new.normalized,new.language);
END;

CREATE TABLE IF NOT EXISTS examples (
    id INTEGER PRIMARY KEY,
    concept_id INTEGER REFERENCES concepts(id) ON DELETE CASCADE,
    release_id INTEGER NOT NULL REFERENCES source_releases(id) ON DELETE CASCADE,
    source_language TEXT NOT NULL,
    target_language TEXT NOT NULL,
    source_text TEXT NOT NULL,
    target_text TEXT NOT NULL,
    context TEXT,
    document_id TEXT
);

CREATE TABLE IF NOT EXISTS wordforms (
    id INTEGER PRIMARY KEY,
    release_id INTEGER NOT NULL REFERENCES source_releases(id) ON DELETE CASCADE,
    lemma TEXT NOT NULL,
    form TEXT NOT NULL,
    normalized TEXT NOT NULL,
    attributes_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS wordforms_normalized ON wordforms(normalized);
CREATE INDEX IF NOT EXISTS wordforms_lemma ON wordforms(lemma);

CREATE VIRTUAL TABLE IF NOT EXISTS examples_fts USING fts5(
    source_text,
    target_text,
    context,
    content='examples',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 0'
);
CREATE TRIGGER IF NOT EXISTS examples_ai AFTER INSERT ON examples BEGIN
    INSERT INTO examples_fts(rowid,source_text,target_text,context)
    VALUES (new.id,new.source_text,new.target_text,new.context);
END;
CREATE TRIGGER IF NOT EXISTS examples_ad AFTER DELETE ON examples BEGIN
    INSERT INTO examples_fts(examples_fts,rowid,source_text,target_text,context)
    VALUES ('delete',old.id,old.source_text,old.target_text,old.context);
END;

CREATE TABLE IF NOT EXISTS glossary_overrides (
    id INTEGER PRIMARY KEY,
    source_language TEXT NOT NULL CHECK(source_language IN ('en','lv')),
    target_language TEXT NOT NULL CHECK(target_language IN ('en','lv')),
    source_text TEXT NOT NULL,
    source_normalized TEXT NOT NULL,
    target_text TEXT NOT NULL,
    domain TEXT NOT NULL DEFAULT '',
    context_pattern TEXT,
    note TEXT,
    approved_at TEXT NOT NULL,
    UNIQUE(source_language, target_language, source_normalized, domain)
);

CREATE TABLE IF NOT EXISTS translation_history (
    id INTEGER PRIMARY KEY,
    document_id TEXT,
    source_language TEXT NOT NULL,
    target_language TEXT NOT NULL,
    source_text TEXT NOT NULL,
    target_text TEXT NOT NULL,
    choices_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS online_cache (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    operation TEXT NOT NULL,
    query TEXT NOT NULL,
    response_json TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    expires_at TEXT,
    UNIQUE(source_id, operation, query)
);

CREATE TABLE IF NOT EXISTS update_events (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    old_release_id INTEGER,
    new_release_id INTEGER,
    action TEXT NOT NULL,
    summary_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

