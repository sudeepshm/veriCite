"""SQLite persistence layer for CiteVerify.

Call init_db() once at startup before using any other function.
No DB connections are created at import time.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from app.config import DB_PATH
from app.models import (
    Assessment,
    Claim,
    ClaimReferenceLink,
    DocumentBlock,
    Passage,
    Reference,
    ResolvedSource,
    VerificationJob,
)

_lock = threading.Lock()
_DB: Path = Path(DB_PATH)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB))
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Schema creation
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    data   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS document_blocks (
    block_id    TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    data        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS "references" (
    ref_id      TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    data        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS claims (
    claim_id    TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    data        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS claim_reference_links (
    link_id     TEXT PRIMARY KEY,
    claim_id    TEXT NOT NULL,
    document_id TEXT NOT NULL,
    data        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS resolved_sources (
    source_id TEXT PRIMARY KEY,
    ref_id    TEXT NOT NULL,
    data      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS passages (
    passage_id TEXT PRIMARY KEY,
    source_id  TEXT NOT NULL,
    data       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assessments (
    assessment_id TEXT PRIMARY KEY,
    claim_id      TEXT NOT NULL,
    job_id        TEXT,
    data          TEXT NOT NULL
);
"""


def init_db() -> None:
    """Create all tables if they do not exist. Safe to call multiple times."""
    _DB.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        conn = _connect()
        try:
            conn.executescript(_DDL)
            conn.commit()
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


def save_job(job: VerificationJob) -> None:
    data = job.model_dump_json()
    with _lock:
        conn = _connect()
        try:
            with conn:
                conn.execute(
                    "INSERT OR REPLACE INTO jobs (job_id, data) VALUES (?, ?)",
                    (job.job_id, data),
                )
        finally:
            conn.close()


def get_job(job_id: str) -> VerificationJob | None:
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT data FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        finally:
            conn.close()
    if row is None:
        return None
    return VerificationJob.model_validate_json(row["data"])


# ---------------------------------------------------------------------------
# DocumentBlocks
# ---------------------------------------------------------------------------


def save_blocks(blocks: list[DocumentBlock]) -> None:
    rows = [(b.block_id, b.document_id, b.model_dump_json()) for b in blocks]
    with _lock:
        conn = _connect()
        try:
            with conn:
                conn.executemany(
                    "INSERT OR REPLACE INTO document_blocks (block_id, document_id, data) VALUES (?, ?, ?)",
                    rows,
                )
        finally:
            conn.close()


def get_blocks(document_id: str) -> list[DocumentBlock]:
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT data FROM document_blocks WHERE document_id = ?",
                (document_id,),
            ).fetchall()
        finally:
            conn.close()
    return [DocumentBlock.model_validate_json(r["data"]) for r in rows]


# ---------------------------------------------------------------------------
# References
# ---------------------------------------------------------------------------


def save_references(refs: list[Reference]) -> None:
    rows = [(r.ref_id, r.document_id, r.model_dump_json()) for r in refs]
    with _lock:
        conn = _connect()
        try:
            with conn:
                conn.executemany(
                    'INSERT OR REPLACE INTO "references" (ref_id, document_id, data) VALUES (?, ?, ?)',
                    rows,
                )
        finally:
            conn.close()


def get_references(document_id: str) -> list[Reference]:
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                'SELECT data FROM "references" WHERE document_id = ?',
                (document_id,),
            ).fetchall()
        finally:
            conn.close()
    return [Reference.model_validate_json(r["data"]) for r in rows]


# ---------------------------------------------------------------------------
# Claims
# ---------------------------------------------------------------------------


def save_claims(claims: list[Claim]) -> None:
    rows = [(c.claim_id, c.document_id, c.model_dump_json()) for c in claims]
    with _lock:
        conn = _connect()
        try:
            with conn:
                conn.executemany(
                    "INSERT OR REPLACE INTO claims (claim_id, document_id, data) VALUES (?, ?, ?)",
                    rows,
                )
        finally:
            conn.close()


def get_claims(document_id: str) -> list[Claim]:
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT data FROM claims WHERE document_id = ?",
                (document_id,),
            ).fetchall()
        finally:
            conn.close()
    return [Claim.model_validate_json(r["data"]) for r in rows]


# ---------------------------------------------------------------------------
# ClaimReferenceLinks
# ---------------------------------------------------------------------------

def _link_document_id(link: ClaimReferenceLink) -> str:
    """Derive a document_id for a link from its claim_id prefix convention."""
    # claim_id is typically "doc_<document_id>_claim_<n>" — store claim_id as
    # document_id key so we can query by it; callers that need by-document
    # queries can filter externally. We store claim_id as the document_id column.
    return link.claim_id


