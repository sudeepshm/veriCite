import React, { useState } from 'react';
import { 
  Split, 
  BookOpen, 
  CheckCircle2, 
  AlertTriangle, 
  FileCheck2, 
  ArrowRight, 
  ShieldCheck, 
  FileText,
  Search,
  Check
} from 'lucide-react';
import { Link } from '../router';

const FEATURE_TABS = [
  {
    id: 'extract-map',
    label: 'Extract & map',
    title: 'Atomic Claim Extraction & Citation Mapping',
    explanation: 'Extract atomic assertions and link citation markers [1] strictly to bibliographic entries without borrowing neighboring citations.',
    destinationText: 'Verify a document',
    destinationLink: '/workspace/verify',
    capabilities: [
      'Strict sentence-boundary isolation prevents marker borrowing',
      'Preserves unverified candidate claims even with missing citations',
      'Supports numeric [1] and author-year (Smith, 2024) syntax'
    ],
    preview: (
      <div className="feature-interactive-showcase">
        <div className="mini-card-header">
          <Split size={15} />
          <span>Multi-Citation Sentence Parsing</span>
          <span className="live-demo-tag">Stage 2</span>
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
    label: 'Retrieve & compare',
    title: 'Passage-Level Source Grounding & Comparison',
    explanation: 'Ground assertions directly against verbatim passages retrieved from OpenAlex, Crossref, and Semantic Scholar.',
    destinationText: 'Review claim evidence',
    destinationLink: '/workspace/overview',
    capabilities: [
      'BM25 and dense embedding chunk retrieval with section metadata',
      'Side-by-side numerical and semantic comparison',
      'Recoverable character offsets and verbatim evidence quotations'
    ],
    preview: (
      <div className="feature-interactive-showcase">
        <div className="mini-card-header">
          <BookOpen size={15} />
          <span>Verbatim Passage Alignment</span>
          <span className="live-demo-tag">Stage 4</span>
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
    label: 'Classify & flag',
    title: 'Discrepancy & Population Mismatch Detection',
    explanation: 'Classify claims as Supported or Contradictory, and isolate population mismatches and missing citations.',
    destinationText: 'Inspect flagged claims',
    destinationLink: '/workspace/overview',
    capabilities: [
      'Polarity & direction checking (detects false support in negated sentences)',
      'Population qualifier mismatch detection (adult pilot vs pediatric cohort)',
      'Deterministic fallback abstains with unable_to_assess when ambiguous'
    ],
    preview: (
      <div className="feature-interactive-showcase">
        <div className="mini-card-header">
          <AlertTriangle size={15} className="text-warning" />
          <span>Population Qualifier Discrepancy</span>
          <span className="live-demo-tag">Stage 5</span>
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
    label: 'Trace & report',
    title: 'Decision Audit Trails & Exportable Reports',
    explanation: 'Preserve full provenance from original manuscript offset to publication DOI with exportable CSV and JSON reports.',
    destinationText: 'View references & audit trail',
    destinationLink: '/workspace/references',
    capabilities: [
      'Complete DOI and verified URL provenance with zero fabricated links',
      'Persistent human reviewer audit decisions and notes',
      'RFC 4180-compliant CSV and structured JSON exports'
    ],
    preview: (
      <div className="feature-interactive-showcase">
        <div className="mini-card-header">
          <FileCheck2 size={15} />
          <span>Auditable Verification Report Row</span>
          <span className="live-demo-tag">Audit Trail</span>
        </div>
        <div className="report-row-preview">
          <div className="row-cell-main">
            <div className="row-meta">
              <span className="badge supported-badge">Supported</span>
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
  const [activeTabId, setActiveTabId] = useState('extract-map');
  const activeTab = FEATURE_TABS.find((t) => t.id === activeTabId) || FEATURE_TABS[0];

  return (
    <section id="features" className="features-section" aria-labelledby="features-heading">
      <div className="section-container">
        <div className="section-header">
          <span className="section-eyebrow">CORE CAPABILITIES</span>
          <h2 id="features-heading" className="section-title">
            Select a task to preview veriCite in action
          </h2>
          <p className="section-subtitle">
            Study how each capability works, review the live interface preview, and open the workspace screen that performs it.
          </p>
        </div>

        {/* Sitechecker-inspired 4-Tab Feature Explorer */}
        <div className="feature-explorer-tabs" role="tablist" aria-label="Product feature preview tabs">
          {FEATURE_TABS.map((tab) => {
            const isSelected = activeTabId === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={isSelected}
                className={`explorer-tab-btn ${isSelected ? 'active' : ''}`}
                onClick={() => setActiveTabId(tab.id)}
              >
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* Feature Explorer Showcase: Explanation + Destination CTA + Interactive Preview */}
        <div className="feature-showcase-panel" role="tabpanel" aria-live="polite">
          <div className="showcase-content">
            <span className="showcase-badge">{activeTab.label}</span>
            <h3 className="showcase-title">{activeTab.title}</h3>
            <p className="showcase-explanation">{activeTab.explanation}</p>

            <ul className="showcase-bullets">
              {activeTab.capabilities.map((cap) => (
                <li key={cap}>
                  <Check size={16} className="cap-check-icon" />
                  <span>{cap}</span>
                </li>
              ))}
            </ul>

            <div className="showcase-action">
              <Link href={activeTab.destinationLink} className="btn btn-primary showcase-cta">
                <span>{activeTab.destinationText}</span>
                <ArrowRight size={15} />
              </Link>
            </div>
          </div>

          <div className="showcase-preview-wrapper">
            {activeTab.preview}
          </div>
        </div>
      </div>
    </section>
  );
}
