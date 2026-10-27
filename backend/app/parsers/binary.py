"""Extraction only: never execute scripts, retrieve URLs, extract ZIP files, or render documents."""

from io import BytesIO
import logging
from pathlib import PurePosixPath
import re
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from app.ingestion import IngestionError, MAX_TEXT_CHARS

MAX_PDF_PAGES = 50
MAX_PAGE_STREAM_BYTES = 1024 * 1024
MAX_PDF_STREAM_BYTES = 4 * 1024 * 1024
MAX_ZIP_ENTRIES = 256
MAX_ZIP_EXPANDED_BYTES = 8 * 1024 * 1024
MAX_XML_BYTES = 2 * 1024 * 1024
MAX_BLOCKS = 500
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def parse_pdf(payload: bytes) -> dict:
    from pypdf import overwrite_configuration
    from pypdf.errors import LimitReachedError

    # Public configuration API of the pinned parser. Bound decoding before its output exists.
    stream_limit = 2 * 1024 * 1024
    overwrite_configuration(
        maximum_declared_stream_length=stream_limit, array_based_stream_maximum_output_length=stream_limit,
        zlib_maximum_output_length=stream_limit, lzw_maximum_output_length=stream_limit,
        run_length_maximum_output_length=stream_limit, brotli_maximum_output_length=stream_limit,
        jbig2_maximum_output_length=stream_limit, image_maximum_buffer_size=stream_limit,
        stream_decoding_work_maximum_length=4 * stream_limit, stream_parsing_work_maximum_count=100_000,
        array_maximum_element_count=10_000, dictionary_maximum_element_count=10_000,
        page_tree_maximum_entries=1000, page_tree_maximum_depth=16,
        xform_maximum_invocations_per_extraction=100, jbig2dec_binary=None,
    )
    try:
        return _pdf_content(payload)
    except LimitReachedError as exc:
        raise IngestionError("PDF expanded content or structural complexity exceeds the extraction limit. Split or simplify it.", 413) from exc


def _pdf_content(payload: bytes) -> dict:
    from pypdf import PdfReader

    if not payload.startswith(b"%PDF-"):
        raise IngestionError("File does not have a PDF signature. Export a valid PDF and retry.")
    # Malformed-file log messages are not document data and must not fill the worker output.
    logging.getLogger("pypdf").setLevel(logging.CRITICAL)
    reader = PdfReader(BytesIO(payload), strict=True)
    if reader.is_encrypted:
        raise IngestionError("Password-protected PDFs are not supported. Upload an unencrypted copy.")
    page_count = len(reader.pages)
    if not page_count:
        raise IngestionError("PDF contains no pages.")
    if page_count > MAX_PDF_PAGES:
        raise IngestionError(f"PDF exceeds the {MAX_PDF_PAGES}-page limit. Split it into smaller files.", 413)
    blocks, empty_pages = [], []
    stream_bytes = text_chars = 0
    for number, page in enumerate(reader.pages, 1):
        contents = page.get_contents()
        size = len(contents.get_data()) if contents is not None else 0
        stream_bytes += size
        if size > MAX_PAGE_STREAM_BYTES or stream_bytes > MAX_PDF_STREAM_BYTES:
            raise IngestionError("PDF expanded content exceeds the extraction limit. Split or simplify it.", 413)
        text = page.extract_text() or ""
        text_chars += len(text)
        if text_chars > MAX_TEXT_CHARS:
            raise IngestionError("PDF extracted text exceeds the 200,000-character limit.", 413)
        if text.strip():
            blocks.append({"text": text, "section": f"Page {number}", "page_number": number, "source_label": f"Page {number}"})
        else:
            empty_pages.append(number)
    if not blocks:
        raise IngestionError("PDF has no extractable text. It may be scanned or blank. OCR is not included; upload a text-based PDF or TXT/DOCX copy.")
    warnings = ["PDF text order and tables can differ from the visual page. Review the extracted text before relying on it."]
    if empty_pages:
        reference = f"Page {empty_pages[0]} has" if len(empty_pages) == 1 else f"Pages {', '.join(map(str, empty_pages))} have"
        warnings.append(f"{reference} no extractable text and was skipped." if len(empty_pages) == 1 else f"{reference} no extractable text and were skipped.")
        warnings[-1] += " These pages may be blank or image-only; OCR is not included."
    return {"blocks": blocks, "page_count": page_count, "warnings": warnings}


