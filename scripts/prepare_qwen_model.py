"""Explicit ~986 MB local model pull; the application never calls /api/pull."""

import http.client
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.rag.ollama import OllamaClient, MODEL, MODEL_DIGEST


def main():
    client = OllamaClient()
    if client.inspect()["state"] == "ready":
        print(f"Pinned model already present: {MODEL} / {MODEL_DIGEST}")
        return
    connection = http.client.HTTPConnection(client.host, client.port, timeout=120)
    try:
        connection.request("POST", "/api/pull", json.dumps({"model": MODEL, "stream": True}), {"Content-Type": "application/json"})
        response = connection.getresponse()
        if response.status != 200:
            raise RuntimeError("Model pull failed. Check local Ollama.")
        last = -1
        while line := response.readline(65537):
            if len(line) > 65536:
                raise RuntimeError("Oversized model-pull response.")
            value = json.loads(line)
            if "error" in value:
                raise RuntimeError("Local model pull failed.")
            if value.get("total"):
                percent = int(100 * value.get("completed", 0) / value["total"])
                if percent >= last+5:
                    print(f"Model layer {percent}%", flush=True)
                    last = percent
            elif value.get("status"):
                print(value["status"], flush=True)
    finally:
        connection.close()
    result = client.inspect()
    if result["state"] != "ready":
        raise RuntimeError("Pulled model does not match the pinned manifest; inference is disabled.")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
