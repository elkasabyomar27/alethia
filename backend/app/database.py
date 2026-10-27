"""Small transactional SQLite document store; all data stays in the local workspace."""

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from app.ingestion import ExtractedDocument, IngestionError
from app.rag.analyzer import index_text
from app.rag.lexical import create_search_schema, ensure_analyzer_version, index_status, search_rows

MAX_DOCUMENTS = 100


class DocumentStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > 3:
                raise RuntimeError("This database needs a newer ALETHIA version.")
            schema = ["""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    format TEXT NOT NULL,
                    content_hash TEXT NOT NULL UNIQUE,
                    text TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    revision INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    processor_version TEXT NOT NULL
                )""", """
                CREATE TABLE IF NOT EXISTS segments (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    ordinal INTEGER NOT NULL,
                    section TEXT NOT NULL,
                    text TEXT NOT NULL,
                    start_char INTEGER NOT NULL,
                    end_char INTEGER NOT NULL,
                    start_line INTEGER NOT NULL,
                    end_line INTEGER NOT NULL
                )""", "CREATE INDEX IF NOT EXISTS segments_document_id ON segments(document_id)"]
            for statement in schema:
                connection.execute(statement)
            if version < 2:
                for statement in [
                    "ALTER TABLE documents ADD COLUMN hash_basis TEXT NOT NULL DEFAULT 'normalized_text'",
                    "ALTER TABLE documents ADD COLUMN page_count INTEGER",
                    "ALTER TABLE documents ADD COLUMN warnings_json TEXT NOT NULL DEFAULT '[]'",
                    "ALTER TABLE segments ADD COLUMN page_number INTEGER",
                    "ALTER TABLE segments ADD COLUMN source_label TEXT",
                ]:
                    connection.execute(statement)
                connection.execute("PRAGMA user_version = 2")
            if version < 3:
                create_search_schema(connection)
                connection.execute("PRAGMA user_version = 3")
            ensure_analyzer_version(connection)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.create_function("alethia_search_tokens", 1, index_text, deterministic=True)
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def metadata(connection: sqlite3.Connection, document_id: str):
        row = connection.execute("""
            SELECT id, filename, format, content_hash, size_bytes, revision, created_at,
                   updated_at, processor_version, hash_basis, page_count, warnings_json, length(text) AS character_count,
                   (SELECT count(*) FROM segments WHERE document_id = d.id) AS segment_count
            FROM documents d WHERE id = ?
        """, (document_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["warnings"] = json.loads(result.pop("warnings_json"))
        return result

    def list_documents(self) -> list[dict]:
        with self.connect() as connection:
            ids = connection.execute("SELECT id FROM documents ORDER BY created_at DESC, id").fetchall()
            return [self.metadata(connection, row["id"]) for row in ids]

    def get(self, document_id: str):
        with self.connect() as connection:
            result = self.metadata(connection, document_id)
            if result is None:
                return None
            result["text"] = connection.execute("SELECT text FROM documents WHERE id = ?", (document_id,)).fetchone()[0]
            result["segments"] = [dict(row) for row in connection.execute(
                "SELECT * FROM segments WHERE document_id = ? ORDER BY ordinal", (document_id,))]
            return result

    def _write(self, connection: sqlite3.Connection, document: ExtractedDocument, replace_id: str | None = None):
        existing = None
        if replace_id:
            existing = connection.execute("SELECT * FROM documents WHERE id = ?", (replace_id,)).fetchone()
            if existing is None:
                raise IngestionError("Document not found.", 404)
        duplicate = connection.execute("SELECT id FROM documents WHERE content_hash = ?", (document.content_hash,)).fetchone()
        if duplicate:
            if replace_id and duplicate["id"] != replace_id:
                raise IngestionError("This content already belongs to another document. No changes were made.", 409)
            return {"outcome": "duplicate", "document": self.metadata(connection, duplicate["id"])}
        if not replace_id and connection.execute("SELECT count(*) FROM documents").fetchone()[0] >= MAX_DOCUMENTS:
            raise IngestionError(f"Library is limited to {MAX_DOCUMENTS} documents. Delete a document before adding more.", 409)
        document_id = replace_id or uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        revision = existing["revision"] + 1 if existing else 1
        if existing:
            connection.execute("DELETE FROM segments WHERE document_id = ?", (document_id,))
            connection.execute("""UPDATE documents SET filename=?, format=?, content_hash=?, text=?, size_bytes=?,
                                  revision=?, updated_at=?, processor_version=?, hash_basis=?, page_count=?, warnings_json=? WHERE id=?""",
                               (document.filename, document.format, document.content_hash, document.text,
                                document.size_bytes, revision, now, document.processor_version, document.hash_basis,
                                document.page_count, json.dumps(document.warnings), document_id))
        else:
            connection.execute("""INSERT INTO documents (id, filename, format, content_hash, text, size_bytes,
                               revision, created_at, updated_at, processor_version, hash_basis, page_count, warnings_json)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                               (document_id, document.filename, document.format, document.content_hash, document.text,
                                document.size_bytes, revision, now, now, document.processor_version, document.hash_basis,
                                document.page_count, json.dumps(document.warnings)))
        for ordinal, segment in enumerate(document.segments):
            segment_id = hashlib.sha256(f"{document_id}:{document.content_hash}:{document.processor_version}:{ordinal}".encode()).hexdigest()
            connection.execute("""INSERT INTO segments (id, document_id, ordinal, section, text, start_char, end_char,
                               start_line, end_line, page_number, source_label) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                               (segment_id, document_id, ordinal, segment.section, segment.text,
                                segment.start_char, segment.end_char, segment.start_line, segment.end_line,
                                segment.page_number, segment.source_label))
        return {"outcome": "updated" if existing else "created", "document": self.metadata(connection, document_id)}

    def save(self, document: ExtractedDocument, replace_id: str | None = None):
        with self.connect() as connection:
            # Serialize read/check/write, including duplicate and capacity checks.
            connection.execute("BEGIN IMMEDIATE")
            return self._write(connection, document, replace_id)

    def import_pack(self, documents: list[ExtractedDocument]):
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            return [self._write(connection, document) for document in documents]

    def delete(self, document_id: str) -> bool:
        with self.connect() as connection:
            return connection.execute("DELETE FROM documents WHERE id = ?", (document_id,)).rowcount > 0

    def retrieval_status(self) -> dict:
        with self.connect() as connection:
            connection.execute("BEGIN")
            return index_status(connection)

    def retrieve(self, terms: list[str], limit: int) -> tuple[dict, list[dict]]:
        with self.connect() as connection:
            # Counts, corpus statistics, and returned source rows share one read snapshot.
            connection.execute("BEGIN")
            return index_status(connection), search_rows(connection, terms, limit)
