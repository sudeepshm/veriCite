"""Stage 4 – Source Retrieval and Passage Ranking.

Downloads each ResolvedSource (PDF or abstract), parses it with Docling,
embeds the resulting passages with sentence-transformers, and returns the
most relevant passages ranked against the supplied claim texts.
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
    EMBEDDING_MODEL,
    MAX_DOWNLOAD_SIZE_MB,
    OPENALEX_API_KEY,
    OPENALEX_EMAIL,
    PROVIDER_TIMEOUT,
    SEMANTIC_SCHOLAR_API_KEY,
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
    # At least 3 meaningful content words shared
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
# Abstract fetchers (fallback when no PDF)
# ---------------------------------------------------------------------------

async def _fetch_abstract_openalex(
    openalex_id: str | None, canonical_doi: str | None, client: httpx.AsyncClient
) -> str | None:
    params: dict = {}
    if OPENALEX_API_KEY:
        params["api_key"] = OPENALEX_API_KEY
    if OPENALEX_EMAIL:
        params["mailto"] = OPENALEX_EMAIL

    if openalex_id:
        # Convert public work URL (e.g. https://openalex.org/W...) to API work URL
        clean_id = openalex_id.strip()
        if "openalex.org/" in clean_id:
            work_short = clean_id.split("openalex.org/")[-1].strip("/")
            url = f"https://api.openalex.org/works/{work_short}"
        else:
            url = f"https://api.openalex.org/works/{clean_id}"
    elif canonical_doi:
        clean_doi = canonical_doi.removeprefix("https://doi.org/").strip()
        url = f"https://api.openalex.org/works/doi:{clean_doi}"
    else:
        return None
    try:
        resp = await client.get(url, params=params, timeout=PROVIDER_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            # OpenAlex stores abstract as inverted index
            inv = data.get("abstract_inverted_index")
            if inv:
                # Reconstruct
                word_pos: list[tuple[int, str]] = []
                for word, positions in inv.items():
                    for pos in positions:
                        word_pos.append((pos, word))
                word_pos.sort()
                return " ".join(w for _, w in word_pos)
    except (httpx.TimeoutException, httpx.ConnectError, Exception):
        pass
    return None


async def _fetch_abstract_s2(
    canonical_doi: str | None,
    matched_title: str | None,
    client: httpx.AsyncClient,
) -> str | None:
    if canonical_doi:
        query = canonical_doi
        url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{canonical_doi}"
        params: dict = {"fields": "abstract"}
    elif matched_title:
        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        params = {"query": matched_title, "fields": "abstract", "limit": 1}
    else:
        return None

    headers: dict = {}
    if SEMANTIC_SCHOLAR_API_KEY:
        headers["x-api-key"] = SEMANTIC_SCHOLAR_API_KEY

    try:
        resp = await client.get(url, params=params, headers=headers, timeout=PROVIDER_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            # Search returns .data list
            if "data" in data:
                items = data["data"]
                if items:
                    return items[0].get("abstract")
            return data.get("abstract")
    except (httpx.TimeoutException, httpx.ConnectError, Exception):
        pass
    return None


async def _get_abstract(source: ResolvedSource, client: httpx.AsyncClient) -> str | None:
    abstract = await _fetch_abstract_openalex(source.openalex_id, source.canonical_doi, client)
    if abstract:
        return abstract
    return await _fetch_abstract_s2(source.canonical_doi, source.matched_title, client)


# ---------------------------------------------------------------------------
# Download
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

            # HTML check: may be login page
            if "text/html" in content_type:
                # Read first 2000 bytes to check
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

            # Stream to temp file
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
# Docling parse
# ---------------------------------------------------------------------------

def _parse_pdf(tmp_path: Path) -> list[tuple[str, str | None, int | None, str | None]]:
    """
    Parse a PDF with Docling.
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
            # Determine section from headings
            item_type = type(item).__name__.lower()
            text_content: str = ""
            page_num: int | None = None
            table_context: str | None = None

            # Extract page number if available
            if hasattr(item, "prov") and item.prov:
                try:
                    page_num = item.prov[0].page_no
                except (IndexError, AttributeError):
                    pass

            if "heading" in item_type or "section" in item_type:
                if hasattr(item, "text"):
                    current_section = item.text
                continue  # don't emit headings as passages

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
        passage_embeddings = _embed_texts(passage_texts)

        # Store embeddings back into passages
        for i, p in enumerate(passages):
            p.embedding = passage_embeddings[i].tolist()

        # Score each passage per claim, accumulate max
        scores = np.zeros(len(passages))

        for claim in claims_text:
            claim_emb = _embed_texts([claim])[0]
            for i, (p_emb, passage) in enumerate(zip(passage_embeddings, passages)):
                sim = _cosine_similarity(claim_emb, p_emb)
                boost = _lexical_boost(claim, passage.verbatim_text)
                combined = sim + boost
                scores[i] = max(scores[i], combined)

        ranked_indices = np.argsort(scores)[::-1]
        seen: set[str] = set()
        top_passages: list[Passage] = []
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
    """Download, parse, embed, and rank passages for a single ResolvedSource."""

    coverage = CoverageStatus.unavailable
    passages: list[Passage] = []
    tmp_path: Path | None = None

    # ------------------------------------------------------------------
    # Step 1 – Download (or get abstract if no URL, or load offline file)
    # ------------------------------------------------------------------
    # Step 1 – Fetch: local file (if explicitly set by resolver) or remote
    # ------------------------------------------------------------------
    abstract_text: str | None = None
    have_pdf = False
    raw_chunks: list[tuple[str, str | None, int | None, str | None]] = []

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
            raw_chunks = [
                (c, local_file.name, None, None) for c in chunks
            ]
            coverage = CoverageStatus.full_text
        except Exception:
            raw_chunks = []
    elif source.source_url is None:
        abstract_text = await _get_abstract(source, client)
        coverage = CoverageStatus.abstract_only if abstract_text else CoverageStatus.unavailable
    else:
        tmp_path, dl_status = await _download_pdf(source.source_url, client)
        if dl_status == "ok" and tmp_path is not None:
            have_pdf = True
        else:
            # Fallback: try abstract
            if dl_status in ("login", "type", "timeout", "size", "error"):
                abstract_text = await _get_abstract(source, client)
            coverage = CoverageStatus.abstract_only if abstract_text else CoverageStatus.unavailable

    # ------------------------------------------------------------------
    # Step 2 – Parse (if PDF was downloaded)
    # ------------------------------------------------------------------
    if have_pdf and tmp_path is not None:
        try:
            raw_chunks = _parse_pdf(tmp_path)
            if raw_chunks:
                coverage = CoverageStatus.full_text
            else:
                # Docling returned nothing — fall back to abstract
                abstract_text = await _get_abstract(source, client)
                coverage = CoverageStatus.abstract_only if abstract_text else CoverageStatus.unavailable
        except Exception:
            abstract_text = await _get_abstract(source, client)
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

    # ------------------------------------------------------------------
    # Step 3 – Create Passage objects
    # ------------------------------------------------------------------
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
                embedding=None,  # filled in step 4
            )
        )

    # ------------------------------------------------------------------
    # Step 4 – Embed and rank
    # ------------------------------------------------------------------
    if claims_text:
        try:
            passages = _rank_passages(passages, claims_text, top_k=10)
        except Exception:
            # If embedding fails (model not downloaded, etc.) return unranked first 10
            passages = passages[:10]

    updated = source.model_copy(update={"coverage": coverage})
    return updated, passages


