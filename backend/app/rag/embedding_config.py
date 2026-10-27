"""Pinned, local-only E5 INT8 runtime configuration. Safe to import without ML packages."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MODEL_ID = "intfloat/multilingual-e5-small"
MODEL_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
MODEL_DIRECTORY = ROOT / "models" / "multilingual-e5-small-int8"
MODEL_FILENAME = "model_qint8_avx512_vnni.onnx"
MODEL_SHA256 = "dd476dd0c2514e9b9be83aeb3853fac0763e0bdf4a71645407587d77c48a2d88"
TOKENIZER_SHA256 = "0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39"
DIMENSION = 384
PASSAGE_TOKEN_LIMIT = 256
QUERY_TOKEN_LIMIT = 512
OVERLAP_TOKENS = 32
EMBEDDING_VERSION = "e5-small-int8-f32-mean-l2-v1"
CHUNKER_VERSION = "e5-offsets-256-overlap32-v1"
WORKER_MEMORY_MIB = 768
MIN_AVAILABLE_MEMORY_MIB = 1024
MAX_DENSE_CHARACTERS = 1_000_000
MAX_DENSE_SOURCES = 5000
MAX_DENSE_CHUNKS = 10_000
BUILD_TIMEOUT_SECONDS = 300
SEARCH_TIMEOUT_SECONDS = 30
