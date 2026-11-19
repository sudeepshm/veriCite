"""Pydantic models for the CiteVerify pipeline."""
from __future__ import annotations

import enum
from datetime import datetime

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class BlockType(str, enum.Enum):
    text = "text"
    table = "table"
    heading = "heading"
    caption = "caption"
    bibliography = "bibliography"


class MappingStatus(str, enum.Enum):
    mapped = "mapped"
    ambiguous = "ambiguous"
    unmatched = "unmatched"


class IdentityStatus(str, enum.Enum):
    matched = "matched"
    ambiguous = "ambiguous"
    unresolved = "unresolved"
    metadata_mismatch = "metadata_mismatch"
    lookup_failed = "lookup_failed"


class CoverageStatus(str, enum.Enum):
    full_text = "full_text"
    partial_text = "partial_text"
    abstract_only = "abstract_only"
    unavailable = "unavailable"


class AssessmentStatus(str, enum.Enum):
    assessed = "assessed"
    unable_to_assess = "unable_to_assess"
    failed = "failed"


class SemanticVerdict(str, enum.Enum):
    SUPPORTED = "SUPPORTED"
    PARTLY_SUPPORTED = "PARTLY_SUPPORTED"
    CONTRADICTORY = "CONTRADICTORY"
    UNSUPPORTED = "UNSUPPORTED"


class HumanReviewStatus(str, enum.Enum):
    pending = "pending"
    reviewed = "reviewed"
    flagged = "flagged"


class JobState(str, enum.Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


# ---------------------------------------------------------------------------
# Pipeline models
# ---------------------------------------------------------------------------


class DocumentBlock(BaseModel):
    block_id: str
    document_id: str
    block_type: BlockType
    text: str
    section: str | None = None
    page: int | None = None
    char_start: int | None = None
    char_end: int | None = None


class Reference(BaseModel):
    ref_id: str
    document_id: str
    raw_entry: str
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    doi: str | None = None
    raw_marker: str | None = None


class Claim(BaseModel):
    claim_id: str
    document_id: str
    block_id: str
    original_span: str
    normalized_text: str
    char_start: int | None = None
    char_end: int | None = None


class ClaimReferenceLink(BaseModel):
    link_id: str
    claim_id: str
    ref_id: str
    citation_marker: str
    marker_char_start: int | None = None
    marker_char_end: int | None = None
    citation_group_id: str | None = None
    mapping_status: MappingStatus


class ResolvedSource(BaseModel):
    source_id: str
    ref_id: str
    canonical_doi: str | None = None
    openalex_id: str | None = None
    s2_id: str | None = None
    matched_title: str | None = None
    matched_authors: list[str] = Field(default_factory=list)
    matched_year: int | None = None
    identity_status: IdentityStatus
    source_url: str | None = None
    coverage: CoverageStatus
    is_retracted: bool = False
    retraction_note: str | None = None
    age_flag: bool = False


class Passage(BaseModel):
    passage_id: str
    source_id: str
    verbatim_text: str
    section: str | None = None
    page: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    table_context: str | None = None
    embedding: list[float] | None = Field(default=None, exclude=True)


class Assessment(BaseModel):
    assessment_id: str
    claim_id: str
    ref_id: str
    assessment_status: AssessmentStatus
    semantic_verdict: SemanticVerdict | None = None
    evidence_passage_ids: list[str] = Field(default_factory=list)
    explanation: str
    issue_flags: list[str] = Field(default_factory=list)
    human_review_status: HumanReviewStatus = HumanReviewStatus.pending
    confidence_score: float | None = None
    confidence_basis: str | None = None


class VerificationJob(BaseModel):
    job_id: str
    input_filename: str | None = None
    input_format: str | None = None
    job_state: JobState = JobState.queued
    current_stage: int | None = Field(default=None, ge=1, le=5)
    report: dict | None = None
    error_message: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class VerificationReport(BaseModel):
    job_id: str
    document_id: str | None = None
    total_claims: int
    total_references: int
    total_pairs: int
    claims: list[Claim] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)
    links: list[ClaimReferenceLink] = Field(default_factory=list)
    sources: list[ResolvedSource] = Field(default_factory=list)
    passages: list[Passage] = Field(default_factory=list)
    assessments: list[Assessment] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    stage_errors: list[str] = Field(default_factory=list)


__all__ = [
    # Enums
    "BlockType",
    "MappingStatus",
    "IdentityStatus",
    "CoverageStatus",
    "AssessmentStatus",
    "SemanticVerdict",
    "HumanReviewStatus",
    "JobState",
    # Models
    "DocumentBlock",
    "Reference",
    "Claim",
    "ClaimReferenceLink",
    "ResolvedSource",
    "Passage",
    "Assessment",
    "VerificationJob",
    "VerificationReport",
]
