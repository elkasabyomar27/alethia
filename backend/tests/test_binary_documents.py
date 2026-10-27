"""Generated minimal parser fixtures, not portfolio document deliverables."""

from html import escape
from io import BytesIO
from pathlib import Path
import sqlite3
import subprocess
import sys
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject, NumberObject
import pytest

from app.database import DocumentStore
from app.ingestion import extract_document
from app.main import create_app
from app.parsers import runner, worker

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
CONTENT_TYPES = b'''<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'''


def paragraph(text: str, style: str | None = None) -> str:
    properties = f'<w:pPr><w:pStyle w:val="{escape(style)}"/></w:pPr>' if style else ""
    return f'<w:p>{properties}<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'


def make_docx(body: str, extra: dict[str, bytes] | None = None, document_xml: bytes | None = None) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("word/document.xml", document_xml or f'<w:document xmlns:w="{W_NS}"><w:body>{body}<w:sectPr/></w:body></w:document>'.encode())
        for name, value in (extra or {}).items():
            archive.writestr(name, value)
    return output.getvalue()


def make_pdf(pages: list[str | None], *, image_only=False, encrypted=False, expanded_stream=False, expanded_bytes=1024 * 1024 + 1) -> bytes:
    writer = PdfWriter()
    font = writer._add_object(DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")}))
    for text in pages:
        page = writer.add_blank_page(width=600, height=800)
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
        if image_only:
            image = DecodedStreamObject()
            image.set_data(b"\x80")
            image.update({NameObject("/Type"): NameObject("/XObject"), NameObject("/Subtype"): NameObject("/Image"), NameObject("/Width"): NumberObject(1), NameObject("/Height"): NumberObject(1), NameObject("/ColorSpace"): NameObject("/DeviceGray"), NameObject("/BitsPerComponent"): NumberObject(8)})
            page["/Resources"][NameObject("/XObject")] = DictionaryObject({NameObject("/Im0"): writer._add_object(image)})
            data = b"q 100 0 0 100 20 20 cm /Im0 Do Q"
        elif text is not None:
            escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            data = f"BT /F1 12 Tf 40 700 Td ({escaped}) Tj ET".encode("latin-1")
        else:
            continue
        if expanded_stream:
            data += b"\n%" + b"X" * expanded_bytes
        stream = DecodedStreamObject()
        stream.set_data(data)
        page[NameObject("/Contents")] = writer._add_object(stream.flate_encode() if expanded_stream else stream)
    if encrypted:
        writer.encrypt("test-password")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "binary.sqlite3")) as test_client:
        yield test_client


def post_file(client, filename, payload):
    return client.post("/api/documents", params={"filename": filename}, content=payload)


def test_pdf_preserves_physical_pages_and_warns_about_empty_pages(client):
    payload = make_pdf(["First page: shipping.", None, "Third page: returns."])
    response = post_file(client, "policies.pdf", payload)
    assert response.status_code == 201, response.text
    metadata = response.json()["document"]
    assert metadata["page_count"] == 3
    assert metadata["format"] == "pdf"
    assert metadata["hash_basis"] == "original_file_bytes"
    assert any("Page 2 has" in warning for warning in metadata["warnings"])
    detail = client.get(f"/api/documents/{metadata['id']}").json()
    assert [segment["page_number"] for segment in detail["segments"]] == [1, 3]
    retrieved = client.post("/api/retrieval/search", json={"query": "shipping"}).json()["hits"]
    assert retrieved[0]["page_number"] == 1 and retrieved[0]["id"] == detail["segments"][0]["id"]
    for segment in detail["segments"]:
        assert segment["source_label"] == f"Page {segment['page_number']}"
        assert detail["text"][segment["start_char"]:segment["end_char"]] == segment["text"]
    repeated = post_file(client, "renamed.pdf", payload)
    assert repeated.json()["outcome"] == "duplicate"
    assert repeated.json()["document"] == metadata
    # Identical extracted TXT must not erase the PDF's page provenance.
    assert post_file(client, "same-text.txt", detail["text"].encode()).status_code == 201


