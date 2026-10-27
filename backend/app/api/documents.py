"""Document management. Raw file bodies allow limits before multipart parsing."""

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.database import DocumentStore
from app.ingestion import IngestionError, MAX_UPLOAD_BYTES, extract_document, validate_filename

router = APIRouter(prefix="/api", tags=["Athena's Library"])
DEMO_DIRECTORY = Path(__file__).resolve().parents[3] / "data" / "demo" / "ecommerce"
DEMO_FILES = ("01-products.md", "02-shipping.md", "03-returns.md", "04-warranty.md", "05-faq.md", "06-support.md")


class DocumentMetadata(BaseModel):
    id: str
    filename: str
    format: Literal["txt", "markdown", "pdf", "docx"]
    content_hash: str
    size_bytes: int
    revision: int
    created_at: str
    updated_at: str
    processor_version: str
    character_count: int
    segment_count: int
    hash_basis: Literal["normalized_text", "original_file_bytes"]
    page_count: int | None
    warnings: list[str]


class SourceSegment(BaseModel):
    id: str
    document_id: str
    ordinal: int
    section: str
    text: str
    start_char: int
    end_char: int
    start_line: int
    end_line: int
    page_number: int | None
    source_label: str | None


class DocumentDetail(DocumentMetadata):
    text: str
    segments: list[SourceSegment]


class SaveResult(BaseModel):
    outcome: Literal["created", "duplicate", "updated"]
    document: DocumentMetadata


def store(request: Request) -> DocumentStore:
    return request.app.state.documents


async def read_upload(request: Request, filename: str):
    validate_filename(filename)
    declared = request.headers.get("content-length")
    if declared:
        try:
            size = int(declared)
        except ValueError as exc:
            raise HTTPException(400, "Invalid Content-Length.") from exc
        if size < 0:
            raise HTTPException(400, "Invalid Content-Length.")
        if size > MAX_UPLOAD_BYTES:
            raise IngestionError("File exceeds the 1 MiB upload limit.", 413)
    payload = bytearray()
    async for block in request.stream():
        if len(payload) + len(block) > MAX_UPLOAD_BYTES:
            raise IngestionError("File exceeds the 1 MiB upload limit.", 413)
        payload.extend(block)
    return await run_in_threadpool(extract_document, filename, bytes(payload))


@router.get("/documents", response_model=list[DocumentMetadata])
def list_documents(request: Request):
    return store(request).list_documents()


@router.post("/documents", response_model=SaveResult)
async def upload_document(request: Request, response: Response, filename: str = Query(max_length=180)):
    """Send the file itself as the body (not multipart), filename as a query parameter."""
    document = await read_upload(request, filename)
    result = await run_in_threadpool(store(request).save, document)
    response.status_code = 201 if result["outcome"] == "created" else 200
    return result


@router.get("/documents/{document_id}", response_model=DocumentDetail)
def get_document(request: Request, document_id: str):
    document = store(request).get(document_id)
    if document is None:
        raise HTTPException(404, "Document not found.")
    return document


@router.put("/documents/{document_id}", response_model=SaveResult)
async def replace_document(request: Request, document_id: str, filename: str = Query(max_length=180)):
    document = await read_upload(request, filename)
    return await run_in_threadpool(store(request).save, document, document_id)


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(request: Request, document_id: str):
    if not store(request).delete(document_id):
        raise HTTPException(404, "Document not found.")
    return Response(status_code=204)


@router.post("/demo/import", response_model=list[SaveResult])
def import_demo(request: Request):
    """Only import the six bundled fictional files; all changes form one transaction."""
    documents = [extract_document(name, (DEMO_DIRECTORY / name).read_bytes()) for name in DEMO_FILES]
    return store(request).import_pack(documents)
