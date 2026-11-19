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

async def unpaywall(client, doi):
    email = os.getenv("UNPAYWALL_EMAIL")
    if not email:
        raise ValueError("UNPAYWALL_EMAIL must be configured")
    data = await get_json(client, f"https://api.unpaywall.org/v2/{quote(doi, safe='')}",
                          {"email": email})
    best = data.get("best_oa_location") or {}
    return {"doi": data.get("doi"), "is_oa": data.get("is_oa"),
            "url_for_pdf": best.get("url_for_pdf"),
            "url_for_landing_page": best.get("url_for_landing_page")}

SEARCH_PROVIDERS = {
    "openalex": openalex, "semantic_scholar": semantic_scholar,
    "crossref": crossref, "pubmed": pubmed,
    "europe_pmc": europe_pmc, "arxiv": arxiv,
}

async def search_all(query, limit=5, providers=None):
    selected = providers or list(SEARCH_PROVIDERS)
    unknown = set(selected) - set(SEARCH_PROVIDERS)
    if unknown:
        raise ValueError(f"Unknown providers: {sorted(unknown)}")
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        results = await asyncio.gather(
            *(SEARCH_PROVIDERS[name](client, query, limit) for name in selected),
            return_exceptions=True)
    papers, errors, seen = [], {}, set()
    for name, result in zip(selected, results):
        if isinstance(result, BaseException):
            errors[name] = (f"Provider returned HTTP {result.response.status_code}"
                            if isinstance(result, httpx.HTTPStatusError)
                            else "Provider request failed; check configuration or retry.")
            continue
        for item in result:
            key = (item.get("doi") or item.get("title") or "").strip().lower()
            if key and key not in seen:
                seen.add(key)
                papers.append(item)
    return {"query": query, "papers": papers, "provider_errors": errors,
            "notice": "Search results are candidates, not verified evidence."}
