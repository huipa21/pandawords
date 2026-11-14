"""Versioned SQLite artifact contract (not the application's SurrealDB schema)."""

import sqlite3

SCHEMA_VERSION = 2

SCHEMA = """
PRAGMA foreign_keys = ON;
PRAGMA user_version = 2;
CREATE TABLE source (
    name TEXT PRIMARY KEY, metadata TEXT NOT NULL CHECK(json_valid(metadata))
);
CREATE TABLE lemma (
    id TEXT PRIMARY KEY CHECK(json_valid(id)),
    text TEXT NOT NULL, lang TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('word', 'phrase')),
    freq_zipf REAL, cefr TEXT, source TEXT NOT NULL REFERENCES source(name),
    UNIQUE(lang, text)
);
CREATE TABLE lexeme (
    id TEXT PRIMARY KEY CHECK(json_valid(id)),
    lemma_id TEXT NOT NULL REFERENCES lemma(id),
    pos TEXT NOT NULL, etymology_no INTEGER NOT NULL CHECK(etymology_no > 0),
    etymology_text TEXT, source TEXT NOT NULL REFERENCES source(name),
    UNIQUE(lemma_id, pos, etymology_no)
);
CREATE TABLE sense (
    id TEXT PRIMARY KEY CHECK(json_valid(id)),
    lexeme_id TEXT NOT NULL REFERENCES lexeme(id),
    definition TEXT NOT NULL, glosses TEXT NOT NULL CHECK(json_valid(glosses)),
    gloss_zh TEXT, tags TEXT NOT NULL CHECK(json_valid(tags)),
    register TEXT NOT NULL CHECK(json_valid(register)),
    domain TEXT NOT NULL CHECK(json_valid(domain)),
    examples TEXT NOT NULL CHECK(json_valid(examples)),
    rank INTEGER NOT NULL CHECK(rank > 0),
    common INTEGER NOT NULL DEFAULT 0 CHECK(common IN (0, 1)),
    source TEXT NOT NULL REFERENCES source(name), source_id TEXT, lexname TEXT
);
CREATE INDEX sense_lexeme_rank ON sense(lexeme_id, rank, id);
CREATE TABLE pron (
    id TEXT PRIMARY KEY, lexeme_id TEXT NOT NULL REFERENCES lexeme(id),
    accent TEXT CHECK(accent IN ('US', 'UK')), ipa TEXT,
    audio TEXT NOT NULL CHECK(json_valid(audio)),
    tags TEXT NOT NULL CHECK(json_valid(tags)),
    source TEXT NOT NULL REFERENCES source(name)
);
CREATE INDEX pron_lexeme_accent ON pron(lexeme_id, accent);
CREATE TABLE form (
    lexeme_id TEXT NOT NULL REFERENCES lexeme(id), form TEXT NOT NULL,
    tags TEXT NOT NULL CHECK(json_valid(tags)),
    source TEXT NOT NULL REFERENCES source(name),
    PRIMARY KEY(lexeme_id, form, tags)
);
CREATE INDEX form_text ON form(form);
CREATE TABLE form_index (
    form TEXT NOT NULL, lemma_id TEXT NOT NULL REFERENCES lemma(id),
    PRIMARY KEY(form, lemma_id)
);
CREATE INDEX form_index_lemma ON form_index(lemma_id);
CREATE TABLE zh_gloss (
    lexeme_id TEXT NOT NULL REFERENCES lexeme(id), gloss TEXT NOT NULL,
    source TEXT NOT NULL REFERENCES source(name), sense_id TEXT REFERENCES sense(id),
    PRIMARY KEY(lexeme_id, gloss, source)
);
CREATE INDEX zh_gloss_sense ON zh_gloss(sense_id);
CREATE TABLE exam_tag (
    lemma_id TEXT NOT NULL REFERENCES lemma(id), tag TEXT NOT NULL,
    source TEXT NOT NULL REFERENCES source(name),
    PRIMARY KEY(lemma_id, tag, source)
);
CREATE TABLE freq (
    lemma_id TEXT NOT NULL REFERENCES lemma(id),
    zipf REAL, bnc INTEGER, coca INTEGER,
    source TEXT NOT NULL REFERENCES source(name),
    PRIMARY KEY(lemma_id, source)
);
CREATE TABLE relation (
    source_sense_id TEXT NOT NULL REFERENCES sense(id),
    target_sense_id TEXT NOT NULL REFERENCES sense(id),
    type TEXT NOT NULL CHECK(type IN ('synonym', 'antonym', 'hypernym', 'hyponym')),
    source TEXT NOT NULL REFERENCES source(name),
    PRIMARY KEY(source_sense_id, target_sense_id, type, source)
);
CREATE INDEX relation_target ON relation(target_sense_id, type);
CREATE TABLE affix (
    lexeme_id TEXT NOT NULL REFERENCES lexeme(id),
    position INTEGER NOT NULL CHECK(position >= 0), text TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('prefix', 'root', 'suffix', 'infix')),
    source TEXT NOT NULL REFERENCES source(name),
    PRIMARY KEY(lexeme_id, position, source)
);
CREATE TABLE phrase_component (
    phrase_id TEXT NOT NULL REFERENCES lemma(id),
    lexeme_id TEXT NOT NULL REFERENCES lexeme(id),
    position INTEGER NOT NULL CHECK(position >= 0),
    source TEXT NOT NULL REFERENCES source(name),
    PRIMARY KEY(phrase_id, position)
);
CREATE INDEX phrase_component_lexeme ON phrase_component(lexeme_id, phrase_id);
CREATE TABLE phrase_usage (
    phrase_id TEXT NOT NULL REFERENCES lemma(id),
    sense_id TEXT NOT NULL REFERENCES sense(id),
    source TEXT NOT NULL REFERENCES source(name),
    PRIMARY KEY(phrase_id, sense_id, source)
);
"""


def initialize(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)


def validate(connection: sqlite3.Connection) -> None:
    """Raise before publication if a build or enrichment broke artifact integrity."""
    if connection.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
        raise ValueError("unsupported lexicon schema version")
    if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
        raise ValueError("lexicon SQLite integrity check failed")
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise ValueError("lexicon contains dangling references")
    if connection.execute("SELECT 1 FROM sense LIMIT 1").fetchone() is None:
        raise ValueError("lexicon contains no usable senses")
