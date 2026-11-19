import React, { useState, useEffect, useRef } from 'react';
import { 
  ArrowRight, 
  FlaskConical, 
  Play, 
  Pause, 
  RotateCcw, 
  FileText, 
  BookOpen, 
  AlertTriangle, 
  Check, 
  Calculator,
  Eye,
  ChevronRight
} from 'lucide-react';
import { Link } from '../router';

const STAGES = [
  {
    num: 1,
    title: 'Claim in Manuscript',
    summary: 'Identify the atomic assertion and the specific citation marker.',
  },
  {
    num: 2,
    title: 'Citation Linked',
    summary: 'Map the marker [1] to its exact bibliography publication.',
  },
  {
    num: 3,
    title: 'Source Paper Retrieved',
    summary: 'Inspect the Results section and extracted baseline/follow-up table.',
  },
  {
    num: 4,
    title: 'Discrepancy Calculated',
    summary: 'Extract exact figures and calculate the actual effect size: 60% - 50% = 10 pp.',
  },
  {
    num: 5,
    title: 'Side-by-Side Verdict',
    summary: 'Flag the quantitative conflict: claimed 20 percentage points vs actual 10 percentage points.',
  },
];

export function Hero3D() {
  const [stage, setStage] = useState(1);
  const [isPlaying, setIsPlaying] = useState(true);
  const [isReducedMotion, setIsReducedMotion] = useState(false);
  const timerRef = useRef(null);

  // Detect user prefers-reduced-motion preference
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    setIsReducedMotion(mq.matches);
    const handler = (e) => setIsReducedMotion(e.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  // Autoplay ticker when not paused and not reduced motion
  useEffect(() => {
    if (!isPlaying || isReducedMotion) {
      clearInterval(timerRef.current);
      return;
    }

    timerRef.current = setInterval(() => {
      setStage((prev) => (prev < 5 ? prev + 1 : 1));
    }, 4200);

    return () => clearInterval(timerRef.current);
  }, [isPlaying, isReducedMotion]);

  const handleStageSelect = (s) => {
    setStage(s);
    setIsPlaying(false); // pause autoplay on user direct interaction
  };

  const togglePlay = () => {
    setIsPlaying(!isPlaying);
  };

  const handleReplay = () => {
    setStage(1);
    setIsPlaying(true);
  };

  return (
    <section className="hero-section" aria-labelledby="hero-title">
      <div className="hero-container">
        {/* Left Column: Headline and Call to Actions */}
        <div className="hero-copy">
          <div className="hero-badge">
            <span className="badge-pulse" />
            Traceable Citation Verification
          </div>

          <h1 id="hero-title" className="hero-headline">
            See what your citations <span className="highlight-text">actually support.</span>
          </h1>

          <p className="hero-description">
            Trace a manuscript claim to its cited paper, inspect the original passage, and review the evidence side by side.
          </p>

          <div className="hero-actions">
            <Link href="/workspace/verify" className="btn btn-primary hero-btn-primary">
              Verify a document
              <ArrowRight size={17} />
            </Link>

            <Link href="/workspace/simulation" className="btn btn-secondary hero-btn-secondary">
              <FlaskConical size={17} />
              Explore Academic Simulation
            </Link>
          </div>

          <div className="hero-guarantees">
            <div className="guarantee-item">
              <Check size={15} className="check-icon" />
              <span>Evidence first, never ungrounded verdicts</span>
            </div>
            <div className="guarantee-item">
              <Check size={15} className="check-icon" />
              <span>OpenAlex & Crossref source provenance</span>
            </div>
          </div>
        </div>

        {/* Right Column: 3D Interactive Demonstration */}
        <div className="hero-demo-wrapper">
          <div className="hero-demo-header">
            <div className="demo-tag">
              <span className="demo-tag-dot" />
              Illustrative example · Fictional demonstration
            </div>
            
            <div className="demo-controls" aria-label="Demonstration playback controls">
              <button
                type="button"
                className="control-icon-btn"
                onClick={togglePlay}
                aria-label={isPlaying ? 'Pause demonstration animation' : 'Play demonstration animation'}
                title={isPlaying ? 'Pause' : 'Play'}
              >
                {isPlaying ? <Pause size={14} /> : <Play size={14} />}
              </button>
              <button
                type="button"
                className="control-icon-btn"
                onClick={handleReplay}
                aria-label="Replay demonstration from step 1"
                title="Restart"
              >
                <RotateCcw size={14} />
              </button>
            </div>
          </div>

          {/* Stepper Pills */}
          <div className="demo-stepper" role="tablist" aria-label="Demonstration steps">
            {STAGES.map((s) => (
              <button
                key={s.num}
                role="tab"
                aria-selected={stage === s.num}
                className={`step-pill ${stage === s.num ? 'active' : ''} ${stage > s.num ? 'completed' : ''}`}
                onClick={() => handleStageSelect(s.num)}
              >
                <span className="step-num">{s.num}</span>
                <span className="step-label">{s.title}</span>
              </button>
            ))}
          </div>

          {/* 3D Scene Viewport */}
          <div 
            className={`scene-viewport ${isReducedMotion ? 'reduced-motion-mode' : ''}`}
            aria-live="polite"
          >
            {/* If prefers-reduced-motion is active, display static side-by-side comparison */}
            {isReducedMotion ? (
              <div className="static-comparison-card">
                <div className="static-col">
                  <div className="scene-card-header manuscript-header">
                    <FileText size={15} />
                    <span>Submitted Manuscript (p. 4)</span>
                  </div>
                  <div className="scene-card-body">
                    <div className="claim-highlight">
                      “Accuracy improved by <mark className="stat-discrepancy">20 percentage points</mark> <span className="cite-marker">[1]</span>.”
                    </div>
                    <div className="bib-snippet">
                      <strong>References</strong>
                      <p>[1] Rao, M. (2025). Classification accuracy in an adult pilot. <em>Fixture Studies</em>, 1, 1.</p>
                    </div>
                  </div>
                </div>

                <div className="static-col">
                  <div className="scene-card-header source-header">
                    <BookOpen size={15} />
                    <span>Cited Publication: Rao (2025) Table 2</span>
                  </div>
                  <div className="scene-card-body">
                    <table className="demo-table">
                      <thead>
                        <tr>
                          <th>Measurement</th>
                          <th>Score</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr>
                          <td>Baseline Accuracy</td>
                          <td className="metric-val">50%</td>
                        </tr>
                        <tr className="highlight-row">
                          <td>Follow-up Accuracy</td>
                          <td className="metric-val">60%</td>
                        </tr>
                      </tbody>
                    </table>
                    <div className="calc-pill">
                      <Calculator size={14} />
                      <span>60% − 50% = <strong>10 percentage points</strong></span>
                    </div>
                    <div className="static-verdict">
                      <span className="badge contradictory">
                        <AlertTriangle size={13} /> Contradictory
                      </span>
                      <p>Claim asserts 20 percentage points; cited paper records 10 percentage points.</p>
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              /* Perspective 3D Stage View */
              <div className={`stage-scene stage-active-${stage}`}>
                {/* 1. Manuscript Layer */}
                <div className={`scene-card manuscript-card ${stage >= 1 ? 'visible' : ''} ${stage >= 5 ? 'settled-left' : ''}`}>
                  <div className="scene-card-header manuscript-header">
                    <FileText size={15} />
                    <span>Draft Manuscript · Findings</span>
                    <span className="card-stage-indicator">Step 1</span>
                  </div>
                  <div className="scene-card-body">
                    <p className="context-text">
                      Across the cohort evaluation, our primary model demonstrated significant convergence.
                    </p>
                    <div className={`claim-highlight-box ${stage >= 1 ? 'highlighted' : ''}`}>
                      “Accuracy improved by <span className="claim-num">20 percentage points</span>{' '}
                      <span className={`marker-pill ${stage >= 2 ? 'marker-connected' : ''}`}>[1]</span>.”
                    </div>
                    
                    {/* Bibliography anchor */}
                    <div className={`bib-section ${stage >= 2 ? 'bib-revealed' : ''}`}>
                      <div className="bib-title">BIBLIOGRAPHY ENTRY</div>
                      <div className="bib-entry">
                        <span className="marker-tag">[1]</span>
                        <div className="bib-details">
                          <strong>Rao, M. (2025)</strong>
                          <p>Classification accuracy in an adult pilot. <em>Fixture Studies</em>, 1, 1.</p>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* 2. Visual Connector Line (Appears in Stage 2) */}
                {stage === 2 && (
                  <div className="connection-tracer" aria-hidden="true">
                    <div className="trace-path" />
                    <span className="trace-badge">Resolving source DOI via Crossref…</span>
                  </div>
                )}

                {/* 3. Cited Source Paper Layer */}
                <div className={`scene-card source-card ${stage >= 3 ? 'visible' : ''} ${stage === 3 ? 'popped-forward' : ''} ${stage >= 5 ? 'settled-right' : ''}`}>
                  <div className="scene-card-header source-header">
                    <BookOpen size={15} />
                    <span>Cited Paper · Rao et al. (2025)</span>
                    <span className="card-stage-indicator">Step 3: Evidence</span>
                  </div>
                  <div className="scene-card-body">
                    <div className="section-title">SECTION 4: RESULTS TABLE 2</div>
                    <table className="demo-table">
                      <thead>
                        <tr>
                          <th>Evaluation Point</th>
                          <th>Reported Accuracy</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr className={stage >= 4 ? 'row-selected' : ''}>
                          <td>Baseline trial (n=40)</td>
                          <td className="num-cell">50%</td>
                        </tr>
                        <tr className={stage >= 4 ? 'row-selected' : ''}>
                          <td>Adult pilot follow-up</td>
                          <td className="num-cell highlight-cell">60%</td>
                        </tr>
                      </tbody>
                    </table>

                    {/* Stage 4: Calculation callout */}
                    {stage >= 4 && (
                      <div className="calculation-callout">
                        <div className="calc-header">
                          <Calculator size={14} />
                          <span>Exact Quantitative Computation</span>
                        </div>
                        <div className="calc-formula">
                          <code>60% − 50% = 10 percentage points</code>
                        </div>
                      </div>
                    )}

                    {/* Stage 5: Final Verdict Summary */}
                    {stage === 5 && (
                      <div className="final-verdict-banner">
                        <div className="verdict-header">
                          <span className="badge contradictory">
                            <AlertTriangle size={13} />
                            Contradictory
                          </span>
                          <span className="verdict-rule-tag">Strict Numerical Comparator</span>
                        </div>
                        <p className="verdict-explanation">
                          Discrepancy detected: The manuscript asserts a <strong>20 percentage point</strong> gain, but the cited paper confirms an absolute gain of <strong>10 percentage points</strong> (50% → 60%).
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Bottom Stage Narrative Explanation */}
          <div className="demo-narrative-bar">
            <div className="narrative-step">
              <span className="step-indicator">Stage {stage} of 5</span>
              <strong>{STAGES[stage - 1].title}:</strong> {STAGES[stage - 1].summary}
            </div>
            {stage < 5 ? (
              <button
                type="button"
                className="narrative-next-btn"
                onClick={() => handleStageSelect(stage + 1)}
              >
                Next step
                <ChevronRight size={14} />
              </button>
            ) : (
              <button
                type="button"
                className="narrative-next-btn restart"
                onClick={handleReplay}
              >
                Replay demonstration
                <RotateCcw size={14} />
              </button>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
