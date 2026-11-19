export const statuses = ['Supported','Partly supported','Unsupported','Contradictory','Possibly outdated','Unable to assess','Unverified'];
export const sampleText = `Active learning improves examination performance in undergraduate STEM courses [1].
Active learning raises every student's score by exactly 30% [1].
The study proves the same effects in primary-school children [1].
Students in traditional lectures fail less often than students in active learning [1].
The 2014 review represents all research available today [1].
Digital learning eliminates the need for teachers [9].

References
[1] Freeman et al. (2014). Active learning increases student performance in science, engineering, and mathematics. https://doi.org/10.1073/pnas.1319030111`;
export function extract(text) {
 const parts=text.split(/^\s*(?:references|bibliography)\s*:?[ \t]*$/im);
 const refs=(parts[1]||'').split('\n').map(x=>x.trim()).filter(Boolean);
 const hasCitations=/\[\d+\]|\(([A-Za-z][A-Za-z -]+),\s*(\d{4})\)/.test(parts[0]);
 const isHeading=s=>/^(?:#{1,6}\s+|(?:\d+\.?\s+)?(?:abstract|introduction|background|related work|methodology|methods|results|findings|discussion|conclusions?|references|bibliography)\s*:?$)/i.test(s.trim());
 const rawSentences=parts[0].split(/\n+|(?<=[.!?])\s+(?=[A-Z])/).map(x=>x.trim()).filter(x=>x.length>12);
 const sentences=rawSentences.filter(s=>{
  if(isHeading(s))return false;
  const markers=[...s.matchAll(/\[(\d+)\]|\(([A-Za-z][A-Za-z -]+),\s*(\d{4})\)/g)];
  if(hasCitations&&!markers.length)return false;
  return true;
 });
 return sentences.map((claim,i)=>{
 const markers=[...claim.matchAll(/\[(\d+)\]|\(([A-Za-z][A-Za-z -]+),\s*(\d{4})\)/g)].map(m=>m[1]?`[${m[1]}]`:`(${m[2]}, ${m[3]})`);
 const references=markers.map(m=>refs.find(r=>m.startsWith('[')?r.startsWith(m):r.toLowerCase().includes(m.slice(1).split(',')[0].toLowerCase())&&r.includes(m.match(/\d{4}/)[0]))).filter(Boolean);
 return {id:`claim-${i+1}`,claim,markers,references,status:'Unverified',confidence:null,evidence:'No original source passage retrieved. Connect the research services to verify this claim.',section:'Not available',reason:'This is a locally extracted candidate claim, not an AI verification result.',flags:!markers.length?['Missing citation']:references.length<markers.length?['Unmatched reference']:[],source:references.flatMap(r=>r.match(/https:\/\/doi\.org\/[^\s]+/g)||[])[0]||null};
 });
}
export function sampleClaims(){
 const rows=extract(sampleText);
 const verdicts=['Supported','Partly supported','Unsupported','Contradictory','Possibly outdated','Unverified'];
 const reasons=['The direction of the claim matches the sample evidence.','The specific 30% figure and universal claim are not established.','The reviewed population was undergraduate STEM students; primary-school outcomes are outside its scope.','The claimed direction of failure risk is reversed.','A review published in 2014 cannot establish coverage of later research. Age alone does not invalidate its findings.','Reference [9] is absent. No source can be compared.'];
 const evidence=['The review describes higher examination performance under active learning.','The review describes average effects, not an exact 30% improvement for every student.','The review concerns undergraduate science, technology, engineering, and mathematics education.','The review describes higher failure rates under traditional lecturing.','The publication dates to 2014; this demo has not searched for more recent evidence.','No evidence available.'];
 return rows.map((r,i)=>({...r,status:verdicts[i],confidence:i===5?null:['High','High','Medium','High','Low'][i],reason:reasons[i],evidence:evidence[i],section:i===5?'Not available':'Illustrative paraphrase · not a retrieved quotation',flags:i===1?['Numeric overstatement']:i===2?['Population mismatch']:i===3?['Reversed conclusion']:i===4?['Freshness review']:r.flags}));
}
export function report(state) {
  return {
    product: 'veriCite',
    generatedAt: new Date().toISOString(),
    mode: state.mode,
    disclaimer: 'Demo only. Sample evidence is illustrative; custom inputs are unverified. Human review is required.',
    document: state.analyzedTitle || state.title,
    claims: state.claims,
    reviews: state.reviews,
    history: state.history,
    summary: state.summary || null,
    stageErrors: state.stageErrors || [],
    assessmentMethod: state.assessmentMethod || (state.mode?.includes('AI-verified') ? 'Automated verification pipeline' : 'Local extraction fallback')
  };
}
export function csv(rows){const cell=v=>'"'+String(v??'').replaceAll('"','""')+'"';return [['Claim','Verdict','Confidence','References','Evidence','Explanation'],...rows.map(r=>[r.claim,r.status,r.confidence,r.references.join('; '),r.evidence,r.reason])].map(r=>r.map(cell).join(',')).join('\r\n');}
