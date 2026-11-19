import React, { useState, useEffect } from 'react';
import { 
  ShieldCheck, 
  LayoutDashboard, 
  FileText, 
  BookOpen, 
  History, 
  Download, 
  Upload, 
  Search, 
  Check, 
  AlertTriangle, 
  ExternalLink, 
  RotateCcw, 
  ChevronRight, 
  FlaskConical, 
  MessageSquare,
  Home
} from 'lucide-react';
import { Link, useRouter } from '../router';
import { statuses, sampleText, sampleClaims, extract, report, csv } from '../engine';
import { checkHealth, submitDocument, submitDocumentFile, getJobStatus, getJobReport } from '../api';
import { AcademicSimulationPage } from './AcademicSimulationPage';

function Badge({ status }) {
  return <span className={'badge ' + (status || 'unverified').toLowerCase().replaceAll(' ', '-')}>{status}</span>;
}

function downloadFile(name, content, type) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function Evidence({ row, review, onReview }) {
  const [note, setNote] = useState(review?.note || '');
  useEffect(() => {
    setNote(review?.note || '');
  }, [row.id, review]);

  return (
    <aside className="evidence panel">
      <div className="eyebrow">EVIDENCE INSPECTOR</div>
      <h2>Behind the claim</h2>
      <Badge status={row.status} />
      <blockquote>{row.claim}</blockquote>
      <div className="section-label">SOURCE EVIDENCE</div>
      <div className="excerpt">
        {row.evidence}
        <small>{row.section}</small>
      </div>
      <div className="section-label">WHY THIS VERDICT?</div>
      <p>{row.reason}</p>
      <div className="confidence">
        <ShieldCheck size={18} />
        <span>{row.confidence ? `${row.confidence} confidence` : 'Confidence unavailable'}</span>
      </div>
      <div className="section-label">MATCHED REFERENCE</div>
      {row.references && row.references.length ? (
        row.references.map((r) => (
          <p className="reference" key={r}>
            {r}
          </p>
        ))
      ) : (
        <p>No matching reference found.</p>
      )}
      {row.source && (
        <a className="source-link" href={row.source} target="_blank" rel="noreferrer">
          Inspect original publication <ExternalLink size={15} />
        </a>
      )}
      <div className="review">
        <label htmlFor="note">Reviewer note</label>
        <textarea
          id="note"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="What needs a closer look?"
          rows={3}
        />
        <div className="actions">
          <button type="button" onClick={() => onReview('Reviewed', note)}>
            <Check size={16} /> Mark reviewed
          </button>
          <button type="button" className="secondary" onClick={() => onReview('Needs follow-up', note)}>
            Flag
          </button>
        </div>
        {review && (
          <small>
            Review: {review.decision} · {new Date(review.at).toLocaleString()}
          </small>
        )}
      </div>
    </aside>
  );
}

