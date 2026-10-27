"""Download only the pinned E5 INT8 artifacts from the official model repository.

Run with .venv/Scripts/python.exe scripts/prepare_embedding_model.py.
Inference and API startup never call this downloader or contact model hubs.
"""

import hashlib
import json
from pathlib import Path
import sys
import tempfile
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.rag.embedding_config import (MODEL_DIRECTORY, MODEL_FILENAME, MODEL_ID, MODEL_REVISION,
                                     MODEL_SHA256, TOKENIZER_SHA256)

FILES = [
    (f"onnx/{MODEL_FILENAME}", MODEL_FILENAME, 118346824, MODEL_SHA256, "sha256"),
    ("tokenizer.json", "tokenizer.json", 17082730, TOKENIZER_SHA256, "sha256"),
    ("config.json", "config.json", 655, "60a2a84020f1d74cc53ea9e8c4e91cf4af6c2b68", "git"),
    ("README.md", "MODEL_CARD.md", 497538, "e56327af55e9742caf76bff9ba83b6904cd2003d", "git"),
]


def digest(path: Path, algorithm: str, size: int):
    checksum = hashlib.sha256() if algorithm == "sha256" else hashlib.sha1()
    if algorithm == "git":
        checksum.update(f"blob {size}\0".encode())
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def main():
    MODEL_DIRECTORY.mkdir(parents=True, exist_ok=True)
    for remote, local, size, expected, algorithm in FILES:
        destination = MODEL_DIRECTORY / local
        if destination.exists():
            if destination.stat().st_size == size and digest(destination, algorithm, size) == expected:
                print(f"Verified existing {local}", flush=True)
                continue
            raise RuntimeError(f"Existing artifact failed verification: {destination}. Preserve or remove it before retrying.")
        temporary = None
        try:
            url = f"https://huggingface.co/{MODEL_ID}/resolve/{MODEL_REVISION}/{remote}"
            with tempfile.NamedTemporaryFile(dir=MODEL_DIRECTORY, prefix="download-", suffix=".part", delete=False) as target:
                temporary = Path(target.name)
                count = 0
                print(f"Downloading {local} ({size / 2**20:.1f} MiB)", flush=True)
                with urlopen(url, timeout=60) as response:
                    while block := response.read(1024 * 1024):
                        count += len(block)
                        if count > size:
                            raise RuntimeError("Remote artifact exceeds its pinned size")
                        target.write(block)
            if count != size or digest(temporary, algorithm, size) != expected:
                raise RuntimeError(f"Artifact integrity check failed for {local}")
            temporary.replace(destination)
            temporary = None
        finally:
            if temporary and temporary.exists():
                temporary.unlink()
    manifest = {"model_id": MODEL_ID, "revision": MODEL_REVISION, "declared_license": "MIT",
                "model_sha256": MODEL_SHA256, "tokenizer_sha256": TOKENIZER_SHA256,
                "source": f"https://huggingface.co/{MODEL_ID}/tree/{MODEL_REVISION}",
                "files": [local for _, local, *_ in FILES]}
    (MODEL_DIRECTORY / "model_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Verified local model ready: {MODEL_DIRECTORY}", flush=True)


if __name__ == "__main__":
    main()
