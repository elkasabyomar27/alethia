from concurrent.futures import ThreadPoolExecutor
import sqlite3

from fastapi.testclient import TestClient
import pytest

from app import database
from app.database import DocumentStore
from app.ingestion import MAX_UPLOAD_BYTES, extract_document
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "test.sqlite3")) as test_client:
        yield test_client


def upload(client, content="# Shipping\nDelivery in 2–4 days.\n\n## الشحن\nالتوصيل داخل مصر فقط.\n", filename="policy.md", **kwargs):
    return client.post("/api/documents", params={"filename": filename}, content=content.encode("utf-8"), **kwargs)


def test_upload_inspection_references_and_plain_text_safety(client):
    text = "# Returns\n<script>alert('x')</script>\n\n## الإرجاع\nيمكن الإرجاع خلال 14 يومًا.\n"
    response = upload(client, text)
    assert response.status_code == 201
    document = response.json()["document"]
    assert document["revision"] == 1
    assert document["format"] == "markdown"
    detail = client.get(f"/api/documents/{document['id']}").json()
    assert detail["text"] == text
    assert detail["segment_count"] == 2
    assert detail["segments"][1]["section"] == "Returns / الإرجاع"
    assert detail["segments"][1]["start_line"] == 4
    assert detail["segments"][1]["end_line"] == 5
    for segment in detail["segments"]:
        assert text[segment["start_char"]:segment["end_char"]] == segment["text"]
        assert segment["document_id"] == document["id"]
    assert len(client.get("/api/documents").json()) == 1
    assert "text" not in client.get("/api/documents").json()[0]


def test_duplicate_normalization_preserves_original_record(client):
    original = upload(client, "café\nسياسة الشحن\n", "original.txt").json()["document"]
    response = upload(client, "\ufeffcafe\u0301\r\nسياسة الشحن\r\n", "renamed.md")
    assert response.status_code == 200
    assert response.json()["outcome"] == "duplicate"
    assert response.json()["document"] == original
    assert len(client.get("/api/documents").json()) == 1


@pytest.mark.parametrize(("name", "content", "status"), [
    ("bad.exe", b"executable", 415), ("bad.doc", b"legacy", 415),
    ("../policy.md", b"text", 422), ("C:\\policy.txt", b"text", 422),
    ("bad\x00.txt", b"text", 422), ("bad\u202e.txt", b"text", 422),
    ("empty.txt", b" \n\t", 422), ("invalid.txt", b"\xff\xfe", 422),
    ("binary.txt", b"text\x00binary", 422),
    ("large.txt", b"x" * (MAX_UPLOAD_BYTES + 1), 413),
    ("long.txt", b"x" * 200_001, 413),
    ("many.md", b"# Heading\n" * 501, 422),
], ids=["executable", "legacy-doc", "relative-path", "absolute-path", "null-filename", "bidi-filename", "empty", "invalid-utf8", "binary", "byte-limit", "character-limit", "section-limit"])
def test_invalid_uploads_are_rejected_without_persistence(client, name, content, status):
    response = client.post("/api/documents", params={"filename": name}, content=content)
    assert response.status_code == status
    assert client.get("/api/documents").json() == []


def test_streamed_body_limit_does_not_depend_on_content_length(client):
    response = client.post("/api/documents?filename=large.txt", content=iter([b"x" * 65536] * 17))
    assert response.status_code == 413
    assert "upload limit" in response.json()["detail"]
    assert client.get("/api/documents").json() == []


def test_replacement_keeps_document_id_invalidates_old_segments_and_is_atomic(client):
    original = upload(client).json()["document"]
    document_id = original["id"]
    old_detail = client.get(f"/api/documents/{document_id}").json()
    response = client.put(f"/api/documents/{document_id}?filename=new.md", content=b"# Updated\nA different policy.")
    assert response.status_code == 200
    assert response.json()["outcome"] == "updated"
    updated = response.json()["document"]
    assert updated["id"] == document_id
    assert updated["revision"] == 2
    assert updated["created_at"] == original["created_at"]
    new_detail = client.get(f"/api/documents/{document_id}").json()
    assert not {s["id"] for s in new_detail["segments"]} & {s["id"] for s in old_detail["segments"]}
    other = upload(client, "Some other policy", "other.txt").json()["document"]
    conflict = client.put(f"/api/documents/{document_id}?filename=other.txt", content=b"Some other policy")
    assert conflict.status_code == 409
    assert client.get(f"/api/documents/{document_id}").json() == new_detail
    invalid = client.put(f"/api/documents/{document_id}?filename=empty.txt", content=b" ")
    assert invalid.status_code == 422
    assert client.get(f"/api/documents/{other['id']}").status_code == 200
    assert client.get(f"/api/documents/{document_id}").json() == new_detail


