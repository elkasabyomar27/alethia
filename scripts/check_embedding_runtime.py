"""Reproducible small inference/resource diagnostic, not a quality benchmark."""

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.rag.embedding_config import MODEL_ID, MODEL_REVISION, MIN_AVAILABLE_MEMORY_MIB
from app.rag.resources import available_memory_mib


def main():
    payload = {"examples": [
        [True, "What happens if my order arrives damaged?"],
        [False, "Report damage within 48 hours of delivery and contact support with the order number and photos."],
        [True, "لو الأوردر اتأخر أعمل إيه؟"],
        [False, "لو الأوردر اتأخر عن المدة المتوقعة، تواصل مع الدعم برقم الأوردر لمراجعة حالة الشحنة."],
    ]}
    before = available_memory_mib()
    if before < MIN_AVAILABLE_MEMORY_MIB:
        raise RuntimeError(f"At least {MIN_AVAILABLE_MEMORY_MIB} MiB free RAM is required; currently {before:.0f} MiB.")
    result = subprocess.run([sys.executable, "-m", "app.rag.dense_worker", "trial"], input=json.dumps(payload).encode(),
        cwd=ROOT / "backend", capture_output=True, timeout=45,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    lines = result.stdout.splitlines()
    if result.returncode or not lines:
        raise RuntimeError("Embedding runtime diagnostic failed.")
    data = json.loads(lines[-1])
    if "error" in data:
        raise RuntimeError(data["error"])
    report = {"purpose": "runtime diagnostic; not retrieval-quality evaluation", "sample_count": 4,
              "model_id": MODEL_ID, "model_revision": MODEL_REVISION, "recorded_at": datetime.now(timezone.utc).isoformat(),
              "available_ram_before_mib": before, "examples": payload["examples"], "result": data}
    directory = ROOT / "reports" / "generated"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "phase2d-runtime-diagnostic.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(path), "dimension": data["dimension"], "elapsed_seconds": data["elapsed_seconds"], "memory": data["memory"]}))


if __name__ == "__main__":
    main()
