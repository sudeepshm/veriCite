"""Acceptance test suite for Crossref-only mode."""
import unittest
from unittest.mock import patch, AsyncMock
import httpx

from app.models import (
    BlockType,
    Claim,
    CoverageStatus,
    DocumentBlock,
    IdentityStatus,
    Passage,
    Reference,
    ResolvedSource,
    SemanticVerdict,
    AssessmentStatus,
)
from app.resolution import resolve_reference, resolve_all_references
from app.retrieval import retrieve_source
from app.verification import assess_claim_reference_pair
from app.extraction import parse_references, extract_claims_and_links
from integrations.providers import search_all, open_access_lookup, crossref


class TestCrossrefOnlyAcceptance(unittest.IsolatedAsyncioTestCase):

    async def test_acceptance_1_outbound_requests_only_crossref(self):
        """1. Instrument outbound requests: only api.crossref.org is contacted."""
        requested_hosts = set()

        async def tracking_send(client_self, request, *args, **kwargs):
            requested_hosts.add(request.url.host)
            if "crossref.org" in request.url.host:
                return httpx.Response(
                    status_code=200,
                    json={"message": {"items": [], "total-results": 0}},
                    request=request,
                )
            return httpx.Response(status_code=403, request=request)

        with patch.object(httpx.AsyncClient, "send", tracking_send):
            # Run citation search
            await search_all("machine learning")

            # Run resolution
            ref = Reference(
                ref_id="r1",
                document_id="doc1",
                raw_marker="[1]",
                raw_entry="[1] Vaswani, A. Attention Is All You Need. 2017.",
                authors=["Vaswani, A."],
                title="Attention Is All You Need",
                year=2017,
                doi="10.5555/3295222.3295349",
            )
            async with httpx.AsyncClient() as client:
                await resolve_reference(ref, client)

        self.assertTrue(all("crossref.org" in h for h in requested_hosts),
                        f"Non-Crossref hosts contacted: {requested_hosts}")

    async def test_acceptance_2_ten_claims_same_doi_reuses_one_lookup(self):
        """2. Ten claims citing the same DOI reuse one successful metadata lookup."""
        refs = [
            Reference(
                ref_id=f"r{i}",
                document_id="doc1",
                raw_marker=f"[{i}]",
                raw_entry=f"[{i}] He, K. Deep Residual Learning. 2016.",
                authors=["He, K."],
                title="Deep Residual Learning",
                year=2016,
                doi="10.1109/CVPR.2016.90",
            )
            for i in range(1, 11)
        ]

        lookup_count = 0

        async def mocked_get(url, params=None, timeout=None):
            nonlocal lookup_count
            lookup_count += 1
            return httpx.Response(
                status_code=200,
                json={
                    "message": {
                        "title": ["Deep Residual Learning for Image Recognition"],
                        "author": [{"family": "He", "given": "Kaiming"}],
                        "published": {"date-parts": [[2016]]},
                        "DOI": "10.1109/CVPR.2016.90",
                    }
                },
                request=httpx.Request("GET", url),
            )

        with patch.object(httpx.AsyncClient, "get", side_effect=mocked_get):
            sources = await resolve_all_references(refs)

        self.assertEqual(len(sources), 10)
        self.assertEqual(lookup_count, 1, f"Expected 1 Crossref lookup, got {lookup_count}")

    async def test_acceptance_3_manuscript_extracts_3_claims_2_refs_3_links(self):
        """3. The existing manuscript fixture produces 3 claims, 2 bibliography entries, and 3 claim–reference links before external lookup."""
        from app.ingestion import ingest_document

        FIXTURE = """Classification results across two trials
Synthetic manuscript for offline testing

Findings
Accuracy rose from 50% to 60% in the adult pilot [1]. The absolute accuracy gain was 20 percentage points in the adult pilot [1]. In a second trial, accuracy fell by 5 percentage points [2].

References
[1] Rao, M. (2025). Accuracy in an adult pilot. Fixture Studies, 1, 1.
[2] Chen, L. (2024). Accuracy across two cohorts. Journal of Testing, 2, 4.
"""
        _, blocks, _ = await ingest_document(FIXTURE.encode("utf-8"), "manuscript.txt", "text/plain")
        refs = parse_references(blocks)
        claims, links, _ = await extract_claims_and_links(blocks, refs)

        self.assertEqual(len(claims), 3, "Must produce 3 claims")
        self.assertEqual(len(refs), 2, "Must produce 2 bibliography references")
        self.assertEqual(len(links), 3, "Must produce 3 claim-reference links")

    async def test_acceptance_4_matched_doi_no_readable_source_produces_unable_to_assess(self):
        """4. A matched DOI with no readable source text produces unable_to_assess."""
        claim = Claim(
            claim_id="c1",
            document_id="doc1",
            block_id="b1",
            original_span="Accuracy rose from 50% to 60%.",
            normalized_text="Accuracy rose from 50% to 60%.",
        )
        source = ResolvedSource(
            source_id="src1",
            ref_id="r1",
            canonical_doi="10.1234/nodoc",
            matched_title="Matched Title With No Document",
            matched_authors=["Author, A."],
            matched_year=2024,
            identity_status=IdentityStatus.matched,
            source_url=None,
            coverage=CoverageStatus.unavailable,
        )
        asm = await assess_claim_reference_pair(claim, source, passages=[])
        self.assertEqual(asm.assessment_status, AssessmentStatus.unable_to_assess)
        self.assertIsNone(asm.semantic_verdict)
        self.assertEqual(asm.evidence_passage_ids, [])

    async def test_acceptance_5_crossref_outage_produces_retryable_lookup_failed(self):
        """5. A Crossref outage produces a retryable lookup failure. It must never mark a reference fabricated or unsupported."""
        ref = Reference(
            ref_id="r1",
            document_id="doc1",
            raw_marker="[1]",
            raw_entry="[1] Smith, J. Some Paper. 2020.",
            title="Some Paper",
            authors=["Smith, J."],
            year=2020,
            doi="10.1000/182",
        )

        async def timeout_get(url, params=None, timeout=None):
            raise httpx.ReadTimeout("Crossref service unavailable")

        with patch.object(httpx.AsyncClient, "get", side_effect=timeout_get):
            async with httpx.AsyncClient() as client:
                src = await resolve_reference(ref, client)

        self.assertEqual(src.identity_status, IdentityStatus.lookup_failed)
        self.assertNotEqual(src.identity_status, IdentityStatus.unresolved)

    async def test_acceptance_6_source_explicitly_denying_claim_never_supported(self):
        """6. A source explicitly denying a claim must never produce SUPPORTED."""
        claim = Claim(
            claim_id="c1",
            document_id="doc1",
            block_id="b1",
            original_span="Accuracy rose from 50% to 60% in the adult pilot [1].",
            normalized_text="Accuracy rose from 50% to 60% in the adult pilot [1].",
        )
        source = ResolvedSource(
            source_id="src1",
            ref_id="r1",
            canonical_doi="10.1234/test",
            matched_title="Adult Pilot Study",
            matched_authors=["Rao, M."],
            matched_year=2025,
            identity_status=IdentityStatus.matched,
            coverage=CoverageStatus.full_text,
        )
        passage = Passage(
            passage_id="p1",
            source_id="src1",
            verbatim_text="Accuracy did not rise from 50% to 60% in the adult pilot.",
        )
        asm = await assess_claim_reference_pair(claim, source, passages=[passage])
        self.assertNotEqual(asm.semantic_verdict, SemanticVerdict.SUPPORTED)

    async def test_acceptance_7_reading_completed_report_makes_zero_external_requests(self):
        """7. Reading a completed report makes zero external requests."""
        from app.database import init_db, save_job, get_job
        from app.pipeline import create_job
        from app.models import VerificationReport, JobState

        init_db()
        job = create_job("manuscript.txt", "text/plain")
        sample_report = VerificationReport(
            job_id=job.job_id,
            document_id="doc1",
            total_claims=1,
            total_references=1,
            total_pairs=1,
            claims=[],
            references=[],
            links=[],
            sources=[],
            passages=[],
            assessments=[],
            stage_errors=[],
        )
        completed_job = job.model_copy(update={"job_state": JobState.completed, "report": sample_report.model_dump()})
        save_job(completed_job)

        with patch.object(httpx.AsyncClient, "send", side_effect=RuntimeError("Outbound HTTP call detected!")):
            loaded_job = get_job(job.job_id)
            self.assertIsNotNone(loaded_job)
            self.assertIsNotNone(loaded_job.report)
            self.assertEqual(loaded_job.report["job_id"], job.job_id)
            self.assertEqual(loaded_job.report["total_claims"], 1)


if __name__ == "__main__":
    unittest.main()
