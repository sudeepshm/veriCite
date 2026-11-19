import test from 'node:test';
import assert from 'node:assert/strict';
import {extract,sampleClaims,csv,report} from './engine.js';
import {calculateBenchmarkDifference} from './simulationCalculations.js';
test('maps numeric citations without including reference entries as claims',()=>{const r=extract('An intervention improves results [1].\n\nReferences\n[1] Smith 2020. Study.');assert.equal(r.length,1);assert.equal(r[0].references.length,1);assert.equal(r[0].status,'Unverified');assert.equal(r[0].confidence,null)});
test('flags missing and unmatched citations',()=>{assert.deepEqual(extract('This assertion has no citation.')[0].flags,['Missing citation']);assert.deepEqual(extract('A finding is supported [7].')[0].flags,['Unmatched reference'])});
test('maps author-year references',()=>{assert.equal(extract('The results improved (Smith, 2020).\nReferences\nSmith (2020). A study.')[0].references.length,1)});
test('does not invent DOI URLs or proof',()=>{const r=extract('This intervention is effective [1].\nReferences\n[1] A paper.')[0];assert.equal(r.source,null);assert.equal(r.status,'Unverified')});
test('sample covers all verdicts',()=>assert.equal(new Set(sampleClaims().map(r=>r.status)).size,6));
test('CSV escapes commas quotes and newlines',()=>assert.match(csv([{claim:'a,"b"\nc',status:'Unverified',references:[]}]),/"a,""b""\nc"/));
test('report preserves decisions and demo disclaimer',()=>{const x=report({title:'Test',claims:[],reviews:{},history:[],mode:'Sample demo'});assert.match(x.disclaimer,/Demo only/);assert.equal(x.document,'Test')});
test('report keeps analyzed document identity while another document is being edited',()=>{const r=report({title:'New draft',analyzedTitle:'Analyzed paper',claims:[],reviews:{},history:[]});assert.equal(r.document,'Analyzed paper')});
test('manuscript alone produces 3 unverified preview cards excluding title, subtitle and headings',()=>{const text=`Classification results across two trials
Synthetic manuscript for offline testing

Findings
Accuracy rose from 50% to 60% in the adult pilot [1].
The absolute accuracy gain was 20 percentage points in the adult pilot [1].
A second trial reported 90% accuracy [2].

References
[1] Rao, M. (2025). Classification accuracy in an adult pilot. Fixture Studies, 1, 1.
[2] Sen, J. (2025). Results from a second trial. Fixture Studies, 2, 1.`;const claims=extract(text);assert.equal(claims.length,3);assert.equal(claims[0].claim,'Accuracy rose from 50% to 60% in the adult pilot [1].');assert.equal(claims[0].status,'Unverified');assert.equal(claims[1].claim,'The absolute accuracy gain was 20 percentage points in the adult pilot [1].');assert.equal(claims[1].status,'Unverified');assert.equal(claims[2].claim,'A second trial reported 90% accuracy [2].');assert.equal(claims[2].status,'Unverified')});
test('manuscript.txt asserts 3 unique claims, 2 references, and 3 claim-reference pairs in report and UI',()=>{const text=`Classification results across two trials
Synthetic manuscript for offline testing

Findings
Accuracy rose from 50% to 60% in the adult pilot [1].
The absolute accuracy gain was 20 percentage points in the adult pilot [1].
A second trial reported 90% accuracy [2].

References
[1] Rao, M. (2025). Classification accuracy in an adult pilot. Fixture Studies, 1, 1.
[2] Sen, J. (2025). Results from a second trial. Fixture Studies, 2, 1.`;
const uiCards=extract(text);
assert.equal(uiCards.length,3,'UI preview must show 3 claim cards');
const uniqueClaimTexts=new Set(uiCards.map(c=>c.claim));
assert.equal(uniqueClaimTexts.size,3,'Must have 3 unique claims');
const allDistinctRefs=new Set(uiCards.flatMap(c=>c.references));
assert.equal(allDistinctRefs.size,2,'Must reference 2 distinct publications');
const claimRefPairs=uiCards.flatMap(c=>c.references.map(r=>({claim:c.claim,ref:r})));
assert.equal(claimRefPairs.length,3,'Must have exactly 3 claim-reference pairs');
const rpt=report({title:'manuscript.txt',claims:uiCards,reviews:{},history:[],mode:'AI-verified document'});
assert.equal(rpt.claims.length,3,'Final report must contain 3 claims');
});

test('calculateBenchmarkDifference: baseline 50% and observed 60% yields +10 pp and +20% rel change',()=>{
  const res = calculateBenchmarkDifference({ baseline: '50', observed: '60', unit: '%' });
  assert.ok(res);
  assert.equal(res.absoluteText, '+10 percentage points');
  assert.equal(res.relativeText, '+20% relative change');
  assert.equal(res.isIncrease, true);
});

test('calculateBenchmarkDifference: baseline 0 provides absolute difference and unavailable relative change',()=>{
  const res = calculateBenchmarkDifference({ baseline: '0', observed: '15', unit: 'ms' });
  assert.ok(res);
  assert.equal(res.absoluteText, '+15 ms');
  assert.match(res.relativeText, /Unavailable/);
});

test('calculateBenchmarkDifference: decreases retain negative sign',()=>{
  const res = calculateBenchmarkDifference({ baseline: '60', observed: '45', unit: 'percentage points' });
  assert.ok(res);
  assert.equal(res.absoluteText, '-15 percentage points');
  assert.equal(res.relativeText, '-25% relative change');
  assert.equal(res.isDecrease, true);
});

test('calculateBenchmarkDifference: missing or invalid values return null',()=>{
  assert.equal(calculateBenchmarkDifference({ baseline: '', observed: '50' }), null);
  assert.equal(calculateBenchmarkDifference({ baseline: 'abc', observed: '50' }), null);
  assert.equal(calculateBenchmarkDifference({ baseline: '50', observed: undefined }), null);
});
