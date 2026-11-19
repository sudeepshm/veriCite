"""Aggregate findings, provenance and coverage into a manuscript report."""
from __future__ import annotations

import collections

from app.models import (
    VerificationReport,
    Assessment,
    AssessmentStatus,
    SemanticVerdict,
    Claim,
    Reference,
    ClaimReferenceLink,
    ResolvedSource,
    IdentityStatus,
)


def build_report(
    job_id: str,
    document_id: str | None,
    claims: list[Claim],
    refs: list[Reference],
    links: list[ClaimReferenceLink],
    sources: list[ResolvedSource],
    assessments: list[Assessment],
    stage_errors: list[str],
) -> VerificationReport:
    """Build the final VerificationReport for a completed pipeline run.

    Args:
        job_id:        The pipeline job identifier.
        document_id:   The ingested document identifier (may be None on early failure).
        claims:        All claims extracted in Stage 2.
        refs:          All references extracted in Stage 2.
        links:         All claim–reference links from Stage 2.
        sources:       All resolved sources from Stage 3.
        assessments:   All assessments produced in Stage 5.
        stage_errors:  Accumulated non-fatal error messages from every stage.

    Returns:
        A populated VerificationReport instance.
    """
    # 1. Count unique entities ------------------------------------------------
    unique_claims: set[str] = {a.claim_id for a in assessments}
    unique_refs: set[str] = {a.ref_id for a in assessments}

    # 2. Build issues list ----------------------------------------------------
    issues: list[str] = []

    # 2a. Issue flags per assessment
    for assessment in assessments:
        for flag in assessment.issue_flags:
            issues.append(
                f"Claim {assessment.claim_id} \u00d7 Ref {assessment.ref_id}: {flag}"
            )

    # Build a quick lookup: ref_id → ResolvedSource
    source_by_ref: dict[str, ResolvedSource] = {src.ref_id: src for src in sources}

    # 2b. Source-level issues
    for ref in refs:
        src = source_by_ref.get(ref.ref_id)
        if src is None:
            # No resolved source at all — treat as unresolved
            issues.append(
                f"Ref {ref.ref_id}: Could not resolve source. Assessment: unable_to_assess."
            )
            continue

        if src.identity_status == IdentityStatus.metadata_mismatch:
            issues.append(
                f"Ref {src.ref_id}: DOI resolved to a different paper (metadata mismatch). "
                "No semantic verdict issued."
            )

        if src.is_retracted:
            issues.append(
                f"Ref {src.ref_id}: Source is retracted. See assessment for semantic verdict."
            )

        if src.identity_status == IdentityStatus.unresolved:
            issues.append(
                f"Ref {src.ref_id}: Could not resolve source. Assessment: unable_to_assess."
            )

    # 3. stage_errors are passed through directly (already collected upstream).

    # 4. Assemble and return report -------------------------------------------
    return VerificationReport(
        job_id=job_id,
        document_id=document_id,
        total_claims=len(claims) if claims else len(unique_claims),
        total_references=len(refs) if refs else len(unique_refs),
        total_pairs=len(assessments),
        claims=claims,
        references=refs,
        assessments=assessments,
        issues=issues,
        stage_errors=stage_errors,
    )


def summarize_verdicts(assessments: list[Assessment]) -> dict:
    """Return a frequency table of semantic verdicts across all assessments.

    Returns:
        A dict with keys: SUPPORTED, PARTLY_SUPPORTED, CONTRADICTORY, UNSUPPORTED,
        unable_to_assess, failed — each mapped to an integer count.
    """
    counts: dict[str, int] = {
        "SUPPORTED": 0,
        "PARTLY_SUPPORTED": 0,
        "CONTRADICTORY": 0,
        "UNSUPPORTED": 0,
        "unable_to_assess": 0,
        "failed": 0,
    }

    for assessment in assessments:
        if assessment.assessment_status == AssessmentStatus.unable_to_assess:
            counts["unable_to_assess"] += 1
        elif assessment.assessment_status == AssessmentStatus.failed:
            counts["failed"] += 1
        elif assessment.semantic_verdict is not None:
            verdict_key = assessment.semantic_verdict.value  # e.g. "SUPPORTED"
            if verdict_key in counts:
                counts[verdict_key] += 1

    return counts


__all__ = ["build_report", "summarize_verdicts"]
