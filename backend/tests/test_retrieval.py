from concurrent.futures import ThreadPoolExecutor
import hashlib
import math
import sqlite3
import unicodedata

from fastapi.testclient import TestClient
import pytest

from app.database import DocumentStore
from app.ingestion import extract_document
from app.main import create_app
from app.rag import lexical
from app.rag.analyzer import index_text, tokenize


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "search.sqlite3")) as test_client:
        yield test_client


def add(client, text, filename="source.txt"):
    response = client.post("/api/documents", params={"filename": filename}, content=text.encode())
    assert response.status_code == 201, response.text
    return response.json()["document"]


def search(client, query, top_k=5):
    response = client.post("/api/retrieval/search", json={"query": query, "top_k": top_k})
    assert response.status_code == 200, response.text
    return response.json()


def check_integrity(store):
    with store.connect() as connection:
        connection.execute("INSERT INTO segment_search(segment_search, rank) VALUES('integrity-check', 1)")
        assert connection.execute("SELECT count(*) FROM lexical_segments").fetchone()[0] == connection.execute("SELECT count(*) FROM segments").fetchone()[0]


def test_normalization_handles_arabic_marks_alef_tatweel_digits_and_english():
    assert tokenize("SHIPPING أَسْئِلَة الـشَّحن إلى ١٤ ۱۴ café") == ["shipping", "اسئلة", "الشحن", "الي", "14", "14", "café"]
    assert tokenize("ASTER-L01 / THAL_B02") == ["aster", "l01", "thal", "b02"]
    assert tokenize("ة ه ؤ ئ") == ["ة", "ه", "ؤ", "ئ"]  # No aggressive stemming or folding.
    assert index_text("  Shipping\nالشحن! ") == "shipping الشحن"


@pytest.mark.parametrize("query", ["shipping", "shipping policy", "policy policy policy"])
def test_native_bm25_scores_match_an_independent_formula(client, query):
    corpus = ["shipping shipping egypt policy", "shipping cairo policy", "returns unused product policy", "lamp warranty policy", "payment card policy"]
    originals = {}
    for index, text in enumerate(corpus):
        filename = f"{index}.txt"
        add(client, text, filename)
        originals[filename] = tokenize(text)
    result = search(client, query, 10)
    terms = list(dict.fromkeys(tokenize(query)))
    average_length = sum(map(len, originals.values())) / len(originals)
    for hit in result["hits"]:
        words = originals[hit["filename"]]
        expected = 0.0
        for term in terms:
            frequency = words.count(term)
            document_frequency = sum(term in tokens for tokens in originals.values())
            idf = max(math.log((len(originals) - document_frequency + 0.5) / (document_frequency + 0.5)), 1e-6)
            expected += idf * (frequency * 2.2) / (frequency + 1.2 * (0.25 + 0.75 * len(words) / average_length))
        assert hit["score"] == pytest.approx(expected, rel=1e-10)
    scores = [hit["score"] for hit in result["hits"]]
    assert scores == sorted(scores, reverse=True)
    assert result["normalized_terms"] == terms
    assert result["latency_ms"] >= 0 and math.isfinite(result["latency_ms"])
    assert "answer" not in result and "confidence" not in result


def test_normalization_does_not_change_original_source_or_references(client):
    text = "أَسْئِلَة الشَّحن إلى ١٤ يومًا"
    document = add(client, text, "سياسة.txt")
    result = search(client, "اسئلة الشحن الي 14")
    assert len(result["hits"]) == 1
    hit = result["hits"][0]
    assert hit["document_id"] == document["id"]
    assert hit["matched_terms"] == ["اسئلة", "الشحن", "الي", "14"]
    assert hit["text"] == unicodedata.normalize("NFC", text)
    detail = client.get(f"/api/documents/{document['id']}").json()
    assert detail["segments"][0]["id"] == hit["id"]
    assert detail["text"][hit["start_char"]:hit["end_char"]] == hit["text"]