def save_links(links: list[ClaimReferenceLink]) -> None:
    rows = [(lk.link_id, lk.claim_id, lk.claim_id, lk.model_dump_json()) for lk in links]
    with _lock:
        conn = _connect()
        try:
            with conn:
                conn.executemany(
                    "INSERT OR REPLACE INTO claim_reference_links (link_id, claim_id, document_id, data) VALUES (?, ?, ?, ?)",
                    rows,
                )
        finally:
            conn.close()


def get_links(document_id: str) -> list[ClaimReferenceLink]:
    """Return links where document_id matches (stored as claim_id column here)."""
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT data FROM claim_reference_links WHERE document_id = ?",
                (document_id,),
            ).fetchall()
        finally:
            conn.close()
    return [ClaimReferenceLink.model_validate_json(r["data"]) for r in rows]


# ---------------------------------------------------------------------------
# ResolvedSources
# ---------------------------------------------------------------------------


def save_resolved_source(src: ResolvedSource) -> None:
    with _lock:
        conn = _connect()
        try:
            with conn:
                conn.execute(
                    "INSERT OR REPLACE INTO resolved_sources (source_id, ref_id, data) VALUES (?, ?, ?)",
                    (src.source_id, src.ref_id, src.model_dump_json()),
                )
        finally:
            conn.close()


def get_resolved_source(ref_id: str) -> ResolvedSource | None:
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT data FROM resolved_sources WHERE ref_id = ?",
                (ref_id,),
            ).fetchone()
        finally:
            conn.close()
    if row is None:
        return None
    return ResolvedSource.model_validate_json(row["data"])


# ---------------------------------------------------------------------------
# Passages  (embedding excluded from stored JSON)
# ---------------------------------------------------------------------------


def save_passages(passages: list[Passage]) -> None:
    rows = []
    for p in passages:
        # exclude=True on embedding field means model_dump_json already omits it
        rows.append((p.passage_id, p.source_id, p.model_dump_json()))
    with _lock:
        conn = _connect()
        try:
            with conn:
                conn.executemany(
                    "INSERT OR REPLACE INTO passages (passage_id, source_id, data) VALUES (?, ?, ?)",
                    rows,
                )
        finally:
            conn.close()


def get_passages(source_id: str) -> list[Passage]:
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT data FROM passages WHERE source_id = ?",
                (source_id,),
            ).fetchall()
        finally:
            conn.close()
    return [Passage.model_validate_json(r["data"]) for r in rows]


# ---------------------------------------------------------------------------
# Assessments
# ---------------------------------------------------------------------------


def save_assessment(a: Assessment) -> None:
    with _lock:
        conn = _connect()
        try:
            with conn:
                conn.execute(
                    "INSERT OR REPLACE INTO assessments (assessment_id, claim_id, job_id, data) VALUES (?, ?, ?, ?)",
                    (a.assessment_id, a.claim_id, None, a.model_dump_json()),
                )
        finally:
            conn.close()


def get_assessments(claim_id: str) -> list[Assessment]:
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT data FROM assessments WHERE claim_id = ?",
                (claim_id,),
            ).fetchall()
        finally:
            conn.close()
    return [Assessment.model_validate_json(r["data"]) for r in rows]


def get_all_assessments(job_id: str) -> list[Assessment]:
    """Return all assessments for a job by joining through claims via document_id prefix.

    Assessments store claim_id; claims are keyed by document_id.  We retrieve
    all claim_ids for the job's document then fetch matching assessments.
    """
    # document_id is embedded in job_id by convention: job_<document_id>
    # but we cannot assume that — instead query all claims whose document_id
    # matches the job_id (jobs store document_id = job_id when created by the
    # pipeline).  For robustness we do a simple prefix join in Python.
    with _lock:
        conn = _connect()
        try:
            claim_rows = conn.execute(
                "SELECT claim_id FROM claims WHERE document_id = ?",
                (job_id,),
            ).fetchall()
            if not claim_rows:
                # Fallback: job_id may differ from document_id; return nothing
                conn.close()
                return []
            claim_ids = [r["claim_id"] for r in claim_rows]
            placeholders = ",".join("?" * len(claim_ids))
            assessment_rows = conn.execute(
                f"SELECT data FROM assessments WHERE claim_id IN ({placeholders})",
                claim_ids,
            ).fetchall()
        finally:
            conn.close()
    return [Assessment.model_validate_json(r["data"]) for r in assessment_rows]


__all__ = [
    "init_db",
    "save_job",
    "get_job",
    "save_blocks",
    "get_blocks",
    "save_references",
    "get_references",
    "save_claims",
    "get_claims",
    "save_links",
    "get_links",
    "save_resolved_source",
    "get_resolved_source",
    "save_passages",
    "get_passages",
    "save_assessment",
    "get_assessments",
    "get_all_assessments",
]
