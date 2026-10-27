"""CPU embedding child process: bounded memory, local artifacts, structured progress."""

import json
import os
import sys
import time

from app.rag.embedding_config import WORKER_MEMORY_MIB


def watch_parent():
    """Exit if the API process dies, including forced Windows termination."""
    import threading
    parent = os.getppid()
    def monitor():
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL("kernel32")
            kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            handle = kernel.OpenProcess(0x00100000, False, parent)
            if handle:
                kernel.WaitForSingleObject(handle, 0xFFFFFFFF)
                os._exit(1)
        else:
            while os.getppid() == parent:
                time.sleep(1)
            os._exit(1)
    threading.Thread(target=monitor, daemon=True, name="embedding-parent-watch").start()


def emit(value):
    print(json.dumps(value, ensure_ascii=True), flush=True)


def main():
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    os.environ["OMP_NUM_THREADS"] = "2"
    os.environ["OMP_WAIT_POLICY"] = "PASSIVE"
    from app.parsers import worker as protection
    protection.MEMORY_LIMIT_BYTES = WORKER_MEMORY_MIB * 2**20
    try:
        protection.apply_memory_limit()
    except (OSError, ValueError, ImportError):
        emit({"error": "Embedding worker memory protection could not initialize.", "status": 503})
        return
    from app.ingestion import IngestionError
    watch_parent()
    try:
        started = time.perf_counter()
        from app.rag.embedding_runtime import E5Encoder
        from app.rag.resources import process_memory
        payload = json.loads(sys.stdin.buffer.read(12 * 1024 * 1024 + 1))
        encoder = E5Encoder()
        if sys.argv[1] == "trial":
            vectors = [encoder.encode(text, query=query) for query, text in payload["examples"]]
            emit({"type": "result", "dimension": vectors[0].shape[1],
                  "norms": [float((v * v).sum() ** .5) for v in vectors],
                  "similarities": [[float((left @ right.T)[0, 0]) for right in vectors] for left in vectors],
                  "elapsed_seconds": time.perf_counter() - started, "memory": process_memory()})
        else:
            from app.rag.dense_artifacts import run_job
            emit({"type": "result", **run_job(sys.argv[1], payload, encoder, emit),
                  "elapsed_seconds": time.perf_counter() - started, "memory": process_memory()})
    except IngestionError as error:
        emit({"error": str(error), "status": error.status})
    except ImportError:
        emit({"error": "CPU dense runtime is missing. Install backend/requirements-ml.txt.", "status": 503})
    except MemoryError:
        emit({"error": f"Embedding worker reached its {WORKER_MEMORY_MIB} MiB memory cap.", "status": 503})
    except Exception as error:
        # No source contents, internal tracebacks, or uploaded filenames in errors.
        emit({"error": f"Local embedding worker failed ({type(error).__name__}). Check the runtime/model installation.", "status": 503})


if __name__ == "__main__":
    main()
