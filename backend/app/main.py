"""Local API. No model loading or network calls at startup."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api.documents import router
from app.api.retrieval import router as retrieval_router
from app.database import DocumentStore
from app.ingestion import IngestionError
from app.rag.dense import DenseIndex
from app.rag.oracle import Oracle
from app.api.oracle import router as oracle_router
from app.conversations import ConversationStore
from app.tickets import TicketStore
from app.api.tickets import router as tickets_router
from app.evaluation.store import EvaluationStore
from app.evaluation.runner import EvaluationRunner
from app.api.evaluation import router as evaluation_router


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str = "0.5.2"
    phase: Literal["benchmark_candidates"] = "benchmark_candidates"


class CapabilitiesResponse(BaseModel):
    knowledge_base: Literal["document_ingestion_ready"] = "document_ingestion_ready"
    retrieval: Literal["bm25_ready"] = "bm25_ready"
    generation: str = "gemini_adapter"
    handoff: Literal["local_tickets_ready"] = "local_tickets_ready"
    evaluation: Literal["retrieval_lab_ready"] = "retrieval_lab_ready"
    dense_retrieval: str = "unavailable"
    hybrid_retrieval: str = "unavailable"


def health() -> HealthResponse:
    """Process liveness only; does not imply model readiness."""
    return HealthResponse()


def capabilities(request: Request) -> CapabilitiesResponse:
    """Report implemented capabilities without simulated product data."""
    dense = getattr(request.app.state, "dense", None)
    state = dense.status() if dense else None
    oracle = getattr(request.app.state,'oracle',None)
    provider = getattr(oracle.client,'provider','gemini') if oracle else 'gemini'
    return CapabilitiesResponse(generation=f'{provider}_adapter', dense_retrieval=state["state"] if state else "unavailable",
                                hybrid_retrieval=state["state"] if state and state["runtime_available"] else "unavailable")


def create_app(database_path: Path | None = None, dense_directory: Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.documents = DocumentStore(database_path or Path(__file__).resolve().parents[2] / "data" / "local" / "alethia.sqlite3")
        # Test/alternate databases get an independent artifact directory by default.
        directory = dense_directory or (database_path.parent / f"{database_path.stem}-dense" if database_path else None)
        application.state.dense = DenseIndex(application.state.documents, directory)
        application.state.oracle = Oracle(application.state.dense)
        application.state.conversations = ConversationStore(application.state.documents.path.with_name(
            application.state.documents.path.stem + '-conversations.sqlite3'), application.state.documents)
        application.state.tickets = TicketStore(application.state.documents.path.with_name(
            application.state.documents.path.stem + '-tickets.sqlite3'),application.state.conversations)
        evaluation_path=application.state.documents.path.with_name(application.state.documents.path.stem+'-evaluations.sqlite3')
        report_path=(database_path.parent/'evaluation-reports' if database_path else Path(__file__).resolve().parents[2]/'reports'/'generated'/'evaluation')
        application.state.evaluations=EvaluationStore(evaluation_path,application.state.documents,report_path)
        application.state.evaluation_runner=EvaluationRunner(application.state.evaluations,application.state.dense)
        try:
            yield
        finally:
            application.state.evaluation_runner.close()
            application.state.dense.close()

    application = FastAPI(title="ALETHIA", version="0.5.2", description="Where Knowledge Becomes Answers.", lifespan=lifespan)

    @application.exception_handler(IngestionError)
    async def ingestion_error(_request: Request, error: IngestionError):
        return JSONResponse(status_code=error.status, content={"detail": str(error)})

    application.add_api_route("/api/health", health, response_model=HealthResponse)
    application.add_api_route("/api/capabilities", capabilities, response_model=CapabilitiesResponse)
    application.include_router(router)
    application.include_router(retrieval_router)
    application.include_router(oracle_router)
    application.include_router(tickets_router)
    application.include_router(evaluation_router)
    return application


app = create_app()
