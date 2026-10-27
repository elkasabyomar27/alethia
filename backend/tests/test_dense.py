"""Dense lifecycle tests use explicitly synthetic vectors; they are not semantic-quality evaluations."""

import hashlib
import json
from pathlib import Path
import sqlite3
import time

import pytest

np = pytest.importorskip("numpy")
faiss = pytest.importorskip("faiss")
pytest.importorskip("onnxruntime")
tokenizers = pytest.importorskip("tokenizers")

from fastapi.testclient import TestClient
from app.database import DocumentStore
from app.ingestion import IngestionError, extract_document
from app.main import create_app
from app.rag import dense as dense_module
from app.rag.dense import DenseIndex
from app.rag.dense_artifacts import build_snapshot, dense_matches, file_hash
from app.rag.embedding_config import DIMENSION, MODEL_DIRECTORY, MODEL_FILENAME, PASSAGE_TOKEN_LIMIT
from app.rag.embedding_runtime import E5Encoder


class FixtureEncoder(E5Encoder):
    """Tiny local tokenizer + synthetic unit vectors. Never used by the application."""
    def __init__(self):
        self.tokenizer = tokenizers.Tokenizer(tokenizers.models.WordLevel({"[UNK]": 0, "[CLS]": 1, "[SEP]": 2}, unk_token="[UNK]"))
        self.tokenizer.pre_tokenizer = tokenizers.pre_tokenizers.Whitespace()
        self.tokenizer.post_processor = tokenizers.processors.TemplateProcessing(single="[CLS] $A [SEP]", special_tokens=[("[CLS]", 1), ("[SEP]", 2)])

    def encode(self, text, query=False):
        vector = np.zeros((1, DIMENSION), dtype=np.float32)
        for index, word in enumerate(("shipping", "warranty", "return", "الشحن")):
            vector[0, index] = text.casefold().count(word)
        vector[0, -1] = 1
        return np.ascontiguousarray(vector / np.linalg.norm(vector), dtype=np.float32)


def fake_worker(self, mode, payload, progress=None):
    encoder = FixtureEncoder()
    if mode == "build":
        result = build_snapshot(payload, encoder, progress or (lambda _: None))
    else:
        directory = Path(payload["directory"])
        manifest = json.loads((directory / "manifest.json").read_text())
        result = {"matches": dense_matches(directory, manifest, encoder.encode(payload["query"], True), payload["top_k"])}
    return {**result, "elapsed_seconds": .001, "memory": {"synthetic_test_fixture": True}}


@pytest.fixture
def configured(tmp_path, monkeypatch):
    monkeypatch.setattr(DenseIndex, "runtime_available", lambda _: True)
    monkeypatch.setattr(DenseIndex, "_worker", fake_worker)
    monkeypatch.setattr(dense_module, "available_memory_mib", lambda: 2048)
    with TestClient(create_app(tmp_path / "source.sqlite3")) as client:
        yield client, client.app.state.documents, client.app.state.dense


def add(store, text, name="policy.txt"):
    return store.save(extract_document(name, text.encode()))["document"]


def build(manager):
    manager.start_build()
    deadline = time.monotonic() + 5
    while manager.status()["state"] == "building" and time.monotonic() < deadline:
        time.sleep(.01)
    result = manager.status()
    assert result["state"] == "ready", result
    return result


@pytest.mark.parametrize("text", [
    " ".join(f"word{i}" for i in range(800)),
    "  الشحن والإرجاع 🌞 ﷲ أَسْئِلَة\n" * 180,
    "first\n\n" + "shipping " * 1000 + "\nfinal  ",
])
def test_chunks_obey_prefixed_token_budget_and_cover_source_without_unicode_gaps(text):
    encoder = FixtureEncoder()
    chunks = encoder.chunks("parent-source", text)
    assert len(chunks) > 1
    covered = set()
    for chunk in chunks:
        passage = text[chunk["start"]:chunk["end"]]
        assert chunk["token_count"] == encoder.token_count(passage) <= PASSAGE_TOKEN_LIMIT
        covered.update(range(chunk["start"], chunk["end"]))
    assert covered == set(range(len(text)))
    assert chunks == encoder.chunks("parent-source", text)
    assert chunks[0]["id"] != encoder.chunks("different-parent", text)[0]["id"]


