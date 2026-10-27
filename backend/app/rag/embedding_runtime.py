"""Local ONNX E5 implementation. Imported only inside the bounded ML worker."""

import hashlib
from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

from app.ingestion import IngestionError
from app.rag.embedding_config import (CHUNKER_VERSION, DIMENSION, MODEL_DIRECTORY, MODEL_FILENAME,
    MODEL_REVISION, MODEL_SHA256, TOKENIZER_SHA256, PASSAGE_TOKEN_LIMIT, QUERY_TOKEN_LIMIT, OVERLAP_TOKENS)


def sha256_file(path: Path):
    checksum = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


class E5Encoder:
    def __init__(self, directory: Path = MODEL_DIRECTORY):
        ort.disable_telemetry_events()
        for filename, expected in [(MODEL_FILENAME, MODEL_SHA256), ("tokenizer.json", TOKENIZER_SHA256)]:
            path = directory / filename
            if not path.exists() or sha256_file(path) != expected:
                raise IngestionError("Pinned embedding artifacts are missing or corrupt. Run scripts/prepare_embedding_model.py.", 503)
        self.tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
        self.tokenizer.no_truncation()
        self.tokenizer.no_padding()
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        options.enable_cpu_mem_arena = False
        options.enable_mem_pattern = False
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
        self.session = ort.InferenceSession(str(directory / MODEL_FILENAME), sess_options=options, providers=["CPUExecutionProvider"])

    def token_count(self, text: str, query=False) -> int:
        return len(self.tokenizer.encode(("query: " if query else "passage: ") + text).ids)

    def encode(self, text: str, query=False):
        encoding = self.tokenizer.encode(("query: " if query else "passage: ") + text)
        limit = QUERY_TOKEN_LIMIT if query else PASSAGE_TOKEN_LIMIT
        if len(encoding.ids) > limit:
            raise IngestionError(f"Encoder input exceeds {limit} tokens including its prefix and special tokens. Shorten the query or rebuild the chunks.")
        values = {"input_ids": np.asarray([encoding.ids], dtype=np.int64),
                  "attention_mask": np.asarray([encoding.attention_mask], dtype=np.int64),
                  "token_type_ids": np.asarray([encoding.type_ids], dtype=np.int64)}
        inputs = {item.name: values[item.name] for item in self.session.get_inputs()}
        output = self.session.run(None, inputs)[0]
        if output.ndim != 3 or output.shape[-1] != DIMENSION:
            raise IngestionError("Unexpected embedding model output shape.", 503)
        mask = values["attention_mask"][..., None].astype(np.float32)
        vector = (output.astype(np.float32) * mask).sum(axis=1) / mask.sum(axis=1)
        norm = np.linalg.norm(vector, axis=1, keepdims=True)
        if not np.isfinite(vector).all() or not np.isfinite(norm).all() or (norm <= 0).any():
            raise IngestionError("Embedding model returned an invalid vector.", 503)
        return np.ascontiguousarray(vector / norm, dtype=np.float32)

    def chunks(self, source_id: str, text: str) -> list[dict]:
        offsets = [(start, end) for start, end in self.tokenizer.encode(text, add_special_tokens=False).offsets if end > start]
        if not offsets:
            return []
        budget = PASSAGE_TOKEN_LIMIT - self.token_count("") - 2
        chunks = []
        first = 0
        while first < len(offsets):
            start = 0 if first == 0 else offsets[first][0]
            last = min(first + budget, len(offsets))
            while last > first:
                end = len(text) if last == len(offsets) else max(stop for _, stop in offsets[first:last])
                count = self.token_count(text[start:end])
                if count <= PASSAGE_TOKEN_LIMIT:
                    break
                last -= 1
            if last <= first or end <= start:
                raise IngestionError("A source span cannot fit the encoder token budget. Simplify the source.")
            identity = f"{source_id}:{MODEL_REVISION}:{CHUNKER_VERSION}:{start}:{end}"
            chunks.append({"id": hashlib.sha256(identity.encode()).hexdigest(), "parent_id": source_id,
                           "start": start, "end": end, "token_count": count})
            if last == len(offsets):
                break
            following = max(first + 1, last - OVERLAP_TOKENS)
            while following < len(offsets) and offsets[following][0] <= start:
                following += 1
            first = following
        return chunks