# ---------------------------------------------------------------------------
# Batch retrieval
# ---------------------------------------------------------------------------

async def retrieve_all_sources(
    sources: list[ResolvedSource],
    claims_text: list[str],
    max_concurrent: int = 3,
) -> tuple[list[ResolvedSource], list[Passage]]:
    """Retrieve and rank passages for all sources concurrently."""
    sem = asyncio.Semaphore(max_concurrent)
    updated_sources: list[ResolvedSource] = []
    all_passages: list[Passage] = []

    async def _retrieve_one(source: ResolvedSource, client: httpx.AsyncClient) -> None:
        async with sem:
            updated, passages = await retrieve_source(source, claims_text, client)
        updated_sources.append(updated)
        all_passages.extend(passages)

    async with httpx.AsyncClient(follow_redirects=True) as client:
        tasks = [
            asyncio.create_task(_retrieve_one(source, client))
            for source in sources
            if source.identity_status.value in ("matched", "ambiguous")
        ]
        # Sources that couldn't be resolved still get coverage=unavailable
        for source in sources:
            if source.identity_status.value not in ("matched", "ambiguous"):
                updated_sources.append(
                    source.model_copy(update={"coverage": CoverageStatus.unavailable})
                )
        await asyncio.gather(*tasks, return_exceptions=True)

    return updated_sources, all_passages