def test_e5_pooling_excludes_padding_and_l2_normalizes():
    encoder = FixtureEncoder()
    encoder.tokenizer.enable_padding(length=12, pad_id=0, pad_token="[UNK]")
    class Session:
        def get_inputs(self):
            return [type("Input", (), {"name": name}) for name in ("input_ids", "attention_mask")]
        def run(self, _, inputs):
            output = np.zeros((1, 12, DIMENSION), dtype=np.float32)
            mask = inputs["attention_mask"][0]
            output[0, mask == 1, 0] = 3
            output[0, mask == 1, 1] = 4
            output[0, mask == 0, 2] = 10000
            return [output]
    encoder.session = Session()
    vector = E5Encoder.encode(encoder, "shipping", query=True)
    assert vector[0, :3] == pytest.approx([.6, .8, 0])
    assert np.linalg.norm(vector) == pytest.approx(1)
    assert vector.dtype == np.float32
    encoder.tokenizer.no_padding()
    with pytest.raises(IngestionError, match="exceeds"):
        E5Encoder.encode(encoder, "word " * 600, query=True)


def test_encoder_refuses_missing_or_corrupt_artifacts(tmp_path):
    (tmp_path / MODEL_FILENAME).write_bytes(b"not the model")
    with pytest.raises(IngestionError, match="missing or corrupt"):
        E5Encoder(tmp_path)


@pytest.mark.skipif(not (MODEL_DIRECTORY / "tokenizer.json").is_file(), reason="Pinned model tokenizer is optional and not prepared")
def test_pinned_tokenizer_preserves_arabic_emoji_and_ligature_offsets_without_truncation():
    encoder = E5Encoder.__new__(E5Encoder)
    encoder.tokenizer = tokenizers.Tokenizer.from_file(str(MODEL_DIRECTORY / "tokenizer.json"))
    encoder.tokenizer.no_truncation()
    encoder.tokenizer.no_padding()
    text = "🌞 شُروط الشحن إلى مصر ﷲ وإجراءات الإرجاع.\n" * 150
    chunks = encoder.chunks("real-offset-fixture", text)
    assert len(chunks) > 1
    covered = set()
    for chunk in chunks:
        assert encoder.token_count(text[chunk["start"]:chunk["end"]]) == chunk["token_count"] <= 256
        covered.update(range(chunk["start"], chunk["end"]))
    assert covered == set(range(len(text)))


def test_shared_chunk_bm25_and_dense_map_to_exact_source_ranges(configured):
    client, store, manager = configured
    source_text = "🌞 " + "a " * 2200 + "shipping within Egypt. " * 50 + "Warranty applies."
    document = add(store, source_text)
    state = build(manager)
    assert state["snapshot"]["chunk_count"] > state["snapshot"]["source_count"]
    responses = []
    for method in ("bm25", "dense", "hybrid"):
        response = client.post("/api/retrieval/search", json={"query": "shipping", "method": method, "corpus": "encoder", "top_k": 10})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["index"]["corpus"] == "encoder"
        assert result["index"]["corpus_hash"] == state["snapshot"]["corpus_hash"]
        assert result["hits"]
        for hit in result["hits"]:
            assert hit["document_id"] == document["id"]
            assert hit["text"] == source_text[hit["start_char"]:hit["end_char"]]
            assert hit["chunk_id"] and hit["token_count"] <= 256
            assert hit["id"] in {s["id"] for s in store.get(document["id"])["segments"]}
        responses.append(result)
    assert responses[0]["index"]["indexed_segments"] == responses[1]["index"]["indexed_segments"]
    assert client.post("/api/retrieval/search", json={"query": "shipping", "method": "dense", "corpus": "source"}).status_code == 422