def test_docx_preserves_body_order_arabic_headings_tables_and_hyperlink_text(client):
    body = paragraph("Returns", "Heading1") + paragraph("يمكن إرجاع المنتج غير المستخدم خلال 14 يومًا.")
    body += '<w:tbl><w:tr><w:tc>' + paragraph("Product") + '</w:tc><w:tc>' + paragraph("Warranty") + '</w:tc></w:tr><w:tr><w:tc>' + paragraph("Lamp") + '</w:tc><w:tc>' + paragraph("12 months") + '</w:tc></w:tr></w:tbl>'
    body += '<w:p><w:hyperlink><w:r><w:t>Visible link text only</w:t></w:r></w:hyperlink></w:p>'
    response = post_file(client, "سياسة.docx", make_docx(body))
    assert response.status_code == 201, response.text
    metadata = response.json()["document"]
    assert metadata["page_count"] is None
    assert metadata["processor_version"] == "docx-sources-v1"
    detail = client.get(f"/api/documents/{metadata['id']}").json()
    assert "يمكن إرجاع المنتج" in detail["text"]
    assert detail["text"].index("Product\tWarranty") < detail["text"].index("Lamp\t12 months") < detail["text"].index("Visible link text")
    assert [segment["source_label"] for segment in detail["segments"]] == ["Paragraph 1", "Paragraph 2", "Table 1, row 1", "Table 1, row 2", "Paragraph 3"]
    assert all(segment["section"] == "Returns" and segment["page_number"] is None for segment in detail["segments"])
    for segment in detail["segments"]:
        assert detail["text"][segment["start_char"]:segment["end_char"]] == segment["text"]
    assert any("headers" in warning for warning in metadata["warnings"])
    retrieved = client.post("/api/retrieval/search", json={"query": "يمكن إرجاع المنتج"}).json()["hits"]
    assert retrieved[0]["source_label"] == "Paragraph 2"
    assert retrieved[0]["page_number"] is None and retrieved[0]["warnings"] == metadata["warnings"]


def test_docx_custom_heading_inheritance_and_explicit_outline():
    styles = f'<w:styles xmlns:w="{W_NS}"><w:style w:styleId="Custom"><w:basedOn w:val="Heading2"/></w:style></w:styles>'.encode()
    body = paragraph("Top", "Heading1") + paragraph("Custom section", "Custom")
    body += '<w:p><w:pPr><w:outlineLvl w:val="2"/></w:pPr><w:r><w:t>Subsection</w:t></w:r></w:p>'
    document = extract_document("styles.docx", make_docx(body, {"word/styles.xml": styles}))
    assert [segment.section for segment in document.segments] == ["Top", "Top / Custom section", "Top / Custom section / Subsection"]


@pytest.mark.parametrize(("name", "payload", "status", "message"), [
    ("fake.pdf", b"not a PDF", 422, "signature"),
    ("broken.pdf", b"%PDF-1.5\ninvalid", 422, "malformed"),
    ("locked.pdf", make_pdf(["Secret"], encrypted=True), 422, "Password-protected"),
    ("blank.pdf", make_pdf([None]), 422, "no extractable text"),
    ("scan.pdf", make_pdf([None], image_only=True), 422, "OCR"),
    ("pages.pdf", make_pdf([None] * 51), 413, "50-page"),
    ("expanded.pdf", make_pdf(["Small text"], expanded_stream=True), 413, "expanded content"),
    ("decode-limit.pdf", make_pdf(["Small text"], expanded_stream=True, expanded_bytes=3 * 1024 * 1024), 413, "expanded content"),
    ("total-streams.pdf", make_pdf(["Small text"] * 5, expanded_stream=True, expanded_bytes=900 * 1024), 413, "expanded content"),
    ("fake.docx", b"plain text", 422, "DOCX ZIP"),
    ("truncated.docx", b"PK\x03\x04broken", 422, "malformed"),
    ("empty.docx", make_docx(paragraph(" ")), 422, "no extractable"),
    ("images.docx", make_docx('<w:p><w:r><w:drawing/></w:r></w:p>'), 422, "OCR"),
    ("changes.docx", make_docx('<w:p><w:ins><w:r><w:t>Changed text</w:t></w:r></w:ins></w:p>'), 422, "tracked changes"),
    ("nested.docx", make_docx('<w:tbl><w:tr><w:tc><w:tbl/></w:tc></w:tr></w:tbl>'), 422, "Nested"),
    ("blocks.docx", make_docx('<w:sdt><w:sdtContent>' + paragraph("Hidden body") + '</w:sdtContent></w:sdt>'), 422, "body blocks"),
    ("large.docx", make_docx(paragraph("x" * 200_001)), 413, "character"),
    ("xml-limit.docx", make_docx(paragraph("Text"), {"word/oversized.xml": b" " * (2 * 1024 * 1024 + 1)}), 413, "2 MiB"),
    ("zip-limit.docx", make_docx(paragraph("Text"), {"word/media/big.bin": b"0" * (9 * 1024 * 1024)}), 413, "expanded-size"),
    ("entries.docx", make_docx(paragraph("Text"), {f"word/{index}.bin": b"" for index in range(255)}), 413, "entry-count"),
    ("unsafe.docx", make_docx(paragraph("Text"), {"../outside.txt": b"do not extract"}), 422, "unsafe"),
    ("entity.docx", make_docx("", document_xml=f'<!DOCTYPE w:document [<!ENTITY xxe SYSTEM "file:///private">]><w:document xmlns:w="{W_NS}"><w:body><w:p><w:r><w:t>&xxe;</w:t></w:r></w:p></w:body></w:document>'.encode()), 422, "malformed"),
], ids=["signature", "malformed-pdf", "encrypted", "blank", "image-only", "page-limit", "expanded-pdf", "decode-limit", "total-streams", "not-docx", "truncated-zip", "empty-docx", "image-docx", "tracked", "nested-table", "body-block", "text-limit", "xml-limit", "zip-size", "zip-entries", "zip-path", "xml-entity"])
def test_binary_rejections_are_clear_and_do_not_persist(client, name, payload, status, message):
    response = post_file(client, name, payload)
    assert response.status_code == status, response.text
    assert message.lower() in response.json()["detail"].lower()
    assert client.get("/api/documents").json() == []


