import React, { useState } from 'react';
import { 
  FileSearch, 
  Split, 
  BookOpen, 
  CheckCircle2, 
  AlertTriangle, 
  FileCheck2, 
  ExternalLink,
  Layers,
  ArrowRight,
  ShieldCheck,
  Tag
} from 'lucide-react';

const FEATURE_GROUPS = [
  {
    id: 'extract-map',
    groupTitle: 'Extract & Map',
    subtitle: 'From unstructured prose to addressable claim-citation links',
    capabilities: [
      'Document and atomic claim extraction',
      'Citation marker detection & multi-ref mapping'
    ],
    renderPreview: () => (
      <div className="feature-interactive-card">
        <div className="mini-card-header">
          <Split size={14} />
          <span>Multi-Citation Sentence Parsing</span>
        </div>
        <div className="mini-card-content">
          <div className="mini-sentence">
            “Model throughput increased tenfold across both benchmarks{' '}
            <span className="mini-cite-pill active-pill">[2, 5]</span>.”
          </div>
          <div className="mini-mapping-tree">
            <div className="mapping-branch">
              <span className="branch-line" />
              <div className="branch-target">
                <span className="target-num">[2]</span>
                <div className="target-text">
                  <strong>Chen et al. (2024)</strong>
                  <p>Inference acceleration in distributed clusters.</p>
                </div>
              </div>
            </div>
            <div className="mapping-branch">
              <span className="branch-line" />
              <div className="branch-target">
                <span className="target-num">[5]</span>
                <div className="target-text">
                  <strong>Vasquez (2023)</strong>
                  <p>High-throughput kernels for transformer layers.</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  },
  {
    id: 'retrieve-compare',
    groupTitle: 'Retrieve & Compare',
    subtitle: 'Direct side-by-side passage grounding from designated publications',
    capabilities: [
      'Original paper retrieval across open providers',
      'Passage-level semantic & numerical comparison'
    ],
    renderPreview: () => (
      <div className="feature-interactive-card">
        <div className="mini-card-header">
          <BookOpen size={14} />
          <span>Passage-Level Evidence Comparison</span>
        </div>
        <div className="mini-side-by-side">
          <div className="mini-side-col">
            <span className="side-label">MANUSCRIPT CLAIM</span>
            <p className="side-quote">“The proposed approach reduced memory usage by 40%.”</p>
          </div>
          <div className="mini-vs-divider">VS</div>
          <div className="mini-side-col target-source">
            <span className="side-label">RETRIEVED PASSAGE (Section 4.1)</span>
            <p className="side-quote">“Peak VRAM consumption dropped from 16 GB to 9.6 GB (a 40% reduction).”</p>
          </div>
        </div>
        <div className="mini-footer-badge">
          <CheckCircle2 size={13} className="text-success" />
          <span>Exact quantitative match in full-text source</span>
        </div>
      </div>
    )
  },
  {
    id: 'classify-flag',
    groupTitle: 'Classify & Flag',
    subtitle: 'Strict polarity, metric, and population disparity classification',
    capabilities: [
      'Claim status classification (Supported / Contradictory)',
      'Misleading reference & population mismatch detection'
    ],
    renderPreview: () => (
      <div className="feature-interactive-card">
        <div className="mini-card-header">
          <AlertTriangle size={14} className="text-warning" />
          <span>Population Qualifier Discrepancy</span>
        </div>
        <div className="mini-flag-preview">
          <div className="flagged-statement">
            <span className="tag-pill tag-claim">Claim</span>
            <p>“Drug efficacy reached 82% in <mark className="mismatch-pop">pediatric cohorts</mark>.”</p>
          </div>
          <div className="flagged-statement">
            <span className="tag-pill tag-source">Evidence</span>
            <p>“Overall response was 82% in <mark className="mismatch-pop">adult trial volunteers</mark>.”</p>
          </div>
          <div className="flag-alert-box">
            <AlertTriangle size={13} />
            <span><strong>Population mismatch:</strong> Finding demonstrated in adults; cannot be generalized to pediatric populations.</span>
          </div>
        </div>
      </div>
    )
  },
  {
    id: 'trace-report',
    groupTitle: 'Trace & Report',
    subtitle: 'Transparent decision audit trails with persistent citation provenance',
    capabilities: [
      'Passage and DOI evidence traceability',
      'Exportable JSON and CSV audit reports'
    ],
    renderPreview: () => (
      <div className="feature-interactive-card">
        <div className="mini-card-header">
          <FileCheck2 size={14} />
          <span>Auditable Verification Report Row</span>
        </div>
        <div className="report-row-preview">
          <div className="row-cell-main">
            <div className="row-meta">
              <span className="badge supported">Supported</span>
              <span className="doi-tag">DOI: 10.1073/pnas.1319030111</span>
            </div>
            <p className="row-claim-text">Active learning raises student performance in undergraduate STEM.</p>
          </div>
          <div className="row-reviewer-decision">
            <span className="decision-label">Human Review Decision</span>
            <span className="decision-status">Reviewed · Confirmed by Auditor</span>
          </div>
        </div>
      </div>
    )
  }
];

export function Features() {
  const [activeGroup, setActiveGroup] = useState('extract-map');

  return (
    <section id="features" className="features-section" aria-labelledby="features-heading">
      <div className="section-container">
        <div className="section-header">
          <span className="section-eyebrow">CORE CAPABILITIES</span>
          <h2 id="features-heading" className="section-title">
            Built for rigorous academic verification
          </h2>
          <p className="section-subtitle">
            Every step is designed to make citation verification verifiable, traceable, and inspectable by human researchers.
          </p>
        </div>

        <div className="features-grid">
          {FEATURE_GROUPS.map((fg) => {
            const isSelected = activeGroup === fg.id;
            return (
              <div 
                key={fg.id} 
                className={`feature-card ${isSelected ? 'active-feature-card' : ''}`}
                onClick={() => setActiveGroup(fg.id)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    setActiveGroup(fg.id);
                  }
                }}
                aria-pressed={isSelected}
              >
                <div className="feature-card-content">
                  <div className="feature-card-heading">
                    <h3>{fg.groupTitle}</h3>
                    <p className="feature-card-desc">{fg.subtitle}</p>
                  </div>

                  <ul className="capabilities-list">
                    {fg.capabilities.map((cap) => (
                      <li key={cap}>
                        <ShieldCheck size={14} className="cap-icon" />
                        <span>{cap}</span>
                      </li>
                    ))}
                  </ul>

                  <div className="feature-preview-box">
                    {fg.renderPreview()}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
