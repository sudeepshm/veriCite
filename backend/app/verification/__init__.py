"""Stage 5: judge claim–paper pairs and validate cited evidence."""
from __future__ import annotations

import uuid
import logging
import re
from app.models import (
    Assessment,
    AssessmentStatus,
    Claim,
    CoverageStatus,
    HumanReviewStatus,
    IdentityStatus,
    Passage,
    ResolvedSource,
    SemanticVerdict,
)
from app.providers import classify_claim_gemini
from app.config import GEMINI_API_KEY

logger = logging.getLogger(__name__)


def _has_negation(text: str) -> bool:
    """Check if *text* contains explicit negation markers."""
    t = text.lower()
    neg_patterns = [
        r"\b(?:not|no|never|neither|nor|without|hardly|scarcely|cannot|can't)\b",
        r"\b(?:did|does|do|was|were|is|are|has|have|had)n['’]?t\b",
        r"\b(?:did|does|do|was|were|is|are|has|have|had)\s+not\b",
        r"\bfail(?:ed|s|ing)?\s+to\b",
    ]
    return any(re.search(pat, t) for pat in neg_patterns)


_INCREASE_WORDS = {"rose", "increased", "increase", "gain", "gained", "grew", "growth", "higher", "improved"}
_DECREASE_WORDS = {"fell", "decreased", "decrease", "dropped", "drop", "declined", "decline", "lower", "reduced", "reduction", "loss"}


def _get_direction(text: str) -> str | None:
    words = set(re.findall(r"\b[a-z]+\b", text.lower()))
    has_inc = bool(words & _INCREASE_WORDS)
    has_dec = bool(words & _DECREASE_WORDS)
    if has_inc and not has_dec:
        return "increase"
    if has_dec and not has_inc:
        return "decrease"
    return None


def _extract_metric_quantity(text: str, unit: str) -> float | None:
    """Extract the specific numeric value that binds directly to *unit*.

    If no number binds to the unit, or if the association is ambiguous, returns None.
    """
    t_lower = text.lower()
    if unit == "percentage points":
        # Match number directly associated with percentage points / percentage-point
        # e.g., "10 percentage points", "10-percentage-point", "gain was 10 percentage points"
        matches = re.findall(
            r"\b(\d+(?:\.\d+)?)\s*(?:-|–|\s)?(?:percentage points?|percentage-points?)\b",
            t_lower,
        )
        if len(matches) == 1:
            return float(matches[0])
        rev = re.findall(
            r"\b(?:percentage points?)\s*[:=]?\s*(\d+(?:\.\d+)?)\b",
            t_lower,
        )
        if len(rev) == 1 and not matches:
            return float(rev[0])
        return None

    if unit in ("%", "percent"):
        matches = re.findall(r"\b(\d+(?:\.\d+)?)\s*(?:%|percent)\b", t_lower)
        if len(matches) == 1:
            return float(matches[0])
        return None

    return None


