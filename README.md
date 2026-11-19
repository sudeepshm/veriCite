# veriCite

React frontend demo for **INNOVEDGE Problem 03: CiteVerify — Scientific Claim and Citation Verification System**.

A research workspace for inspecting academic claims, following citations, comparing illustrative evidence, recording human review, and exporting a transparent report.

## Run locally

Use Node.js 22.12+ (Node 24 recommended).

```bash
cd frontend
npm ci
npm run dev
```

Open the URL Vite prints. For production:

```bash
npm test
npm run build
npm run preview
```

Deploy `frontend/dist` to a static host. For Vercel choose root directory `frontend`, build command `npm run build`, output directory `dist`. No environment variables or API keys are needed for this demo. The existing academic discovery backend is preserved and is not called by this frontend demo. See [backend/README.md](backend/README.md) for its independent setup.

## Eight working frontend features

| # | Feature | What works now |
|---|---|---|
| 1 | Document input and candidate extraction | Paste text or upload TXT/Markdown up to 1 MB; extract sentences locally. Empty/unsupported inputs show errors. |
| 2 | Citation detection and mapping | Detect simple numeric `[1]` and author-year `(Smith, 2020)` citations; match entries under a References or Bibliography heading. |
| 3 | Verdict dashboard | Summary counts and six illustrative states: supported, partly supported, unsupported, contradictory, possibly outdated, unverified. |
| 4 | Evidence inspector and source trace | Select a claim to inspect its evidence paraphrase, explanation, uncertainty, mapped reference and DOI link when present. |
| 5 | Misleading-reference issue view | Sample flags demonstrate number overstatement, population mismatch, reversed conclusions and freshness review; custom inputs detect missing/unmatched references. |
| 6 | Search and verdict filtering | Filter results by status and search claims/reference text; clear empty results. |
| 7 | Human review and history | Add notes, mark reviewed or flag for follow-up; append timestamped decisions and persist the session in localStorage. |
| 8 | Verification report export | Download JSON with claims, evidence, explanations and complete review history; CSV includes all claims and their current demo verdicts. |

## Demo script (about 3 minutes)

1. Start on the preloaded active-learning sample and inspect dashboard counts.
2. Select the 30% claim. Explain why a real paper does not automatically support every number attributed to it.
3. Select the contradictory and population-mismatch claims; show the explanations.
4. Filter by a verdict and search for a phrase.
5. Add a reviewer note and flag a claim; inspect Review history and reload to show persistence.
6. Open References and follow the original publication DOI.
7. In Document, paste your own text with a References section and select Extract claims. These results are explicitly **Unverified**.
8. Export JSON and CSV; Load sample restores the showcase and clears current reviews.

## What is simulated vs real

The UI, file reading, extraction heuristics, citation matching, search, filters, review history, local persistence and downloads are real frontend behavior. Sample verdicts, confidence labels and evidence are **authored illustrative fixtures**, not live AI outputs or verbatim source quotations. The DOI points to a real publication, but this demo does not retrieve or validate its text. A confidence label is not a calibrated probability. Custom input always remains Unverified, even if it equals the sample text.

PDF, scanned PDF and DOCX parsing, live metadata lookups, evidence retrieval, semantic inference, authentication and cloud persistence are **not implemented**. Only plain TXT and Markdown uploads are accepted. The parser is a deliberately small heuristic: it does not support citation ranges, complex author lists, multiline bibliography entries or exhaustive scientific claim detection. Old publication dates alone do not make findings false.

Document text and reviews stay in this browser's localStorage; there is no upload server. Clear this site's browser storage to remove them. Exports contain document claims and reviewer notes. Google Fonts requests font assets; system font fallbacks work offline. Package installation requires network access; the running demo does not require research API access.

## APIs for the real product

**None are required for the current frontend demo.** A production backend should use:

