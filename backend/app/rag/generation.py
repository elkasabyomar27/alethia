"""Explicit provider selection. Never fall back between local and cloud calls."""

from app.generation_config import settings
from app.rag.gemini import GeminiClient
from app.rag.ollama import OllamaClient


def generation_client():
    provider = settings().get('ALETHIA_LLM_PROVIDER') or 'gemini'
    if provider == 'gemini':
        return GeminiClient()
    if provider == 'ollama':
        return OllamaClient()
    raise ValueError('ALETHIA_LLM_PROVIDER must be gemini or ollama.')
