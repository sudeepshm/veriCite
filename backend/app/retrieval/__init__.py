"""Stage 4 – Source Retrieval and Passage Ranking (Crossref-only).

Downloads each ResolvedSource if an accessible content link was supplied by its matched
Crossref record, or uses the Crossref record abstract.
Passages are extracted, embedded with sentence-transformers, and ranked against claim texts.
"""
from __future__ import annotations

import asyncio
import re
import tempfile
import uuid
from pathlib import Path
from typing import Optional

import httpx
import numpy as np

from app.config import (
    CROSSREF_MAILTO,
    EMBEDDING_MODEL,
    MAX_DOWNLOAD_SIZE_MB,
    PROVIDER_TIMEOUT,
)
from app.models import CoverageStatus, DocumentBlock, Passage, ResolvedSource

# ---------------------------------------------------------------------------
# Module-level embedding model cache
# ---------------------------------------------------------------------------

_embedding_model = None


def get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer

        _embedding_model = SentenceTransformer(EMBEDDING_MODEL)
    return _embedding_model


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LOGIN_SIGNALS = re.compile(r"login|sign in|access denied|please log in", re.IGNORECASE)
_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:%|mg|kg|ml|l|km|m|cm|mm|g|s|ms|µ[a-z]*)?\b")


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _lexical_boost(claim: str, passage_text: str) -> float:
    """Return +0.1 if the passage shares numbers, units, or key content words with the claim."""
    claim_numbers = set(_NUMBER_RE.findall(claim.lower()))
    passage_numbers = set(_NUMBER_RE.findall(passage_text.lower()))
    if claim_numbers & passage_numbers:
        return 0.1

    claim_words = set(re.findall(r"\b[a-z]{4,}\b", claim.lower()))
    passage_words = set(re.findall(r"\b[a-z]{4,}\b", passage_text.lower()))
    overlap = claim_words & passage_words
    if len(overlap) >= 3:
        return 0.05
    return 0.0


def _chunk_abstract(text: str) -> list[str]:
    """Split abstract into sentence chunks of at least 20 chars."""
    raw = re.split(r"\.\s+", text)
    chunks = []
    for s in raw:
        s = s.strip()
        if len(s) >= 20:
            chunks.append(s if s.endswith(".") else s + ".")
    if not chunks and len(text) >= 20:
        chunks = [text]
    return chunks


# ---------------------------------------------------------------------------
# Crossref abstract retrieval
# ---------------------------------------------------------------------------