export function WorkspacePage({ state, setState, backendOnline }) {
  const { path, navigate } = useRouter();

  // Determine active tab based on route path
  let activeTab = 'Overview';
  if (path.includes('/simulation')) {
    activeTab = 'Simulation';
  } else if (path.includes('/verify') || path.includes('/document')) {
    activeTab = 'Document';
  } else if (path.includes('/chat')) {
    activeTab = 'Paper chat';
  } else if (path.includes('/references')) {
    activeTab = 'References';
  } else if (path.includes('/history')) {
    activeTab = 'Review history';
  } else if (path.includes('/overview') || path === '/workspace') {
    activeTab = 'Overview';
  }

  const [thread, setThread] = useState([]);
  const [question, setQuestion] = useState('');
  const [selected, setSelected] = useState(null);
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('All verdicts');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState(null);

  // Resume active job on page refresh
  useEffect(() => {
    const activeJobId = localStorage.getItem('vericite_active_job_id');
    if (activeJobId && backendOnline && !busy) {
      pollJob(activeJobId, state.title || 'Resumed document');
    }
  }, [backendOnline]);

  const update = (patch) => setState((s) => ({ ...s, ...patch }));

  const visible = state.claims.filter(
    (r) =>
      (filter === 'All verdicts' || r.status === filter) &&
      (r.claim + ' ' + (r.references || []).join(' ')).toLowerCase().includes(query.toLowerCase())
  );
  const row = visible.find((r) => r.id === selected) || visible[0];
  const reviewed = Object.keys(state.reviews).length;

  const handleTabClick = (tabName) => {
    switch (tabName) {
      case 'Document':
        navigate('/workspace/verify');
        break;
      case 'Simulation':
        navigate('/workspace/simulation');
        break;
      case 'Overview':
        navigate('/workspace/overview');
        break;
      case 'Paper chat':
        navigate('/workspace/chat');
        break;
      case 'References':
        navigate('/workspace/references');
        break;
      case 'Review history':
        navigate('/workspace/history');
        break;
      default:
        navigate('/workspace/overview');
    }
  };

  const loadSample = () => {
    setThread([]);
    setQuestion('');
    setState({
      title: 'Active learning · literature review',
      analyzedTitle: 'Active learning · literature review',
      text: sampleText,
      claims: sampleClaims(),
      mode: 'Sample demo',
      reviews: {},
      history: []
    });
    setSelected(null);
    setQuery('');
    setFilter('All verdicts');
    setMessage('Sample restored. Verdicts and evidence are illustrative.');
  };

  const pollJob = async (job_id, docTitle) => {
    setBusy(true);
    setStage(null);
    setMessage('Verification started. Parsing document…');
    localStorage.setItem('vericite_active_job_id', job_id);

    const stageNames = {
      1: 'Parsing document…',
      2: 'Extracting claims & references…',
      3: 'Resolving references…',
      4: 'Retrieving source passages…',
      5: 'Verifying claims against evidence…'
    };

    const poll = async () => {
      try {
        const job = await getJobStatus(job_id);
        setStage(job.current_stage);
        if (job.current_stage) setMessage(stageNames[job.current_stage] || 'Processing…');

        if (job.job_state === 'completed') {
          localStorage.removeItem('vericite_active_job_id');
          const rpt = job.report || (await getJobReport(job_id));
          const verdictMap = {
            SUPPORTED: 'Supported',
            PARTLY_SUPPORTED: 'Partly supported',
            CONTRADICTORY: 'Contradictory',
            UNSUPPORTED: 'Unsupported'
          };
          const localExtracted = state.text ? extract(state.text) : [];
          const claimsList = rpt.claims && rpt.claims.length ? rpt.claims : localExtracted;
          const assessments = rpt.assessments || [];
          const links = rpt.links || [];
          const references = rpt.references || [];
          const passages = rpt.passages || [];
          const passageMap = new Map(passages.map((p) => [p.passage_id, p]));
          const refMap = new Map(references.map((r) => [r.ref_id, r]));
          const backendClaims = [];

          let assessedCount = 0;
          let abstainedCount = 0;
          let failedCount = 0;

          assessments.forEach((a) => {
            if (a.assessment_status === 'assessed') {
              assessedCount++;
            } else if (a.assessment_status === 'unable_to_assess') {
              abstainedCount++;
            } else if (a.assessment_status === 'failed') {
              failedCount++;
            }
          });

          claimsList.forEach((c, i) => {
            const claimText = c.normalized_text || c.original_span || c.claim || `Claim ${i + 1}`;
            const claimLinks = links.filter((l) => l.claim_id === c.claim_id);
            if (claimLinks.length > 0) {
              claimLinks.forEach((lk, linkIdx) => {
                const asm = lk.ref_id
                  ? assessments.find((a) => a.claim_id === c.claim_id && a.ref_id === lk.ref_id)
                  : null;
                const refObj = lk.ref_id ? refMap.get(lk.ref_id) : null;
                const markerStr = lk.citation_marker || (refObj && refObj.raw_marker) || '';
                const refDisplay = refObj
                  ? `${refObj.raw_marker ? `${refObj.raw_marker} ` : ''}${refObj.authors?.join(', ') || ''} (${refObj.year || ''}) ${refObj.title || ''}`.trim()
                  : markerStr
                  ? `Citation ${markerStr}`
                  : '';
                let verdict = 'Unverified';
                let confidence = null;
                let reason = asm
                  ? asm.explanation || 'Assessment completed.'
                  : lk.mapping_status === 'unmatched'
                  ? `Unmatched citation marker ${lk.citation_marker || ''}.`.trim()
                  : 'Candidate claim awaiting verification.';
                let evidence = 'No source passage available.';
                let section = 'Not available';
                let flags = asm
                  ? asm.issue_flags || []
                  : lk.mapping_status === 'unmatched'
                  ? ['unmatched_citation']
                  : [];

                if (asm) {
                  if (asm.semantic_verdict) {
                    verdict = verdictMap[asm.semantic_verdict] || 'Unverified';
                  } else if (asm.assessment_status === 'unable_to_assess') {
                    verdict = 'Unable to assess';
                  } else if (asm.assessment_status === 'failed') {
                    verdict = 'Failed';
                  }
                  if (asm.confidence_score != null) {
                    confidence = asm.confidence_score > 0.7 ? 'High' : asm.confidence_score > 0.4 ? 'Medium' : 'Low';
                  }
                  if (asm.evidence_passage_ids && asm.evidence_passage_ids.length > 0) {
                    const matched = asm.evidence_passage_ids.map((pid) => passageMap.get(pid)).filter(Boolean);
                    if (matched.length > 0) {
                      evidence = matched.map((p) => p.verbatim_text).join('\n\n');
                      section = matched
                        .map((p) => p.section || (p.page ? `Page ${p.page}` : 'Retrieved passage'))
                        .join(', ');
                    }
                  }
                }

                backendClaims.push({
                  id: `${c.claim_id || i + 1}_${lk.ref_id || linkIdx}`,
                  claimId: c.claim_id,
                  refId: lk.ref_id,
                  claim: claimText,
                  markers: markerStr ? [markerStr] : [],
                  references: refDisplay ? [refDisplay] : [],
                  status: verdict,
                  confidence,
                  evidence,
                  section,
                  reason,
                  flags,
                  source:
                    rpt.sources && lk.ref_id
                      ? rpt.sources.find((s) => s.ref_id === lk.ref_id)?.source_url || null
                      : null
                });
              });
            } else {
              backendClaims.push({
                id: c.claim_id || `claim-${i + 1}`,
                claimId: c.claim_id,
                claim: claimText,
                markers: [],
                references: [],
                status: 'Unverified',
                confidence: null,
                evidence: 'No source passage available.',
                section: 'Not available',
                reason: 'Candidate claim with no citation markers.',
                flags: ['missing_citation'],
                source: null
              });
            }
          });

          // Determine accurate verification mode label
          let modeLabel = 'Custom document · unverified';
          if (assessedCount > 0) {
            modeLabel = 'AI-verified document';
          } else if (abstainedCount > 0 || failedCount > 0) {
            modeLabel = 'Partially verified (inconclusive evidence)';
          }

          setThread([]);
          setQuestion('');
          update({
            claims: backendClaims.length ? backendClaims : localExtracted,
            analyzedTitle: docTitle || state.title,
            mode: modeLabel,
            summary: {
              totalPairs: assessments.length,
              assessedCount,
              abstainedCount,
              failedCount
            },
            stageErrors: rpt.stage_errors || [],
            assessmentMethod: rpt.sources?.some(s => s.coverage === 'full_text') ? 'Full-text retrieval & semantic verification' : 'Abstract retrieval & rule-based verification',
            reviews: {},
            history: []
          });
          setSelected(null);
          setFilter('All verdicts');
          setQuery('');
          handleTabClick('Overview');
          setStage(null);
          setBusy(false);
          setMessage(
            `Verification complete: ${assessedCount} assessed, ${abstainedCount} abstained, ${failedCount} failed.`
          );
          return;
        }

        if (job.job_state === 'failed') {
          localStorage.removeItem('vericite_active_job_id');
          setMessage('Verification failed: ' + (job.error_message || 'Unknown error.') + ' Falling back to local extraction.');
          const c = extract(state.text);
          update({
            claims: c,
            analyzedTitle: docTitle || state.title,
            mode: 'Custom document · unverified (backend failed)',
            reviews: {},
            history: []
          });
          setSelected(null);
          setFilter('All verdicts');
          setQuery('');
          handleTabClick('Overview');
          setStage(null);
          setBusy(false);
          return;
        }

        setTimeout(poll, 2000);
      } catch (err) {
        setMessage('Polling error: ' + err.message);
        setBusy(false);
      }
    };
    await poll();
  };

  const analyze = async () => {
    if (!state.text.trim()) {
      setMessage('Paste text or upload a document first.');
      return;
    }
    if (backendOnline) {
      setBusy(true);
      setStage(null);
      setMessage('Submitting document to verification backend…');
      try {
        const { job_id } = await submitDocument(state.text, state.title || 'document.txt');
        await pollJob(job_id, state.title || 'document.txt');
      } catch (e) {
        setMessage('Backend error: ' + e.message + '. Using local extraction.');
        const c = extract(state.text);
        if (!c.length) {
          setMessage('No candidate sentences found.');
          setBusy(false);
          return;
        }
        update({
          claims: c,
          analyzedTitle: state.title,
          mode: 'Custom document · unverified',
          reviews: {},
          history: []
        });
        setSelected(null);
        setFilter('All verdicts');
        setQuery('');
        handleTabClick('Overview');
        setBusy(false);
      }
    } else {
      const claims = extract(state.text);
      if (!claims.length) {
        setMessage('No candidate sentences found. Add a sentence longer than 12 characters.');
        return;
      }
      setThread([]);
      setQuestion('');
      update({
        claims,
        analyzedTitle: state.title,
        mode: 'Custom document · unverified',
        reviews: {},
        history: []
      });
      setSelected(null);
      setFilter('All verdicts');
      setQuery('');
      handleTabClick('Overview');
      setMessage(`Extracted ${claims.length} candidate claims. Connect the backend for AI-powered verification.`);
    }
  };

  const uploadFile = async (file) => {
    if (!file) return;
    if (!/\.(txt|md|pdf|docx)$/i.test(file.name)) {
      setMessage('Please choose a supported academic file (.txt, .md, .pdf, or .docx).');
      return;
    }
    if (file.size > 20 * 1024 * 1024) {
      setMessage('Choose a file smaller than 20 MB.');
      return;
    }
    setBusy(true);

    // If PDF or DOCX and backend is online, upload directly via multipart binary route
    if (/\.(pdf|docx)$/i.test(file.name)) {
      if (!backendOnline) {
        setMessage('Backend connection is required to parse binary PDF/DOCX documents.');
        setBusy(false);
        return;
      }
      try {
        setMessage(`Uploading ${file.name} to server for Docling parsing…`);
        const { job_id } = await submitDocumentFile(file);
        update({ title: file.name, text: `[Binary document ${file.name} uploaded for parsing]` });
        await pollJob(job_id, file.name);
      } catch (err) {
        setMessage('Binary upload failed: ' + err.message);
        setBusy(false);
      }
      return;
    }

    // TXT / Markdown file
    try {
      const content = await file.text();
      update({ text: content, title: file.name });
      setMessage('Document loaded. Select Extract claims to process it.');
    } catch {
      setMessage('Could not read this file. Try pasting its text.');
    } finally {
      setBusy(false);
    }
  };

  const handleReview = (decision, note) => {
    if (!row) return;
    const entry = { claimId: row.id, decision, note, at: new Date().toISOString() };
    setState((s) => ({
      ...s,
      reviews: { ...s.reviews, [row.id]: entry },
      history: [entry, ...s.history]
    }));
    setMessage('Review saved in this browser.');
  };

  const ask = (input) => {
    const q = input.trim();
    if (!q) return;
    const rows = state.claims;
    const number = q.match(/claim\s*#?\s*(\d+)/i);
    const previous = thread.at(-1)?.index;
    const terms = q.toLowerCase().match(/[a-z0-9]{3,}/g) || [];
    const matches = rows
      .map((r, index) => ({
        index,
        score: terms.filter(
          (t) => !['the', 'and', 'what', 'for', 'this', 'about', 'does', 'show', 'claim'].includes(t) &&
                 (r.claim + ' ' + (r.references || []).join(' ')).toLowerCase().includes(t)
        ).length
      }))
      .sort((a, b) => b.score - a.score);

    let index = number ? Number(number[1]) - 1 : matches[0]?.score ? matches[0].index : previous;
    let a;
    if (/summari|summary|overview/i.test(q)) {
      index = undefined;
      a =
        state.analyzedTitle +
        '\n' +
        rows.length +
        ' candidate claims. ' +
        rows.filter((r) => r.references && r.references.length).length +
        ' have mapped references.\n' +
        statuses
          .map((status) => [status, rows.filter((r) => r.status === status).length])
          .filter(([, n]) => n)
          .map(([status, n]) => status + ' · ' + n)
          .join('\n');
    } else if (!number && /issues|flagged|missing citations/i.test(q)) {
      index = undefined;
      a =
        rows
          .flatMap((r, i) => (r.flags && r.flags.length ? ['Claim ' + (i + 1) + ' — ' + r.flags.join(', ')] : []))
          .join('\n') || 'No citation issues are recorded.';
    } else if (rows[index]) {
      const r = rows[index];
      a =
        'Claim ' +
        (index + 1) +
        ' — ' +
        r.claim +
        '\n' +
        r.status +
        ' · ' +
        r.reason +
        '\n' +
        r.evidence +
        '\n' +
        ((r.references && r.references.join('\n')) || 'No mapped reference.');
    } else {
      a = 'Try a claim number from 1 to ' + rows.length + ', a phrase from the paper, or “Show citation issues”.';
    }
    setThread((t) => [...t, { q, a, index }]);
    setQuestion('');
  };

  const exportJson = () => {
    downloadFile('vericite-report.json', JSON.stringify(report(state), null, 2), 'application/json');
  };

  const sidebarLinks = [
    { id: 'Document', label: 'Verify a document', icon: FileText, route: '/workspace/verify' },
    { id: 'Simulation', label: 'Academic Simulation', icon: FlaskConical, route: '/workspace/simulation' },
    { id: 'Overview', label: 'Overview', icon: LayoutDashboard, route: '/workspace/overview', count: state.claims.length },
    { id: 'Paper chat', label: 'Paper chat', icon: MessageSquare, route: '/workspace/chat' },
    { id: 'References', label: 'References', icon: BookOpen, route: '/workspace/references' },
    { id: 'Review history', label: 'Review history', icon: History, route: '/workspace/history' }
  ];

  return (
    <div className="app">
      {/* Workspace Sidebar */}
      <nav className="sidebar" aria-label="Workspace Sidebar">
        <Link href="/" className="brand" title="veriCite Homepage">
          <span className="brand-icon">
            <ShieldCheck />
          </span>
          veri<span>Cite</span>
        </Link>

        <div className="workspace-label">RESEARCH WORKSPACE</div>

        <div className="sidebar-nav-list">
          {sidebarLinks.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                type="button"
                className={'nav-link ' + (isActive ? 'active' : '')}
                onClick={() => handleTabClick(item.id)}
              >
                <Icon size={19} />
                <span>{item.label}</span>
                {item.count !== undefined && <span className="nav-count">{item.count}</span>}
              </button>
            );
          })}
        </div>

        <div className="sidebar-home-link">
          <Link href="/" className="nav-link home-return-btn">
            <Home size={17} />
            <span>Back to Home</span>
          </Link>
        </div>

        <div className="sidebar-bottom">
          <BookOpen size={22} />
          <strong>Current paper</strong>
          <p>{state.analyzedTitle}</p>
        </div>

        <div className="profile">
          <span>R</span>
          <div>
            Research workspace
            <small>Local browser session</small>
          </div>
        </div>
      </nav>

      {/* Main Workspace Workspace Content Area */}
      <main>
        <header>
          <div className="breadcrumb">
            <Link href="/" className="breadcrumb-home">Home</Link>
            <ChevronRight size={15} />
            <span>Workspace</span>
            <ChevronRight size={15} />
            <strong>{activeTab}</strong>
          </div>
          <div className="header-actions-group">
            {activeTab !== 'Simulation' && (
              <button type="button" className="secondary" onClick={exportJson}>
                <Download size={16} /> Export report
              </button>
            )}
          </div>
        </header>

        <div className="content">
          {activeTab !== 'Simulation' && (
            <>
              <div className="heading">
                <h1>{activeTab === 'Document' ? 'Verify a research document' : activeTab === 'Overview' ? 'Verification results' : activeTab}</h1>
                <p>{activeTab === 'Document' ? 'Upload your paper to extract claims and trace their citations.' : state.analyzedTitle}</p>
              </div>

              <div className="notice">
                <FlaskConical size={19} />
                <span>
                  <strong>{state.mode}.</strong>{' '}
                  {backendOnline
                    ? 'Connected to AI verification backend.' + (stage ? ' Stage ' + stage + '/5: verifying…' : '')
                    : 'No live AI or source retrieval. Sample evidence is illustrative; custom claims remain unverified.'}
                </span>
                <button type="button" onClick={loadSample}>Load sample</button>
              </div>
            </>
          )}

          {message && (
            <div role="status" className="toast">
              {message}
              <button type="button" aria-label="Dismiss message" onClick={() => setMessage('')}>×</button>
            </div>
          )}

          {/* VIEW SWITCHING */}
          {activeTab === 'Simulation' ? (
            <AcademicSimulationPage
              currentClaims={state.claims}
              analyzedTitle={state.analyzedTitle}
            />
          ) : activeTab === 'Document' ? (
            <section className="panel document">
              <h2>Upload your paper</h2>
              <p>Paste academic text with a References section, or import a TXT, Markdown, PDF, or DOCX document (up to 20 MB).</p>

              <label
                className="upload"
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  if (!busy) uploadFile(e.dataTransfer.files[0]);
                }}
              >
                <Upload size={34} />
                <strong>{busy ? 'Processing document…' : 'Drop your document here (TXT, MD, PDF, DOCX)'}</strong>
                <input
                  type="file"
                  accept=".txt,.md,.pdf,.docx"
                  disabled={busy}
                  onChange={(e) => {
                    uploadFile(e.target.files[0]);
                    e.target.value = '';
                  }}
                />
              </label>

              <div className="workflow">
                {[
                  'Extract claims',
                  'Map citations',
                  'View verdicts',
                  'Inspect evidence',
                  'Find citation issues',
                  'Search and filter',
                  'Record review',
                  'Export report'
                ].map((label, i) => (
                  <span key={label}>
                    <b>{String(i + 1).padStart(2, '0')}</b>
                    {label}
                  </span>
                ))}
              </div>

              <label htmlFor="title">Document name</label>
              <input
                id="title"
                value={state.title}
                onChange={(e) => update({ title: e.target.value })}
              />

              <label htmlFor="document">Document text</label>
              <textarea
                id="document"
                rows={15}
                value={state.text}
                onChange={(e) => update({ text: e.target.value })}
              />

              <div className="actions">
                <button type="button" disabled={busy} onClick={analyze}>
                  Extract claims
                </button>
                <button type="button" className="secondary" onClick={loadSample}>
                  <RotateCcw size={16} /> Load sample
                </button>
              </div>
              <small>Local heuristics detect candidate sentences and [1] or (Author, Year) citations. This is not scientific claim verification.</small>
            </section>
          ) : activeTab === 'Paper chat' ? (
            <section className="panel conversation">
              <h2>Ask about this paper</h2>
              <p>Explore the current verification results by claim number, keyword, or citation.</p>
              <div className="actions">
                {['Summarize the paper', 'Show citation issues', 'Explain claim 1'].map((q) => (
                  <button type="button" className="secondary" key={q} onClick={() => ask(q)}>
                    {q}
                  </button>
                ))}
              </div>
              <div aria-live="polite">
                {thread.map(({ q, a }, i) => (
                  <article key={i}>
                    <strong>{q}</strong>
                    <p>{a}</p>
                  </article>
                ))}
              </div>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  ask(question);
                }}
              >
                <input
                  aria-label="Question about the current paper"
                  placeholder="Ask a follow-up question…"
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                />
                <button type="submit" disabled={!question.trim()}>
                  Send
                </button>
              </form>
            </section>
          ) : activeTab === 'References' ? (
            <section className="panel reference-list">
              <h2>Follow the source trail</h2>
              <p>References mapped to your extracted claims. Metadata has not been checked against a live service.</p>
              {[...new Set(state.claims.flatMap((r) => r.references || []))].map((ref, i) => (
                <article key={ref}>
                  <span className="ref-icon">
                    <BookOpen />
                  </span>
                  <div>
                    <h3>Reference {i + 1}</h3>
                    <p>{ref}</p>
                    <small>
                      Linked to {state.claims.filter((r) => r.references && r.references.includes(ref)).length} claims
                    </small>
                  </div>
                </article>
              ))}
              {!state.claims.some((r) => r.references && r.references.length) && (
                <p>No mapped references. Add a References heading and numbered entries to your document.</p>
              )}
              <h3>Citation issues</h3>
              {state.claims
                .filter((r) => r.flags && r.flags.length)
                .map((r) => (
                  <button
                    type="button"
                    className="issue"
                    key={r.id}
                    onClick={() => {
                      setSelected(r.id);
                      handleTabClick('Overview');
                    }}
                  >
                    <AlertTriangle size={18} />
                    <span>
                      {r.flags.join(' · ')}
                      <small>{r.claim}</small>
                    </span>
                  </button>
                ))}
            </section>
          ) : activeTab === 'Review history' ? (
            <section className="panel history">
              <h2>A transparent review trail</h2>
              <p>{state.history.length} decisions saved on this device.</p>
              {!state.history.length && (
                <div className="empty">
                  <History />
                  <h3>No reviews yet</h3>
                  <p>Open a claim in Overview, add a note, and mark it reviewed or flag it.</p>
                </div>
              )}
              {state.history.map((h, i) => (
                <article key={i}>
                  <span className="history-icon">
                    <Check size={18} />
                  </span>
                  <div>
                    <strong>{h.decision}</strong>
                    <p>{state.claims.find((r) => r.id === h.claimId)?.claim}</p>
                    {h.note && <blockquote>{h.note}</blockquote>}
                    <small>{new Date(h.at).toLocaleString()}</small>
                  </div>
                </article>
              ))}
            </section>
          ) : (
            /* Overview tab */
            <>
              <section className="stats">
                {[
                  [state.claims.length, 'Claims extracted', 'Ready for inspection'],
                  [
                    state.summary?.assessedCount != null
                      ? state.summary.assessedCount
                      : state.claims.filter((r) => r.status === 'Supported').length,
                    'Assessed pairs',
                    'Evidence matched'
                  ],
                  [
                    state.summary?.abstainedCount != null
                      ? state.summary.abstainedCount
                      : state.claims.filter((r) => r.status === 'Unable to assess').length,
                    'Abstained pairs',
                    'Inconclusive evidence'
                  ],
                  [
                    state.summary?.failedCount != null
                      ? state.summary.failedCount
                      : state.claims.filter((r) => r.status === 'Failed').length,
                    'Failed pairs',
                    'Provider or parse errors'
                  ]
                ].map(([n, l, h]) => (
                  <div key={l}>
                    <span>{l}</span>
                    <strong>{n}</strong>
                    <small>{h}</small>
                  </div>
                ))}
              </section>

              <div className="results-heading">
                <div>
                  <h2>Claim-by-claim review</h2>
                  <p>{state.analyzedTitle || state.title}</p>
                </div>
                <button type="button" className="secondary" onClick={() => handleTabClick('Document')}>
                  <Upload size={16} /> New document
                </button>
              </div>

              <div className="toolbar">
                <label className="search">
                  <Search size={18} />
                  <input
                    aria-label="Search claims and references"
                    placeholder="Search claims or references…"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                  />
                </label>
                <select
                  aria-label="Filter verdicts"
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                >
                  {['All verdicts', ...statuses].map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => downloadFile('vericite-claims.csv', csv(state.claims), 'text/csv')}
                >
                  Export CSV
                </button>
              </div>

              <div className="review-grid">
                <section className="claim-list" aria-label="Extracted claims">
                  {visible.map((r, i) => (
                    <button
                      key={r.id}
                      type="button"
                      onClick={() => setSelected(r.id)}
                      className={'claim-card ' + (row?.id === r.id ? 'selected' : '')}
                    >
                      <div className="card-top">
                        <span>
                          CLAIM {state.claims.indexOf(r) + 1 < 10 ? '0' : ''}
                          {state.claims.indexOf(r) + 1}
                        </span>
                        <Badge status={r.status} />
                      </div>
                      <h3>{r.claim}</h3>
                      <div className="card-bottom">
                        <span>
                          <BookOpen size={14} />
                          {(r.markers && r.markers.join(', ')) || 'No citation'}
                        </span>
                        <span>{state.reviews[r.id]?.decision || 'Awaiting review'}</span>
                      </div>
                      {r.flags && r.flags.length > 0 && (
                        <div className="flag">
                          <AlertTriangle size={13} />
                          {r.flags.join(' · ')}
                        </div>
                      )}
                    </button>
                  ))}

                  {!state.claims.length ? (
                    <div className="panel empty">
                      <FileText size={36} />
                      <h3>No manuscript loaded yet</h3>
                      <p>Upload or paste your academic text with citations to begin verification.</p>
                      <button
                        type="button"
                        className="btn btn-primary"
                        onClick={() => handleTabClick('Document')}
                      >
                        <Upload size={16} /> Verify a document
                      </button>
                    </div>
                  ) : !visible.length ? (
                    <div className="panel empty">
                      <Search />
                      <h3>No matching claims</h3>
                      <p>Try another search or verdict filter.</p>
                      <button
                        type="button"
                        onClick={() => {
                          setQuery('');
                          setFilter('All verdicts');
                        }}
                      >
                        Clear filters
                      </button>
                    </div>
                  ) : null}
                </section>

                {row && visible.length > 0 && (
                  <Evidence
                    key={row.id}
                    row={row}
                    review={state.reviews[row.id]}
                    onReview={handleReview}
                  />
                )}
              </div>
            </>
          )}

          <footer>
            <span>
              <ShieldCheck size={15} /> Evidence first. Human judgment always.
            </span>
            <span>veriCite · Transparent Citation Verification</span>
          </footer>
        </div>
      </main>
    </div>
  );
}
