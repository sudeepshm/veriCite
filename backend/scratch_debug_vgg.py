import asyncio, httpx
from app.resolution import _candidate_score, _parse_crossref_work
from app.models import Reference
from app.extraction import _extract_authors, _extract_title, _extract_year

entry = '[40] K. Simonyan and A. Zisserman. Very deep convolutional networks\nfor large-scale image recognition. In ICLR, 2015.'
year = _extract_year(entry)
authors = _extract_authors(entry, year)
title = _extract_title(entry, authors, year)
ref = Reference(ref_id='r0', document_id='d0', raw_entry=entry, title=title, authors=authors, year=year)

print('ref.title:', title)
print('ref.authors:', authors)
print('ref.year:', year)

async def test():
    headers = {'User-Agent': 'veriCite/1.0 (mailto:user@verycite.app)'}
    async with httpx.AsyncClient(headers=headers, timeout=20.0) as client:
        query = str(title) + ' ' + str(year)
        resp = await client.get('https://api.crossref.org/works', params={'query.bibliographic': query, 'rows': 5})
        items = resp.json().get('message', {}).get('items', [])
        for item in items:
            ct, ca, cy, doi, _, _ = _parse_crossref_work(item)
            score = _candidate_score(ref, ct, ca, cy)
            print(f'  score={score:.3f} doi={doi}')
            print(f'    title={ct}')

asyncio.run(test())
