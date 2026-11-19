import asyncio, httpx, sqlite3, json
from app.extraction import _extract_authors, _extract_title, _extract_year
from app.resolution import _crossref_bib_search
from app.models import Reference
from collections import Counter

conn = sqlite3.connect('verycite.db')
c = conn.cursor()
c.execute('SELECT data FROM jobs WHERE job_id = ?', ('job_1d07bda17e43437b',))
d = json.loads(c.fetchone()[0])
raw_refs = d.get('report', {}).get('references', [])

async def test():
    headers = {'User-Agent': 'veriCite/1.0 (mailto:user@verycite.app)'}
    statuses = Counter()
    async with httpx.AsyncClient(headers=headers, timeout=25.0) as client:
        for i, r in enumerate(raw_refs[:49]):
            raw = r.get('raw_entry', '')
            year = _extract_year(raw)
            authors = _extract_authors(raw, year)
            title = _extract_title(raw, authors, year)
            ref = Reference(ref_id=f'r{i}', document_id='d', raw_entry=raw, title=title, authors=authors, year=year)
            status, t, a, y, doi, url, _ = await _crossref_bib_search(ref, client)
            statuses[str(status)] += 1
            marker = r.get('raw_marker', '?')
            if 'matched' in str(status):
                print(f'[{i+1}] MATCHED {marker} doi={doi}')
            elif 'lookup' in str(status):
                print(f'[{i+1}] FAILED {marker} title={title}')
            elif 'unresolved' in str(status):
                print(f'[{i+1}] UNRESOLVED {marker} title={title}')
            await asyncio.sleep(0.35)
    print('\n=== SUMMARY ===')
    for k, v in sorted(statuses.items()):
        print(f'{k}: {v}')

asyncio.run(test())
