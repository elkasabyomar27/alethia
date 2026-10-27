"""Oracle generation and local saved conversations."""

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Literal
from app.rag.oracle import Claim

router = APIRouter(prefix="/api/oracle", tags=["The Oracle"])


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=500)
    conversation_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    expected_revision: int | None = Field(default=None, ge=1, strict=True)

    @field_validator("question")
    @classmethod
    def trim(cls, value):
        if not value.strip():
            raise ValueError("Enter a question.")
        return value.strip()


class CitedSource(BaseModel):
    source_id: str
    document_id: str
    id: str
    chunk_id: str
    filename: str
    section: str
    revision: int
    start_char: int
    end_char: int
    text: str
    citation_state: Literal['current','changed','deleted'] = 'current'


class OracleResponse(BaseModel):
    question: str
    status: Literal["answered", "needs_human", "needs_clarification"]
    reason: str | None
    claims: list[Claim]
    sources: list[CitedSource]
    latency_ms: float
    model: str
    model_digest: str | None
    provider: str | None = None
    model_version: str | None = None
    prompt_version: str
    corpus_hash: str | None
    context_version: str | None = None
    prompt_budget_bytes: int
    generation_diagnostics: dict | None
    conversation_id: str | None = None
    conversation_revision: int | None = None
    turn_id: str | None = None
    created_at: str | None = None
    ticket_id: str | None = None


@router.get("/status")
def status(request: Request):
    return request.app.state.oracle.status()


@router.post("/ask", response_model=OracleResponse)
def ask(request: Request, body: Question):
    store = request.app.state.conversations
    store.check(body.conversation_id, body.expected_revision)
    result = request.app.state.oracle.ask(body.question)
    return store.append(result, body.conversation_id, body.expected_revision)


@router.get('/conversations')
def conversations(request: Request):
    return request.app.state.conversations.list()


@router.get('/conversations/{identity}')
def conversation(request: Request, identity: str):
    detail=request.app.state.conversations.get(identity)
    links=request.app.state.tickets.links([turn['turn_id'] for turn in detail['turns']])
    for turn in detail['turns']: turn['ticket_id']=links.get(turn['turn_id'])
    return detail


@router.delete('/conversations/{identity}', status_code=204)
def delete_conversation(request: Request, identity: str):
    request.app.state.conversations.delete(identity)
    return Response(status_code=204)