def test_faiss_inner_products_match_numpy_and_snapshot_survives_restart(configured):
    _, store, manager = configured
    for name, text in [("a.txt", "shipping shipping"), ("b.txt", "shipping warranty"), ("c.txt", "return")]:
        add(store, text, name)
    original = build(manager)["snapshot"]
    index, hits, _ = manager.search("shipping", ["shipping"], 10, "dense")
    encoder = FixtureEncoder()
    expected = []
    for document in store.list_documents():
        for segment in store.get(document["id"])["segments"]:
            chunk = encoder.chunks(segment["id"], segment["text"])[0]
            expected.append((float((encoder.encode(segment["text"]) @ encoder.encode("shipping").T)[0, 0]), chunk["id"]))
    expected.sort(key=lambda item: (-item[0], item[1]))
    assert [(row["score"], row["chunk_id"]) for row in hits] == expected
    reopened = DenseIndex(store, manager.directory)
    assert reopened.status()["snapshot"] == original
    assert reopened.search("shipping", ["shipping"], 10, "dense")[1] == hits
    assert index["dimension"] == 384


@pytest.mark.parametrize("change", ["upload", "replace", "delete"])
def test_library_changes_mark_snapshot_stale_and_block_encoder_search(configured, change):
    client, store, manager = configured
    document = add(store, "shipping original")
    build(manager)
    if change == "upload": add(store, "new warranty", "second.txt")
    elif change == "replace": store.save(extract_document("new.txt", b"warranty updated"), document["id"])
    else: store.delete(document["id"])
    assert manager.status()["state"] == "stale"
    for method in ("bm25", "dense", "hybrid"):
        response = client.post("/api/retrieval/search", json={"query": "shipping", "method": method, "corpus": "encoder"})
        assert response.status_code == 409
    assert client.post("/api/retrieval/search", json={"query": "shipping"}).status_code == 200


def test_duplicate_and_rollback_do_not_invalidate_valid_snapshot(configured):
    _, store, manager = configured
    document = add(store, "shipping original")
    original = build(manager)["snapshot"]
    assert store.save(extract_document("same.txt", b"shipping original"))["outcome"] == "duplicate"
    assert manager.status()["state"] == "ready"
    with store.connect() as connection:
        connection.execute("CREATE TRIGGER fail_dense BEFORE INSERT ON segments BEGIN SELECT RAISE(ABORT,'test'); END")
    with pytest.raises(sqlite3.IntegrityError):
        store.save(extract_document("new.txt", b"warranty changed"), document["id"])
    assert manager.status()["snapshot"] == original and manager.status()["state"] == "ready"


def test_rebuild_failure_keeps_previous_generation_and_success_retires_old_cache(configured, monkeypatch):
    _, store, manager = configured
    add(store, "shipping original")
    build(manager)
    old_pointer = (manager.directory / "current.json").read_bytes()
    old_directory, _ = manager._active()
    def fail(*args, **kwargs): raise IngestionError("synthetic worker failure", 503)
    with monkeypatch.context() as patch:
        patch.setattr(manager, "_worker", fail)
        manager.start_build()
        deadline = time.monotonic() + 3
        while manager.status()["state"] == "building" and time.monotonic() < deadline: time.sleep(.01)
    assert manager.status()["state"] == "ready" and "synthetic" in manager.status()["last_error"]
    assert (manager.directory / "current.json").read_bytes() == old_pointer
    build(manager)
    assert not old_directory.exists()


def test_change_during_build_never_publishes_stale_generation(configured, monkeypatch):
    _, store, manager = configured
    add(store, "shipping original")
    def changing(mode, payload, progress=None):
        result = fake_worker(manager, mode, payload, progress)
        add(store, "new warranty", "new.txt")
        return result
    monkeypatch.setattr(manager, "_worker", changing)
    manager.start_build()
    deadline = time.monotonic() + 3
    while manager.status()["state"] == "building" and time.monotonic() < deadline: time.sleep(.01)
    assert manager.status()["state"] == "failed"
    assert not (manager.directory / "current.json").exists()
    assert "library changed" in manager.status()["last_error"]


@pytest.mark.parametrize("method", ["dense", "hybrid"])
def test_change_during_dense_query_is_rejected_before_returning_sources(configured, monkeypatch, method):
    _, store, manager = configured
    add(store, "shipping original")
    build(manager)
    def changing(mode, payload, progress=None):
        result = fake_worker(manager, mode, payload, progress)
        add(store, "new warranty", "new.txt")
        return result
    monkeypatch.setattr(manager, "_worker", changing)
    with pytest.raises(IngestionError, match="changed while searching"):
        manager.search("shipping", ["shipping"], 5, method)


