import sqlite3, json

conn = sqlite3.connect('backend/verycite.db')
c = conn.cursor()
c.execute('SELECT data FROM jobs WHERE job_id = ?', ('job_801eae5e45654ebb',))
row = c.fetchone()
if not row:
    print('Job not found')
    exit()

d = json.loads(row[0])
rep = d.get('report') or {}

sources = {s['source_id']: s for s in rep.get('sources', [])}
refs = {r['ref_id']: r for r in rep.get('references', [])}
claims = {cl['claim_id']: cl for cl in rep.get('claims', [])}
passages = {p['passage_id']: p for p in rep.get('passages', [])}
assessments = rep.get('assessments', [])

print('=== PAPERS ACTUALLY RETRIEVED (FULL TEXT / ABSTRACT) ===')
for s in rep.get('sources', []):
    if s.get('coverage') in ('full_text', 'abstract_only'):
        ref = refs.get(s['ref_id'], {})
        print(f"Citation {ref.get('raw_marker', '?')}: {s.get('matched_title')}")
        print(f"  DOI: {s.get('canonical_doi')}")
        print(f"  Coverage: {s.get('coverage')}")
        print(f"  Source URL: {s.get('source_url')}")

print('\n=== CLAIM-REFERENCE PAIRS WITH ATTACHED EVIDENCE PASSAGES ===')
count = 0
for a in assessments:
    if a.get('evidence_passage_ids'):
        count += 1
        cl = claims.get(a['claim_id'], {})
        ref = refs.get(a['ref_id'], {})
        s = next((src for src in rep.get('sources', []) if src['ref_id'] == a['ref_id']), {})
        print('----------------------------------------------------')
        print(f"Claim: {cl.get('original_span')}")
        print(f"Cites Ref {ref.get('raw_marker')}: {s.get('matched_title')}")
        print(f"Status: {a.get('assessment_status')}")
        print(f"Explanation: {a.get('explanation')}")
        print(f"Evidence Passages retrieved from cited paper ({len(a.get('evidence_passage_ids'))} passages):")
        for pid in a.get('evidence_passage_ids'):
            p = passages.get(pid, {})
            print(f"  - [Page {p.get('page')}] {repr(p.get('verbatim_text'))}")

print(f'\nTotal pairs with evidence passages attached: {count}')
