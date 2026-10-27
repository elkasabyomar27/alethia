from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_reports_liveness_without_claiming_rag_readiness():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.5.2", "phase": "benchmark_candidates"}


def test_capabilities_do_not_claim_unbuilt_features_or_results():
    response = client.get("/api/capabilities")
    assert response.status_code == 200
    assert response.json() == {
        "knowledge_base": "document_ingestion_ready",
        "retrieval": "bm25_ready",
        "generation": "gemini_adapter",
        "handoff": "local_tickets_ready",
        "evaluation": "retrieval_lab_ready",
        "dense_retrieval": "unavailable",
        "hybrid_retrieval": "unavailable",
    }


def test_unimplemented_chat_is_not_a_simulated_answer():
    assert client.post("/api/chat", json={"question": "What is the return policy?"}).status_code == 404
