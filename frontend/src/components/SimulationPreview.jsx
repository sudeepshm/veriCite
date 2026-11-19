import React from 'react';
import { FlaskConical, ArrowRight, Check, Sparkles, TrendingUp, Layers } from 'lucide-react';
import { Link } from '../router';
import { calculateBenchmarkDifference } from '../simulationCalculations';

export function SimulationPreview() {
  const sampleCalc = calculateBenchmarkDifference({
    baseline: '50',
    observed: '60',
    unit: '%'
  });

  return (
    <section className="simulation-preview-section" aria-labelledby="simulation-preview-title">
      <div className="section-container">
        <div className="simulation-preview-grid">
          {/* Left: Explanatory Copy */}
          <div className="sim-preview-copy">
            <div className="sim-badge">
              <FlaskConical size={16} />
              <span>RESEARCH PLANNING WORKSPACE</span>
            </div>

            <h2 id="simulation-preview-title" className="section-title">
              Define what was tested, where it was tested, and what it was compared against.
            </h2>

            <p className="section-subtitle">
              Academic Simulation bridges experimental planning with literature grounding. Capture your hypothesis, specify computational, laboratory, or field environments, and benchmark observed metrics against prior findings.
            </p>

            <div className="sim-feature-checks">
              <div className="check-line">
                <Check size={16} className="text-brand" />
                <span>Zero physical experiment claim — treats input as research planning</span>
              </div>
              <div className="check-line">
                <Check size={16} className="text-brand" />
                <span>Deterministic absolute and relative benchmark calculations</span>
              </div>
              <div className="check-line">
                <Check size={16} className="text-brand" />
                <span>Integrated citation discovery across approved academic registries</span>
              </div>
            </div>

            <div className="sim-preview-actions">
              <Link href="/workspace/simulation" className="btn btn-primary">
                <FlaskConical size={16} />
                Open Academic Simulation
                <ArrowRight size={15} />
              </Link>
            </div>
          </div>

          {/* Right: Realistic interactive form preview */}
          <div className="sim-card-preview" aria-hidden="true">
            <div className="sim-card-header">
              <div className="sim-card-title">
                <FlaskConical size={16} />
                <span>Academic Simulation · Quick Preview</span>
              </div>
              <span className="live-tag">Interactive Workspace</span>
            </div>

            <div className="sim-card-body">
              {/* Step 1 Preview */}
              <div className="sim-preview-field">
                <label className="preview-label">Step 1 · Research Claim</label>
                <div className="mock-input mock-textarea">
                  “Transformer quantization with 4-bit weights maintains 98% of FP16 accuracy on standard NLP benchmarks.”
                </div>
              </div>

              {/* Step 2 Preview: Environment */}
              <div className="sim-preview-field">
                <label className="preview-label">Step 2 · Validation Environment</label>
                <div className="mock-env-selector">
                  <div className="mock-env-pill selected">
                    <span className="pill-dot" />
                    <strong>Simulation</strong>
                    <small>Computational & modeled</small>
                  </div>
                  <div className="mock-env-pill">
                    <strong>Laboratory</strong>
                    <small>Controlled testing</small>
                  </div>
                  <div className="mock-env-pill">
                    <strong>Field deployment</strong>
                    <small>Real-world operations</small>
                  </div>
                </div>
              </div>

              {/* Step 3 Preview: Benchmark */}
              <div className="sim-preview-field">
                <label className="preview-label">Step 3 · Comparator & Benchmark Calculation</label>
                <div className="mock-benchmark-card">
                  <div className="bench-row">
                    <span>Comparator: <strong>FP16 Baseline</strong></span>
                    <span>Metric: <strong>Accuracy (%)</strong></span>
                  </div>
                  <div className="bench-calc-row">
                    <div className="bench-val">
                      <small>Baseline</small>
                      <strong>50%</strong>
                    </div>
                    <ArrowRight size={15} className="arrow-sep" />
                    <div className="bench-val">
                      <small>Observed</small>
                      <strong>60%</strong>
                    </div>
                    <div className="bench-result-badge">
                      <TrendingUp size={13} />
                      <span>{sampleCalc.absoluteText}</span>
                      <span className="rel-tag">{sampleCalc.relativeText}</span>
                    </div>
                  </div>
                </div>
              </div>

              <div className="sim-preview-footer">
                <small>Researcher-entered benchmark calculation · Isolated from verification reports</small>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
