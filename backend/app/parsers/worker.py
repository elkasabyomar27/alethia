"""Short-lived child process. Set resource limits before loading binary parsers."""

import json
import sys

MEMORY_LIMIT_BYTES = 256 * 1024 * 1024
_job_handle = None


def apply_memory_limit():
    global _job_handle
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class BasicLimits(ctypes.Structure):
            _fields_ = [("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
                        ("flags", wintypes.DWORD), ("min_working_set", ctypes.c_size_t),
                        ("max_working_set", ctypes.c_size_t), ("active_processes", wintypes.DWORD),
                        ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD)]

        class IOCounts(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in ("reads", "writes", "other", "read_bytes", "write_bytes", "other_bytes")]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [("basic", BasicLimits), ("io", IOCounts), ("process_memory", ctypes.c_size_t),
                        ("job_memory", ctypes.c_size_t), ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel.SetInformationJobObject.restype = wintypes.BOOL
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        _job_handle = kernel.CreateJobObjectW(None, None)
        limits = ExtendedLimits()
        limits.basic.flags = 0x100 | 0x8 | 0x2000  # Process memory, one process, kill on close.
        limits.basic.active_processes = 1
        limits.process_memory = MEMORY_LIMIT_BYTES
        if not _job_handle or not kernel.SetInformationJobObject(_job_handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            raise OSError("Cannot configure parser memory limits")
        if not kernel.AssignProcessToJobObject(_job_handle, kernel.GetCurrentProcess()):
            raise OSError("Cannot apply parser memory limits")
    else:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT_BYTES, MEMORY_LIMIT_BYTES))


def main():
    try:
        apply_memory_limit()
    except (OSError, ImportError, ValueError):
        print(json.dumps({"error": "Parser resource protection could not be initialized. Check the local runtime.", "status": 503}))
        return
    from app.ingestion import IngestionError, MAX_UPLOAD_BYTES
    try:
        from app.parsers.binary import parse_docx, parse_pdf
        payload = sys.stdin.buffer.read(MAX_UPLOAD_BYTES + 1)
        if len(payload) > MAX_UPLOAD_BYTES:
            raise IngestionError("File exceeds the 1 MiB upload limit.", 413)
        parser = {"pdf": parse_pdf, "docx": parse_docx}[sys.argv[1]]
        result = parser(payload)
    except IngestionError as error:
        result = {"error": str(error), "status": error.status}
    except ImportError:
        result = {"error": "Document parser dependencies are missing. Install backend/requirements-lock.txt.", "status": 503}
    except MemoryError:
        result = {"error": "Document extraction reached the 256 MiB worker memory limit. Split or simplify the file.", "status": 422}
    except Exception:
        result = {"error": "The file is malformed, unsupported, or too complex to extract. Export a simpler PDF/DOCX and retry.", "status": 422}
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))


if __name__ == "__main__":
    main()
