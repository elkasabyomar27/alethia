"""Persistent SQLite FTS5 BM25 index over stored inspection segments."""

from datetime import datetime, timezone
import sqlite3

from app.rag.analyzer import ANALYZER_VERSION

RETRIEVER_VERSION = "sqlite-fts5-bm25-v1"


def create_search_schema(connection: sqlite3.Connection):
    """Called inside the document store's migration transaction."""
    statements = [
        """CREATE TABLE lexical_segments (
            id INTEGER PRIMARY KEY,
            segment_id TEXT NOT NULL UNIQUE REFERENCES segments(id) ON DELETE CASCADE,
            tokens TEXT NOT NULL
        )""",
        """CREATE VIRTUAL TABLE segment_search USING fts5(
            tokens, content='lexical_segments', content_rowid='id',
            tokenize='unicode61 remove_diacritics 0'
        )""",
        """CREATE TABLE lexical_config (
            id INTEGER PRIMARY KEY CHECK (id = 1), analyzer_version TEXT NOT NULL, built_at TEXT NOT NULL,
            revision INTEGER NOT NULL DEFAULT 0
        )""",
        """CREATE TRIGGER lexical_insert AFTER INSERT ON lexical_segments BEGIN
            INSERT INTO segment_search(rowid, tokens) VALUES (new.id, new.tokens);
            UPDATE lexical_config SET revision = revision + 1 WHERE id = 1;
        END""",
        """CREATE TRIGGER lexical_delete AFTER DELETE ON lexical_segments BEGIN
            INSERT INTO segment_search(segment_search, rowid, tokens) VALUES ('delete', old.id, old.tokens);
            UPDATE lexical_config SET revision = revision + 1 WHERE id = 1;
        END""",
        """CREATE TRIGGER lexical_update AFTER UPDATE OF tokens ON lexical_segments BEGIN
            INSERT INTO segment_search(segment_search, rowid, tokens) VALUES ('delete', old.id, old.tokens);
            INSERT INTO segment_search(rowid, tokens) VALUES (new.id, new.tokens);
            UPDATE lexical_config SET revision = revision + 1 WHERE id = 1;
        END""",
        """CREATE TRIGGER source_lexical_insert AFTER INSERT ON segments BEGIN
            INSERT INTO lexical_segments(segment_id, tokens) VALUES (new.id, alethia_search_tokens(new.text));
        END""",
        """CREATE TRIGGER source_lexical_update AFTER UPDATE OF text ON segments BEGIN
            UPDATE lexical_segments SET tokens = alethia_search_tokens(new.text) WHERE segment_id = new.id;
        END""",
    ]
    for statement in statements:
        connection.execute(statement)
    connection.execute("INSERT INTO lexical_config(id, analyzer_version, built_at) VALUES (1, ?, ?)",
                       (ANALYZER_VERSION, datetime.now(timezone.utc).isoformat()))
    # Creating triggers does not index existing rows: explicitly backfill once.
    connection.execute("INSERT INTO lexical_segments(segment_id, tokens) SELECT id, alethia_search_tokens(text) FROM segments ORDER BY id")


def ensure_analyzer_version(connection: sqlite3.Connection):
    version = connection.execute("SELECT analyzer_version FROM lexical_config WHERE id = 1").fetchone()[0]
    if version != ANALYZER_VERSION:
        # The caller holds one migration transaction; source identities remain untouched.
        connection.execute("DELETE FROM lexical_segments")
        connection.execute("INSERT INTO lexical_segments(segment_id, tokens) SELECT id, alethia_search_tokens(text) FROM segments ORDER BY id")
        connection.execute("UPDATE lexical_config SET analyzer_version = ?, built_at = ? WHERE id = 1",
                           (ANALYZER_VERSION, datetime.now(timezone.utc).isoformat()))


def index_status(connection: sqlite3.Connection) -> dict:
    row = connection.execute("""SELECT count(*) AS indexed_segments,
        coalesce(sum(tokens != ''), 0) AS searchable_segments,
        count(DISTINCT s.document_id) AS indexed_documents
        FROM lexical_segments l JOIN segments s ON s.id = l.segment_id""").fetchone()
    config = connection.execute("SELECT analyzer_version, built_at, revision FROM lexical_config WHERE id = 1").fetchone()
    return {
        **dict(row), "state": "ready" if row["searchable_segments"] else "empty",
        "method": "bm25", "retriever_version": RETRIEVER_VERSION,
        "analyzer_version": config["analyzer_version"], "built_at": config["built_at"],
        "index_revision": config["revision"],
        "sqlite_version": sqlite3.sqlite_version, "k1": 1.2, "b": 0.75,
        "chunking": "stored-character-segments-v1", "match_mode": "any_term",
        "score_meaning": "Positive SQLite FTS5 BM25 ranking score; not confidence or answer correctness.",
    }


def search_rows(connection: sqlite3.Connection, terms: list[str], limit: int) -> list[dict]:
    # Only analyzed words enter MATCH, quoted individually; user operators never become syntax.
    expression = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
    rows = connection.execute("""
        SELECT s.*, d.filename, d.format, d.revision, d.content_hash, d.processor_version,
               d.warnings_json, -bm25(segment_search) AS score
        FROM segment_search
        JOIN lexical_segments l ON l.id = segment_search.rowid
        JOIN segments s ON s.id = l.segment_id
        JOIN documents d ON d.id = s.document_id
        WHERE segment_search MATCH ?
        ORDER BY bm25(segment_search) ASC, d.content_hash ASC, s.ordinal ASC, s.id ASC
        LIMIT ?
    """, (expression, limit)).fetchall()
    return [dict(row) for row in rows]