def test_corrupt_artifact_is_never_loaded_and_legacy_bm25_remains_available(configured):
    client, store, manager = configured
    add(store, "shipping original")
    build(manager)
    directory, _ = manager._active()
    with (directory / "index.faiss").open("ab") as target: target.write(b"corruption")
    response = client.post("/api/retrieval/search", json={"query": "shipping", "method": "dense"})
    assert response.status_code == 409 and "integrity" in response.json()["detail"]
    assert client.post("/api/retrieval/search", json={"query": "shipping"}).json()["hits"]


@pytest.mark.parametrize("contents", ['[]', '{"generation":"../../outside"}', '{"generation":123}'])
def test_invalid_snapshot_pointer_fails_closed(configured, contents):
    _, _, manager = configured
    (manager.directory / "current.json").write_text(contents)
    assert manager.status()["state"] == "failed"
    with pytest.raises(IngestionError, match="metadata"):
        manager.search("shipping", ["shipping"], 5, "bm25")


def test_low_memory_busy_missing_runtime_and_empty_corpus_are_clear(configured, monkeypatch):
    _, store, manager = configured
    with pytest.raises(IngestionError, match="readable"):
        manager.start_build()
    add(store, "shipping original")
    with monkeypatch.context() as patch:
        patch.setattr(dense_module, "available_memory_mib", lambda: 500)
        with pytest.raises(IngestionError, match="available RAM"): manager.start_build()
    manager._busy = True
    with pytest.raises(IngestionError, match="already running"): manager.start_build()
    manager._busy = False
    build(manager)
    monkeypatch.setattr(manager, "runtime_available", lambda: False)
    assert manager.search("shipping", ["shipping"], 5, "bm25")[1]
    with pytest.raises(IngestionError, match="runtime or pinned model"): manager.search("shipping", ["shipping"], 5, "dense")


def test_dense_source_limits_are_enforced_before_launch(configured, monkeypatch):
    _, store, manager = configured
    add(store, "shipping original")
    monkeypatch.setattr(dense_module, "MAX_DENSE_CHARACTERS", 5)
    with pytest.raises(IngestionError, match="limited"):
        manager.start_build()
    assert not manager._busy


def test_same_index_revision_with_different_source_ids_is_stale(configured):
    _, store, manager = configured
    document = add(store, "shipping original")
    build(manager)
    revision = store.retrieval_status()["index_revision"]
    store.save(extract_document("new.txt", b"warranty replacement"), document["id"])
    with store.connect() as connection:
        connection.execute("UPDATE lexical_config SET revision=?", (revision,))
    assert manager.status()["state"] == "stale"


def test_shutdown_refuses_new_operations(configured):
    _, store, manager = configured
    add(store, "shipping original")
    manager.close()
    with pytest.raises(IngestionError, match="shutting down"):
        manager.start_build()


def test_hybrid_fixed_candidate_pool_top_k_prefix_and_rank_provenance(configured, monkeypatch):
    client, store, manager = configured
    for i in range(25):
        add(store, f"Policy {i}. shipping " + "warranty " * (i + 1), f"policy-{i}.txt")
    snapshot = build(manager)["snapshot"]
    calls = []
    def recording(mode, payload, progress=None):
        calls.append((mode, payload["top_k"]))
        return fake_worker(manager, mode, payload, progress)
    monkeypatch.setattr(manager, "_worker", recording)
    outputs = []
    for count in (3, 10):
        response = client.post("/api/retrieval/search", json={"query": "shipping", "method": "hybrid", "top_k": count})
        assert response.status_code == 200, response.text
        body = response.json()
        assert len(body["hits"]) == count
        assert body["index"]["corpus_hash"] == snapshot["corpus_hash"]
        assert body["index"]["fusion"] == {"algorithm": "rrf", "rank_constant": 60, "candidate_depth": 20,
                                           "weights": {"bm25": 1, "dense": 1}, "candidate_counts": {"bm25": 20, "dense": 20}}
        for hit in body["hits"]:
            assert hit["score"] == sum(item["contribution"] for item in hit["retrievers"].values() if item)
            for component in hit["retrievers"].values():
                if component:
                    assert 1 <= component["rank"] <= 20
                    assert component["contribution"] == 1/(60+component["rank"])
        outputs.append(body)
    assert outputs[0]["hits"] == outputs[1]["hits"][:3]
    assert calls == [("search", 20), ("search", 20)]
    assert client.post("/api/retrieval/search", json={"query": "shipping", "method": "hybrid", "corpus": "source"}).status_code == 422
    reopened = DenseIndex(store, manager.directory)
    assert reopened.search("shipping", ["shipping"], 3, "hybrid")[1] == manager.search("shipping", ["shipping"], 3, "hybrid")[1]


