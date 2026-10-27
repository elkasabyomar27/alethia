"""Bounded loopback-only Ollama adapter. No SDK, cloud API, or automatic pull."""

import http.client
import json
import os
import socket
import subprocess
from urllib.parse import urlsplit

from app.ingestion import IngestionError

MODEL = "qwen2.5:1.5b"
MODEL_DIGEST = "65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b"
CONTEXT_TOKENS = 4096
OUTPUT_TOKENS = 384


def available_vram_mib():
    try:
        result = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        return max(int(line.strip()) for line in result.stdout.splitlines()) if result.returncode == 0 else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


class OllamaClient:
    provider = 'ollama'
    model = MODEL
    model_digest = MODEL_DIGEST
    requires_local_inference = True
    def __init__(self):
        value = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        parsed = urlsplit(value)
        if (parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1")
                or parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
            raise ValueError("OLLAMA_BASE_URL must be a plain loopback HTTP origin.")
        self.host = "127.0.0.1" if parsed.hostname == "localhost" else parsed.hostname
        self.port = parsed.port or 11434
        if os.environ.get("OLLAMA_MODEL", MODEL) != MODEL:
            raise ValueError(f"This measured runtime supports only {MODEL}.")

    def request(self, path, payload=None, timeout=3, limit=65536):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=timeout)
        try:
            body = json.dumps(payload, ensure_ascii=False).encode("utf8") if payload is not None else None
            connection.request("POST" if body is not None else "GET", path, body,
                               {"Content-Type": "application/json"})
            response = connection.getresponse()
            data = response.read(limit + 1)
            if len(data) > limit:
                raise IngestionError("Local inference returned an oversized response.", 503)
            if response.status != 200:
                raise IngestionError("Local inference failed. Check Ollama and the pinned model installation.", 503)
            value = json.loads(data)
            if not isinstance(value, dict) or "error" in value:
                raise ValueError("Invalid Ollama response")
            return value
        except (OSError, socket.timeout, http.client.HTTPException, ValueError, UnicodeError) as error:
            raise IngestionError("Local Ollama is unavailable or returned an invalid response. Start the local runtime and retry.", 503) from error
        finally:
            connection.close()

    def inspect(self):
        version = self.request("/api/version").get("version")
        models = self.request("/api/tags", limit=1024 * 1024).get("models", [])
        if not isinstance(version, str) or not isinstance(models, list) or any(not isinstance(item, dict) for item in models):
            raise IngestionError("Local Ollama returned invalid model metadata.", 503)
        model = next((item for item in models if item.get("name") == MODEL), None)
        if model is None:
            return {"state": "model_missing", "runtime_version": version, "model": MODEL, "digest": None}
        if model.get("digest") != MODEL_DIGEST:
            return {"state": "model_mismatch", "runtime_version": version, "model": MODEL, "digest": model.get("digest")}
        return {"state": "ready", "runtime_version": version, "model": MODEL, "digest": MODEL_DIGEST,
                "size_bytes": model.get("size"), "details": model.get("details")}

    def assert_idle(self):
        models = self.request("/api/ps").get("models")
        if not isinstance(models, list):
            raise IngestionError("Local Ollama did not report loaded models correctly.", 503)
        if models:
            raise IngestionError("Ollama already has a loaded model. Unload it before starting an ALETHIA answer.", 503)

    def generate(self, messages, schema):
        response = self.request("/api/chat", {"model": MODEL, "messages": messages, "format": schema,
            "stream": False, "keep_alive": 0, "options": {"num_ctx": CONTEXT_TOKENS,
            "num_predict": OUTPUT_TOKENS, "temperature": 0, "seed": 42, "num_thread": 2, "num_gpu": 99}}, timeout=120)
        if response.get("done") is not True or response.get("done_reason") != "stop":
            raise IngestionError("Local generation did not finish within its output limit. Try a narrower question.", 503)
        return response

    def unload(self):
        self.request("/api/generate", {"model": MODEL, "keep_alive": 0, "stream": False}, timeout=15)
        self.assert_idle()
