"""Stage 1: parse manuscripts into addressable text and table blocks."""

from __future__ import annotations

import pathlib
import re
import tempfile
import uuid
from typing import TYPE_CHECKING

from app.config import MAX_FILE_SIZE_MB
from app.models import BlockType, DocumentBlock, Reference  # noqa: F401

# ---------------------------------------------------------------------------
# Format detection helpers
# ---------------------------------------------------------------------------

_DOCLING_EXTS = {".pdf", ".docx"}
_LATEX_EXTS = {".tex"}
_PLAIN_EXTS = {".txt", ".md"}

_DOCLING_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
_LATEX_CONTENT_TYPES = {"text/x-tex"}
_PLAIN_CONTENT_TYPES = {"text/plain", "text/markdown"}


def _detect_format(filename: str, content_type: str) -> str:
    """Return one of 'docling', 'latex', 'plain', or raise ValueError."""
    ext = pathlib.Path(filename).suffix.lower()
    ct = (content_type or "").split(";")[0].strip().lower()

    if ext in _DOCLING_EXTS or ct in _DOCLING_CONTENT_TYPES:
        return "docling"
    if ext in _LATEX_EXTS or ct in _LATEX_CONTENT_TYPES:
        return "latex"
    if ext in _PLAIN_EXTS or ct in _PLAIN_CONTENT_TYPES:
        return "plain"

    raise ValueError(
        f"Unsupported format: extension='{ext}', content_type='{content_type}'. "
        "Supported: .pdf, .docx, .tex, .txt, .md"
    )


# ---------------------------------------------------------------------------
# Docling parsing
# ---------------------------------------------------------------------------

def _docling_blocks(
    content: bytes, filename: str, document_id: str
) -> list[DocumentBlock]:
    """Parse PDF/DOCX via Docling and return DocumentBlock list."""
    try:
        from docling.document_converter import DocumentConverter
    except ImportError as exc:
        raise ValueError(f"Parsing failed: docling not installed — {exc}") from exc

    suffix = pathlib.Path(filename).suffix or ".pdf"
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(content)
            tmp_path = pathlib.Path(tmp.name)

        converter = DocumentConverter()
        result = converter.convert(tmp_path)
        doc = result.document
    except Exception as exc:
        raise ValueError(f"Parsing failed: {exc}") from exc
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass

    blocks: list[DocumentBlock] = []
    index = 0
    char_offset = 0
    current_section: str | None = None
    in_bib = False

    # Docling exposes items via doc.iterate_items() which yields (item, level)
    # We walk all items and map their type.
    try:
        items = list(doc.iterate_items())
    except AttributeError:
        # Fallback: try .body or .elements
        try:
            items = [(el, 0) for el in doc.body]
        except AttributeError:
            items = []

    for item, _level in items:
        # Determine text
        try:
            text = item.text if hasattr(item, "text") else str(item)
        except Exception:
            text = ""

        text = text or ""

        # Map type
        item_type_str = type(item).__name__.lower()
        label_str = ""
        try:
            label_str = str(item.label).lower() if hasattr(item, "label") else ""
        except Exception:
            pass

        # Identify headings / captions / tables
        is_heading = any(
            tok in item_type_str or tok in label_str
            for tok in ("sectionheader", "heading", "section_header", "title")
        )
        is_table = "table" in item_type_str or "table" in label_str
        is_caption = "caption" in item_type_str or "caption" in label_str

        if is_heading:
            current_section = text.strip() or current_section
            # Check if we just entered bibliography
            normalized = (current_section or "").lower()
            if "reference" in normalized or "bibliography" in normalized:
                in_bib = True
            else:
                in_bib = False

        # Page number
        page: int | None = None
        try:
            prov = item.prov[0] if (hasattr(item, "prov") and item.prov) else None
            if prov is not None:
                page = getattr(prov, "page_no", None)
        except Exception:
            pass

        # Block type
        if in_bib and not is_heading:
            btype = BlockType.bibliography
        elif is_heading:
            btype = BlockType.heading
        elif is_table:
            btype = BlockType.table
        elif is_caption:
            btype = BlockType.caption
        else:
            btype = BlockType.text

        # Skip empty blocks
        stripped = text.strip()
        if not stripped:
            continue

        char_start = char_offset
        char_end = char_offset + len(stripped)
        char_offset = char_end + 1  # +1 for separator

        blocks.append(
            DocumentBlock(
                block_id=f"{document_id}_b{index:04d}",
                document_id=document_id,
                block_type=btype,
                text=stripped,
                section=current_section,
                page=page,
                char_start=char_start,
                char_end=char_end,
            )
        )
        index += 1

    if not blocks:
        raise ValueError("Parsing yielded no usable content")

    return blocks


# ---------------------------------------------------------------------------
# LaTeX processing
# ---------------------------------------------------------------------------

