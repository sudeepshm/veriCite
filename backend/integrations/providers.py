"""Academic discovery provider (Crossref-only).

In Crossref-only mode, Crossref is the sole external metadata API.
Outbound calls to OpenAlex, Semantic Scholar, Unpaywall, PubMed, Europe PMC, and arXiv have been removed.
"""
from __future__ import annotations

import os
from typing import Any
import httpx

from app.config import CROSSREF_MAILTO, PROVIDER_TIMEOUT

TIMEOUT = PROVIDER_TIMEOUT


def paper(title, url=None, doi=None, year=None, source=None, abstract=None, **extra):
    return {
        "title": title,
        "url": url,
        "doi": doi,
        "year": year,
        "source": source or "crossref",
        "abstract": abstract,
        **extra,
    }


async def get_json(client: httpx.AsyncClient, url: str, params: dict | None = None, headers: dict | None = None):
    r = await client.get(url, params=params, headers=headers)
    r.raise_for_status()
    return r.json()


async def crossref(client: httpx.AsyncClient, query: str, limit: int = 5) -> list[dict]:
    """Query Crossref /works via query.bibliographic with mailto."""
    params: dict = {
        "query.bibliographic": query,
        "rows": limit,
    }
    if CROSSREF_MAILTO:
        params["mailto"] = CROSSREF_MAILTO

    data = await get_json(client, "https://api.crossref.org/works", params)
    items = data.get("message", {}).get("items", [])
    results: list[dict] = []
    for x in items:
        titles = x.get("title") or []
        title = titles[0] if titles else None
        doi = x.get("DOI")
        pub_year = None
        dp = ((x.get("published") or {}).get("date-parts") or [[None]])[0]
        if dp and dp[0]:
            try:
                pub_year = int(dp[0])
            except (ValueError, TypeError):
                pub_year = None

        # Content / direct PDF link from item.link if available
        links = x.get("link") or []
        pdf_url = None
        for lk in links:
            url = lk.get("URL")
            ct = lk.get("content-type", "").lower()
            if url and ("pdf" in ct or "octet-stream" in ct):
                pdf_url = url
                break

        results.append(
            paper(
                title=title,
                url=x.get("URL"),
                doi=doi,
                year=pub_year,
                source="crossref",
                abstract=x.get("abstract"),
                open_access_pdf=pdf_url,
            )
        )
    return results


async def open_access_lookup(client: httpx.AsyncClient, doi: str) -> dict[str, Any]:
    """Look up paper direct links from Crossref works record for a DOI."""
    canonical_doi = doi.removeprefix("https://doi.org/").strip()
    params: dict = {}
    if CROSSREF_MAILTO:
        params["mailto"] = CROSSREF_MAILTO

    url = f"https://api.crossref.org/works/{canonical_doi}"
    try:
        data = await get_json(client, url, params=params)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return {
                "doi": canonical_doi,
                "is_oa": False,
                "url_for_pdf": None,
                "url_for_landing_page": None,
                "source": "crossref",
                "status": "not_found",
            }
        raise
    except (httpx.TimeoutException, httpx.ConnectError) as exc:
        return {
            "doi": canonical_doi,
            "status": "lookup_failed",
            "is_oa": None,
            "url_for_pdf": None,
            "url_for_landing_page": None,
            "source": "crossref",
            "error": "Crossref request failed; check network or retry.",
        }

    item = data.get("message", {})
    links = item.get("link") or []
    pdf_url = None
    landing_url = item.get("URL")
    for lk in links:
        u = lk.get("URL")
        ct = lk.get("content-type", "").lower()
        if u and ("pdf" in ct or "octet-stream" in ct):
            pdf_url = u
            break

    return {
        "doi": canonical_doi,
        "is_oa": bool(pdf_url),
        "url_for_pdf": pdf_url,
        "url_for_landing_page": landing_url,
        "source": "crossref",
        "status": "success",
    }


# In Crossref-only mode, only Crossref is queried
PRIMARY_SEARCH_PROVIDERS = {
    "crossref": crossref,
}

SEARCH_PROVIDERS = {
    "crossref": crossref,
}


async def search_all(query: str, limit: int = 5, providers: list[str] | None = None) -> dict[str, Any]:
    """Search academic literature using Crossref only."""
    if providers is not None:
        unknown = set(providers) - set(SEARCH_PROVIDERS)
        if unknown:
            raise ValueError(f"Unknown providers: {sorted(unknown)}. Only 'crossref' is supported in Crossref-only mode.")
        target_keys = providers
    else:
        target_keys = list(SEARCH_PROVIDERS.keys())

    papers = []
    errors = {}
    seen = set()

    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        for prov_name in target_keys:
            prov_fn = SEARCH_PROVIDERS.get(prov_name)
            if not prov_fn:
                continue
            try:
                results = await prov_fn(client, query, limit)
                for item in results:
                    key = (item.get("doi") or item.get("title") or "").strip().lower()
                    if key and key not in seen:
                        seen.add(key)
                        papers.append(item)
            except httpx.HTTPStatusError as exc:
                errors[prov_name] = f"Provider returned HTTP {exc.response.status_code}"
            except (httpx.TimeoutException, httpx.ConnectError):
                errors[prov_name] = "Provider request failed or timed out; retryable."
            except Exception as exc:
                errors[prov_name] = str(exc)

    return {
        "query": query,
        "papers": papers,
        "provider_errors": errors,
        "notice": "Candidate citations from Crossref. Search relevance does not establish source support.",
    }


__all__ = [
    "crossref",
    "open_access_lookup",
    "search_all",
    "SEARCH_PROVIDERS",
    "PRIMARY_SEARCH_PROVIDERS",
]
