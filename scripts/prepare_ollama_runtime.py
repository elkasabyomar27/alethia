"""Explicit, pinned portable Windows Ollama setup; never invoked by the API."""

import hashlib
import json
from pathlib import Path
import shutil
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "v0.40.11"
SIZE = 1_586_356_606
SHA256 = "bda4a493ba8a7c24d57263cd843cd68cee84f44aed4299eeed532acad7eda12a"
URL = f"https://github.com/ollama/ollama/releases/download/{VERSION}/ollama-windows-amd64.zip"


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def main():
    directory = ROOT / "models" / "ollama-runtime" / VERSION
    runtime = directory / "runtime"
    if (runtime / "ollama.exe").is_file():
        print(f"Existing portable runtime: {runtime}", flush=True)
        return
    if shutil.disk_usage(ROOT).free < 8 * 1024**3:
        raise RuntimeError("At least 8 GiB free disk space is required for portable setup and a small model.")
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / "ollama-windows-amd64.zip"
    if not archive.exists():
        partial = archive.with_suffix(".zip.part")
        count = 0
        checkpoint = 0
        checksum = hashlib.sha256()
        with urllib.request.urlopen(URL, timeout=60) as source, partial.open("wb") as target:
            while block := source.read(1024 * 1024):
                count += len(block)
                if count > SIZE:
                    raise RuntimeError("Runtime download exceeds its pinned size.")
                target.write(block)
                checksum.update(block)
                if count - checkpoint >= 64 * 1024**2:
                    print(f"Runtime download {count / SIZE:.0%}", flush=True)
                    checkpoint = count
        if count != SIZE or checksum.hexdigest() != SHA256:
            raise RuntimeError("Runtime download failed pinned size/SHA256 validation.")
        partial.replace(archive)
    elif archive.stat().st_size != SIZE or digest(archive) != SHA256:
        raise RuntimeError("Existing archive failed pinned verification; inspect it before retrying.")
    staging = directory / "extracting"
    if staging.exists():
        raise RuntimeError("A previous extraction directory exists; inspect it before retrying.")
    staging.mkdir()
    with zipfile.ZipFile(archive) as source:
        if sum(item.file_size for item in source.infolist()) > 8 * 1024**3:
            raise RuntimeError("Archive exceeds extraction budget.")
        for item in source.infolist():
            target = (staging / item.filename).resolve()
            if not target.is_relative_to(staging.resolve()) or (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise RuntimeError("Unsafe runtime archive member.")
        source.extractall(staging)
    if not (staging / "ollama.exe").is_file():
        raise RuntimeError("Official archive did not contain the expected executable.")
    staging.rename(runtime)
    (directory / "provenance.json").write_text(json.dumps({"version": VERSION, "url": URL,
        "sha256": SHA256, "size": SIZE}, indent=2), encoding="utf8")
    print(f"Verified portable runtime: {runtime}", flush=True)


if __name__ == "__main__":
    main()