def test_hybrid_empty_lexical_ranking_is_explicit_not_an_error(configured):
    client, store, manager = configured
    add(store, "shipping policy")
    build(manager)
    body = client.post("/api/retrieval/search", json={"query": "unmatchedword", "method": "hybrid"}).json()
    assert body["index"]["fusion"]["candidate_counts"] == {"bm25": 0, "dense": 1}
    assert body["hits"][0]["retrievers"]["bm25"] is None
    assert body["hits"][0]["score"] == 1/61


@pytest.mark.parametrize("failure", ["dense", "bm25", "memory", "busy", "missing_runtime"])
def test_hybrid_never_silently_falls_back_and_releases_worker_guard(configured, monkeypatch, failure):
    client, store, manager = configured
    add(store, "shipping policy")
    build(manager)
    def fail(*args, **kwargs): raise IngestionError("Test component failure", 503)
    with monkeypatch.context() as patch:
        if failure == "dense": patch.setattr(manager, "_worker", fail)
        elif failure == "bm25": patch.setattr(dense_module, "chunk_bm25_matches", fail)
        elif failure == "memory": patch.setattr(dense_module, "available_memory_mib", lambda: 500)
        elif failure == "missing_runtime": patch.setattr(manager, "runtime_available", lambda: False)
        else: manager._busy = True
        response = client.post("/api/retrieval/search", json={"query": "shipping", "method": "hybrid"})
        assert response.status_code == 503
        assert "hits" not in response.json()
    if failure == "busy": manager._busy = False
    assert not manager._busy
    assert client.post("/api/retrieval/search", json={"query": "shipping", "method": "hybrid"}).status_code == 200


def test_change_between_components_rejects_hybrid_before_returning_sources(configured, monkeypatch):
    client, store, manager = configured
    add(store, "shipping original")
    build(manager)
    original = dense_module.chunk_bm25_matches
    def changing(*args, **kwargs):
        results = original(*args, **kwargs)
        add(store, "new policy", "new.txt")
        return results
    monkeypatch.setattr(dense_module, "chunk_bm25_matches", changing)
    result = client.post("/api/retrieval/search", json={"query": "shipping", "method": "hybrid"})
    assert result.status_code == 409 and "changed while searching" in result.json()["detail"]
    assert not manager._busy


def test_oracle_holds_real_dense_admission_and_preserves_exact_provenance(configured, monkeypatch):
    from app.rag import oracle as oracle_module
    from app.rag.ollama import MODEL_DIGEST
    client, store, manager = configured
    add(store, "shipping original policy for all customers")
    build(manager)
    monkeypatch.setattr(oracle_module, "available_vram_mib", lambda: 3000)
    class LocalFixture:
        def inspect(self): return {"state": "ready", "digest": MODEL_DIGEST}
        def assert_idle(self): pass
        def unload(self): assert manager._busy
        def generate(self, messages, schema):
            with pytest.raises(IngestionError, match="already running"): manager.start_build()
            payload = json.loads(messages[1]["content"])
            source = payload["sources"][0]
            return {"message": {"content": json.dumps({"status": "answer", "claims": [{"text": "Shipping policy applies.",
                "evidence": [{"source_id": source["id"], "quote": source["text"]}]}]})}}
    client.app.state.oracle.client = LocalFixture()
    result = client.post('/api/oracle/ask', json={"question": "shipping policy"})
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["status"] == "answered"
    source = body["sources"][0]
    document = store.get(source["document_id"])
    assert document["text"][source["start_char"]:source["end_char"]] == source["text"]
    assert not manager._busy