| Service | Purpose | Access/configuration | Limitation |
|---|---|---|---|
| [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/) | Resolve DOI/title/author/year and validate bibliographic metadata. | Public metadata endpoints; identify the application and supply a contact email as appropriate. | Metadata is not evidence that a claim is true; coverage is incomplete. |
| [Unpaywall](https://unpaywall.org/products/api) | Find legal open-access locations for a resolved DOI. | Email parameter; backend configuration `UNPAYWALL_EMAIL`. | A link may be unavailable, inaccessible or insufficient for the specific claim. |
| [Semantic Scholar](https://www.semanticscholar.org/product/api) | Optional fallback discovery, references and related papers. | Request an API key where needed; server-side `SEMANTIC_SCHOLAR_API_KEY`. Respect current endpoint limits. | Abstracts and publication metadata do not replace full evidence. |
| [Gemini API](https://ai.google.dev/gemini-api/docs) | Extract structured claims and compare them to retrieved evidence passages. | Server-side `GEMINI_API_KEY`; choose a currently supported model after evaluation. | Model output must be validated and linked to actual passage spans; no evidence means abstain. |

Use **Crossref + Unpaywall + one LLM provider** for the first backend version. Semantic Scholar is optional, not a prerequisite. You do not need multiple LLM providers. Keep all provider keys on the server—never in React code or `VITE_*` variables. Pricing, quotas and model availability must be checked before integration.

## How to build the real platform

1. Keep this React workspace and replace the fixture/heuristic layer with a typed API adapter. Render explicit loading, partial success, unavailable source and retry states.
2. Implement a backend (FastAPI is a continuation of the existing discovery API in `backend/main.py`) to accept documents, enforce size/type limits and run background jobs. Parse PDF/DOCX with page and character offsets; use OCR for scanned pages.
3. Extract claims and citation mappings into structured JSON. Retain the exact original claim and its location. Use deterministic parsing plus an LLM, validated against a schema.
4. Resolve each reference with Crossref; compare title, authors, year and DOI rather than trusting the first search result. Return ambiguous matches for user review.
5. Use Unpaywall to obtain permitted source text, optionally use Semantic Scholar for discovery. Cache metadata and respect service limits. Safely validate fetched URLs and file types.
6. Retrieve relevant source passages and compare population, numeric values, direction, study design and limitations. Return supported/partly supported/unsupported/contradictory only when evidence is sufficient; otherwise return unverified. Freshness needs a dated search for later evidence.
7. Attach the original passage, page/section, source URL, retrieval time, reasoning and uncertainty to every verdict. Evaluate on a human-labeled set before treating confidence as meaningful.
8. Store projects, evidence and append-only review decisions in PostgreSQL; add authentication, document access controls and server-generated reports when needed.

Proposed API contract (design only, not implemented):

- `POST /api/documents` → document ID and extraction job ID.
- `GET /api/jobs/:id` → progress, partial results, errors.
- `GET /api/documents/:id/claims` → exact claim, location, citation mapping, status, evidence spans and uncertainty.
- `POST /api/claims/:id/reviews` → reviewer decision and note, appended to history.
- `GET /api/documents/:id/report` → report with provenance, limitations and history.

## Code layout

```text
frontend/
  index.html          Vite entry document
  package.json        React, React DOM, Lucide icons and Vite
  src/main.jsx        React App, Evidence inspector and Badge components
  src/styles.css      Responsive workspace styling
  src/engine.js       Pure extraction, sample data and export helpers
  src/engine.test.js  Node tests for parsing and report integrity
backend/              Existing discovery API; preserved, not connected to this demo
```

## Validation

Run `npm test` and `npm run build` inside `frontend`. Tests cover citation mapping, missing references, honest unverified results, sample status coverage, CSV escaping and report metadata. For manual acceptance: test all eight features, reload after review, upload unsupported/empty files, verify mobile layout, and inspect JSON/CSV exports. Human review never changes the scientific verdict automatically.