_RE_CITE = re.compile(r"\\cite[pt]?\{([^}]+)\}")
_RE_BIBLIOGRAPHY_CMD = re.compile(r"\\bibliography\{([^}]+)\}")
_RE_BEGIN_THEBIB = re.compile(r"\\begin\{thebibliography\}")
_RE_SECTION = re.compile(r"\\(?:section|subsection|subsubsection|chapter)\*?\{([^}]*)\}")
_RE_BEGIN_END = re.compile(r"\\(?:begin|end)\{[^}]*\}")
_RE_LABEL = re.compile(r"\\label\{[^}]*\}")
_RE_REF = re.compile(r"\\ref\{[^}]*\}")


def _latex_blocks(content: bytes, document_id: str) -> tuple[list[DocumentBlock], str | None]:
    """Parse LaTeX source into DocumentBlock list."""
    source = content.decode("utf-8", errors="replace")
    bib_warning: str | None = None

    # Check for \bibliography{...}
    if _RE_BIBLIOGRAPHY_CMD.search(source):
        bib_warning = (
            r"LaTeX \bibliography{...} command found; external .bib file was not supplied. "
            "Citation keys are preserved."
        )

    # Strip LaTeX commands while preserving section names and cite keys
    # We'll walk line by line, tracking sections and building a plain-text version
    # but we do it on a sanitised copy that keeps \cite markers.

    def _strip_latex(text: str) -> str:
        r"""Remove most LaTeX markup except \cite variants."""
        # Remove \begin{...} \end{...}
        text = _RE_BEGIN_END.sub("", text)
        # Remove \label{...}
        text = _RE_LABEL.sub("", text)
        # Replace \ref{key} with [ref]
        text = _RE_REF.sub("[ref]", text)
        # Replace \section{name} → name
        text = _RE_SECTION.sub(lambda m: m.group(1), text)
        # Remove remaining backslash commands that are not \cite
        text = re.sub(r"\\(?!cite[pt]?\{)[a-zA-Z]+\*?\{[^}]*\}", "", text)
        text = re.sub(r"\\(?!cite[pt]?)[a-zA-Z]+\*?(?=\s|$|\{)", "", text)
        # Remove lone braces
        text = re.sub(r"[{}]", "", text)
        return text

    blocks: list[DocumentBlock] = []
    index = 0
    char_offset = 0
    current_section: str | None = None
    in_bib = False

    # Split into logical chunks at double newlines
    # First, detect bibliography environment boundaries
    # We'll split the source at \begin{thebibliography}
    bib_start_match = _RE_BEGIN_THEBIB.search(source)
    pre_bib = source[: bib_start_match.start()] if bib_start_match else source
    post_bib = source[bib_start_match.start():] if bib_start_match else ""

    def _process_chunk(raw: str, force_bib: bool) -> None:
        nonlocal index, char_offset, current_section, in_bib

        # Extract section headings and split accordingly
        # We'll process line by line
        paragraphs_raw = re.split(r"\n{2,}", raw)

        for para in paragraphs_raw:
            para_stripped = para.strip()
            if not para_stripped:
                continue

            # Check for section command inside paragraph
            sec_match = _RE_SECTION.search(para_stripped)
            if sec_match:
                sec_name = sec_match.group(1).strip()
                current_section = sec_name
                normalized_sec = sec_name.lower()
                if "reference" in normalized_sec or "bibliography" in normalized_sec:
                    in_bib = True
                else:
                    in_bib = False

            # Strip LaTeX commands from paragraph text
            clean = _strip_latex(para_stripped)
            clean = clean.strip()

            if not clean:
                continue

            # Determine block type
            if force_bib or in_bib:
                effective_in_bib = True
            else:
                effective_in_bib = False

            # Detect if this is a heading-only paragraph
            is_heading_para = bool(sec_match) and len(clean) < 120

            if is_heading_para:
                btype = BlockType.heading
            elif effective_in_bib:
                btype = BlockType.bibliography
            else:
                btype = BlockType.text

            char_start = char_offset
            char_end = char_offset + len(clean)
            char_offset = char_end + 1

            blocks.append(
                DocumentBlock(
                    block_id=f"{document_id}_b{index:04d}",
                    document_id=document_id,
                    block_type=btype,
                    text=clean,
                    section=current_section,
                    page=None,
                    char_start=char_start,
                    char_end=char_end,
                )
            )
            index += 1

    _process_chunk(pre_bib, force_bib=False)
    if post_bib:
        in_bib = True
        _process_chunk(post_bib, force_bib=True)

    if not blocks:
        raise ValueError("Parsing yielded no usable content")

    return blocks, bib_warning


# ---------------------------------------------------------------------------
# Plain text / Markdown processing
# ---------------------------------------------------------------------------

_KNOWN_SECTION_NAMES = {
    "abstract", "introduction", "background", "related work",
    "methodology", "methods", "results", "discussion", "conclusion",
    "conclusions", "references", "bibliography", "acknowledgements",
    "acknowledgments", "appendix", "supplementary",
}

