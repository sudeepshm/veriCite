import React, { useState } from 'react';
import { 
  FileText, 
  Split, 
  Globe, 
  Search, 
  ShieldCheck, 
  ArrowRight,
  Cpu,
  Database,
  CheckCircle2,
  AlertCircle
} from 'lucide-react';

const STAGES = [
  {
    id: 1,
    name: 'Parse',
    badge: 'Stage 1',
    inputDesc: 'Manuscript document (.txt, .md supported; PDF / DOCX planned via Docling)',
    technology: 'Regex paragraph/heading boundaries & sentence-span tokenizer',
    outputDesc: 'Structured text, heading, and bibliography blocks with character offsets',
    icon: FileText,
    exampleInput: 'Accuracy rose from 50% to 60% in the adult pilot [1].',
    exampleOutput: 'DocumentBlock(block_id="b0002", type=text, char_start=45, char_end=102)'
  },
  {
    id: 2,
    name: 'Extract',
    badge: 'Stage 2',
    inputDesc: 'Structured blocks and parsed Reference bibliography objects',
    technology: 'Citation marker regex + Gemini claim extractor (with strict sentence-boundary validation)',
    outputDesc: 'Atomic claims strictly linked to cited reference IDs; unmatched markers isolated',
    icon: Split,
    exampleInput: 'Sentence: "Accuracy rose... [1]" + Ref: "[1] Rao, M. (2025)..."',
    exampleOutput: 'Claim(claim_id="c_01") mapped to ClaimReferenceLink(ref_id="r_01", marker="[1]")'
  },
  {
    id: 3,
    name: 'Resolve',
    badge: 'Stage 3',
    inputDesc: 'Raw bibliographic entries, titles, and DOIs',
    technology: 'Primary OpenAlex & Crossref metadata lookup; Semantic Scholar fallback',
    outputDesc: 'ResolvedSource with verified DOI, publication identity, and open-access PDF/URL',
    icon: Globe,
    exampleInput: 'Rao, M. (2025). Classification accuracy in an adult pilot.',
    exampleOutput: 'ResolvedSource(doi="10.1073/pnas.1319030111", coverage="full_text", is_oa=True)'
  },
  {
    id: 4,
    name: 'Retrieve',
    badge: 'Stage 4',
    inputDesc: 'Resolved source full text / abstract and target claim assertions',
    technology: 'BM25 and local sentence-transformers passage chunking & ranking',
    outputDesc: 'Top relevant verbatim passages with section metadata and recoverable locations',
    icon: Search,
    exampleInput: 'Claim: "Accuracy rose from 50% to 60%" vs. Paper Text',
    exampleOutput: 'Passage(passage_id="p_401", section="Results Table 2", verbatim="...rose from 50% to 60%...")'
  },
  {
    id: 5,
    name: 'Assess',
    badge: 'Stage 5',
    inputDesc: 'Atomic claim + target source passages + validation metadata',
    technology: 'Gemini classification or strict deterministic numerical comparator (polarity/metric/population matching)',
    outputDesc: 'Assessment verdict (Supported, Contradictory, or Unable to assess) with explanation & evidence IDs',
    icon: ShieldCheck,
    exampleInput: 'Claim assertion vs. Retrieved candidate passages',
    exampleOutput: 'Assessment(verdict=SUPPORTED, evidence_ids=["p_401"], confidence=0.90)'
  }
];

export function WorkflowSection() {
  const [activeStage, setActiveStage] = useState(1);
  const current = STAGES.find(s => s.id === activeStage) || STAGES[0];
  const CurrentIcon = current.icon;

  return (
    <section id="how-it-works" className="workflow-section" aria-labelledby="workflow-heading">
      <div className="section-container">
        <div className="section-header">
          <span className="section-eyebrow">UNDER THE HOOD</span>
          <h2 id="workflow-heading" className="section-title">
            The 5-Stage Verification Pipeline
          </h2>
          <p className="section-subtitle">
            Every manuscript passes through a strict 5-stage sequential pipeline where claims, sources, and verdicts maintain verifiable provenance.
          </p>
        </div>

        {/* Stage selection tabs */}
        <div className="pipeline-track" role="tablist" aria-label="Pipeline stages">
          {STAGES.map((s, idx) => {
            const Icon = s.icon;
            const isSelected = activeStage === s.id;
            const isPast = activeStage > s.id;
            return (
              <React.Fragment key={s.id}>
                <button
                  type="button"
                  role="tab"
                  aria-selected={isSelected}
                  className={`pipeline-node ${isSelected ? 'selected' : ''} ${isPast ? 'past' : ''}`}
                  onClick={() => setActiveStage(s.id)}
                >
                  <div className="node-icon-wrapper">
                    <Icon size={18} />
                  </div>
                  <div className="node-info">
                    <span className="node-badge">{s.badge}</span>
                    <strong className="node-name">{s.name}</strong>
                  </div>
                </button>
                {idx < STAGES.length - 1 && (
                  <div className={`pipeline-connector ${activeStage > s.id ? 'connector-active' : ''}`} aria-hidden="true">
                    <span className="connector-dot" />
                  </div>
                )}
              </React.Fragment>
            );
          })}
        </div>

        {/* Selected Stage Detail Panel */}
        <div className="stage-detail-panel" role="tabpanel" aria-live="polite">
          <div className="stage-detail-header">
            <div className="stage-title-wrap">
              <span className="stage-indicator-pill">Stage {current.id} of 5</span>
              <h3>{current.name} Pipeline Stage</h3>
            </div>
            <div className="tech-badge">
              <Cpu size={14} />
              <span>{current.technology}</span>
            </div>
          </div>

          <div className="stage-io-grid">
            <div className="io-card io-input">
              <span className="io-label">STAGE INPUT</span>
              <p className="io-desc">{current.inputDesc}</p>
              <div className="code-example">
                <code>{current.exampleInput}</code>
              </div>
            </div>

            <div className="io-arrow-divider" aria-hidden="true">
              <ArrowRight size={20} />
            </div>

            <div className="io-card io-output">
              <span className="io-label">PRODUCED ARTIFACT (OUTPUT)</span>
              <p className="io-desc">{current.outputDesc}</p>
              <div className="code-example output-code">
                <code>{current.exampleOutput}</code>
              </div>
            </div>
          </div>

          <div className="stage-guarantee-note">
            <CheckCircle2 size={15} className="text-success" />
            <span>
              <strong>Contract guarantee:</strong> A missing source, network timeout, or provider failure never fabricates a negative verdict. If evidence cannot be retrieved, the pipeline abstains with <code>unable_to_assess</code>.
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}
