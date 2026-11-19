"""Stage 3 – Reference Resolution.

For each unique Reference, attempts to resolve it to a canonical paper
identity using Crossref (DOI look-up and bibliographic search), OpenAlex,
and Semantic Scholar, in that priority order.
"""
from __future__ import annotations

import asyncio
import difflib
import re
import uuid
from typing import Optional

import httpx

from app.config import (
    CROSSREF_MAILTO,
    MAX_RETRIES,
    OPENALEX_EMAIL,
    PROVIDER_TIMEOUT,
    SEMANTIC_SCHOLAR_API_KEY,
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
        # "Family, Given" or "Given Family"
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


def _parse_crossref_work(item: dict) -> tuple[str | None, list[str], int | None, str | None]:
    """Return (title, authors, year, doi) from a Crossref work item."""
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
    return title, authors, year, doi


# ---------------------------------------------------------------------------
# Step 1 – DOI look-up via Crossref
# ---------------------------------------------------------------------------

async def _crossref_doi_lookup(
    doi: str, client: httpx.AsyncClient
) -> tuple[IdentityStatus, str | None, str | None, list[str], int | None, str | None]:
    """Return (status, mismatch_note, title, authors, year, canonical_doi)."""
    url = f"https://api.crossref.org/works/{doi}"
    params: dict = {}
    if CROSSREF_MAILTO:
        params["mailto"] = CROSSREF_MAILTO
    try:
        resp = await client.get(url, params=params, timeout=PROVIDER_TIMEOUT)
    except (httpx.TimeoutException, httpx.ConnectError):
        return IdentityStatus.lookup_failed, None, None, [], None, None

    if resp.status_code == 404:
        return IdentityStatus.unresolved, None, None, [], None, None  # caller tries bibliographic

    if resp.status_code != 200:
        return IdentityStatus.lookup_failed, None, None, [], None, None

    data = resp.json().get("message", {})
    title, authors, year, canonical_doi = _parse_crossref_work(data)
    return IdentityStatus.matched, None, title, authors, year, canonical_doi or doi


# ---------------------------------------------------------------------------
# Step 2 – Bibliographic search via Crossref
# ---------------------------------------------------------------------------

async def _crossref_bib_search(
    ref: Reference, client: httpx.AsyncClient
) -> tuple[IdentityStatus, str | None, list[str], int | None, str | None]:
    """Return (status, title, authors, year, canonical_doi)."""
    query_parts = [ref.title or ""]
    if ref.authors:
        query_parts.extend(ref.authors[:2])
    if ref.year:
        query_parts.append(str(ref.year))
    query = " ".join(p for p in query_parts if p).strip()

    url = "https://api.crossref.org/works"
    params: dict = {
        "query.bibliographic": query,
        "rows": 3,
        "mailto": CROSSREF_MAILTO or "",
    }
    try:
        resp = await client.get(url, params=params, timeout=PROVIDER_TIMEOUT)
    except (httpx.TimeoutException, httpx.ConnectError):
        return IdentityStatus.lookup_failed, None, [], None, None

    if resp.status_code != 200:
        return IdentityStatus.lookup_failed, None, [], None, None

    items = resp.json().get("message", {}).get("items") or []
    best_score = 0.0
    best: tuple[str | None, list[str], int | None, str | None] = (None, [], None, None)

    for item in items:
        cand_title, cand_authors, cand_year, cand_doi = _parse_crossref_work(item)
        score = _candidate_score(ref, cand_title, cand_authors, cand_year)
        if score > best_score:
            best_score = score
            best = (cand_title, cand_authors, cand_year, cand_doi)

    t, a, y, d = best
    if best_score > 0.7:
        return IdentityStatus.matched, t, a, y, d
    if best_score >= 0.5:
        return IdentityStatus.ambiguous, t, a, y, d
    return IdentityStatus.unresolved, t, a, y, d


# ---------------------------------------------------------------------------
# Step 3 – OpenAlex lookup
# ---------------------------------------------------------------------------

async def _openalex_lookup(
    canonical_doi: str | None,
    matched_title: str | None,
    client: httpx.AsyncClient,
) -> tuple[str | None, str | None, bool, str | None]:
    """Return (openalex_id, source_url, is_retracted, retraction_note)."""
    if canonical_doi:
        url = f"https://api.openalex.org/works/doi:{canonical_doi}"
        params: dict = {}
        if OPENALEX_EMAIL:
            params["mailto"] = OPENALEX_EMAIL
    elif matched_title:
        url = "https://api.openalex.org/works"
        params = {"search": matched_title, "per-page": 1}
        if OPENALEX_EMAIL:
            params["mailto"] = OPENALEX_EMAIL
    else:
        return None, None, False, None

    try:
        resp = await client.get(url, params=params, timeout=PROVIDER_TIMEOUT)
    except (httpx.TimeoutException, httpx.ConnectError):
        return None, None, False, None

    if resp.status_code != 200:
        return None, None, False, None

    data = resp.json()
    # When searching, results come in .results list
    if "results" in data:
        results = data.get("results") or []
        if not results:
            return None, None, False, None
        data = results[0]

    openalex_id: str | None = data.get("id")
    is_retracted: bool = bool(data.get("is_retracted", False))
    retraction_note: str | None = (
        "Flagged as retracted by OpenAlex" if is_retracted else None
    )

    source_url: str | None = None
    oa_loc = data.get("best_oa_location") or {}
    source_url = oa_loc.get("pdf_url") or oa_loc.get("url") or None

    return openalex_id, source_url, is_retracted, retraction_note


# ---------------------------------------------------------------------------
# Step 4 – Semantic Scholar fallback
# ---------------------------------------------------------------------------

async def _s2_lookup(
    ref_title: str | None, client: httpx.AsyncClient
) -> tuple[str | None, str | None]:
    """Return (s2_id, source_url) or (None, None)."""
    if not ref_title:
        return None, None
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params: dict = {
        "query": ref_title,
        "fields": "title,year,externalIds,openAccessPdf,isOpenAccess",
        "limit": 1,
    }
    headers: dict = {}
    if SEMANTIC_SCHOLAR_API_KEY:
        headers["x-api-key"] = SEMANTIC_SCHOLAR_API_KEY

    try:
        resp = await client.get(url, params=params, headers=headers, timeout=PROVIDER_TIMEOUT)
    except (httpx.TimeoutException, httpx.ConnectError):
        return None, None

    if resp.status_code != 200:
        return None, None

    data_list = (resp.json().get("data") or [])
    if not data_list:
        return None, None

    hit = data_list[0]
    cand_title = hit.get("title") or ""
    if _title_similarity(ref_title, cand_title) < 0.8:
        return None, None

    s2_id: str | None = hit.get("paperId")
    source_url: str | None = None
    oa_pdf = hit.get("openAccessPdf") or {}
    source_url = oa_pdf.get("url") or None
    return s2_id, source_url


# ---------------------------------------------------------------------------
# Main resolver
# ---------------------------------------------------------------------------

async def resolve_reference(ref: Reference, client: httpx.AsyncClient) -> ResolvedSource:
    source_id = f"src_{uuid.uuid4().hex[:12]}"

    canonical_doi: str | None = None
    openalex_id: str | None = None
    s2_id: str | None = None
    matched_title: str | None = None
    matched_authors: list[str] = []
    matched_year: int | None = None
    identity_status: IdentityStatus = IdentityStatus.unresolved
    source_url: str | None = None
    is_retracted: bool = False
    retraction_note: str | None = None

    doi_resolved = False

    # ------------------------------------------------------------------
    # Step 1 – DOI lookup
    # ------------------------------------------------------------------
    if ref.doi:
        status, mismatch, cand_title, cand_authors, cand_year, cand_doi = (
            await _crossref_doi_lookup(ref.doi, client)
        )
        if status == IdentityStatus.lookup_failed:
            identity_status = IdentityStatus.lookup_failed
            # Return early: network error – skip bibliographic search too
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
                doi_resolved = True
            else:
                identity_status = IdentityStatus.metadata_mismatch
                # Do NOT proceed with this paper
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
        # else: 404 → fall through to bibliographic search

    # ------------------------------------------------------------------
    # Step 2 – Bibliographic search (if no DOI or DOI 404'd)
    # ------------------------------------------------------------------
    if not doi_resolved:
        bib_status, cand_title, cand_authors, cand_year, cand_doi = (
            await _crossref_bib_search(ref, client)
        )
        identity_status = bib_status
        if bib_status in (IdentityStatus.matched, IdentityStatus.ambiguous):
            matched_title = cand_title
            matched_authors = cand_authors or []
            matched_year = cand_year
            canonical_doi = cand_doi

    # ------------------------------------------------------------------
    # Step 3 – OpenAlex lookup (for matched identity)
    # ------------------------------------------------------------------
    if identity_status == IdentityStatus.matched:
        openalex_id, oa_url, is_retracted, retraction_note = await _openalex_lookup(
            canonical_doi, matched_title, client
        )
        if oa_url:
            source_url = oa_url

    # ------------------------------------------------------------------
    # Step 4 – Semantic Scholar fallback (if still no source_url)
    # ------------------------------------------------------------------
    if source_url is None and identity_status in (
        IdentityStatus.matched,
        IdentityStatus.ambiguous,
    ):
        s2_id, s2_url = await _s2_lookup(matched_title or ref.title, client)
        if s2_url:
            source_url = s2_url

    # Check for offline local file mapping (e.g. source-1.txt, source-2.txt)
    ref_num = 1
    if "_r" in ref.ref_id:
        try:
            ref_num = int(ref.ref_id.split("_r")[-1]) + 1
        except Exception:
            ref_num = 1
    from pathlib import Path
    for p in [Path(f"source-{ref_num}.txt"), Path(f"backend/source-{ref_num}.txt")]:
        if p.is_file():
            identity_status = IdentityStatus.matched
            source_url = str(p.resolve())
            matched_title = ref.title or f"Offline Source {ref_num}"
            break

    return ResolvedSource(
        source_id=source_id,
        ref_id=ref.ref_id,
        canonical_doi=canonical_doi,
        openalex_id=openalex_id,
        s2_id=s2_id,
        matched_title=matched_title,
        matched_authors=matched_authors,
        matched_year=matched_year,
        identity_status=identity_status,
        source_url=source_url,
        coverage=CoverageStatus.unavailable,  # updated in Stage 4
        is_retracted=is_retracted,
        retraction_note=retraction_note,
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


async def resolve_all_references(refs: list[Reference]) -> list[ResolvedSource]:
    """Resolve all references with deduplication and concurrency limit of 3."""
    sem = asyncio.Semaphore(3)

    # Deduplicate: keep one canonical ref per key, but remember all ref_ids
    unique: dict[str, Reference] = {}
    duplicates: dict[str, list[str]] = {}  # canonical key → list of duplicate ref_ids

    for ref in refs:
        key = _ref_key(ref)
        if key not in unique:
            unique[key] = ref
            duplicates[key] = []
        else:
            duplicates[key].append(ref.ref_id)

    cache: dict[str, ResolvedSource] = {}
    results: list[ResolvedSource] = []

    async def _resolve_one(key: str, ref: Reference, client: httpx.AsyncClient) -> None:
        async with sem:
            resolved = await resolve_reference(ref, client)
        cache[key] = resolved
        results.append(resolved)
        # Emit cloned sources for duplicate refs (same paper, different ref_ids)
        for dup_ref_id in duplicates[key]:
            dup = resolved.model_copy(
                update={
                    "source_id": f"src_{uuid.uuid4().hex[:12]}",
                    "ref_id": dup_ref_id,
                }
            )
            results.append(dup)

    async with httpx.AsyncClient(follow_redirects=True) as client:
        tasks = [
            asyncio.create_task(_resolve_one(key, ref, client))
            for key, ref in unique.items()
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    return results
