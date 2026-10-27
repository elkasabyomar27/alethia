"""Immutable dense generations and a BM25 index over the identical encoder chunks."""

from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sqlite3

from app.ingestion import IngestionError
from app.rag.analyzer import index_text, ANALYZER_VERSION
from app.rag.embedding_config import (CHUNKER_VERSION, DIMENSION, EMBEDDING_VERSION, MAX_DENSE_CHUNKS,
    MODEL_ID, MODEL_REVISION, MODEL_SHA256, TOKENIZER_SHA256, PASSAGE_TOKEN_LIMIT, OVERLAP_TOKENS)


def file_hash(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def read_chunk_db(directory: Path):
    connection = sqlite3.connect((directory / "chunks.sqlite3").resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def verify_generation(directory: Path, manifest: dict):
    if (manifest.get("model_revision") != MODEL_REVISION or manifest.get("embedding_version") != EMBEDDING_VERSION
            or manifest.get("chunker_version") != CHUNKER_VERSION or manifest.get("dimension") != DIMENSION
            or manifest.get("analyzer_version") != ANALYZER_VERSION or manifest.get("model_sha256") != MODEL_SHA256
            or manifest.get("tokenizer_sha256") != TOKENIZER_SHA256):
        raise IngestionError("Embedding snapshot configuration changed. Rebuild the encoder index.", 409)
    if not 0 < manifest.get("chunk_count", 0) <= MAX_DENSE_CHUNKS:
        raise IngestionError("Embedding snapshot has an invalid chunk count. Rebuild it.", 409)
    for name in ("index.faiss", "chunks.sqlite3"):
        path = directory / name
        item = manifest.get("files", {}).get(name, {})
        if not path.is_file() or path.stat().st_size != item.get("size") or file_hash(path) != item.get("sha256"):
            raise IngestionError("Embedding snapshot failed its integrity check. Rebuild the encoder index.", 409)


def build_snapshot(payload: dict, encoder, emit) -> dict:
    import faiss
    import numpy as np

    faiss.omp_set_num_threads(2)
    directory = Path(payload["directory"])
    sources = payload["sources"]
    source_text = {source["id"]: source["text"] for source in sources}
    chunks = []
    for ordinal, source in enumerate(sources, 1):
        chunks.extend(encoder.chunks(source["id"], source["text"]))
        if len(chunks) > MAX_DENSE_CHUNKS:
            raise IngestionError(f"Dense snapshot exceeds {MAX_DENSE_CHUNKS:,} chunks. Use a smaller corpus.", 413)
        emit({"type": "progress", "stage": "chunking", "completed": ordinal, "total": len(sources)})
    if not chunks:
        raise IngestionError("No encoder chunks could be created. Add readable documents first.")
    index = faiss.IndexFlatIP(DIMENSION)
    connection = sqlite3.connect(directory / "chunks.sqlite3")
    try:
        with connection:
            connection.execute("""CREATE TABLE chunks (ordinal INTEGER PRIMARY KEY, id TEXT UNIQUE NOT NULL,
                parent_id TEXT NOT NULL, start INTEGER NOT NULL, end INTEGER NOT NULL, token_count INTEGER NOT NULL,
                text TEXT NOT NULL, tokens TEXT NOT NULL)""")
            connection.execute("CREATE VIRTUAL TABLE chunk_search USING fts5(tokens, content='chunks', content_rowid='ordinal', tokenize='unicode61 remove_diacritics 0')")
            for ordinal, chunk in enumerate(chunks):
                text = source_text[chunk["parent_id"]][chunk["start"]:chunk["end"]]
                vector = encoder.encode(text)
                if vector.shape != (1, DIMENSION) or not np.isfinite(vector).all():
                    raise IngestionError("Invalid vector generated while building the index.", 503)
                index.add(vector)
                connection.execute("INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                   (ordinal, chunk["id"], chunk["parent_id"], chunk["start"], chunk["end"], chunk["token_count"], text, index_text(text)))
                emit({"type": "progress", "stage": "embedding", "completed": ordinal + 1, "total": len(chunks)})
            connection.execute("INSERT INTO chunk_search(chunk_search) VALUES ('rebuild')")
            connection.execute("INSERT INTO chunk_search(chunk_search, rank) VALUES ('integrity-check', 1)")
    finally:
        connection.close()
    emit({"type": "progress", "stage": "writing", "completed": len(chunks), "total": len(chunks)})
    faiss.write_index(index, str(directory / "index.faiss"))
    manifest = {"schema": 1, "model_id": MODEL_ID, "model_revision": MODEL_REVISION,
                "model_sha256": MODEL_SHA256, "tokenizer_sha256": TOKENIZER_SHA256,
                "embedding_version": EMBEDDING_VERSION, "chunker_version": CHUNKER_VERSION,
                "analyzer_version": ANALYZER_VERSION, "dimension": DIMENSION,
                "source_revision": payload["source_revision"], "source_fingerprint": payload["source_fingerprint"],
                "corpus_hash": hashlib.sha256("\n".join(chunk["id"] for chunk in chunks).encode()).hexdigest(),
                "source_count": len(sources), "document_count": payload["document_count"],
                "chunk_count": len(chunks), "passage_token_limit": PASSAGE_TOKEN_LIMIT,
                "overlap_tokens": OVERLAP_TOKENS, "pooling": "attention-mask mean; L2 normalization",
                "prefixes": {"query": "query: ", "passage": "passage: "}, "provider": "CPUExecutionProvider",
                "built_at": datetime.now(timezone.utc).isoformat(),
                "runtime": {name: version(name) for name in ("onnxruntime", "tokenizers", "numpy", "faiss-cpu")},
                "files": {name: {"size": (directory / name).stat().st_size, "sha256": file_hash(directory / name)}
                          for name in ("chunks.sqlite3", "index.faiss")}}
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"chunk_count": len(chunks), "source_count": len(sources)}


def dense_matches(directory: Path, manifest: dict, vector, top_k: int) -> list[dict]:
    import faiss
    faiss.omp_set_num_threads(2)
    verify_generation(directory, manifest)
    index = faiss.read_index(str(directory / "index.faiss"))
    if index.d != DIMENSION or index.ntotal != manifest["chunk_count"] or index.ntotal > MAX_DENSE_CHUNKS:
        raise IngestionError("FAISS snapshot shape is invalid. Rebuild the encoder index.", 409)
    scores, identifiers = index.search(vector, index.ntotal)
    connection = read_chunk_db(directory)
    try:
        chunks = {row["ordinal"]: dict(row) for row in connection.execute("SELECT ordinal,id,parent_id,start,end,token_count FROM chunks")}
    finally:
        connection.close()
    matches = [{**chunks[int(ordinal)], "score": float(score)} for ordinal, score in zip(identifiers[0], scores[0]) if int(ordinal) >= 0]
    matches.sort(key=lambda row: (-row["score"], row["id"]))
    return matches[:top_k]


def chunk_bm25_matches(directory: Path, manifest: dict, terms: list[str], top_k: int) -> list[dict]:
    verify_generation(directory, manifest)
    expression = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
    connection = read_chunk_db(directory)
    try:
        return [dict(row) for row in connection.execute("""SELECT c.ordinal,c.id,c.parent_id,c.start,c.end,c.token_count,
            -bm25(chunk_search) AS score FROM chunk_search JOIN chunks c ON c.ordinal=chunk_search.rowid
            WHERE chunk_search MATCH ? ORDER BY bm25(chunk_search),c.id LIMIT ?""", (expression, top_k))]
    finally:
        connection.close()


def run_job(mode: str, payload: dict, encoder, emit):
    if mode == "build":
        return build_snapshot(payload, encoder, emit)
    if mode == "search":
        directory = Path(payload["directory"])
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        return {"matches": dense_matches(directory, manifest, encoder.encode(payload["query"], query=True), payload["top_k"])}
    raise IngestionError("Unknown embedding worker operation.", 400)