def test_invalid_binary_replacement_leaves_existing_document_unchanged(client):
    document_id = post_file(client, "original.txt", b"Keep this policy.").json()["document"]["id"]
    original = client.get(f"/api/documents/{document_id}").json()
    assert client.put(f"/api/documents/{document_id}?filename=blank.pdf", content=make_pdf([None])).status_code == 422
    assert client.get(f"/api/documents/{document_id}").json() == original
    updated = client.put(f"/api/documents/{document_id}?filename=new.pdf", content=make_pdf(["New policy"]))
    assert updated.status_code == 200
    assert updated.json()["document"]["revision"] == 2
    assert updated.json()["document"]["id"] == document_id
    assert client.get(f"/api/documents/{document_id}").json()["segments"][0]["page_number"] == 1


def test_binary_metadata_survives_restart(tmp_path):
    path = tmp_path / "restart.sqlite3"
    with TestClient(create_app(path)) as first:
        document_id = post_file(first, "two.pdf", make_pdf(["Page one", "Page two"])).json()["document"]["id"]
        original = first.get(f"/api/documents/{document_id}").json()
    with TestClient(create_app(path)) as second:
        assert second.get(f"/api/documents/{document_id}").json() == original


def test_worker_timeout_and_busy_slot_leave_library_unchanged(client, monkeypatch):
    payload = make_pdf(["Safe text"])
    with monkeypatch.context() as context:
        context.setattr(runner, "PARSER_TIMEOUT_SECONDS", 0.001)
        response = post_file(client, "slow.pdf", payload)
        assert response.status_code == 422
        assert "10-second" in response.json()["detail"]
    assert client.get("/api/documents").json() == []
    assert runner._slot.acquire(blocking=False)
    try:
        assert post_file(client, "busy.pdf", payload).status_code == 503
    finally:
        runner._slot.release()
    assert post_file(client, "recovered.pdf", payload).status_code == 201


def test_worker_resource_protection_fails_closed(monkeypatch, capsys):
    def unavailable():
        raise OSError("Unavailable in test")
    monkeypatch.setattr(worker, "apply_memory_limit", unavailable)
    worker.main()
    assert '"status": 503' in capsys.readouterr().out


def test_actual_worker_memory_limit_rejects_large_allocation():
    code = "from app.parsers.worker import apply_memory_limit; apply_memory_limit()\ntry:\n    data = bytearray(320 * 1024 * 1024)\nexcept MemoryError:\n    print('allocation blocked')\nelse:\n    raise SystemExit('memory cap failed')"
    result = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1], capture_output=True,
                            timeout=10, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert b"allocation blocked" in result.stdout


def test_version_one_migration_preserves_document_and_segment_identity(tmp_path):
    path = tmp_path / "old.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.executescript('''
            CREATE TABLE documents (id TEXT PRIMARY KEY, filename TEXT NOT NULL, format TEXT NOT NULL,
                content_hash TEXT NOT NULL UNIQUE, text TEXT NOT NULL, size_bytes INTEGER NOT NULL,
                revision INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, processor_version TEXT NOT NULL);
            CREATE TABLE segments (id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                ordinal INTEGER NOT NULL, section TEXT NOT NULL, text TEXT NOT NULL, start_char INTEGER NOT NULL,
                end_char INTEGER NOT NULL, start_line INTEGER NOT NULL, end_line INTEGER NOT NULL);
            INSERT INTO documents VALUES ('old-doc', 'old.txt', 'txt', 'hash', 'Existing policy', 15, 1, 'then', 'then', 'text-sections-v1');
            INSERT INTO segments VALUES ('old-segment', 'old-doc', 0, 'Document', 'Existing policy', 0, 15, 1, 1);
            PRAGMA user_version = 1;
        ''')
    store = DocumentStore(path)
    document = store.get("old-doc")
    assert document["text"] == "Existing policy"
    assert document["segments"][0]["id"] == "old-segment"
    assert document["hash_basis"] == "normalized_text"
    assert document["page_count"] is None and document["warnings"] == []
    assert document["segments"][0]["page_number"] is None
    assert DocumentStore(path).get("old-doc") == document
    with store.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3


def test_future_database_version_is_not_downgraded(tmp_path):
    path = tmp_path / "future.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version = 4")
    with pytest.raises(RuntimeError, match="newer"):
        DocumentStore(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 4
