"""Academic discovery providers. Only public metadata/open-access links are returned."""
import asyncio
import os
import xml.etree.ElementTree as ET
from urllib.parse import quote
import httpx

TIMEOUT = 20

def paper(title, url=None, doi=None, year=None, source=None, abstract=None, **extra):
    return {"title": title, "url": url, "doi": doi, "year": year,
            "source": source, "abstract": abstract, **extra}

async def get_json(client, url, params=None, headers=None):
    r = await client.get(url, params=params, headers=headers)
    r.raise_for_status()
    return r.json()

async def openalex(client, query, limit=5):
    params = {"search": query, "per_page": limit}
    if os.getenv("OPENALEX_API_KEY"):
        params["api_key"] = os.environ["OPENALEX_API_KEY"]
    data = await get_json(client, "https://api.openalex.org/works", params)
    return [paper(x.get("display_name"), x.get("id"), x.get("doi"),
                  x.get("publication_year"), "openalex",
                  openalex_abstract(x.get("abstract_inverted_index")))
            for x in data.get("results", [])]

def openalex_abstract(index):
    if not index:
        return None
    words = [(position, word) for word, positions in index.items() for position in positions]
    return " ".join(word for _, word in sorted(words))

async def semantic_scholar(client, query, limit=5):
    headers = {}
    if os.getenv("SEMANTIC_SCHOLAR_API_KEY"):
        headers["x-api-key"] = os.environ["SEMANTIC_SCHOLAR_API_KEY"]
    data = await get_json(client, "https://api.semanticscholar.org/graph/v1/paper/search",
                          {"query": query, "limit": limit,
                           "fields": "title,url,year,abstract,externalIds,openAccessPdf"}, headers)
    return [paper(x.get("title"), x.get("url"),
                  (x.get("externalIds") or {}).get("DOI"), x.get("year"),
                  "semantic_scholar", x.get("abstract"),
                  open_access_pdf=(x.get("openAccessPdf") or {}).get("url"))
            for x in data.get("data", [])]

async def crossref(client, query, limit=5):
    data = await get_json(client, "https://api.crossref.org/works",
                          {"query.bibliographic": query, "rows": limit})
    return [paper((x.get("title") or [None])[0], x.get("URL"), x.get("DOI"),
                  ((x.get("published") or {}).get("date-parts") or [[None]])[0][0],
                  "crossref") for x in data.get("message", {}).get("items", [])]

async def pubmed(client, query, limit=5):
    params = {"db": "pubmed", "term": query, "retmax": limit, "retmode": "json",
              "tool": "vericite", "email": os.getenv("NCBI_EMAIL", "")}
    if os.getenv("NCBI_API_KEY"):
        params["api_key"] = os.environ["NCBI_API_KEY"]
    result = await get_json(client, "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi", params)
    ids = result.get("esearchresult", {}).get("idlist", [])
    if not ids:
        return []
    summary = await get_json(client, "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
                             {"db": "pubmed", "id": ",".join(ids), "retmode": "json"})
    return [paper(summary["result"][i].get("title"), f"https://pubmed.ncbi.nlm.nih.gov/{i}/",
                  next((v.get("value") for v in summary["result"][i].get("articleids", [])
                        if v.get("idtype") == "doi"), None),
                  (summary["result"][i].get("pubdate") or "")[:4], "pubmed")
            for i in ids if i in summary.get("result", {})]

async def europe_pmc(client, query, limit=5):
    data = await get_json(client, "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
                          {"query": query, "pageSize": limit, "format": "json"})
    return [paper(x.get("title"), f"https://europepmc.org/article/{x.get('source')}/{x.get('id')}",
                  x.get("doi"), x.get("pubYear"), "europe_pmc",
                  x.get("abstractText"), pmcid=x.get("pmcid"))
            for x in data.get("resultList", {}).get("result", [])]

async def arxiv(client, query, limit=5):
    r = await client.get("https://export.arxiv.org/api/query",
                         params={"search_query": f"all:{query}", "start": 0, "max_results": limit})
    r.raise_for_status()
    root = ET.fromstring(r.text)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    return [paper(" ".join(e.findtext("a:title", default="", namespaces=ns).split()),
                  e.findtext("a:id", namespaces=ns), None,
                  e.findtext("a:published", default="", namespaces=ns)[:4],
                  "arxiv", " ".join(e.findtext("a:summary", default="", namespaces=ns).split()))
            for e in root.findall("a:entry", ns)]

async def agris(client, query, limit=5):
    # AGRIS does not offer the same stable public search contract as the other providers.
    # Use OpenAlex for agricultural discovery until an approved AGRIS API is configured.
    raise NotImplementedError("AGRIS connector requires a verified API contract")

