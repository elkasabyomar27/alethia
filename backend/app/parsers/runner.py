"""One isolated parser at a time; uploaded filenames never become commands or paths."""

import json
from pathlib import Path
import subprocess
import sys
import threading

from app.ingestion import IngestionError

PARSER_TIMEOUT_SECONDS = 10
_slot = threading.BoundedSemaphore(1)


def parse_binary(format_name: str, payload: bytes) -> dict:
    if not _slot.acquire(blocking=False):
        raise IngestionError("Another document is being extracted. Please retry shortly.", 503)
    try:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "app.parsers.worker", format_name], input=payload,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                cwd=Path(__file__).resolve().parents[2], timeout=PARSER_TIMEOUT_SECONDS,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise IngestionError("Document extraction exceeded the 10-second limit. Split or simplify the file.", 422) from exc
        except OSError as exc:
            raise IngestionError("The document extraction worker could not start. Please check the local installation.", 503) from exc
        if result.returncode != 0 or len(result.stdout) > 2 * 1024 * 1024:
            raise IngestionError("Document extraction stopped at a resource limit or parser error. Split or simplify the file.")
        try:
            parsed = json.loads(result.stdout)
        except (ValueError, UnicodeDecodeError) as exc:
            raise IngestionError("Document extraction failed safely. Please export a simpler file and retry.") from exc
        if "error" in parsed:
            raise IngestionError(parsed["error"], parsed.get("status", 422))
        return parsed
    finally:
        _slot.release()