def test_empty_library_no_matches_and_punctuation_only_source_are_explicit(client):
    empty = search(client, "shipping")
    assert empty["hits"] == [] and empty["index"]["state"] == "empty"
    add(client, "!!! ---", "punctuation.txt")
    status = client.get("/api/retrieval/status").json()
    assert status["indexed_segments"] == 1 and status["searchable_segments"] == 0
    add(client, "Shipping within Egypt")
    result = search(client, "xyzunfindable")
    assert result["hits"] == [] and result["index"]["state"] == "ready"
    assert search(client, "إرجاع")['hits'] == []  # Lexical retrieval does not translate English.


@pytest.mark.parametrize("body", [
    {"query": ""}, {"query": "  \n "}, {"query": "!!!"}, {"query": "x" * 501},
    {"query": " ".join(f"term{i}" for i in range(65))},
    {"query": "shipping", "top_k": 0}, {"query": "shipping", "top_k": 11},
    {"query": "shipping", "top_k": True}, {"query": "shipping", "top_k": 2.5},
    {"query": "shipping", "method": "unknown"},
], ids=["empty", "whitespace", "no-terms", "long", "many-terms", "low-k", "high-k", "bool-k", "float-k", "unknown-method"])
def test_query_limits_are_validated(client, body):
    assert client.post("/api/retrieval/search", json=body).status_code == 422


def test_query_operators_are_literal_terms_and_repetition_does_not_boost_scores(client):
    add(client, "shipping only")
    single = search(client, "shipping")
    repeated = search(client, "shipping shipping SHIPPING")
    assert repeated["hits"] == single["hits"]
    injected = search(client, 'tokens:shipping OR "NOT" NEAR(*) ; DROP TABLE documents --')
    assert len(injected["hits"]) == 1
    assert injected["hits"][0]["matched_terms"] == ["shipping"]
    assert len(client.get("/api/documents").json()) == 1


def test_top_k_tie_order_is_reproducible_across_different_import_order(tmp_path):
    corpus = [("a.txt", "shipping alpha"), ("b.txt", "shipping beta"), ("c.txt", "shipping gamma")]
    expected = [filename for filename, _ in sorted(corpus, key=lambda item: hashlib.sha256(item[1].encode()).hexdigest())]
    outputs = []
    for ordinal, items in enumerate([corpus, list(reversed(corpus))]):
        with TestClient(create_app(tmp_path / f"{ordinal}.sqlite3")) as client:
            for filename, text in items:
                add(client, text, filename)
            hits = search(client, "shipping", 2)["hits"]
            outputs.append([hit["filename"] for hit in hits])
            assert [hit["rank"] for hit in hits] == [1, 2]
    assert outputs[0] == outputs[1] == expected[:2]


def test_duplicate_replacement_and_delete_update_index_in_same_transaction(client):
    document = add(client, "shipping alpha")
    old = search(client, "shipping")
    old_revision = old["index"]["index_revision"]
    duplicate = client.post("/api/documents?filename=renamed.txt", content=b"shipping alpha")
    assert duplicate.json()["outcome"] == "duplicate"
    assert client.get("/api/retrieval/status").json()["index_revision"] == old_revision
    assert client.put(f"/api/documents/{document['id']}?filename=new.txt", content=b"warranty beta").status_code == 200
    assert search(client, "shipping")["hits"] == []
    new = search(client, "warranty")
    assert new["hits"][0]["revision"] == 2
    assert new["hits"][0]["id"] != old["hits"][0]["id"]
    assert new["index"]["index_revision"] > old_revision
    assert client.delete(f"/api/documents/{document['id']}").status_code == 204
    deleted = search(client, "warranty")
    assert deleted["hits"] == [] and deleted["index"]["indexed_segments"] == 0
    check_integrity(client.app.state.documents)


