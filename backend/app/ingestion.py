"""Bounded text extraction and inspectable source segments. No model imports."""

from bisect import bisect_right
from dataclasses import dataclass, field
import hashlib
from pathlib import PurePath
import re
import unicodedata

MAX_UPLOAD_BYTES = 1024 * 1024
MAX_TEXT_CHARS = 200_000
MAX_SEGMENTS = 500
PROCESSOR_VERSION = "text-sections-v1"


class IngestionError(ValueError):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Segment:
    text: str
    section: str
    start_char: int
    end_char: int
    start_line: int
    end_line: int
    page_number: int | None = None
    source_label: str | None = None


@dataclass(frozen=True)
class ExtractedDocument:
    filename: str
    format: str
    text: str
    content_hash: str
    size_bytes: int
    segments: list[Segment]
    processor_version: str = PROCESSOR_VERSION
    hash_basis: str = "normalized_text"
    page_count: int | None = None
    warnings: list[str] = field(default_factory=list)


def validate_filename(filename: str) -> str:
    if not filename or len(filename) > 180 or filename != filename.strip():
        raise IngestionError("Use a filename between 1 and 180 characters without surrounding spaces.")
    if re.search(r'[/\\:<>"|?*\x00-\x1f]', filename) or any(unicodedata.category(c) in {"Cc", "Cf"} for c in filename):
        raise IngestionError("Use a filename without paths, control characters, or reserved symbols.")
    suffix = PurePath(filename).suffix.lower()
    formats = {".txt": "txt", ".md": "markdown", ".markdown": "markdown", ".pdf": "pdf", ".docx": "docx"}
    if suffix not in formats:
        raise IngestionError("Choose a PDF, DOCX, UTF-8 TXT, or Markdown file. Legacy DOC is not supported.", 415)
    return formats[suffix]


def section_ranges(text: str, markdown: bool) -> list[tuple[int, int, str]]:
    """Recognize ATX headings outside fenced code; preserve every source offset."""
    if not markdown:
        return [(0, len(text), "Document")]
    headings: list[tuple[int, str]] = []
    hierarchy: list[tuple[int, str]] = []
    offset = 0
    fence_char = ""
    fence_length = 0
    for line in text.splitlines(keepends=True):
        fence = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line.rstrip("\n"))
        if fence:
            marker, tail = fence.groups()
            if not fence_char:
                fence_char, fence_length = marker[0], len(marker)
            elif marker[0] == fence_char and len(marker) >= fence_length and not tail.strip():
                fence_char = ""
        elif not fence_char:
            heading = re.match(r"^ {0,3}(#{1,6})[ \t]+(.+?)\s*$", line)
            if heading:
                level = len(heading[1])
                title = re.sub(r"[ \t]+#+[ \t]*$", "", heading[2]).strip()
                if title:
                    hierarchy = [(depth, label) for depth, label in hierarchy if depth < level]
                    hierarchy.append((level, title))
                    headings.append((offset, " / ".join(label for _, label in hierarchy)))
        offset += len(line)
    starts = ([(0, "Preamble")] if not headings or headings[0][0] > 0 else []) + headings
    return [(start, starts[index + 1][0] if index + 1 < len(starts) else len(text), title)
            for index, (start, title) in enumerate(starts)]


def segment_text(text: str, markdown: bool, ranges: list[tuple[int, int, str, int | None, str | None]] | None = None) -> list[Segment]:
    """Character-based inspection segments, not yet embedding-token chunks."""
    segments: list[Segment] = []
    newlines = [index for index, character in enumerate(text) if character == "\n"]
    source_ranges = ranges if ranges is not None else [(start, stop, section, None, None) for start, stop, section in section_ranges(text, markdown)]
    for start, stop, section, page_number, source_label in source_ranges:
        while start < stop:
            end = min(start + 1200, stop)
            if end < stop:
                boundary = max(text.rfind("\n", start + 600, end), text.rfind(" ", start + 600, end))
                if boundary > start:
                    end = boundary + 1
            if text[start:end].strip():
                segments.append(Segment(text[start:end], section, start, end,
                                        bisect_right(newlines, start - 1) + 1,
                                        bisect_right(newlines, end - 2) + 1, page_number, source_label))
                if len(segments) > MAX_SEGMENTS:
                    raise IngestionError(f"Document exceeds the {MAX_SEGMENTS}-segment limit. Split it into smaller files.")
            if end == stop:
                break
            start = max(start + 1, end - 160)
    return segments


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
    if not text.strip():
        raise IngestionError("Document contains no readable text.")
    if any(unicodedata.category(c) == "Cc" and c not in "\n\t" for c in text):
        raise IngestionError("Document contains binary or unsupported control characters.")
    if len(text) > MAX_TEXT_CHARS:
        raise IngestionError(f"Extracted text exceeds {MAX_TEXT_CHARS:,} characters.", 413)
    return text


def extract_document(filename: str, payload: bytes) -> ExtractedDocument:
    format_name = validate_filename(filename)
    if len(payload) > MAX_UPLOAD_BYTES:
        raise IngestionError("File exceeds the 1 MiB upload limit.", 413)
    if format_name in {"pdf", "docx"}:
        from app.parsers.runner import parse_binary
        parsed = parse_binary(format_name, payload)
        text = ""
        ranges = []
        for block in parsed["blocks"]:
            value = normalize_text(block["text"]) + "\n\n"
            start = len(text)
            text += value
            if len(text) > MAX_TEXT_CHARS:
                raise IngestionError(f"Extracted text exceeds {MAX_TEXT_CHARS:,} characters.", 413)
            ranges.append((start, len(text), block["section"], block["page_number"], block["source_label"]))
        if not ranges:
            raise IngestionError("Document contains no extractable text.")
        return ExtractedDocument(
            filename, format_name, text, hashlib.sha256(payload).hexdigest(), len(payload),
            segment_text(text, False, ranges), processor_version=f"{format_name}-sources-v1",
            hash_basis="original_file_bytes", page_count=parsed["page_count"], warnings=parsed["warnings"],
        )
    try:
        text = normalize_text(payload.decode("utf-8-sig"))
    except UnicodeDecodeError as exc:
        raise IngestionError("File must be valid UTF-8 text. Save it as UTF-8 and retry.") from exc
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return ExtractedDocument(filename, format_name, text, digest, len(payload), segment_text(text, format_name == "markdown"))
