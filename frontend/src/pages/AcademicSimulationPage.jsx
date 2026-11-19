import React, { useState, useEffect, useMemo, useRef } from 'react';
import { 
  FlaskConical, 
  Search, 
  Plus, 
  Trash2, 
  RotateCcw, 
  ExternalLink, 
  Check, 
  AlertCircle, 
  TrendingUp, 
  BookOpen, 
  FileText, 
  Sparkles,
  Layers,
  ArrowRight,
  Info
} from 'lucide-react';
import { calculateBenchmarkDifference } from '../simulationCalculations';
import { searchEvidence, submitDocument } from '../api';
import { useRouter } from '../router';

const DRAFT_STORAGE_KEY = 'vericite-simulation-v1';

const ENVIRONMENTS = [
  {
    id: 'simulation',
    label: 'Simulation',
    tagline: 'Computational or modeled conditions',
    desc: 'Synthetic datasets, numerical modeling, algorithmic benchmarks, or simulated physics environments.'
  },
  {
    id: 'laboratory',
    label: 'Laboratory',
    tagline: 'Controlled experimental conditions',
    desc: 'In vitro, bench-top, controlled hardware testbeds, or calibrated participant laboratory settings.'
  },
  {
    id: 'field',
    label: 'Field deployment',
    tagline: 'Real-world operating conditions',
    desc: 'In-the-wild longitudinal trials, production server traffic, clinical cohorts, or operational deployment.'
  }
];

const SAMPLE_SIMULATION = {
  claim: 'Active learning raises examination performance by 10 percentage points over traditional lectures in undergraduate STEM courses [1].',
  environment: 'laboratory',
  conditions: 'Undergraduate science & engineering classroom cohort (n=120) with active engagement interventions.',
  comparatorName: 'Traditional lecturing',
  metric: 'Examination score',
  baselineValue: '50',
  observedValue: '60',
  unit: '%',
  attachedCitations: [
    {
      id: 'demo_s2_01',
      title: 'Active learning increases student performance in science, engineering, and mathematics',
      authors: ['Freeman, S.', 'Eddy, S. L.', 'McDonough, M.'],
      year: 2014,
      provider: 'OpenAlex',
      doi: '10.1073/pnas.1319030111',
      url: 'https://doi.org/10.1073/pnas.1319030111'
    }
  ]
};

