import React, { useState, useEffect, useRef } from 'react';
import { 
  ArrowRight, 
  FlaskConical, 
  Play, 
  Pause, 
  RotateCcw, 
  ChevronLeft, 
  ChevronRight,
  FileText, 
  BookOpen, 
  AlertTriangle, 
  Check, 
  Calculator,
  Info
} from 'lucide-react';
import { Link } from '../router';

const MOMENTS = [
  {
    moment: 1,
    timeRange: '0–2s',
    label: 'Identify Assertion',
    learning: 'The engine identifies a specific assertion and its citation.'
  },
  {
    moment: 2,
    timeRange: '2–4s',
    label: 'Extract Source Evidence',
    learning: 'The comparison uses values from the cited source.'
  },
  {
    moment: 3,
    timeRange: '4–6s',
    label: 'Compare Discrepancy',
    learning: 'The visitor can see and check the discrepancy without trusting a badge.'
  }
];

export function Hero3D() {
  const [moment, setMoment] = useState(1);
  const [isPlaying, setIsPlaying] = useState(true);
  const [isReducedMotion, setIsReducedMotion] = useState(false);
  const timerRef = useRef(null);

  // Check prefers-reduced-motion
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (mq.matches) {
      setIsReducedMotion(true);
      setMoment(3); // start at settled final state
      setIsPlaying(false);
    }
    const handler = (e) => {
      setIsReducedMotion(e.matches);
      if (e.matches) {
        setMoment(3);
        setIsPlaying(false);
      }
    };
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  // Autoplay: 0-2s (Moment 1) -> 2-4s (Moment 2) -> 4-6s (Moment 3), then hold!
  useEffect(() => {
    if (!isPlaying || isReducedMotion) {
      clearInterval(timerRef.current);
      return;
    }

    timerRef.current = setInterval(() => {
      setMoment((prev) => {
        if (prev < 3) {
          return prev + 1;
        } else {
          // Play once, then hold the result
          setIsPlaying(false);
          clearInterval(timerRef.current);
          return 3;
        }
      });
    }, 2000); // 2000ms per moment = 6 seconds total

    return () => clearInterval(timerRef.current);
  }, [isPlaying, isReducedMotion]);

  const goToMoment = (m) => {
    setMoment(m);
    setIsPlaying(false); // hold on manual click
  };

  const handleNext = () => {
    if (moment < 3) {
      setMoment(moment + 1);
      setIsPlaying(false);
    }
  };

  const handlePrev = () => {
    if (moment > 1) {
      setMoment(moment - 1);
      setIsPlaying(false);
    }
  };

  const handleReplay = () => {
    setMoment(1);
    setIsPlaying(true);
  };

  const togglePlay = () => {
    setIsPlaying(!isPlaying);
  };

  return (
    <section className="hero-section" aria-labelledby="hero-title">
      <div className="hero-container">
        {/* Left Column: Headline and Call to Actions */}
        <div className="hero-copy">
          <div className="hero-badge">
            <span className="badge-pulse" />
            TRACEABLE CITATION VERIFICATION
          </div>

          <h1 id="hero-title" className="hero-headline">
            Does your source support your claim?
          </h1>

          <p className="hero-description">
            Follow a statement from your manuscript to the exact passage in the cited paper.
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

        {/* Right Column: 3D Interactive Paper Stack */}
        <div className="hero-demo-wrapper">
          <div className="hero-demo-header">
            <div className="demo-tag">
              <span className="demo-tag-dot" />
              Illustrative example
            </div>

            {/* Playback Controls: Previous, Play/Pause, Next, Replay */}
            <div className="demo-controls" aria-label="Demonstration playback controls">
              <button
                type="button"
                className="control-icon-btn"
                onClick={handlePrev}
                disabled={moment <= 1}
                aria-label="Previous step"
                title="Previous step"
              >
                <ChevronLeft size={16} />
              </button>

              <button
                type="button"
                className="control-icon-btn"
                onClick={togglePlay}
                aria-label={isPlaying ? 'Pause animation' : 'Play animation'}
                title={isPlaying ? 'Pause' : 'Play'}
              >
                {isPlaying ? <Pause size={15} /> : <Play size={15} />}
              </button>

              <button
                type="button"
                className="control-icon-btn"
                onClick={handleNext}
                disabled={moment >= 3}
                aria-label="Next step"
                title="Next step"
              >
                <ChevronRight size={16} />
              </button>

              <button
                type="button"
                className="control-icon-btn"
                onClick={handleReplay}
                aria-label="Replay animation from beginning"
                title="Replay demonstration"
              >
                <RotateCcw size={15} />
              </button>
            </div>
          </div>

          {/* Moment Navigation Stepper */}
          <div className="demo-stepper" role="tablist" aria-label="Demonstration moments">
            {MOMENTS.map((m) => (
              <button
                key={m.moment}
                type="button"
                role="tab"
                aria-selected={moment === m.moment}
                className={`step-pill ${moment === m.moment ? 'active' : ''} ${m.moment < moment ? 'completed' : ''}`}
                onClick={() => goToMoment(m.moment)}
              >
                <span className="step-num">{m.moment}</span>
                <span className="step-label">{m.label} ({m.timeRange})</span>
              </button>
            ))}
          </div>

          {/* 3D Scene Viewport */}
          <div 
            className={`scene-viewport moment-${moment} ${isReducedMotion ? 'reduced-motion' : ''}`}
            aria-live="polite"
          >
            {/* 3D Paper Stack Scene */}
            <div className={`stage-scene moment-active-${moment}`}>
              {/* Paper 1: Draft Manuscript */}
              <div className={`scene-card manuscript-card ${moment >= 1 ? 'visible' : ''} ${moment === 3 ? 'settled-left' : ''}`}>
                <div className="scene-card-header manuscript-header">
                  <FileText size={15} />
                  <span>Draft Manuscript (p. 4)</span>
                  <span className="card-stage-indicator">Claim</span>
                </div>
                
                <div className="scene-card-body">
                  <p className="context-text">
                    Across the adult cohort evaluation, the model demonstrated significant accuracy gains:
                  </p>
                  
                  <div className={`claim-highlight-box ${moment >= 1 ? 'highlighted' : ''}`}>
                    “Accuracy improved by{' '}
                    <span className="claim-num-lime">20 percentage points</span>{' '}
                    <span className={`marker-pill ${moment >= 1 ? 'marker-connected' : ''}`}>[1]</span>.”
                    {/* Animated connector traveling from assertion to [1] */}
                    <span className={`lime-connector-line ${moment >= 1 ? 'active' : ''}`} />
                  </div>

                  <div className="bib-section-mini">
                    <span className="bib-label">BIBLIOGRAPHY ENTRY</span>
                    <p className="bib-text">
                      <strong>[1] Rao, M. (2025).</strong> Classification accuracy in an adult pilot. <em>Fixture Studies</em>, 1, 1.
                    </p>
                  </div>
                </div>
              </div>

              {/* Paper 2: Cited Publication (Slides forward behind manuscript in Moment 2, settles side by side in Moment 3) */}
              <div className={`scene-card source-card ${moment >= 2 ? 'visible' : ''} ${moment === 3 ? 'settled-right' : ''}`}>
                <div className="scene-card-header source-header">
                  <BookOpen size={15} />
                  <span>Cited Publication · Rao (2025)</span>
                  <span className="card-stage-indicator source-indicator">Source Evidence</span>
                </div>

                <div className="scene-card-body">
                  <div className="table-caption">Table 2: Adult Pilot Classification Performance</div>
                  <table className="demo-table">
                    <thead>
                      <tr>
                        <th>Measurement Group</th>
                        <th>Score</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr className={moment >= 2 ? 'row-selected' : ''}>
                        <td>Baseline Accuracy</td>
                        <td className="num-cell highlight-cell">50%</td>
                      </tr>
                      <tr className={moment >= 2 ? 'row-selected' : ''}>
                        <td>Follow-up Accuracy</td>
                        <td className="num-cell highlight-cell">60%</td>
                      </tr>
                    </tbody>
                  </table>

                  {/* Arithmetic extraction callout */}
                  <div className="calculation-callout">
                    <div className="calc-header">
                      <Calculator size={13} />
                      <span>Quantitative Grounding</span>
                    </div>
                    <div className="calc-formula">
                      <code>60% − 50% = <strong>10 percentage points</strong></code>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Moment 3 Revealed Comparison Bar */}
          <div className={`discrepancy-settlement-bar ${moment === 3 ? 'revealed' : ''}`}>
            <div className="settlement-values">
              <div className="val-box claim-val">
                <span className="val-label">Manuscript Claim</span>
                <strong>+20 percentage points</strong>
              </div>
              <span className="vs-divider">≠</span>
              <div className="val-box source-val">
                <span className="val-label">Cited Paper (Rao 2025)</span>
                <strong>+10 percentage points</strong>
              </div>
            </div>
            <div className="settlement-verdict">
              <span className="badge contradictory-badge">
                <AlertTriangle size={13} />
                Contradictory
              </span>
              <span className="discrepancy-note">
                10-point discrepancy verified directly against Table 2.
              </span>
            </div>
          </div>

          {/* Bottom Narrative / Learning Bar */}
          <div className="demo-narrative-bar">
            <div className="narrative-learning">
              <span className="learning-tag">MOMENT {moment} OF 3</span>
              <span className="learning-text">{MOMENTS[moment - 1].learning}</span>
            </div>

            <div className="narrative-action">
              {moment < 3 ? (
                <button
                  type="button"
                  className="narrative-next-btn"
                  onClick={handleNext}
                >
                  <span>Next moment</span>
                  <ChevronRight size={14} />
                </button>
              ) : (
                <button
                  type="button"
                  className="narrative-replay-btn"
                  onClick={handleReplay}
                >
                  <RotateCcw size={13} />
                  <span>Replay demonstration</span>
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