def test_delete_cascades_and_missing_ids_return_404(client):
    document_id = upload(client).json()["document"]["id"]
    assert client.delete(f"/api/documents/{document_id}").status_code == 204
    assert client.get(f"/api/documents/{document_id}").status_code == 404
    assert client.delete(f"/api/documents/{document_id}").status_code == 404
    assert client.put("/api/documents/missing?filename=valid.txt", content=b"valid").status_code == 404
    with client.app.state.documents.connect() as connection:
        assert connection.execute("SELECT count(*) FROM segments").fetchone()[0] == 0


def test_persistence_across_application_restart(tmp_path):
    path = tmp_path / "persistent.sqlite3"
    with TestClient(create_app(path)) as first:
        document_id = upload(first).json()["document"]["id"]
        detail = first.get(f"/api/documents/{document_id}").json()
    with TestClient(create_app(path)) as second:
        assert second.get(f"/api/documents/{document_id}").json() == detail
        assert upload(second).json()["outcome"] == "duplicate"


def test_demo_import_is_repeatable_and_capacity_failure_rolls_back(client, monkeypatch):
    monkeypatch.setattr(database, "MAX_DOCUMENTS", 2)
    assert client.post("/api/demo/import").status_code == 409
    assert client.get("/api/documents").json() == []
    monkeypatch.setattr(database, "MAX_DOCUMENTS", 100)
    first = client.post("/api/demo/import")
    assert first.status_code == 200
    assert len(first.json()) == 6
    assert all(result["outcome"] == "created" for result in first.json())
    assert all(result["outcome"] == "duplicate" for result in client.post("/api/demo/import").json())
    assert len(client.get("/api/documents").json()) == 6


def test_capacity_does_not_block_duplicates_or_replacements(client, monkeypatch):
    monkeypatch.setattr(database, "MAX_DOCUMENTS", 1)
    original = upload(client).json()["document"]
    assert upload(client).json()["outcome"] == "duplicate"
    assert upload(client, "Another policy").status_code == 409
    assert client.put(f"/api/documents/{original['id']}?filename=policy.txt", content=b"Updated text").status_code == 200


def test_concurrent_duplicates_create_one_record(tmp_path):
    store = DocumentStore(tmp_path / "concurrent.sqlite3")
    document = extract_document("test.txt", b"A test policy")
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: store.save(document), range(4)))
    assert [item["outcome"] for item in results].count("created") == 1
    assert len({item["document"]["id"] for item in results}) == 1
    assert len(store.list_documents()) == 1


def test_failed_replacement_rolls_back_document_and_segments(tmp_path):
    store = DocumentStore(tmp_path / "rollback.sqlite3")
    document_id = store.save(extract_document("old.txt", b"Old policy"))["document"]["id"]
    original = store.get(document_id)
    with store.connect() as connection:
        connection.execute("CREATE TRIGGER fail_segment BEFORE INSERT ON segments BEGIN SELECT RAISE(ABORT, 'test failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        store.save(extract_document("new.txt", b"New policy"), document_id)
    assert store.get(document_id) == original


def test_long_segments_cover_source_and_fenced_headings_are_not_sections():
    text = "# Main\n```markdown\n# Not a heading\n```\n" + ("سياسة الشحن وإجراءات الإرجاع. " * 160) + "\n## Details\nDone."
    document = extract_document("long.md", text.encode())
    assert {segment.section for segment in document.segments} == {"Main", "Main / Details"}
    covered = set()
    for segment in document.segments:
        assert len(segment.text) <= 1200
        assert segment.text == text[segment.start_char:segment.end_char]
        covered.update(range(segment.start_char, segment.end_char))
    assert covered == set(range(len(text)))