async def assess_claim_reference_pair(
    claim: Claim,
    source: ResolvedSource,
    passages: list[Passage],
    is_retracted: bool = False,
) -> Assessment:
    """Assess whether the evidence in *passages* from *source* supports *claim*."""
    assessment_id = f"asm_{uuid.uuid4().hex[:12]}"
    issue_flags: list[str] = []

    if is_retracted or source.is_retracted:
        issue_flags.append("retracted_source")

    # If source could not be resolved or metadata mismatch
    if source.identity_status == IdentityStatus.metadata_mismatch:
        return Assessment(
            assessment_id=assessment_id,
            claim_id=claim.claim_id,
            ref_id=source.ref_id,
            assessment_status=AssessmentStatus.unable_to_assess,
            semantic_verdict=None,
            evidence_passage_ids=[],
            explanation="Source DOI resolved with metadata mismatch. Verification halted.",
            issue_flags=["metadata_mismatch", *issue_flags],
            human_review_status=HumanReviewStatus.pending,
            confidence_score=None,
            confidence_basis="Metadata mismatch prevents safe comparison.",
        )

    if source.identity_status in (IdentityStatus.unresolved, IdentityStatus.lookup_failed):
        return Assessment(
            assessment_id=assessment_id,
            claim_id=claim.claim_id,
            ref_id=source.ref_id,
            assessment_status=AssessmentStatus.unable_to_assess,
            semantic_verdict=None,
            evidence_passage_ids=[],
            explanation="Source reference could not be resolved to a known publication.",
            issue_flags=["unresolved_source", *issue_flags],
            human_review_status=HumanReviewStatus.pending,
            confidence_score=None,
            confidence_basis="Source reference unverified.",
        )

    # If no passages are available
    if not passages or source.coverage == CoverageStatus.unavailable:
        return Assessment(
            assessment_id=assessment_id,
            claim_id=claim.claim_id,
            ref_id=source.ref_id,
            assessment_status=AssessmentStatus.unable_to_assess,
            semantic_verdict=None,
            evidence_passage_ids=[],
            explanation="No text or abstract passages could be retrieved for this source.",
            issue_flags=["no_evidence_passages", *issue_flags],
            human_review_status=HumanReviewStatus.pending,
            confidence_score=None,
            confidence_basis="Passage retrieval yielded no usable text.",
        )

    # Format passages for classifier
    passage_dicts = [
        {
            "passage_id": p.passage_id,
            "text": p.verbatim_text,
            "section": p.section,
            "page": p.page,
        }
        for p in passages
    ]

    coverage_str = (
        source.coverage.value
        if hasattr(source.coverage, "value")
        else str(source.coverage)
    )
    source_title = source.matched_title or "Referenced publication"

    valid_source_passage_ids = {p.passage_id for p in passages}

    # Call Gemini classifier if API key is provided
    if GEMINI_API_KEY:
        try:
            res = await classify_claim_gemini(
                claim_text=claim.normalized_text,
                passages=passage_dicts,
                coverage=coverage_str,
                source_title=source_title,
            )
            raw_verdict = res.get("verdict")
            verdict = None
            if raw_verdict:
                try:
                    verdict = SemanticVerdict(raw_verdict.upper())
                except (ValueError, KeyError):
                    pass

            flags = list(set(issue_flags + res.get("issue_flags", [])))
            # Require at least one validated passage belonging to this designated source
            raw_passage_ids = res.get("evidence_passage_ids", [])
            passage_ids = [pid for pid in raw_passage_ids if pid in valid_source_passage_ids]
            explanation = res.get("explanation", "Verification completed.")

            confidence = 0.85 if source.coverage == CoverageStatus.full_text else 0.65
            if not verdict or not passage_ids:
                status = AssessmentStatus.unable_to_assess
                verdict = None
                passage_ids = []
            else:
                status = AssessmentStatus.assessed

            return Assessment(
                assessment_id=assessment_id,
                claim_id=claim.claim_id,
                ref_id=source.ref_id,
                assessment_status=status,
                semantic_verdict=verdict,
                evidence_passage_ids=passage_ids,
                explanation=explanation,
                issue_flags=flags,
                human_review_status=HumanReviewStatus.pending,
                confidence_score=confidence if status == AssessmentStatus.assessed else None,
                confidence_basis=f"Assessed via Gemini against {len(passages)} passages ({coverage_str}).",
            )
        except Exception as exc:
            logger.warning("Classification failed with error: %s", exc)

    # Fallback: strict numerical rule when Gemini is unavailable.
    # Only decide a verdict when metric, unit, population, and comparator match.
    c_lower = claim.normalized_text.lower()
    populations = ["adult pilot", "second trial", "pediatric pilot", "pilot study", "clinical trial"]
    claim_pop = next((p for p in populations if p in c_lower), None)

    metrics = [
        ("absolute accuracy gain", ["absolute accuracy gain", "accuracy gain"]),
        ("accuracy", ["accuracy", "classification accuracy"]),
    ]
    claim_metric = None
    for m_name, m_aliases in metrics:
        if any(a in c_lower for a in m_aliases):
            claim_metric = m_name
            break

    units = ["percentage points", "%", "percent"]
    claim_unit = next((u for u in units if u in c_lower), None)

    if claim_pop and claim_metric and claim_unit:
        for passage in passages:
            p_lower = passage.verbatim_text.lower()
            if claim_pop not in p_lower:
                continue

            if not any(a in p_lower for m_name, aliases in metrics if m_name == claim_metric for a in aliases):
                continue

            if claim_unit == "percentage points" and "percentage points" in p_lower:
                # Check polarity: if polarities conflict (e.g. "not 10 percentage points"), abstain from support
                if _has_negation(c_lower) != _has_negation(p_lower):
                    continue

                claim_val = _extract_metric_quantity(c_lower, claim_unit)
                passage_val = _extract_metric_quantity(p_lower, claim_unit)
                if claim_val is not None and passage_val is not None:
                    if claim_val == passage_val:
                        return Assessment(
                            assessment_id=assessment_id,
                            claim_id=claim.claim_id,
                            ref_id=source.ref_id,
                            assessment_status=AssessmentStatus.assessed,
                            semantic_verdict=SemanticVerdict.SUPPORTED,
                            evidence_passage_ids=[passage.passage_id],
                            explanation=f"Source passage confirms {claim_metric} of {passage_val:g} {claim_unit} in {claim_pop}: '{passage.verbatim_text.strip()}'.",
                            issue_flags=issue_flags,
                            human_review_status=HumanReviewStatus.pending,
                            confidence_score=0.9 if source.coverage == CoverageStatus.full_text else 0.7,
                            confidence_basis=f"Strict numerical comparator rule ({coverage_str}).",
                        )
                    else:
                        return Assessment(
                            assessment_id=assessment_id,
                            claim_id=claim.claim_id,
                            ref_id=source.ref_id,
                            assessment_status=AssessmentStatus.assessed,
                            semantic_verdict=SemanticVerdict.CONTRADICTORY,
                            evidence_passage_ids=[passage.passage_id],
                            explanation=f"Source reports {claim_metric} of {passage_val:g} {claim_unit} in {claim_pop}, contradicting the claimed {claim_val:g} {claim_unit}.",
                            issue_flags=issue_flags,
                            human_review_status=HumanReviewStatus.pending,
                            confidence_score=0.9 if source.coverage == CoverageStatus.full_text else 0.7,
                            confidence_basis=f"Strict numerical comparator rule ({coverage_str}).",
                        )

            rise_match_claim = re.search(r"(\d+)%?\s*(?:to|rose from \d+%\s*to)\s*(\d+)%?", c_lower)
            rise_match_pass = re.search(r"(\d+)%?\s*(?:to|rose from \d+%\s*to)\s*(\d+)%?", p_lower)
            if rise_match_claim and rise_match_pass:
                # Check polarity and direction
                if _has_negation(c_lower) != _has_negation(p_lower):
                    continue  # Opposing polarity; cannot establish polarity, abstain

                claim_dir = _get_direction(c_lower)
                pass_dir = _get_direction(p_lower)
                if claim_dir and pass_dir and claim_dir != pass_dir:
                    continue  # Direction conflict; abstain

                if rise_match_claim.groups() == rise_match_pass.groups():
                    return Assessment(
                        assessment_id=assessment_id,
                        claim_id=claim.claim_id,
                        ref_id=source.ref_id,
                        assessment_status=AssessmentStatus.assessed,
                        semantic_verdict=SemanticVerdict.SUPPORTED,
                        evidence_passage_ids=[passage.passage_id],
                        explanation=f"Source confirms accuracy rose from {rise_match_pass.group(1)}% to {rise_match_pass.group(2)}% in {claim_pop}: '{passage.verbatim_text.strip()}'.",
                        issue_flags=issue_flags,
                        human_review_status=HumanReviewStatus.pending,
                        confidence_score=0.9 if source.coverage == CoverageStatus.full_text else 0.7,
                        confidence_basis=f"Strict numerical comparator rule ({coverage_str}).",
                    )
                else:
                    return Assessment(
                        assessment_id=assessment_id,
                        claim_id=claim.claim_id,
                        ref_id=source.ref_id,
                        assessment_status=AssessmentStatus.assessed,
                        semantic_verdict=SemanticVerdict.CONTRADICTORY,
                        evidence_passage_ids=[passage.passage_id],
                        explanation=f"Source reports change from {rise_match_pass.group(1)}% to {rise_match_pass.group(2)}%, contradicting claim.",
                        issue_flags=issue_flags,
                        human_review_status=HumanReviewStatus.pending,
                        confidence_score=0.9 if source.coverage == CoverageStatus.full_text else 0.7,
                        confidence_basis=f"Strict numerical comparator rule ({coverage_str}).",
                    )

    # When classifier is unavailable and no strict numerical rule matches, return unable_to_assess
    return Assessment(
        assessment_id=assessment_id,
        claim_id=claim.claim_id,
        ref_id=source.ref_id,
        assessment_status=AssessmentStatus.unable_to_assess,
        semantic_verdict=None,
        evidence_passage_ids=[],
        explanation="Unable to assess: active classifier or exact quantitative comparator required.",
        issue_flags=issue_flags,
        human_review_status=HumanReviewStatus.pending,
        confidence_score=None,
        confidence_basis=f"No matching quantitative or semantic verification available ({coverage_str}).",
    )


__all__ = ["assess_claim_reference_pair"]