export function AcademicSimulationPage({ currentClaims = [], analyzedTitle = '' }) {
  // Restore draft from localStorage or empty template
  const [draft, setDraft] = useState(() => {
    try {
      const saved = localStorage.getItem(DRAFT_STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed && typeof parsed === 'object') {
          return {
            claim: parsed.claim || '',
            environment: parsed.environment || 'simulation',
            conditions: parsed.conditions || '',
            comparatorName: parsed.comparatorName || '',
            metric: parsed.metric || '',
            baselineValue: parsed.baselineValue || '',
            observedValue: parsed.observedValue || '',
            unit: parsed.unit || '',
            attachedCitations: Array.isArray(parsed.attachedCitations) ? parsed.attachedCitations : []
          };
        }
      }
    } catch {
      // ignore
    }
    return SAMPLE_SIMULATION;
  });

  // Modal / selector for choosing from current manuscript
  const [showClaimPicker, setShowClaimPicker] = useState(false);

  // Search state
  const [searchQuery, setSearchQuery] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState(null);
  const [providerErrors, setProviderErrors] = useState({});
  const [searchResults, setSearchResults] = useState([]);
  const [hasSearched, setHasSearched] = useState(false);
  const [saveToast, setSaveToast] = useState(false);
  const [calcFlash, setCalcFlash] = useState(false);
  const [isVerifyingPair, setIsVerifyingPair] = useState(false);
  const [verifyPairStatus, setVerifyPairStatus] = useState(null);
  const { search, navigate } = useRouter();

  // Scroll to Step 4 if ?step=4 in URL
  useEffect(() => {
    if (search && (search.includes('step=4') || search.includes('find-citations'))) {
      const el = document.getElementById('step4-heading');
      if (el) {
        setTimeout(() => {
          el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 100);
      }
    }
  }, [search]);

  // Brief highlight on changed calculation value
  useEffect(() => {
    setCalcFlash(true);
    const timer = setTimeout(() => setCalcFlash(false), 900);
    return () => clearTimeout(timer);
  }, [draft.baselineValue, draft.observedValue, draft.unit]);

  // Auto-save draft to localStorage whenever it changes
  useEffect(() => {
    try {
      localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(draft));
      setSaveToast(true);
      const timer = setTimeout(() => setSaveToast(false), 2000);
      return () => clearTimeout(timer);
    } catch {
      // storage unavailable
    }
  }, [draft]);

  // Derive initial search query suggestions based on claim, metric, comparator
  useEffect(() => {
    if (!searchQuery) {
      const parts = [draft.comparatorName, draft.metric].filter(Boolean);
      if (parts.length > 0) {
        setSearchQuery(parts.join(' '));
      } else if (draft.claim) {
        // take first few words of claim
        const terms = draft.claim.replace(/\[\d+\]/g, '').split(/\s+/).slice(0, 5).join(' ');
        setSearchQuery(terms);
      }
    }
  }, [draft.comparatorName, draft.metric, draft.claim]);

  // Benchmark difference calculation
  const benchmarkCalc = useMemo(() => {
    return calculateBenchmarkDifference({
      baseline: draft.baselineValue,
      observed: draft.observedValue,
      unit: draft.unit
    });
  }, [draft.baselineValue, draft.observedValue, draft.unit]);

  const updateDraft = (patch) => {
    setDraft((prev) => ({ ...prev, ...patch }));
  };

  const handleLoadExample = () => {
    setDraft(SAMPLE_SIMULATION);
    setSearchQuery('active learning stem undergraduate performance');
    setSearchResults([]);
    setHasSearched(false);
    setSearchError(null);
  };

  const handleResetDraft = () => {
    if (window.confirm('Reset all fields in this Academic Simulation draft?')) {
      const empty = {
        claim: '',
        environment: 'simulation',
        conditions: '',
        comparatorName: '',
        metric: '',
        baselineValue: '',
        observedValue: '',
        unit: '',
        attachedCitations: []
      };
      setDraft(empty);
      setSearchQuery('');
      setSearchResults([]);
      setHasSearched(false);
      setSearchError(null);
      localStorage.removeItem(DRAFT_STORAGE_KEY);
    }
  };

  const handleImportClaim = (claimObj) => {
    const text = claimObj.claim || claimObj.original_span || '';
    updateDraft({ claim: text });
    setShowClaimPicker(false);
  };

  // Execute Citation Search
  const handleFindCitations = async () => {
    const q = searchQuery.trim();
    if (!q) return;

    setIsSearching(true);
    setSearchError(null);
    setProviderErrors({});
    setHasSearched(true);

    try {
      // Omit explicit providers so backend fallback policy (OpenAlex/Crossref primary -> Semantic Scholar fallback) is respected
      const res = await searchEvidence(q, 6);
      const papers = res.papers || res.results || [];
      const normalizedPapers = papers.map((p) => ({
        ...p,
        provider: p.source || p.provider || 'unknown',
      }));
      setSearchResults(normalizedPapers);
      if (res.provider_errors && Object.keys(res.provider_errors).length > 0) {
        setProviderErrors(res.provider_errors);
      }
    } catch (err) {
      setSearchError(err.message || 'Unable to contact evidence search endpoint. Check backend connection.');
      setSearchResults([]);
    } finally {
      setIsSearching(false);
    }
  };

  // Attach citation to summary
  const handleAttachCitation = (citation) => {
    const key = citation.doi || citation.title || citation.url;
    const exists = draft.attachedCitations.some(
      (c) => (c.doi && c.doi === citation.doi) || (c.title && c.title.toLowerCase() === citation.title.toLowerCase())
    );
    if (!exists) {
      updateDraft({
        attachedCitations: [...draft.attachedCitations, citation]
      });
    }
  };

  // Remove citation from summary
  const handleRemoveCitation = (indexToRemove) => {
    updateDraft({
      attachedCitations: draft.attachedCitations.filter((_, idx) => idx !== indexToRemove)
    });
  };

  // Explicit action: verify attached simulation claim against attached candidate citation
  const handleVerifyAttachedPair = async (citation) => {
    const claimText = draft.claim.trim();
    if (!claimText) {
      setVerifyPairStatus({ error: 'Please enter a research claim to verify.' });
      return;
    }
    const citRef = citation.doi
      ? `[1] ${citation.title}. https://doi.org/${citation.doi}`
      : `[1] ${citation.title}. (${citation.year || '2024'}).`;

    const syntheticDoc = `${claimText} [1].\n\nReferences\n${citRef}`;

    setIsVerifyingPair(true);
    setVerifyPairStatus({ info: `Submitting claim against "${citation.title}" for verification…` });

    try {
      const res = await submitDocument(syntheticDoc, `simulation_${citation.doi ? citation.doi.replace(/[^a-zA-Z0-9]/g, '_') : 'citation'}.txt`);
      if (res && res.job_id) {
        localStorage.setItem('vericite_active_job_id', res.job_id);
        setVerifyPairStatus({ success: `Job queued (${res.job_id}). Transitioning to workspace overview…` });
        setTimeout(() => {
          navigate('/workspace/overview');
        }, 800);
      }
    } catch (err) {
      setVerifyPairStatus({ error: `Verification request failed: ${err.message}` });
    } finally {
      setIsVerifyingPair(false);
    }
  };

  return (
    <div className="simulation-page" aria-labelledby="simulation-main-heading">
      {/* Top Banner */}
      <div className="sim-header-banner">
        <div>
          <div className="sim-tag">
            <FlaskConical size={16} />
            <span>RESEARCH PLANNING & COMPARISON WORKSPACE</span>
          </div>
          <h1 id="simulation-main-heading">Academic Simulation</h1>
          <p className="sim-header-desc">
            Capture a hypothesis or claim, record the conditions under which it was evaluated, benchmark observed metrics against existing baselines, and ground findings with candidate citations.
          </p>
        </div>

        <div className="sim-header-actions">
          <button type="button" className="btn btn-secondary" onClick={handleLoadExample}>
            <Sparkles size={15} />
            Load example
          </button>
          <button type="button" className="btn btn-secondary reset-btn" onClick={handleResetDraft}>
            <RotateCcw size={15} />
            Reset draft
          </button>
        </div>
      </div>

      <div className="sim-notice-bar">
        <Info size={16} />
        <span>
          <strong>Research Planning Workspace:</strong> Selecting “Simulation”, “Laboratory”, or “Field deployment” records experimental methodology. It does not run a physical or biological experiment. Calculations are researcher-entered benchmarks, not verification verdicts.
        </span>
      </div>

      {/* Main Two-Column Layout */}
      <div className="simulation-layout-grid">
        {/* Left Column: 4-Step Interactive Form */}
        <div className="simulation-form-column">
          {/* STEP 1: Research Claim */}
          <section className="sim-step-card" aria-labelledby="step1-heading">
            <div className="step-card-header">
              <span className="step-badge">Step 1</span>
              <div>
                <h2 id="step1-heading">Capture the research claim</h2>
                <p className="step-desc">Enter the specific hypothesis, claim, or finding under investigation.</p>
              </div>
            </div>

            <div className="step-body">
              <div className="field-group">
                <div className="field-top-row">
                  <label htmlFor="sim-claim">Research claim</label>
                  {currentClaims.length > 0 && (
                    <button
                      type="button"
                      className="text-btn"
                      onClick={() => setShowClaimPicker(!showClaimPicker)}
                    >
                      <FileText size={14} />
                      Choose from current manuscript ({currentClaims.length})
                    </button>
                  )}
                </div>

                {showClaimPicker && (
                  <div className="claim-import-drawer" role="dialog" aria-label="Import manuscript claim">
                    <div className="import-header">
                      <strong>Claims extracted from current manuscript:</strong>
                      <button type="button" className="close-btn" onClick={() => setShowClaimPicker(false)}>×</button>
                    </div>
                    <div className="import-list">
                      {currentClaims.map((c, i) => (
                        <button
                          key={c.id || i}
                          type="button"
                          className="import-claim-item"
                          onClick={() => handleImportClaim(c)}
                        >
                          <span className="claim-idx">Claim {i + 1}</span>
                          <span className="claim-body">{c.claim}</span>
                          {c.markers?.length > 0 && (
                            <span className="claim-marker-pill">{c.markers.join(', ')}</span>
                          )}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                <textarea
                  id="sim-claim"
                  rows={3}
                  value={draft.claim}
                  onChange={(e) => updateDraft({ claim: e.target.value })}
                  placeholder="e.g. Active learning improves exam scores by 10 percentage points over traditional lecturing in undergraduate courses [1]."
                />
              </div>
            </div>
          </section>

          {/* STEP 2: Validation Environment */}
          <section className="sim-step-card" aria-labelledby="step2-heading">
            <div className="step-card-header">
              <span className="step-badge">Step 2</span>
              <div>
                <h2 id="step2-heading">Validation environment</h2>
                <p className="step-desc">Record the operational scope and validation conditions.</p>
              </div>
            </div>

            <div className="step-body">
              <fieldset className="env-fieldset">
                <legend className="sr-only">Choose a validation environment</legend>
                <div className="env-options-grid">
                  {ENVIRONMENTS.map((env) => {
                    const isSelected = draft.environment === env.id;
                    return (
                      <label 
                        key={env.id} 
                        className={`env-card-option ${isSelected ? 'selected' : ''}`}
                      >
                        <input
                          type="radio"
                          name="validation-environment"
                          value={env.id}
                          checked={isSelected}
                          onChange={(e) => updateDraft({ environment: e.target.value })}
                          className="sr-only"
                        />
                        <div className="env-card-top">
                          <span className={`radio-dot ${isSelected ? 'active' : ''}`} />
                          <strong>{env.label}</strong>
                        </div>
                        <span className="env-tagline">{env.tagline}</span>
                        <p className="env-desc">{env.desc}</p>
                      </label>
                    );
                  })}
                </div>
              </fieldset>

              <div className="field-group mt-16">
                <label htmlFor="sim-conditions">Conditions & Setup (optional)</label>
                <input
                  id="sim-conditions"
                  type="text"
                  value={draft.conditions}
                  onChange={(e) => updateDraft({ conditions: e.target.value })}
                  placeholder="e.g. Hardware accelerator, participant sample size (n=120), dataset, or deployment environment."
                />
              </div>
            </div>
          </section>

          {/* STEP 3: Comparator or Benchmark */}
          <section className="sim-step-card" aria-labelledby="step3-heading">
            <div className="step-card-header">
              <span className="step-badge">Step 3</span>
              <div>
                <h2 id="step3-heading">Comparator or benchmark</h2>
                <p className="step-desc">Specify the baseline and quantify the observed difference.</p>
              </div>
            </div>

            <div className="step-body">
              <div className="form-row-2">
                <div className="field-group">
                  <label htmlFor="sim-comparator">Comparator / Benchmark name</label>
                  <input
                    id="sim-comparator"
                    type="text"
                    value={draft.comparatorName}
                    onChange={(e) => updateDraft({ comparatorName: e.target.value })}
                    placeholder="e.g. Traditional lectures, ResNet-50 baseline"
                  />
                </div>

                <div className="field-group">
                  <label htmlFor="sim-metric">Metric</label>
                  <input
                    id="sim-metric"
                    type="text"
                    value={draft.metric}
                    onChange={(e) => updateDraft({ metric: e.target.value })}
                    placeholder="e.g. Examination score, Accuracy, Latency"
                  />
                </div>
              </div>

              <div className="form-row-3 mt-12">
                <div className="field-group">
                  <label htmlFor="sim-baseline">Baseline value</label>
                  <input
                    id="sim-baseline"
                    type="number"
                    step="any"
                    value={draft.baselineValue}
                    onChange={(e) => updateDraft({ baselineValue: e.target.value })}
                    placeholder="e.g. 50"
                  />
                </div>

                <div className="field-group">
                  <label htmlFor="sim-observed">Observed value</label>
                  <input
                    id="sim-observed"
                    type="number"
                    step="any"
                    value={draft.observedValue}
                    onChange={(e) => updateDraft({ observedValue: e.target.value })}
                    placeholder="e.g. 60"
                  />
                </div>

                <div className="field-group">
                  <label htmlFor="sim-unit">Unit</label>
                  <input
                    id="sim-unit"
                    type="text"
                    value={draft.unit}
                    onChange={(e) => updateDraft({ unit: e.target.value })}
                    placeholder="e.g. %, percentage points, ms"
                  />
                </div>
              </div>

              {/* Live Calculation Display */}
              <div className="benchmark-calculation-box">
                <div className="calc-title-row">
                  <span className="calc-eyebrow">RESEARCHER-ENTERED BENCHMARK CALCULATION</span>
                  <span className="non-verdict-tag">Not a verification verdict</span>
                </div>

                {benchmarkCalc ? (
                  <div className="calc-results-row">
                    <div className="calc-result-item">
                      <small>Absolute Difference</small>
                      <strong className={`calc-val ${benchmarkCalc.isIncrease ? 'text-increase' : benchmarkCalc.isDecrease ? 'text-decrease' : ''} ${calcFlash ? 'calc-value-updated' : ''}`}>
                        {benchmarkCalc.absoluteText}
                      </strong>
                    </div>

                    <div className="calc-result-item">
                      <small>Relative Change</small>
                      <strong className={`calc-val ${benchmarkCalc.isIncrease ? 'text-increase' : benchmarkCalc.isDecrease ? 'text-decrease' : ''} ${calcFlash ? 'calc-value-updated' : ''}`}>
                        {benchmarkCalc.relativeText}
                      </strong>
                    </div>

                    <div className="calc-result-summary">
                      <span>Baseline: <strong>{draft.baselineValue} {draft.unit}</strong></span>
                      <ArrowRight size={14} className="calc-arrow" />
                      <span>Observed: <strong>{draft.observedValue} {draft.unit}</strong></span>
                    </div>
                  </div>
                ) : (
                  <p className="calc-empty-hint">
                    Enter valid numeric baseline and observed values above to compute absolute difference and relative change.
                  </p>
                )}
              </div>
            </div>
          </section>

          {/* STEP 4: Find Citations */}
          <section className="sim-step-card" aria-labelledby="step4-heading">
            <div className="step-card-header">
              <span className="step-badge">Step 4</span>
              <div>
                <h2 id="step4-heading">Find citations</h2>
                <p className="step-desc">Query approved academic registries to discover literature baselines.</p>
              </div>
            </div>

            <div className="step-body">
              <div className="search-bar-row">
                <div className="search-input-wrap">
                  <Search size={17} className="search-icon" />
                  <input
                    type="text"
                    aria-label="Search query for literature baselines"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search literature (e.g. active learning undergraduate stem performance)"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        handleFindCitations();
                      }
                    }}
                  />
                </div>
                <button
                  type="button"
                  className="btn btn-primary search-action-btn"
                  onClick={handleFindCitations}
                  disabled={isSearching || !searchQuery.trim()}
                >
                  {isSearching ? 'Searching…' : 'Find citations'}
                </button>
              </div>

              <div className="approved-providers-note">
                <span>Registry queried: <strong>Crossref</strong> (Crossref-only mode).</span>
              </div>

              {/* Search States */}
              {isSearching && (
                <div className="search-status-box loading">
                  <span className="spinner" />
                  <span>Querying open academic registries…</span>
                </div>
              )}

              {searchError && (
                <div className="search-status-box error" role="alert">
                  <AlertCircle size={18} />
                  <div>
                    <strong>Search failed</strong>
                    <p>{searchError}</p>
                  </div>
                  <button type="button" className="btn btn-secondary retry-btn" onClick={handleFindCitations}>
                    Retry
                  </button>
                </div>
              )}

              {/* Partial provider failure banner when some results still retrieved */}
              {!isSearching && Object.keys(providerErrors).length > 0 && (
                <div className="search-status-box warning partial-provider-warning" role="status">
                  <AlertCircle size={16} />
                  <div>
                    <strong>Notice: Some registries encountered errors</strong>
                    <ul className="provider-error-list">
                      {Object.entries(providerErrors).map(([prov, err]) => (
                        <li key={prov}><strong>{prov}</strong>: {err}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}

              {!isSearching && hasSearched && searchResults.length === 0 && !searchError && (
                <div className="search-status-box empty">
                  <BookOpen size={20} />
                  {Object.keys(providerErrors).length > 0 ? (
                    <p>Crossref returned an error or no matches for “{searchQuery}”.</p>
                  ) : (
                    <p>No matching candidate citations found in Crossref for “{searchQuery}”. Try refining your query terms.</p>
                  )}
                </div>
              )}

              {/* Search Results List */}
              {searchResults.length > 0 && (
                <div className="search-results-list" aria-label="Literature search results">
                  <div className="results-header">
                    <span>Found {searchResults.length} candidate citations:</span>
                    <small>Search relevance does not establish source support.</small>
                  </div>

                  {searchResults.map((pub, idx) => {
                    const isAttached = draft.attachedCitations.some(
                      (c) => (c.doi && c.doi === pub.doi) || (c.title && c.title.toLowerCase() === pub.title.toLowerCase())
                    );

                    return (
                      <article key={pub.doi || idx} className="pub-result-card">
                        <div className="pub-card-main">
                          <h3 className="pub-title">{pub.title}</h3>
                          <div className="pub-meta">
                            {pub.authors && pub.authors.length > 0 && (
                              <span className="pub-authors">
                                {Array.isArray(pub.authors) ? pub.authors.slice(0, 3).join(', ') : pub.authors}
                                {Array.isArray(pub.authors) && pub.authors.length > 3 ? ' et al.' : ''}
                              </span>
                            )}
                            {pub.year && <span className="pub-year">({pub.year})</span>}
                            {pub.provider && (
                              <span className="provider-tag">{pub.provider}</span>
                            )}
                            {pub.doi && (
                              <a
                                href={pub.url || `https://doi.org/${pub.doi}`}
                                target="_blank"
                                rel="noreferrer"
                                className="doi-link"
                              >
                                DOI:{pub.doi}
                                <ExternalLink size={12} />
                              </a>
                            )}
                          </div>
                        </div>

                        <div className="pub-card-action">
                          {isAttached ? (
                            <button
                              type="button"
                              className="btn btn-attached attached-status"
                              onClick={() => {
                                const idx = draft.attachedCitations.findIndex(
                                  (c) => (c.doi && c.doi === pub.doi) || (c.title && c.title.toLowerCase() === pub.title.toLowerCase())
                                );
                                if (idx >= 0) handleRemoveCitation(idx);
                              }}
                              title="Attached as candidate citation (click to detach)"
                            >
                              <Check size={14} /> Attached
                            </button>
                          ) : (
                            <button
                              type="button"
                              className="btn btn-secondary attach-btn"
                              onClick={() => handleAttachCitation(pub)}
                            >
                              <Plus size={14} />
                              Attach
                            </button>
                          )}
                        </div>
                      </article>
                    );
                  })}
                </div>
              )}
            </div>
          </section>
        </div>

        {/* Right Column: Live Simulation Summary */}
        <aside className="simulation-summary-column" aria-label="Simulation Draft Summary">
          <div className="summary-card sticky-summary">
            <div className="summary-header">
              <div className="summary-title-wrap">
                <FlaskConical size={18} />
                <h2>Simulation Summary</h2>
              </div>
              <span className="draft-saved-tag">
                <Check size={12} /> Draft saved locally
              </span>
            </div>

            <div className="summary-body">
              {/* Claim section */}
              <div className="summary-section">
                <span className="summary-label">RESEARCH CLAIM</span>
                <p className="summary-claim-text">
                  {draft.claim || <em className="text-muted">No research claim entered yet.</em>}
                </p>
              </div>

              {/* Environment section */}
              <div className="summary-section">
                <span className="summary-label">VALIDATION ENVIRONMENT</span>
                <div className="summary-env-badge">
                  <strong>{ENVIRONMENTS.find((e) => e.id === draft.environment)?.label}</strong>
                  <span className="env-sub-tag">
                    {ENVIRONMENTS.find((e) => e.id === draft.environment)?.tagline}
                  </span>
                </div>
                {draft.conditions && (
                  <p className="summary-conditions-snippet">
                    <strong>Conditions:</strong> {draft.conditions}
                  </p>
                )}
              </div>

              {/* Benchmark section */}
              <div className="summary-section">
                <span className="summary-label">COMPARATOR & BENCHMARK</span>
                <div className="summary-benchmark-grid">
                  <div className="bench-meta-item">
                    <small>Comparator</small>
                    <span>{draft.comparatorName || '—'}</span>
                  </div>
                  <div className="bench-meta-item">
                    <small>Metric</small>
                    <span>{draft.metric || '—'}</span>
                  </div>
                </div>

                {benchmarkCalc && (
                  <div className="summary-calc-card">
                    <div className="calc-row">
                      <span>Baseline: <strong>{draft.baselineValue} {draft.unit}</strong></span>
                      <ArrowRight size={13} />
                      <span>Observed: <strong>{draft.observedValue} {draft.unit}</strong></span>
                    </div>
                    <div className="calc-badge-row">
                      <span className="badge-tag abs-tag">
                        <TrendingUp size={13} />
                        {benchmarkCalc.absoluteText}
                      </span>
                      <span className="badge-tag rel-tag">
                        {benchmarkCalc.relativeText}
                      </span>
                    </div>
                  </div>
                )}
              </div>

              {/* Attached citations section */}
              <div className="summary-section">
                <div className="attached-header">
                  <span className="summary-label">
                    CANDIDATE CITATIONS ({draft.attachedCitations.length})
                  </span>
                </div>

                {draft.attachedCitations.length === 0 ? (
                  <p className="empty-citations-hint">
                    No candidate citations attached. Use Step 4 to find and attach relevant literature.
                  </p>
                ) : (
                  <>
                    <ul className="attached-citations-list">
                      {draft.attachedCitations.map((c, i) => (
                        <li key={c.doi || i} className="attached-citation-item">
                          <div className="item-text">
                            <strong>{c.title}</strong>
                            <span className="item-meta">
                              {c.year && `(${c.year}) `}
                              {c.provider && `[${c.provider}] `}
                              {c.doi && `DOI: ${c.doi}`}
                            </span>
                            <div className="verify-action-row" style={{ marginTop: '0.4rem' }}>
                              <button
                                type="button"
                                className="btn btn-secondary btn-verify-pair"
                                disabled={isVerifyingPair || !draft.claim.trim()}
                                onClick={() => handleVerifyAttachedPair(c)}
                                style={{ fontSize: '0.8rem', padding: '0.25rem 0.6rem' }}
                                title="Run backend verification for this claim–paper pair"
                              >
                                <Sparkles size={12} style={{ marginRight: '4px' }} />
                                Verify this claim against this paper
                              </button>
                            </div>
                          </div>
                          <button
                            type="button"
                            className="remove-btn"
                            aria-label={`Remove citation ${c.title}`}
                            onClick={() => handleRemoveCitation(i)}
                            title="Remove citation"
                          >
                            <Trash2 size={14} />
                          </button>
                        </li>
                      ))}
                    </ul>
                    {verifyPairStatus && (
                      <div className="sim-verify-status-box" style={{ marginTop: '0.75rem', fontSize: '0.82rem', padding: '0.5rem', borderRadius: '4px', background: verifyPairStatus.error ? '#fdf0f1' : '#f1f7e5', color: verifyPairStatus.error ? '#96222b' : '#365b17' }}>
                        {verifyPairStatus.error || verifyPairStatus.success || verifyPairStatus.info}
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>

            <div className="summary-footer">
              <small>
                This simulation draft is stored locally on this machine and kept separate from manuscript verification results and reports.
              </small>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
