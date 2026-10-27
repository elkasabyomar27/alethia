"""Low-memory dense index lifecycle. The API never imports the ML runtime."""

from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
from uuid import uuid4

from app.ingestion import IngestionError
from app.rag.dense_artifacts import chunk_bm25_matches, file_hash, verify_generation
from app.rag.embedding_config import (ROOT, MODEL_DIRECTORY, MODEL_FILENAME, MODEL_ID, MODEL_REVISION,
    DIMENSION, PASSAGE_TOKEN_LIMIT, WORKER_MEMORY_MIB, MIN_AVAILABLE_MEMORY_MIB, MAX_DENSE_CHARACTERS,
    MAX_DENSE_SOURCES, BUILD_TIMEOUT_SECONDS, SEARCH_TIMEOUT_SECONDS)
from app.rag.resources import available_memory_mib
from app.rag.fusion import reciprocal_rank_fusion, RRF_RANK_CONSTANT, RRF_CANDIDATE_DEPTH, RRF_VERSION


class DenseIndex:
    def __init__(self, store, directory: Path | None = None):
        self.store = store
        self.directory = (directory or ROOT / "data" / "indexes" / "dense").resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self._guard = threading.Lock()
        self._artifacts = threading.RLock()
        self._busy = False
        self._process = None
        self._job = None
        self._error = None
        self._closed = False

    def runtime_available(self):
        return all(importlib.util.find_spec(name) is not None for name in ("numpy", "onnxruntime", "tokenizers", "faiss")) and all(
            (MODEL_DIRECTORY / name).is_file() for name in (MODEL_FILENAME, "tokenizer.json"))

    def _active(self):
        pointer = self.directory / "current.json"
        if not pointer.exists():
            return None
        try:
            if pointer.stat().st_size > 4096:
                raise ValueError("Invalid pointer")
            data = json.loads(pointer.read_text(encoding="utf-8"))
            generation = data["generation"]
            if not re.fullmatch(r"[a-f0-9]{32}", generation):
                raise ValueError("Invalid generation")
            candidate = self.directory / generation
            if candidate.is_symlink():
                raise ValueError("Invalid folder")
            folder = candidate.resolve()
            if folder.parent != self.directory:
                raise ValueError("Invalid folder")
            path = folder / "manifest.json"
            if path.stat().st_size > 32768 or file_hash(path) != data["manifest_sha256"]:
                raise ValueError("Invalid manifest")
            manifest = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(manifest, dict) or manifest.get("schema") != 1 or not isinstance(manifest.get("source_revision"), int):
                raise ValueError("Invalid manifest schema")
            if any(not isinstance(manifest.get(key), str) or not re.fullmatch(r"[a-f0-9]{64}", manifest[key]) for key in ("source_fingerprint", "corpus_hash")):
                raise ValueError("Invalid corpus identity")
            return folder, manifest
        except (OSError, KeyError, ValueError, TypeError) as exc:
            raise IngestionError("Encoder snapshot metadata is missing or corrupt. Rebuild the encoder index.", 409) from exc

    def status(self):
        source, fingerprint = self._source_state()
        error = self._error
        try:
            with self._artifacts:
                active = self._active()
        except IngestionError as exc:
            active = None
            error = str(exc)
        manifest = active[1] if active else None
        state = "not_built"
        if manifest:
            state = "ready" if (manifest["source_revision"] == source["index_revision"]
                                and manifest.get("source_fingerprint") == fingerprint) else "stale"
        elif error:
            state = "failed"
        elif not self.runtime_available():
            state = "unavailable"
        job = dict(self._job) if self._job else None
        if job and job.get("state") == "building":
            state = "building"
        return {"state": state, "runtime_available": self.runtime_available(), "model_id": MODEL_ID,
                "model_revision": MODEL_REVISION, "dimension": DIMENSION, "passage_token_limit": PASSAGE_TOKEN_LIMIT,
                "worker_memory_limit_mib": WORKER_MEMORY_MIB, "available_memory_mib": available_memory_mib(),
                "current_source_revision": source["index_revision"], "snapshot": manifest, "job": job, "last_error": error}

    def _claim(self):
        with self._guard:
            if self._closed:
                raise IngestionError("Embedding service is shutting down.", 503)
            if self._busy:
                raise IngestionError("An embedding operation is already running. Retry when it finishes.", 503)
            if not self.runtime_available():
                raise IngestionError("Dense runtime or pinned model is missing. Install requirements-ml.txt and run prepare_embedding_model.py.", 503)
            if available_memory_mib() < MIN_AVAILABLE_MEMORY_MIB:
                raise IngestionError(f"Dense operations need at least {MIN_AVAILABLE_MEMORY_MIB} MiB available RAM. Close heavy apps and retry.", 503)
            self._busy = True

    def _release(self):
        with self._guard:
            self._busy = False

    def _worker(self, mode: str, payload: dict, progress=None):
        timeout = BUILD_TIMEOUT_SECONDS if mode == "build" else SEARCH_TIMEOUT_SECONDS
        try:
            process = subprocess.Popen([sys.executable, "-m", "app.rag.dense_worker", mode], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=ROOT / "backend",
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        except OSError as exc:
            raise IngestionError("Embedding worker could not start. Check local resources and installation.", 503) from exc
        self._process = process
        timed_out = threading.Event()
        def terminate():
            timed_out.set()
            if process.poll() is None:
                process.kill()
        timer = threading.Timer(timeout, terminate)
        timer.daemon = True
        timer.start()
        result = None
        try:
            encoded = json.dumps(payload, ensure_ascii=True).encode()
            if len(encoded) > 12 * 1024 * 1024:
                raise IngestionError("Dense snapshot input exceeds the worker protocol limit.", 413)
            process.stdin.write(encoded)
            process.stdin.close()
            for line in process.stdout:
                if len(line) > 2 * 1024 * 1024:
                    raise IngestionError("Embedding worker returned an oversized response.", 503)
                message = json.loads(line)
                if "error" in message:
                    raise IngestionError(message["error"], message.get("status", 503))
                if message.get("type") == "progress" and progress:
                    progress(message)
                elif message.get("type") == "result":
                    result = message
            process.wait()
            if timed_out.is_set():
                raise IngestionError(f"Embedding worker exceeded its {timeout}-second limit. Use a smaller corpus or query.", 503)
            if process.returncode != 0 or result is None:
                raise IngestionError("Embedding worker stopped at a resource limit or runtime failure.", 503)
            return result
        except (BrokenPipeError, OSError, ValueError) as exc:
            raise IngestionError("Embedding worker communication failed. Check local resources and installation.", 503) from exc
        finally:
            timer.cancel()
            if process.poll() is None:
                process.kill()
            process.wait()
            process.stdout.close()
            if not process.stdin.closed:
                process.stdin.close()
            self._process = None

    def _snapshot(self):
        with self.store.connect() as connection:
            connection.execute("BEGIN")
            from app.rag.lexical import index_status
            status = index_status(connection)
            sources, characters = [], 0
            for row in connection.execute("SELECT id,text FROM segments ORDER BY id"):
                characters += len(row["text"])
                if characters > MAX_DENSE_CHARACTERS or len(sources) >= MAX_DENSE_SOURCES:
                    raise IngestionError("Dense indexing is limited to 1,000,000 source characters and 5,000 source segments on this machine.", 413)
                sources.append(dict(row))
            if not sources:
                raise IngestionError("Add readable documents before building the encoder index.")
            return {"sources": sources, "source_revision": status["index_revision"],
                    "document_count": status["indexed_documents"],
                    "source_fingerprint": hashlib.sha256("\n".join(row["id"] for row in sources).encode()).hexdigest()}

    @staticmethod
    def _fingerprint(connection):
        checksum = hashlib.sha256()
        first = True
        for row in connection.execute("SELECT id FROM segments ORDER BY id"):
            if not first:
                checksum.update(b"\n")
            checksum.update(row["id"].encode())
            first = False
        return checksum.hexdigest()

    def _source_state(self):
        from app.rag.lexical import index_status
        with self.store.connect() as connection:
            connection.execute("BEGIN")
            return index_status(connection), self._fingerprint(connection)

    def start_build(self):
        self._claim()
        try:
            payload = self._snapshot()
        except Exception:
            self._release()
            raise
        self._error = None
        self._job = {"state": "building", "stage": "starting", "completed": 0, "total": 0,
                     "started_at": datetime.now(timezone.utc).isoformat()}
        threading.Thread(target=self._build, args=(payload,), daemon=True, name="alethia-dense-build").start()
        return self.status()

    def _remove_generation(self, folder):
        if folder.is_symlink():
            return
        folder = folder.resolve()
        if folder.parent != self.directory or not re.fullmatch(r"[a-f0-9]{32}", folder.name) or not folder.is_dir():
            return
        allowed = {"index.faiss", "chunks.sqlite3", "chunks.sqlite3-journal", "manifest.json"}
        if any(item.name not in allowed or not item.is_file() or item.is_symlink() for item in folder.iterdir()):
            return
        try:
            for item in folder.iterdir():
                item.unlink()
            folder.rmdir()
        except OSError:
            pass  # A reader may still hold a file; leave it for a later build.

    def _build(self, payload):
        folder = self.directory / uuid4().hex
        published = False
        try:
            folder.mkdir()
            payload["directory"] = str(folder)
            def progress(message):
                self._job.update({key: message[key] for key in ("stage", "completed", "total")})
            result = self._worker("build", payload, progress)
            with self._artifacts:
                if self._closed:
                    raise IngestionError("Encoder build was cancelled during shutdown.", 503)
                current, fingerprint = self._source_state()
                if current["index_revision"] != payload["source_revision"] or fingerprint != payload["source_fingerprint"]:
                    raise IngestionError("The library changed during embedding. Rebuild after uploads finish.", 409)
                path = folder / "manifest.json"
                manifest = json.loads(path.read_text(encoding="utf-8"))
                manifest["build_diagnostics"] = {key: result[key] for key in ("elapsed_seconds", "memory")}
                path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
                verify_generation(folder, manifest)
                pointer = {"generation": folder.name, "manifest_sha256": file_hash(path)}
                temporary = self.directory / "current.json.part"
                temporary.write_text(json.dumps(pointer), encoding="utf-8")
                temporary.replace(self.directory / "current.json")
                published = True
                for older in self.directory.iterdir():
                    if older.is_dir() and older != folder:
                        self._remove_generation(older)
            self._job.update({"state": "complete", "stage": "ready"})
        except Exception as error:
            self._error = str(error) if isinstance(error, IngestionError) else "Encoder index build failed. Check local resources and retry."
            self._job.update({"state": "failed", "stage": "failed"})
        finally:
            if not published:
                self._remove_generation(folder)
            self._release()

    def search(self, query: str, terms: list[str], top_k: int, method: str):
        if method not in ("bm25", "dense", "hybrid"):
            raise IngestionError("Unknown encoder retrieval method.", 422)
        uses_encoder = method in ("dense", "hybrid")
        if uses_encoder:
            self._claim()
        try:
            with self._artifacts:
                active = self._active()
                if active is None:
                    raise IngestionError("Build the encoder index before using this retrieval mode.", 409)
                folder, manifest = active
                current, fingerprint = self._source_state()
                if manifest["source_revision"] != current["index_revision"] or manifest.get("source_fingerprint") != fingerprint:
                    raise IngestionError("The encoder index is stale because the library changed. Rebuild it before searching.", 409)
                verify_generation(folder, manifest)
                fusion = None
                if uses_encoder:
                    depth = RRF_CANDIDATE_DEPTH if method == "hybrid" else top_k
                    result = self._worker("search", {"directory": str(folder), "query": query, "top_k": depth})
                    matches = result["matches"]
                    diagnostics = {key: result[key] for key in ("elapsed_seconds", "memory")}
                    if method == "hybrid":
                        lexical = chunk_bm25_matches(folder, manifest, terms, RRF_CANDIDATE_DEPTH)
                        fusion = {"algorithm": "rrf", "rank_constant": RRF_RANK_CONSTANT,
                                  "candidate_depth": RRF_CANDIDATE_DEPTH, "weights": {"bm25": 1, "dense": 1},
                                  "candidate_counts": {"bm25": len(lexical), "dense": len(matches)}}
                        matches = reciprocal_rank_fusion(lexical, matches, top_k)
                else:
                    matches = chunk_bm25_matches(folder, manifest, terms, top_k)
                    diagnostics = None
                rows = self._resolve(matches, manifest)
                index = {"state": "ready", "method": method, "indexed_segments": manifest["chunk_count"],
                         "searchable_segments": manifest["chunk_count"], "indexed_documents": manifest["document_count"],
                         "index_revision": manifest["source_revision"], "retriever_version": RRF_VERSION if method == "hybrid" else "faiss-e5-int8-ip-v1" if method == "dense" else "sqlite-fts5-encoder-bm25-v1",
                         "analyzer_version": manifest["analyzer_version"], "built_at": manifest["built_at"],
                         "sqlite_version": __import__("sqlite3").sqlite_version, "k1": 1.2, "b": .75,
                         "chunking": manifest["chunker_version"], "match_mode": "rank_fusion" if method == "hybrid" else "cosine" if method == "dense" else "any_term",
                         "score_meaning": "RRF combines candidate ranks, not raw scores. Its score is not confidence or factual correctness." if method == "hybrid" else "Cosine similarity is a ranking signal, not confidence or factual correctness." if method == "dense" else "BM25 ranks lexical overlap, not confidence.",
                         "corpus": "encoder", "corpus_hash": manifest["corpus_hash"], "model_revision": MODEL_REVISION,
                         "dimension": DIMENSION, "fusion": fusion}
                return index, rows, diagnostics
        finally:
            if uses_encoder:
                self._release()

    def _resolve(self, matches, manifest):
        with self.store.connect() as connection:
            connection.execute("BEGIN")
            from app.rag.lexical import index_status
            if (index_status(connection)["index_revision"] != manifest["source_revision"]
                    or self._fingerprint(connection) != manifest.get("source_fingerprint")):
                raise IngestionError("The library changed while searching. Rebuild the encoder index and retry.", 409)
            rows = []
            for match in matches:
                source = connection.execute("""SELECT s.*,d.filename,d.format,d.revision,d.content_hash,d.processor_version,d.warnings_json
                    FROM segments s JOIN documents d ON d.id=s.document_id WHERE s.id=?""", (match["parent_id"],)).fetchone()
                if source is None or not 0 <= match["start"] < match["end"] <= len(source["text"]):
                    raise IngestionError("A chunk source is missing or invalid. Rebuild the encoder index.", 409)
                row = dict(source)
                parent_text = row["text"]
                row.update({"chunk_id": match["id"], "token_count": match["token_count"], "score": match["score"],
                            "text": parent_text[match["start"]:match["end"]],
                            "start_char": source["start_char"] + match["start"], "end_char": source["start_char"] + match["end"],
                            "start_line": source["start_line"] + parent_text[:match["start"]].count("\n"),
                            "end_line": source["start_line"] + parent_text[:match["end"] - 1].count("\n")})
                if "retrievers" in match:
                    row["retrievers"] = match["retrievers"]
                rows.append(row)
            return rows

    def close(self):
        self._closed = True
        process = self._process
        if process and process.poll() is None:
            process.kill()
