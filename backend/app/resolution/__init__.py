"""Stage 3 – Reference Resolution (Crossref-only).

For each unique Reference, attempts to resolve it to a canonical paper
identity using Crossref (DOI look-up and bibliographic search) as the sole external API.
"""
from __future__ import annotations

import asyncio
import difflib
import re
import uuid
from typing import Any, Optional

import httpx

from app.config import (
    CROSSREF_MAILTO,
    PROVIDER_TIMEOUT,
)
from app.models import CoverageStatus, IdentityStatus, Reference, ResolvedSource

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SURNAME_RE = re.compile(r"\b[A-Z][a-z]+\b")


def _title_similarity(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _year_score(ref_year: int | None, cand_year: int | None) -> float:
    if ref_year is None or cand_year is None:
        return 0.0
    diff = abs(ref_year - cand_year)
    if diff == 0:
        return 1.0
    if diff == 1:
        return 0.5
    return 0.0


def _extract_surnames(names: list[str]) -> set[str]:
    """Return a set of lower-case surnames extracted from a list of author strings."""
    surnames: set[str] = set()
    for name in names:
        parts = name.split(",")
        surname = parts[0].strip() if len(parts) >= 2 else name.strip().split()[-1]
        surnames.add(surname.lower())
    return surnames


def _author_jaccard(ref_authors: list[str], cand_authors: list[str]) -> float:
    a = _extract_surnames(ref_authors)
    b = _extract_surnames(cand_authors)
    if not a and not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union else 0.0


def _candidate_score(
    ref: Reference,
    cand_title: str | None,
    cand_authors: list[str],
    cand_year: int | None,
) -> float:
    ts = _title_similarity(ref.title, cand_title)
    ys = _year_score(ref.year, cand_year)
    ao = _author_jaccard(ref.authors, cand_authors)
    return 0.5 * ts + 0.3 * ys + 0.2 * ao


def _clean_abstract(raw: str | None) -> str | None:
    """Strip JATS XML tags like <jats:p> from Crossref abstract field."""
    if not raw:
        return None
    cleaned = re.sub(r"<[^>]+>", " ", raw)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or None


def _parse_crossref_work(item: dict) -> tuple[str | None, list[str], int | None, str | None, str | None, str | None]:
    """Return (title, authors, year, doi, content_url, abstract) from a Crossref work item."""
    titles = item.get("title") or []
    title: str | None = titles[0] if titles else None
    raw_authors = item.get("author") or []
    authors: list[str] = []
    for a in raw_authors:
        family = a.get("family", "")
        given = a.get("given", "")
        if family:
            authors.append(f"{family}, {given}".strip(", "))
    year: int | None = None
    dp = item.get("published", {}).get("date-parts")
    if dp and dp[0]:
        try:
            year = int(dp[0][0])
        except (ValueError, TypeError, IndexError):
            pass
    doi: str | None = item.get("DOI")

    # Look for accessible direct link in item.link list
    content_url: str | None = None
    links = item.get("link") or []
    for lk in links:
        url = lk.get("URL")
        ct = lk.get("content-type", "").lower()
        if url and ("pdf" in ct or "octet-stream" in ct):
            content_url = url
            break
    if not content_url and links:
        for lk in links:
            url = lk.get("URL")
            if url:
                content_url = url
                break

    # Also check abstract if present
    abstract = _clean_abstract(item.get("abstract"))
    return title, authors, year, doi, content_url, abstract


# In-memory session cache for Crossref lookups
_CROSSREF_CACHE: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Step 1 – DOI look-up via Crossref
# ---------------------------------------------------------------------------

async def _crossref_doi_lookup(
    doi: str, client: httpx.AsyncClient
) -> tuple[IdentityStatus, str | None, str | None, list[str], int | None, str | None, str | None, str | None]:
    """Return (status, mismatch_note, title, authors, year, canonical_doi, content_url, abstract)."""
    clean_doi = doi.removeprefix("https://doi.org/").strip()
    cache_key = f"doi:{clean_doi.lower()}"
    if cache_key in _CROSSREF_CACHE:
        c = _CROSSREF_CACHE[cache_key]
        return (
            c["status"],
            c.get("mismatch_note"),
            c.get("title"),
            c.get("authors", []),
            c.get("year"),
            c.get("canonical_doi"),
            c.get("content_url"),
            c.get("abstract"),
        )

    url = f"https://api.crossref.org/works/{clean_doi}"
    params: dict = {}
    if CROSSREF_MAILTO:
        params["mailto"] = CROSSREF_MAILTO

    resp = None
    for attempt in range(2):
        try:
            resp = await client.get(url, params=params, timeout=PROVIDER_TIMEOUT)
            if resp.status_code == 429:
                retry_after = resp.headers.get("retry-after")
                delay = min(int(retry_after), 3) if (retry_after and retry_after.isdigit()) else 1.0
                await asyncio.sleep(delay)
                continue
            break
        except (httpx.TimeoutException, httpx.ConnectError):
            if attempt == 0:
                await asyncio.sleep(1.0)
                continue
            resp = None

    if resp is None:
        return IdentityStatus.lookup_failed, None, None, [], None, None, None, None

    if resp.status_code == 404:
        return IdentityStatus.unresolved, None, None, [], None, None, None, None

    if resp.status_code != 200:
        return IdentityStatus.lookup_failed, None, None, [], None, None, None, None

    data = resp.json().get("message", {})
    title, authors, year, canonical_doi, content_url, abstract = _parse_crossref_work(data)
    entry = {
        "status": IdentityStatus.matched,
        "title": title,
        "authors": authors,
        "year": year,
        "canonical_doi": canonical_doi or clean_doi,
        "content_url": content_url,
        "abstract": abstract,
    }
    _CROSSREF_CACHE[cache_key] = entry
    return IdentityStatus.matched, None, title, authors, year, canonical_doi or clean_doi, content_url, abstract


# ---------------------------------------------------------------------------
# Step 2 – Bibliographic search via Crossref
# ---------------------------------------------------------------------------

async def _crossref_bib_search(
    ref: Reference, client: httpx.AsyncClient
) -> tuple[IdentityStatus, str | None, list[str], int | None, str | None, str | None, str | None]:
    """Return (status, title, authors, year, canonical_doi, content_url, abstract)."""
    query_parts = [ref.title or ""]
    if ref.authors:
        query_parts.extend(ref.authors[:2])
    if ref.year:
        query_parts.append(str(ref.year))
    query = " ".join(p for p in query_parts if p).strip()

    cache_key = f"bib:{query.lower()}"
    if cache_key in _CROSSREF_CACHE:
        c = _CROSSREF_CACHE[cache_key]
        return (
            c["status"],
            c.get("title"),
            c.get("authors", []),
            c.get("year"),
            c.get("canonical_doi"),
            c.get("content_url"),
            c.get("abstract"),
        )

    url = "https://api.crossref.org/works"
    params: dict = {
        "query.bibliographic": query,
        "rows": 3,
    }
    if CROSSREF_MAILTO:
        params["mailto"] = CROSSREF_MAILTO

    try:
        resp = await client.get(url, params=params, timeout=PROVIDER_TIMEOUT)
    except (httpx.TimeoutException, httpx.ConnectError):
        return IdentityStatus.lookup_failed, None, [], None, None, None, None

    if resp.status_code == 429 or resp.status_code >= 500:
        return IdentityStatus.lookup_failed, None, [], None, None, None, None

    if resp.status_code != 200:
        return IdentityStatus.unresolved, None, [], None, None, None, None

    items = resp.json().get("message", {}).get("items") or []
    if not items:
        entry = {"status": IdentityStatus.unresolved}
        _CROSSREF_CACHE[cache_key] = entry
        return IdentityStatus.unresolved, None, [], None, None, None, None

    best_score = 0.0
    best_item: dict | None = None
    second_best_score = 0.0

    for item in items:
        cand_title, cand_authors, cand_year, _, _, _ = _parse_crossref_work(item)
        score = _candidate_score(ref, cand_title, cand_authors, cand_year)
        if score > best_score:
            second_best_score = best_score
            best_score = score
            best_item = item
        elif score > second_best_score:
            second_best_score = score

    if not best_item:
        return IdentityStatus.unresolved, None, [], None, None, None, None

    title, authors, year, canonical_doi, content_url, abstract = _parse_crossref_work(best_item)

    # Ambiguity check: high similarity on multiple candidates
    if best_score >= 0.7 and (best_score - second_best_score) < 0.1 and second_best_score >= 0.65:
        status = IdentityStatus.ambiguous
    elif best_score > 0.7:
        status = IdentityStatus.matched
    elif best_score >= 0.5:
        status = IdentityStatus.ambiguous
    else:
        status = IdentityStatus.unresolved

    entry = {
        "status": status,
        "title": title,
        "authors": authors,
        "year": year,
        "canonical_doi": canonical_doi,
        "content_url": content_url,
        "abstract": abstract,
    }
    _CROSSREF_CACHE[cache_key] = entry
    return status, title, authors, year, canonical_doi, content_url, abstract


# ---------------------------------------------------------------------------
# Main reference resolver
# ---------------------------------------------------------------------------

async def resolve_reference(
    ref: Reference,
    client: httpx.AsyncClient,
    test_resolver: Any | None = None,
) -> ResolvedSource:
    source_id = f"src_{uuid.uuid4().hex[:12]}"

    if test_resolver is not None:
        if callable(test_resolver):
            override = test_resolver(ref)
            if override is not None:
                return override
        elif isinstance(test_resolver, dict):
            raw = (ref.raw_marker or "").strip("[] ")
            target_path = (
                test_resolver.get(ref.raw_marker)
                or test_resolver.get(raw)
                or test_resolver.get(ref.ref_id)
                or (test_resolver.get(ref.title) if ref.title else None)
            )
            if target_path:
                from pathlib import Path
                p = Path(target_path)
                if not p.is_file():
                    p = Path("backend") / target_path
                if p.is_file():
                    return ResolvedSource(
                        source_id=source_id,
                        ref_id=ref.ref_id,
                        identity_status=IdentityStatus.matched,
                        matched_title=ref.title or f"Offline Source {ref.raw_marker}",
                        matched_authors=ref.authors,
                        matched_year=ref.year,
                        source_url=str(p.resolve()),
                        coverage=CoverageStatus.unavailable,
                        is_retracted=False,
                        retraction_note=None,
                        age_flag=False,
                    )

    canonical_doi: str | None = None
    matched_title: str | None = None
    matched_authors: list[str] = []
    matched_year: int | None = None
    identity_status: IdentityStatus = IdentityStatus.unresolved
    source_url: str | None = None
    abstract_text: str | None = None

    doi_resolved = False

    # Step 1 – DOI lookup via Crossref
    if ref.doi:
        status, mismatch, cand_title, cand_authors, cand_year, cand_doi, c_url, c_abs = (
            await _crossref_doi_lookup(ref.doi, client)
        )
        if status == IdentityStatus.lookup_failed:
            return ResolvedSource(
                source_id=source_id,
                ref_id=ref.ref_id,
                canonical_doi=ref.doi,
                openalex_id=None,
                s2_id=None,
                matched_title=None,
                matched_authors=[],
                matched_year=None,
                identity_status=IdentityStatus.lookup_failed,
                source_url=None,
                coverage=CoverageStatus.unavailable,
                is_retracted=False,
                retraction_note=None,
                age_flag=False,
            )

        if status == IdentityStatus.matched:
            # Validate against ref metadata
            ts = _title_similarity(ref.title, cand_title)
            ys = abs((ref.year or 0) - (cand_year or 0)) <= 1
            ref_surnames = _extract_surnames(ref.authors)
            cand_surnames = _extract_surnames(cand_authors)
            author_match = bool(ref_surnames & cand_surnames) if (ref_surnames and cand_surnames) else True

            if ts > 0.85 and (not ref.year or ys) and (not ref.authors or author_match):
                identity_status = IdentityStatus.matched
                canonical_doi = cand_doi or ref.doi
                matched_title = cand_title
                matched_authors = cand_authors
                matched_year = cand_year
                source_url = c_url
                abstract_text = c_abs
                doi_resolved = True
            else:
                identity_status = IdentityStatus.metadata_mismatch
                return ResolvedSource(
                    source_id=source_id,
                    ref_id=ref.ref_id,
                    canonical_doi=ref.doi,
                    openalex_id=None,
                    s2_id=None,
                    matched_title=cand_title,
                    matched_authors=cand_authors,
                    matched_year=cand_year,
                    identity_status=IdentityStatus.metadata_mismatch,
                    source_url=None,
                    coverage=CoverageStatus.unavailable,
                    is_retracted=False,
                    retraction_note=None,
                    age_flag=bool(cand_year and cand_year < 2015),
                )

    # Step 2 – Bibliographic search (if no DOI or DOI 404'd)
    if not doi_resolved:
        bib_status, cand_title, cand_authors, cand_year, cand_doi, c_url, c_abs = (
            await _crossref_bib_search(ref, client)
        )
        identity_status = bib_status
        if bib_status in (IdentityStatus.matched, IdentityStatus.ambiguous):
            matched_title = cand_title
            matched_authors = cand_authors or []
            matched_year = cand_year
            canonical_doi = cand_doi
            source_url = c_url
            abstract_text = c_abs

    # Store abstract on the source if found from Crossref
    return ResolvedSource(
        source_id=source_id,
        ref_id=ref.ref_id,
        canonical_doi=canonical_doi,
        openalex_id=None,
        s2_id=None,
        matched_title=matched_title,
        matched_authors=matched_authors,
        matched_year=matched_year,
        identity_status=identity_status,
        source_url=source_url,
        coverage=CoverageStatus.abstract_only if abstract_text and not source_url else CoverageStatus.unavailable,
        is_retracted=False,
        retraction_note=None,
        age_flag=bool(matched_year and matched_year < 2015),
    )


# ---------------------------------------------------------------------------
# Batch resolver with deduplication
# ---------------------------------------------------------------------------

def _ref_key(ref: Reference) -> str:
    """Canonical key for deduplication."""
    if ref.doi:
        return f"doi:{ref.doi.lower().strip()}"
    title_key = (ref.title or "").lower().strip()
    year_key = str(ref.year) if ref.year else ""
    return f"title:{title_key}|year:{year_key}"


async def resolve_all_references(
    refs: list[Reference],
    client: httpx.AsyncClient | None = None,
    test_resolver: Any | None = None,
) -> list[ResolvedSource]:
    """Resolve all references with deduplication and concurrency limit of 3."""
    sem = asyncio.Semaphore(3)

    unique: dict[str, Reference] = {}
    duplicates: dict[str, list[str]] = {}

    for ref in refs:
        key = _ref_key(ref)
        if key not in unique:
            unique[key] = ref
            duplicates[key] = []
        else:
            duplicates[key].append(ref.ref_id)

    cache: dict[str, ResolvedSource] = {}
    results: list[ResolvedSource] = []

    async def _resolve_one(key: str, ref: Reference, http_client: httpx.AsyncClient) -> None:
        async with sem:
            resolved = await resolve_reference(ref, http_client, test_resolver=test_resolver)
        cache[key] = resolved
        results.append(resolved)
        for dup_ref_id in duplicates[key]:
            dup = resolved.model_copy(
                update={
                    "source_id": f"src_{uuid.uuid4().hex[:12]}",
                    "ref_id": dup_ref_id,
                }
            )
            results.append(dup)

    if client is not None:
        tasks = [
            asyncio.create_task(_resolve_one(key, ref, client))
            for key, ref in unique.items()
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
    else:
        async with httpx.AsyncClient(follow_redirects=True) as local_client:
            tasks = [
                asyncio.create_task(_resolve_one(key, ref, local_client))
                for key, ref in unique.items()
            ]
            await asyncio.gather(*tasks, return_exceptions=True)

    return results