async def _fetch_abstract_crossref(canonical_doi: str | None, client: httpx.AsyncClient) -> str | None:
    """Fetch abstract directly from Crossref record if not already parsed."""
    if not canonical_doi:
        return None
    clean_doi = canonical_doi.removeprefix("https://doi.org/").strip()
    try:
        from app.database import get_cached_crossref, set_cached_crossref
        cached = get_cached_crossref(clean_doi)
        if cached and isinstance(cached, dict):
            raw_abstract = cached.get("abstract")
            if raw_abstract:
                cleaned = re.sub(r"<[^>]+>", " ", raw_abstract)
                cleaned = re.sub(r"\s+", " ", cleaned).strip()
                return cleaned or None
    except Exception:
        pass

    url = f"https://api.crossref.org/works/{clean_doi}"
    params: dict = {}
    if CROSSREF_MAILTO:
        params["mailto"] = CROSSREF_MAILTO
    try:
        resp = await client.get(url, params=params, timeout=PROVIDER_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json().get("message", {})
            try:
                set_cached_crossref(clean_doi, data)
            except Exception:
                pass
            raw_abstract = data.get("abstract")
            if raw_abstract:
                cleaned = re.sub(r"<[^>]+>", " ", raw_abstract)
                cleaned = re.sub(r"\s+", " ", cleaned).strip()
                return cleaned or None
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Direct download of accessible paper from matched Crossref record link
# ---------------------------------------------------------------------------

async def _download_pdf(
    source_url: str, client: httpx.AsyncClient
) -> tuple[Path | None, str]:
    """Download URL → temp file. Returns (path, status) where status is 'ok', 'login', 'size', 'type', 'error'."""
    max_bytes = MAX_DOWNLOAD_SIZE_MB * 1024 * 1024
    try:
        async with client.stream(
            "GET", source_url, follow_redirects=True, timeout=PROVIDER_TIMEOUT
        ) as resp:
            if resp.status_code != 200:
                return None, "error"

            content_length = resp.headers.get("content-length")
            if content_length and int(content_length) > max_bytes:
                return None, "size"

            content_type = resp.headers.get("content-type", "").lower()

            if "text/html" in content_type:
                chunk_data = b""
                async for chunk in resp.aiter_bytes(chunk_size=2048):
                    chunk_data += chunk
                    break
                snippet = chunk_data[:2000].decode("utf-8", errors="replace")
                if _LOGIN_SIGNALS.search(snippet):
                    return None, "login"
                return None, "type"

            is_pdf = (
                "application/pdf" in content_type
                or "application/octet-stream" in content_type
                or "pdf" in content_type
            )
            if not is_pdf:
                return None, "type"

            suffix = ".pdf"
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            downloaded = 0
            async for chunk in resp.aiter_bytes(chunk_size=65536):
                downloaded += len(chunk)
                if downloaded > max_bytes:
                    tmp.close()
                    Path(tmp.name).unlink(missing_ok=True)
                    return None, "size"
                tmp.write(chunk)
            tmp.close()
            return Path(tmp.name), "ok"

    except httpx.TimeoutException:
        return None, "timeout"
    except (httpx.ConnectError, Exception):
        return None, "error"


# ---------------------------------------------------------------------------
# PDF parse (Docling with PyMuPDF fallback)
# ---------------------------------------------------------------------------

def _parse_pdf(tmp_path: Path) -> list[tuple[str, str | None, int | None, str | None]]:
    """Parse a PDF with Docling, with PyMuPDF fallback.
    Returns list of (text, section, page, table_context).
    """
    try:
        from docling.document_converter import DocumentConverter

        converter = DocumentConverter()
        result = converter.convert(str(tmp_path))
        doc = result.document

        chunks: list[tuple[str, str | None, int | None, str | None]] = []
        current_section: str | None = None

        for item, level in doc.iterate_items():
            item_type = type(item).__name__.lower()
            text_content: str = ""
            page_num: int | None = None
            table_context: str | None = None

            if hasattr(item, "prov") and item.prov:
                try:
                    page_num = item.prov[0].page_no
                except (IndexError, AttributeError):
                    pass

            if "heading" in item_type or "section" in item_type:
                if hasattr(item, "text"):
                    current_section = item.text
                continue

            if "table" in item_type:
                try:
                    text_content = item.export_to_markdown()
                    table_context = text_content[:200] if text_content else None
                except Exception:
                    try:
                        text_content = str(item)
                    except Exception:
                        continue
            elif hasattr(item, "text"):
                text_content = item.text or ""
            else:
                try:
                    text_content = str(item)
                except Exception:
                    continue

            text_content = text_content.strip()
            if len(text_content) >= 20:
                chunks.append((text_content, current_section, page_num, table_context))

        if chunks:
            return chunks
    except Exception:
        pass

    # PyMuPDF fallback
    try:
        import fitz
        doc = fitz.open(str(tmp_path))
        chunks = []
        for page_num, page in enumerate(doc):
            blocks = page.get_text("blocks")
            for b in blocks:
                text = b[4].strip()
                if len(text) >= 20:
                    chunks.append((text, None, page_num + 1, None))
        return chunks
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Embedding and ranking
# ---------------------------------------------------------------------------

def _embed_texts(texts: list[str]) -> np.ndarray:
    model = get_embedding_model()
    return model.encode(texts, convert_to_numpy=True, show_progress_bar=False)


def _rank_passages(
    passages: list[Passage],
    claims_text: list[str],
    top_k: int = 10,
) -> list[Passage]:
    if not passages or not claims_text:
        return passages

    try:
        passage_texts = [p.verbatim_text for p in passages]
        p_embeds = _embed_texts(passage_texts)
        c_embeds = _embed_texts(claims_text)

        mean_claim_embed = np.mean(c_embeds, axis=0)

        scores = []
        for idx, p in enumerate(passages):
            cos_sim = _cosine_similarity(p_embeds[idx], mean_claim_embed)
            boost = max(_lexical_boost(c, p.verbatim_text) for c in claims_text)
            scores.append((cos_sim + boost, idx))

        scores.sort(key=lambda x: x[0], reverse=True)
        ranked_indices = [idx for _, idx in scores]

        top_passages: list[Passage] = []
        seen = set()
        for idx in ranked_indices:
            if len(top_passages) >= top_k:
                break
            p = passages[idx]
            if p.passage_id not in seen:
                seen.add(p.passage_id)
                top_passages.append(p)
        return top_passages
    except Exception:
        return passages[:top_k]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def retrieve_source(
    source: ResolvedSource,
    claims_text: list[str],
    client: httpx.AsyncClient,
) -> tuple[ResolvedSource, list[Passage]]:
    """Download, parse, embed, and rank passages for a single ResolvedSource using Crossref data."""

    coverage = CoverageStatus.unavailable
    passages: list[Passage] = []
    tmp_path: Path | None = None
    abstract_text: str | None = None
    have_pdf = False
    raw_chunks: list[tuple[str, str | None, int | None, str | None]] = []

    # Check for local file path override (test resolver)
    local_file: Path | None = None
    if source.source_url:
        cleaned_url = source.source_url.removeprefix("file://")
        p = Path(cleaned_url)
        if p.is_file():
            local_file = p

    if local_file is not None:
        try:
            content_str = local_file.read_text(encoding="utf-8", errors="replace")
            chunks = [s.strip() for s in content_str.splitlines() if len(s.strip()) > 10]
            raw_chunks = [(c, local_file.name, None, None) for c in chunks]
            coverage = CoverageStatus.full_text
        except Exception:
            raw_chunks = []
    elif source.source_url is None:
        # No content link from Crossref: try fetching Crossref abstract
        abstract_text = await _fetch_abstract_crossref(source.canonical_doi, client)
        coverage = CoverageStatus.abstract_only if abstract_text else CoverageStatus.unavailable
    else:
        # Download accessible link from Crossref record
        tmp_path, dl_status = await _download_pdf(source.source_url, client)
        if dl_status == "ok" and tmp_path is not None:
            have_pdf = True
        else:
            abstract_text = await _fetch_abstract_crossref(source.canonical_doi, client)
            coverage = CoverageStatus.abstract_only if abstract_text else CoverageStatus.unavailable

    # Step 2 – Parse downloaded PDF
    if have_pdf and tmp_path is not None:
        try:
            raw_chunks = _parse_pdf(tmp_path)
            if raw_chunks:
                coverage = CoverageStatus.full_text
            else:
                abstract_text = await _fetch_abstract_crossref(source.canonical_doi, client)
                coverage = CoverageStatus.abstract_only if abstract_text else CoverageStatus.unavailable
        except Exception:
            abstract_text = await _fetch_abstract_crossref(source.canonical_doi, client)
            coverage = CoverageStatus.abstract_only if abstract_text else CoverageStatus.unavailable
        finally:
            if tmp_path and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass

    if not raw_chunks and abstract_text:
        for sentence in _chunk_abstract(abstract_text):
            raw_chunks.append((sentence, None, None, None))
        coverage = CoverageStatus.abstract_only

    if not raw_chunks:
        updated = source.model_copy(update={"coverage": CoverageStatus.unavailable})
        return updated, []

    # Step 3 – Create Passage objects
    for chunk_text, section, page, table_context in raw_chunks:
        passages.append(
            Passage(
                passage_id=f"p_{uuid.uuid4().hex[:12]}",
                source_id=source.source_id,
                verbatim_text=chunk_text,
                section=section,
                page=page,
                char_start=None,
                char_end=None,
                table_context=table_context,
                embedding=None,
            )
        )

    # Step 4 – Embed and rank
    if claims_text:
        try:
            passages = _rank_passages(passages, claims_text, top_k=10)
        except Exception:
            passages = passages[:10]

    updated = source.model_copy(update={"coverage": coverage})
    return updated, passages


async def retrieve_all_sources(
    sources: list[ResolvedSource],
    claims_text: list[str],
    client: httpx.AsyncClient | None = None,
) -> tuple[list[ResolvedSource], list[Passage]]:
    """Retrieve and process all sources concurrently with limit of 3."""
    sem = asyncio.Semaphore(3)

    async def _process_one(s: ResolvedSource, http_client: httpx.AsyncClient):
        async with sem:
            return await retrieve_source(s, claims_text, http_client)

    if client is not None:
        tasks = [_process_one(s, client) for s in sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    else:
        async with httpx.AsyncClient(follow_redirects=True) as local_client:
            tasks = [_process_one(s, local_client) for s in sources]
            results = await asyncio.gather(*tasks, return_exceptions=True)

    updated_sources: list[ResolvedSource] = []
    all_passages: list[Passage] = []

    for r in results:
        if isinstance(r, BaseException):
            continue
        src, plist = r
        updated_sources.append(src)
        all_passages.extend(plist)

    return updated_sources, all_passages


__all__ = [
    "retrieve_source",
    "retrieve_all_sources",
]
