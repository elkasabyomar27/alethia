"""Source retrieval only. No generated answer or answerability decision."""

import json
import time
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.documents import SourceSegment
from app.rag.analyzer import tokenize

router = APIRouter(prefix="/api/retrieval", tags=["Knowledge retrieval"])


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=10, strict=True)
    method: Literal["bm25", "dense", "hybrid"] = "bm25"
    corpus: Literal["source", "encoder"] | None = None

    @field_validator("query")
    @classmethod
    def trim_query(cls, value: str):
        value = value.strip()
        if not value:
            raise ValueError("Enter a question or search phrase.")
        return value


class FusionConfiguration(BaseModel):
    algorithm: Literal["rrf"]
    rank_constant: int
    candidate_depth: int
    weights: dict[str, float]
    candidate_counts: dict[str, int]


class RetrievalContribution(BaseModel):
    rank: int
    score: float
    contribution: float


class IndexStatus(BaseModel):
    state: Literal["ready", "empty"]
    method: Literal["bm25", "dense", "hybrid"]
    indexed_segments: int
    searchable_segments: int
    indexed_documents: int
    index_revision: int
    retriever_version: str
    analyzer_version: str
    built_at: str
    sqlite_version: str
    k1: float
    b: float
    chunking: str
    match_mode: Literal["any_term", "cosine", "rank_fusion"]
    score_meaning: str
    corpus: Literal["source", "encoder"] = "source"
    corpus_hash: str | None = None
    model_revision: str | None = None
    dimension: int | None = None
    fusion: FusionConfiguration | None = None


class SearchHit(SourceSegment):
    rank: int
    filename: str
    format: Literal["txt", "markdown", "pdf", "docx"]
    revision: int
    content_hash: str
    processor_version: str
    score: float
    matched_terms: list[str]
    warnings: list[str]
    chunk_id: str | None = None
    token_count: int | None = None
    retrievers: dict[str, RetrievalContribution | None] | None = None


class SearchResponse(BaseModel):
    query: str
    normalized_terms: list[str]
    top_k: int
    latency_ms: float
    index: IndexStatus
    hits: list[SearchHit]
    worker_diagnostics: dict | None = None


@router.get("/status", response_model=IndexStatus)
def status(request: Request):
    return request.app.state.documents.retrieval_status()


@router.get("/dense/status")
def dense_status(request: Request):
    return request.app.state.dense.status()


@router.post("/dense/build", status_code=202)
def build_dense(request: Request):
    return request.app.state.dense.start_build()


@router.post("/search", response_model=SearchResponse)
def search(request: Request, body: SearchRequest):
    started = time.perf_counter()
    terms = list(dict.fromkeys(tokenize(body.query)))
    if not terms:
        raise HTTPException(422, "Enter at least one word or number to search.")
    if len(terms) > 64:
        raise HTTPException(422, "Use no more than 64 distinct search terms.")
    corpus = body.corpus or ("encoder" if body.method in ("dense", "hybrid") else "source")
    if body.method in ("dense", "hybrid") and corpus != "encoder":
        raise HTTPException(422, "Dense and hybrid retrieval require the encoder chunk corpus.")
    diagnostics = None
    if corpus == "encoder":
        index, rows, diagnostics = request.app.state.dense.search(body.query, terms, body.top_k, body.method)
    else:
        index, rows = request.app.state.documents.retrieve(terms, body.top_k)
    hits = []
    for rank, row in enumerate(rows, 1):
        row["warnings"] = json.loads(row.pop("warnings_json"))
        source_terms = set(tokenize(row["text"]))
        hits.append({**row, "rank": rank, "matched_terms": [term for term in terms if term in source_terms]})
    return {"query": body.query, "normalized_terms": terms, "top_k": body.top_k,
            "latency_ms": (time.perf_counter() - started) * 1000, "index": index, "hits": hits,
            "worker_diagnostics": diagnostics}