_RE_MD_HEADING = re.compile(r"^#{1,6}\s+(.+)$")
_RE_ALL_CAPS = re.compile(r"^[A-Z][A-Z0-9 \t\-:,/()&]{3,}$")


def _is_heading(para: str) -> bool:
    """Heuristic: is this paragraph a section heading?"""
    lines = para.strip().splitlines()
    if not lines:
        return False
    first_line = lines[0].strip()

    # Markdown heading
    if _RE_MD_HEADING.match(first_line):
        return True

    # Only one line and it's short
    if len(lines) == 1:
        # ALL CAPS
        if _RE_ALL_CAPS.match(first_line):
            return True
        # Ends with colon and short
        if first_line.endswith(":") and len(first_line) < 60:
            return True
        # Known section name (case-insensitive)
        if first_line.rstrip(":").strip().lower() in _KNOWN_SECTION_NAMES:
            return True

    return False


def _heading_text(para: str) -> str:
    """Extract the heading label from a heading paragraph."""
    first_line = para.strip().splitlines()[0].strip()
    md_m = _RE_MD_HEADING.match(first_line)
    if md_m:
        return md_m.group(1).strip()
    return first_line.rstrip(":").strip()


def _plain_blocks(content: bytes, document_id: str) -> tuple[list[DocumentBlock], str | None]:
    """Parse plain text / Markdown into DocumentBlock list."""
    try:
        text = content.decode("utf-8", errors="replace")
    except Exception as exc:
        raise ValueError(f"Could not decode text content: {exc}") from exc

    # Normalize: ensure standalone heading lines (e.g. "References\n[1]")
    # have paragraph breaks so heading detection works reliably.
    text = re.sub(
        r"(?im)^((?:#{1,6}\s+.*|(?:references|bibliography|findings|results|discussion|conclusion|conclusions|introduction|methods|abstract)\s*:?))\n(?!\n)",
        r"\1\n\n",
        text,
    )

    paragraphs = re.split(r"\n{2,}", text)

    blocks: list[DocumentBlock] = []
    index = 0
    char_offset = 0
    current_section: str | None = None
    in_bib = False

    for para in paragraphs:
        stripped = para.strip()
        if not stripped:
            char_offset += len(para) + 2  # account for double newline
            continue

        # Locate paragraph in original text for accurate char offsets
        para_start = text.find(para, char_offset if char_offset <= len(text) else 0)
        if para_start == -1:
            para_start = char_offset
        para_end = para_start + len(stripped)

        is_hd = _is_heading(stripped)

        if is_hd:
            heading_label = _heading_text(stripped)
            current_section = heading_label
            normalized_hd = heading_label.lower()
            if "reference" in normalized_hd or "bibliography" in normalized_hd:
                in_bib = True
            else:
                in_bib = False
            btype = BlockType.heading
        elif in_bib:
            btype = BlockType.bibliography
        else:
            btype = BlockType.text

        blocks.append(
            DocumentBlock(
                block_id=f"{document_id}_b{index:04d}",
                document_id=document_id,
                block_type=btype,
                text=stripped,
                section=current_section,
                page=None,
                char_start=para_start,
                char_end=para_end,
            )
        )
        index += 1
        char_offset = para_end + 2  # skip the double newline separator

    if not blocks:
        raise ValueError("Parsing yielded no usable content")

    return blocks, None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def ingest_document(
    content: bytes,
    filename: str,
    content_type: str,
) -> tuple[str, list[DocumentBlock], str | None]:
    """Parse a manuscript into addressable text and table blocks.

    Parameters
    ----------
    content:
        Raw file bytes.
    filename:
        Original filename (used for extension-based format detection).
    content_type:
        MIME type (used as fallback for format detection).

    Returns
    -------
    (document_id, blocks, bib_warning)
        document_id — UUID4 string that ties all blocks to this ingestion run.
        blocks      — Ordered list of DocumentBlock covering the document.
        bib_warning — None, or a human-readable warning string when the
                      bibliography could not be fully resolved from the
                      supplied bytes alone (e.g. LaTeX .bib file missing).


    Raises
    ------
    ValueError
        For unsupported formats, files exceeding MAX_FILE_SIZE_MB, failed
        parsing, or documents that yield no usable content.
    """
    # Size check
    max_bytes = MAX_FILE_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise ValueError(
            f"File size {len(content) / (1024 * 1024):.1f} MB exceeds the "
            f"{MAX_FILE_SIZE_MB} MB limit."
        )

    fmt = _detect_format(filename, content_type)
    document_id = str(uuid.uuid4())
    bib_warning: str | None = None

    if fmt == "docling":
        blocks = _docling_blocks(content, filename, document_id)
    elif fmt == "latex":
        blocks, bib_warning = _latex_blocks(content, document_id)
    else:  # plain / markdown
        blocks, bib_warning = _plain_blocks(content, document_id)

    # Final safety check
    if not blocks:
        raise ValueError("Parsing yielded no usable content")

    return document_id, blocks, bib_warning
