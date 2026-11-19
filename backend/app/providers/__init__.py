"""Local helpers for CiteVerify.
External LLM APIs (Gemini, Groq, OpenAI) have been removed in Crossref-only mode.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def extract_claims_gemini(*args, **kwargs) -> list[dict]:
    """Stub kept for test fixture compatibility; always returns empty list in Crossref-only mode."""
    return []


async def classify_claim_gemini(*args, **kwargs) -> dict:
    """Stub kept for test fixture compatibility; always returns unable_to_assess."""
    return {
        "verdict": None,
        "evidence_passage_ids": [],
        "explanation": "External LLM APIs are disabled in Crossref-only mode.",
        "issue_flags": [],
    }


__all__ = [
    "extract_claims_gemini",
    "classify_claim_gemini",
]
