"""One local end-to-end resource/functional diagnostic; not a quality benchmark."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import http.client
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.rag.ollama import OllamaClient
from app.rag.generation import generation_client
from app.rag.resources import available_memory_mib


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", default="What is the return policy?")
    parser.add_argument("--label", default="english")
    parser.add_argument('--phase', choices=['phase3a','phase3b'], default='phase3b')
    args = parser.parse_args()
    if not args.label.replace("-", "").isalnum():
        raise ValueError("Use an alphanumeric report label.")
    def ask():
        connection = http.client.HTTPConnection("127.0.0.1", 8000, timeout=165)
        try:
            connection.request("POST", "/api/oracle/ask", json.dumps({"question": args.question}), {"Content-Type": "application/json"})
            response = connection.getresponse()
            result = json.loads(response.read(128 * 1024))
            return response.status, result
        finally:
            connection.close()
    runtime = generation_client()
    local = runtime.requires_local_inference
    samples = []
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(ask)
        while not future.done():
            try:
                samples.append({"seconds": time.perf_counter()-started,
                    "free_ram_mib": available_memory_mib(), "loaded_models": runtime.request("/api/ps").get("models") if local else None})
            except Exception:
                pass  # A missing sampler result is recorded by its absence, never as zero usage.
            time.sleep(.5)
        status, result = future.result()
    report = {"purpose": "single functional/resource diagnostic, not quality evaluation",
              "recorded_at": datetime.now(timezone.utc).isoformat(), "http_status": status,
              "result": result, "samples": samples, "loaded_models_after": runtime.request("/api/ps").get("models") if local else None}
    directory = ROOT / "reports" / "generated"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{args.phase}-{args.label}.json"
    if path.exists():
        path = directory / f"{args.phase}-{args.label}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps({"report": str(path), "http_status": status, "result": result,
        "minimum_sampled_free_ram_mib": min((sample["free_ram_mib"] for sample in samples), default=None),
        "maximum_reported_model_vram_bytes": max((model.get("size_vram", 0) for sample in samples
            for model in sample["loaded_models"] or []), default=None),
        "loaded_models_after": report["loaded_models_after"]}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