async def open_access_lookup(client: httpx.AsyncClient, doi: str) -> dict:
    """Find open-access PDF and landing page via OpenAlex, falling back to Semantic Scholar for PDF."""
    clean_doi = doi.removeprefix("https://doi.org/").strip()
    if not clean_doi:
        raise ValueError("DOI must be provided")

    oa_meta: dict | None = None
    openalex_failed = False
    oa_pdf_url: str | None = None
    landing_url: str | None = None
    is_oa: bool | None = None
    canonical_doi = f"https://doi.org/{clean_doi}"

    # 1. OpenAlex lookup
    try:
        params = {}
        if os.getenv("OPENALEX_API_KEY"):
            params["api_key"] = os.environ["OPENALEX_API_KEY"]
        data = await get_json(
            client,
            f"https://api.openalex.org/works/https://doi.org/{clean_doi}",
            params=params or None,
        )
        canonical_doi = data.get("doi") or canonical_doi
        oa = data.get("open_access") or {}
        best = data.get("best_oa_location") or {}
        is_oa = oa.get("is_oa", False)
        oa_pdf_url = best.get("pdf_url")
        landing_url = best.get("landing_page_url")
        oa_meta = {
            "doi": canonical_doi,
            "title": data.get("display_name"),
            "year": data.get("publication_year"),
            "landing_page_url": landing_url,
            "source": "openalex",
        }
    except Exception:
        openalex_failed = True

    # If OpenAlex found a direct PDF, return immediately
    if oa_meta and oa_pdf_url:
        return {
            "doi": canonical_doi,
            "is_oa": True,
            "url_for_pdf": oa_pdf_url,
            "url_for_landing_page": landing_url,
            "source": "openalex",
            "status": "success",
        }

    # 2. Semantic Scholar fallback (if OpenAlex has no PDF or OpenAlex failed)
    s2_failed = False
    s2_pdf_url: str | None = None
    s2_landing_url: str | None = None

    headers = {}
    if os.getenv("SEMANTIC_SCHOLAR_API_KEY"):
        headers["x-api-key"] = os.environ["SEMANTIC_SCHOLAR_API_KEY"]
    try:
        data = await get_json(
            client,
            f"https://api.semanticscholar.org/graph/v1/paper/DOI:{clean_doi}",
            params={"fields": "openAccessPdf,url"},
            headers=headers,
        )
        oa_pdf = data.get("openAccessPdf") or {}
        s2_pdf_url = oa_pdf.get("url")
        s2_landing_url = data.get("url")
    except Exception:
        s2_failed = True

    # Case: Both providers failed (timeout / error)
    if openalex_failed and s2_failed:
        return {
            "doi": canonical_doi,
            "status": "lookup_failed",
            "is_oa": None,
            "url_for_pdf": None,
            "url_for_landing_page": None,
            "source": None,
            "error": "Both providers timed out or failed to respond.",
        }

    # Case: OpenAlex has metadata only, Semantic Scholar has the PDF
    final_pdf_url = oa_pdf_url or s2_pdf_url
    final_landing_url = landing_url or s2_landing_url
    final_is_oa = True if final_pdf_url else (is_oa if is_oa is not None else False)

    return {
        "doi": canonical_doi,
        "is_oa": final_is_oa,
        "url_for_pdf": final_pdf_url,
        "url_for_landing_page": final_landing_url,
        "source": "openalex" if oa_meta else "semantic_scholar",
        "status": "success",
    }


# Approved discovery providers: OpenAlex and Crossref are primary; Semantic Scholar is fallback-only
PRIMARY_SEARCH_PROVIDERS = {
    "openalex": openalex,
    "crossref": crossref,
}

FALLBACK_SEARCH_PROVIDERS = {
    "semantic_scholar": semantic_scholar,
}

# The callable registry of approved search providers (unapproved providers removed)
SEARCH_PROVIDERS = {
    **PRIMARY_SEARCH_PROVIDERS,
    **FALLBACK_SEARCH_PROVIDERS,
}


async def search_all(query, limit=5, providers=None):
    if providers is not None:
        unknown = set(providers) - set(SEARCH_PROVIDERS)
        if unknown:
            raise ValueError(f"Unknown providers: {sorted(unknown)}")
        selected = providers
        target_providers = {name: SEARCH_PROVIDERS[name] for name in selected}
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
            results = await asyncio.gather(
                *(target_providers[name](client, query, limit) for name in selected),
                return_exceptions=True,
            )
        papers, errors, seen = [], {}, set()
        for name, result in zip(selected, results):
            if isinstance(result, BaseException):
                errors[name] = (
                    f"Provider returned HTTP {result.response.status_code}"
                    if isinstance(result, httpx.HTTPStatusError)
                    else "Provider request failed; check configuration or retry."
                )
                continue
            for item in result:
                key = (item.get("doi") or item.get("title") or "").strip().lower()
                if key and key not in seen:
                    seen.add(key)
                    papers.append(item)
        return {
            "query": query,
            "papers": papers,
            "provider_errors": errors,
            "notice": "Search results are candidates, not verified evidence.",
        }

    # Default dispatch: Query primary providers first (OpenAlex, Crossref)
    primary_names = list(PRIMARY_SEARCH_PROVIDERS)
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        primary_results = await asyncio.gather(
            *(PRIMARY_SEARCH_PROVIDERS[name](client, query, limit) for name in primary_names),
            return_exceptions=True,
        )

    papers, errors, seen = [], {}, set()
    for name, result in zip(primary_names, primary_results):
        if isinstance(result, BaseException):
            errors[name] = (
                f"Provider returned HTTP {result.response.status_code}"
                if isinstance(result, httpx.HTTPStatusError)
                else "Provider request failed; check configuration or retry."
            )
            continue
        for item in result:
            key = (item.get("doi") or item.get("title") or "").strip().lower()
            if key and key not in seen:
                seen.add(key)
                papers.append(item)

    # When the primary lookup succeeds, Semantic Scholar receives zero calls
    if papers:
        return {
            "query": query,
            "papers": papers,
            "provider_errors": errors,
            "notice": "Search results are candidates, not verified evidence.",
        }

    # Fallback: only call Semantic Scholar if primary providers yielded no papers
    if "semantic_scholar" in SEARCH_PROVIDERS:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
            try:
                s2_papers = await SEARCH_PROVIDERS["semantic_scholar"](client, query, limit)
                for item in s2_papers:
                    key = (item.get("doi") or item.get("title") or "").strip().lower()
                    if key and key not in seen:
                        seen.add(key)
                        papers.append(item)
            except Exception as exc:
                errors["semantic_scholar"] = str(exc)

    return {
        "query": query,
        "papers": papers,
        "provider_errors": errors,
        "notice": "Search results are candidates, not verified evidence.",
    }