def test_failed_replacement_rolls_back_postings_statistics_and_revision(tmp_path):
    store = DocumentStore(tmp_path / "rollback.sqlite3")
    document = store.save(extract_document("old.txt", b"shipping alpha"))["document"]
    original = store.retrieve(["shipping"], 5)
    with store.connect() as connection:
        connection.execute("CREATE TRIGGER fail_search_source BEFORE INSERT ON segments BEGIN SELECT RAISE(ABORT, 'test failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        store.save(extract_document("new.txt", b"warranty beta"), document["id"])
    assert store.retrieve(["shipping"], 5) == original
    assert store.retrieve(["warranty"], 5)[1] == []
    check_integrity(store)


def test_persisted_index_and_vacuum_preserve_search_identity(tmp_path):
    path = tmp_path / "persistent.sqlite3"
    store = DocumentStore(path)
    removed = store.save(extract_document("removed.txt", b"obsolete"))["document"]["id"]
    store.save(extract_document("keep.txt", b"shipping Egypt"))
    store.delete(removed)
    before = store.retrieve(["shipping"], 5)
    with store.connect() as connection:
        connection.execute("VACUUM")
    assert DocumentStore(path).retrieve(["shipping"], 5) == before
    check_integrity(store)


def test_uncommitted_replacement_is_not_visible_to_search(tmp_path):
    store = DocumentStore(tmp_path / "snapshot.sqlite3")
    document_id = store.save(extract_document("old.txt", b"shipping alpha"))["document"]["id"]
    with ThreadPoolExecutor(max_workers=1) as executor:
        with store.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            store._write(connection, extract_document("new.txt", b"warranty beta"), document_id)
            status, hits = executor.submit(store.retrieve, ["shipping"], 5).result(timeout=3)
            assert status["indexed_segments"] == 1
            assert hits[0]["revision"] == 1 and hits[0]["text"] == "shipping alpha"
        assert store.retrieve(["shipping"], 5)[1] == []
        assert store.retrieve(["warranty"], 5)[1][0]["revision"] == 2


def test_schema_two_migration_backfills_sources_without_changing_them(tmp_path):
    path = tmp_path / "schema-two.sqlite3"
    store = DocumentStore(path)
    document_id = store.save(extract_document("existing.txt", b"shipping existing"))["document"]["id"]
    original = store.get(document_id)
    # Remove only derived schema-3 objects to reproduce the previous schema-2 store.
    with store.connect() as connection:
        for trigger in ["source_lexical_insert", "source_lexical_update", "lexical_insert", "lexical_update", "lexical_delete"]:
            connection.execute(f"DROP TRIGGER {trigger}")
        connection.execute("DROP TABLE segment_search")
        connection.execute("DROP TABLE lexical_segments")
        connection.execute("DROP TABLE lexical_config")
        connection.execute("PRAGMA user_version = 2")
    migrated = DocumentStore(path)
    assert migrated.get(document_id) == original
    status, hits = migrated.retrieve(["shipping"], 5)
    assert status["indexed_segments"] == 1 and hits[0]["id"] == original["segments"][0]["id"]
    check_integrity(migrated)


def test_analyzer_version_change_rebuilds_only_derived_index(tmp_path, monkeypatch):
    path = tmp_path / "analyzer.sqlite3"
    store = DocumentStore(path)
    document_id = store.save(extract_document("policy.txt", "الشَّحن".encode()))["document"]["id"]
    original = store.get(document_id)
    with monkeypatch.context() as context:
        context.setattr(lexical, "ANALYZER_VERSION", "en-ar-lexical-test-v2")
        rebuilt = DocumentStore(path)
        assert rebuilt.get(document_id) == original
        assert rebuilt.retrieve(["الشحن"], 5)[1][0]["document_id"] == document_id
        assert rebuilt.retrieval_status()["analyzer_version"] == "en-ar-lexical-test-v2"
    check_integrity(DocumentStore(path))


def test_demo_english_and_egyptian_queries_return_expected_supporting_sources(client):
    assert client.post("/api/demo/import").status_code == 200
    english = search(client, "return unused original packaging")
    egyptian = search(client, "لو الأوردر اتأخر أعمل إيه؟")
    assert any(hit["filename"] == "03-returns.md" and "unused" in hit["text"] for hit in english["hits"])
    assert any(hit["filename"] == "02-shipping.md" and "اتأخر" in hit["text"] for hit in egyptian["hits"])
    assert english["index"]["indexed_documents"] == 6
    # Functional smoke examples, not a retrieval benchmark or a human-reviewed quality score.