def xml_root(data: bytes):
    from defusedxml.ElementTree import fromstring
    root = fromstring(data, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    stack = [(root, 1)]
    nodes = 0
    while stack:
        node, depth = stack.pop()
        nodes += 1
        if nodes > 30_000 or depth > 64:
            raise IngestionError("DOCX XML is too complex. Split or simplify the document.", 413)
        stack.extend((child, depth + 1) for child in node)
    return root


def paragraph_text(paragraph) -> str:
    parts = []
    stack = [paragraph]
    while stack:
        node = stack.pop()
        if node.tag in {W + "drawing", W + "pict", W + "object", W + "txbxContent"}:
            continue
        if node.tag == W + "t":
            parts.append(node.text or "")
        elif node.tag == W + "tab":
            parts.append("\t")
        elif node.tag in {W + "br", W + "cr"}:
            parts.append("\n")
        elif node.tag == W + "noBreakHyphen":
            parts.append("-")
        else:
            stack.extend(reversed(list(node)))
    return "".join(parts)


def heading_level(paragraph, styles) -> int | None:
    properties = paragraph.find(W + "pPr")
    if properties is None:
        return None
    outline = properties.find(W + "outlineLvl")
    if outline is not None:
        value = outline.get(W + "val", "9")
        return int(value) + 1 if value.isdigit() and int(value) < 9 else None
    style = properties.find(W + "pStyle")
    style_id = style.get(W + "val") if style is not None else None
    visited = set()
    while style_id and style_id not in visited and len(visited) < 20:
        visited.add(style_id)
        candidate = styles.get(style_id)
        if candidate is None:
            match = re.fullmatch(r"Heading([1-9])", style_id)
            return int(match[1]) if match else None
        outline = candidate.find(f"{W}pPr/{W}outlineLvl")
        if outline is not None:
            value = outline.get(W + "val", "9")
            return int(value) + 1 if value.isdigit() and int(value) < 9 else None
        name = candidate.find(W + "name")
        match = re.fullmatch(r"heading ?([1-9])", name.get(W + "val", ""), re.IGNORECASE) if name is not None else None
        if match:
            return int(match[1])
        parent = candidate.find(W + "basedOn")
        style_id = parent.get(W + "val") if parent is not None else None
    return None


def parse_docx(payload: bytes) -> dict:
    if not payload.startswith(b"PK\x03\x04"):
        raise IngestionError("File is not a DOCX ZIP package. Legacy DOC and encrypted Word files are not supported.")
    with ZipFile(BytesIO(payload)) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_ZIP_ENTRIES or sum(item.file_size for item in entries) > MAX_ZIP_EXPANDED_BYTES:
            raise IngestionError("DOCX archive exceeds the expanded-size or entry-count limit.", 413)
        names = set()
        for item in entries:
            path = PurePosixPath(item.filename)
            if item.filename in names or path.is_absolute() or ".." in path.parts or "\\" in item.filename or ":" in item.filename:
                raise IngestionError("DOCX archive contains duplicate or unsafe entry names.")
            names.add(item.filename)
            if item.flag_bits & 1 or item.compress_type not in {ZIP_DEFLATED, ZIP_STORED}:
                raise IngestionError("DOCX archive encryption or compression method is not supported.")
            if item.file_size > MAX_XML_BYTES and item.filename.endswith(".xml"):
                raise IngestionError("DOCX XML exceeds the 2 MiB entry limit.", 413)
        if "word/document.xml" not in names or "[Content_Types].xml" not in names:
            raise IngestionError("DOCX package is missing its main document or content types.")
        content_types = xml_root(archive.read("[Content_Types].xml"))
        main_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
        if not any(node.get("PartName") == "/word/document.xml" and node.get("ContentType") == main_type for node in content_types):
            raise IngestionError("Only standard DOCX documents are supported; macro-enabled and other Office formats are not accepted.")
        root = xml_root(archive.read("word/document.xml"))
        styles_root = xml_root(archive.read("word/styles.xml")) if "word/styles.xml" in names else None
    body = root.find(W + "body")
    if root.tag != W + "document" or body is None:
        raise IngestionError("DOCX main document is invalid or uses an unsupported XML format.")
    if any(node.tag in {W + "ins", W + "del", W + "moveFrom", W + "moveTo", W + "altChunk"} for node in root.iter()):
        raise IngestionError("Resolve tracked changes and imported content before uploading this DOCX.")
    styles = {node.get(W + "styleId"): node for node in styles_root or []}
    blocks, hierarchy = [], []
    paragraph_index = table_index = total_chars = 0

    def add(text: str, label: str):
        nonlocal total_chars
        if not text.strip():
            return
        total_chars += len(text) + 2
        if total_chars > MAX_TEXT_CHARS or len(blocks) >= MAX_BLOCKS:
            raise IngestionError("DOCX exceeds the 200,000-character or 500-source-block limit. Split the file.", 413)
        blocks.append({"text": text, "section": " / ".join(title for _, title in hierarchy) or "Document body", "page_number": None, "source_label": label})

    for element in body:
        if element.tag == W + "p":
            paragraph_index += 1
            text = paragraph_text(element)
            level = heading_level(element, styles)
            if level and text.strip():
                hierarchy = [(depth, title) for depth, title in hierarchy if depth < level] + [(level, text.strip())]
            add(text, f"Paragraph {paragraph_index}")
        elif element.tag == W + "tbl":
            table_index += 1
            if any(node.tag == W + "tbl" for child in element for node in child.iter()):
                raise IngestionError("Nested DOCX tables are not supported. Flatten the table or export it as TXT.")
            for row_index, row in enumerate(element.findall(W + "tr"), 1):
                cells = ["\n".join(paragraph_text(p) for p in cell.findall(W + "p")) for cell in row.findall(W + "tc")]
                add("\t".join(cells), f"Table {table_index}, row {row_index}")
        elif element.tag != W + "sectPr":
            raise IngestionError("DOCX contains unsupported body blocks. Export plain paragraphs/tables or a TXT copy.")
    if not blocks:
        raise IngestionError("DOCX contains no extractable body text. Images are not OCR processed; upload a text-based copy.")
    return {"blocks": blocks, "page_count": None, "warnings": [
        "DOCX references use headings, body paragraphs, and table rows; Word page numbers are not assigned.",
        "Only body paragraphs and basic tables are extracted. Images, text boxes, headers, footers, comments, and footnotes are not included.",
    ]}
