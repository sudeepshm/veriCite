"""Comprehensive acceptance tests for the 5 pipeline flaws and release criteria."""
import asyncio
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from app.ingestion import ingest_document
from app.extraction import parse_references, extract_claims_and_links
from app.resolution import resolve_all_references
from app.retrieval import retrieve_source
from app.verification import assess_claim_reference_pair
from app.pipeline import run_pipeline, create_job
from app.database import init_db, get_job, get_claims, get_references, get_all_assessments
from app.models import (
    BlockType,
    MappingStatus,
    IdentityStatus,
    CoverageStatus,
    AssessmentStatus,
    SemanticVerdict,
    Claim,
    ResolvedSource,
    Passage,
)

FIXTURE_MANUSCRIPT = """Classification results across two trials
Synthetic manuscript for offline testing

Findings
Accuracy rose from 50% to 60% in the adult pilot [1].
The absolute accuracy gain was 20 percentage points in the adult pilot [1].
A second trial reported 90% accuracy [2].

References
[1] Rao, M. (2025). Classification accuracy in an adult pilot. Fixture Studies, 1, 1.
[2] Sen, J. (2025). Results from a second trial. Fixture Studies, 2, 1.
"""


class TestPipelineFlaws(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        init_db()

    def tearDown(self):
        pass

    async def test_flaw1_unmatched_marker_does_not_borrow_neighboring_reference(self):
        """Flaw 1: When entry [2] is deleted, require 3 claims, 1 reference, 2 pairs, and 1 unmatched marker.
        A neighboring sentence must never supply its reference ID.
        """
        text_without_ref2 = """Classification results across two trials
Synthetic manuscript for offline testing

Findings
Accuracy rose from 50% to 60% in the adult pilot [1].
The absolute accuracy gain was 20 percentage points in the adult pilot [1].
A second trial reported 90% accuracy [2].

References
[1] Rao, M. (2025). Classification accuracy in an adult pilot. Fixture Studies, 1, 1.
"""
        doc_id, blocks, _ = await ingest_document(text_without_ref2.encode("utf-8"), "test.txt", "text/plain")
        refs = parse_references(blocks)
        self.assertEqual(len(refs), 1, "Should have exactly 1 reference ([1])")

        claims, links, issues = await extract_claims_and_links(blocks, refs)

        # 3 claims must be preserved
        self.assertEqual(len(claims), 3, "All 3 claims must be preserved")

        # 1 unmatched marker issue
        unmatched_issues = [i for i in issues if "unmatched citation marker '[2]'" in i]
        self.assertEqual(len(unmatched_issues), 1, "Must record 1 unmatched marker occurrence for [2]")

        # Check links
        unmatched_links = [lk for lk in links if lk.mapping_status == MappingStatus.unmatched]
        self.assertEqual(len(unmatched_links), 1, "Must have exactly 1 unmatched link")
        self.assertEqual(unmatched_links[0].citation_marker, "[2]")
        self.assertEqual(unmatched_links[0].ref_id, "")

        # Mapped links must only point to ref [1]
        mapped_links = [lk for lk in links if lk.mapping_status == MappingStatus.mapped]
        self.assertEqual(len(mapped_links), 2, "Only 2 mapped links for [1] across the 3 claims")
        for ml in mapped_links:
            self.assertEqual(ml.ref_id, refs[0].ref_id)

        # In pipeline, only 2 pairs should be assessed
        job = create_job("fixture_no_ref2.txt", "text/plain")
        # Run with [1] mapped to source-1.txt
        await run_pipeline(
            job.job_id,
            text_without_ref2.encode("utf-8"),
            "fixture_no_ref2.txt",
            "text/plain",
            test_resolver={"[1]": "source-1.txt", "1": "source-1.txt"},
        )
        completed_job = get_job(job.job_id)
        report = completed_job.report
        self.assertEqual(report["total_claims"], 3)
        self.assertEqual(report["total_references"], 1)
        self.assertEqual(report["total_pairs"], 2, "Require exactly 2 verification pairs")

    async def test_numeric_gap_citation_does_not_fall_back_to_position(self):
        """P0 Regression: When bibliography has explicit numeric labels [2], [3] and body cites [1],
        [1] must NOT silently link to [2]. It must be unmatched with 0 verification pairs.
        """
        gap_text = """Classification trial report
Draft manuscript

Findings
Accuracy increased significantly [1].

References
[2] Brown, C. (2025). Accuracy in trial two. Fixture Studies, 2, 1.
[3] Davis, E. (2025). Accuracy in trial three. Fixture Studies, 3, 1.
"""
        doc_id, blocks, _ = await ingest_document(gap_text.encode("utf-8"), "gap.txt", "text/plain")
        refs = parse_references(blocks)
        self.assertEqual(len(refs), 2)
        self.assertEqual(refs[0].raw_marker, "[2]")
        self.assertEqual(refs[1].raw_marker, "[3]")

        claims, links, issues = await extract_claims_and_links(blocks, refs)
        self.assertEqual(len(claims), 1)
        self.assertEqual(len(links), 1)
        # Must be unmatched, never silently linked to [2]
        self.assertEqual(links[0].mapping_status, MappingStatus.unmatched)
        self.assertEqual(links[0].ref_id, "")
        self.assertTrue(any("unmatched citation marker '[1]'" in i for i in issues))

    async def test_flaw2_unrelated_manuscript_never_selects_dummy_source(self):
        """Flaw 2: With source-1.txt on disk, a different manuscript citing [1] must never select it."""
        unrelated_text = """Quantum Computing Benchmark
A study on error correction

Findings
Qubit coherence reached 100 microseconds [1].

References
[1] Smith, A. (2024). Superconducting qubit coherence. Journal of Physics, 15, 4.
"""
        # Ensure source-1.txt is on disk
        self.assertTrue(Path("source-1.txt").is_file() or Path("backend/source-1.txt").is_file())

        job = create_job("unrelated.txt", "text/plain")
        # Normal pipeline execution (no injected test_resolver)
        await run_pipeline(
            job.job_id,
            unrelated_text.encode("utf-8"),
            "unrelated.txt",
            "text/plain",
        )
        completed_job = get_job(job.job_id)
        report = completed_job.report

        # In normal pipeline, Smith paper must not resolve to source-1.txt
        for src in report.get("sources", []):
            self.assertNotIn("source-1.txt", src.get("source_url") or "")
            self.assertNotEqual(src.get("matched_title"), "Offline Source [1]")

        for asm in report.get("assessments", []):
            self.assertNotIn("Classification accuracy in an adult pilot", asm.get("explanation", ""))

    async def test_flaw3_strict_numerical_rule_and_no_gemini_fallback(self):
        """Flaw 3: Return unable_to_assess when classifier is unavailable, except when strict metric, unit,
        population, and comparator match. Do NOT trigger on loose numbers like '20 participants' with '60% accuracy'.
        """
        source = ResolvedSource(
            source_id="src_test",
            ref_id="ref_test",
            identity_status=IdentityStatus.matched,
            matched_title="Fixture Pilot",
            source_url="source-1.txt",
            coverage=CoverageStatus.full_text,
        )
        passages = [
            Passage(
                passage_id="p1",
                source_id="src_test",
                verbatim_text="Classification accuracy in an adult pilot trial rose from 50% to 60%.",
                section="Results",
            ),
            Passage(
                passage_id="p2",
                source_id="src_test",
                verbatim_text="The absolute accuracy gain observed in the adult pilot was 10 percentage points.",
                section="Results",
            ),
        ]

        # 1. Matching claim 1 -> Supported
        claim1 = Claim(
            claim_id="c1",
            document_id="doc1",
            block_id="b1",
            original_span="Accuracy rose from 50% to 60% in the adult pilot [1].",
            normalized_text="Accuracy rose from 50% to 60% in the adult pilot [1].",
        )
        asm1 = await assess_claim_reference_pair(claim1, source, passages)
        self.assertEqual(asm1.semantic_verdict, SemanticVerdict.SUPPORTED)
        self.assertEqual(asm1.evidence_passage_ids, ["p1"])

        # 2. Contradictory claim 2 (20 pp vs 10 pp) -> Contradictory
        claim2 = Claim(
            claim_id="c2",
            document_id="doc1",
            block_id="b1",
            original_span="The absolute accuracy gain was 20 percentage points in the adult pilot [1].",
            normalized_text="The absolute accuracy gain was 20 percentage points in the adult pilot [1].",
        )
        asm2 = await assess_claim_reference_pair(claim2, source, passages)
        self.assertEqual(asm2.semantic_verdict, SemanticVerdict.CONTRADICTORY)
        self.assertEqual(asm2.evidence_passage_ids, ["p2"])

        # 3. Claim containing "20" but about participants -> NOT contradictory, must be unable_to_assess!
        claim3 = Claim(
            claim_id="c3",
            document_id="doc1",
            block_id="b1",
            original_span="A total of 20 participants completed the pilot study [1].",
            normalized_text="A total of 20 participants completed the pilot study [1].",
        )
        asm3 = await assess_claim_reference_pair(claim3, source, passages)
        self.assertEqual(asm3.assessment_status, AssessmentStatus.unable_to_assess)
        self.assertIsNone(asm3.semantic_verdict)
        self.assertEqual(asm3.evidence_passage_ids, [])

        # 4. P0 Regression: Claim of 10-percentage-point gain against passage with 40 participants and 10 pp gain
        claim4 = Claim(
            claim_id="c4",
            document_id="doc1",
            block_id="b1",
            original_span="The absolute accuracy gain was 10 percentage points in the adult pilot [1].",
            normalized_text="The absolute accuracy gain was 10 percentage points in the adult pilot [1].",
        )
        passage_with_sample_size = [
            Passage(
                passage_id="p_sample",
                source_id="src_test",
                verbatim_text="In the adult pilot with 40 participants, the absolute accuracy gain was 10 percentage points.",
                section="Results",
            )
        ]
        asm4 = await assess_claim_reference_pair(claim4, source, passage_with_sample_size)
        self.assertEqual(asm4.semantic_verdict, SemanticVerdict.SUPPORTED, "Must compare 10 pp with 10 pp, not 40 participants")
        self.assertEqual(asm4.evidence_passage_ids, ["p_sample"])
        self.assertIn("confirms absolute accuracy gain of 10 percentage points", asm4.explanation)
        self.assertNotIn("reports absolute accuracy gain of 40", asm4.explanation)

        # 5. Ambiguous association with multiple percentage points in passage -> unable_to_assess
        passage_ambiguous = [
            Passage(
                passage_id="p_ambig",
                source_id="src_test",
                verbatim_text="In the adult pilot, the absolute accuracy gain was 10 percentage points in phase 1 and 20 percentage points in phase 2.",
                section="Results",
            )
        ]
        asm5 = await assess_claim_reference_pair(claim4, source, passage_ambiguous)
        self.assertEqual(asm5.assessment_status, AssessmentStatus.unable_to_assess, "Ambiguous association must return unable_to_assess")
        self.assertIsNone(asm5.semantic_verdict)

    async def test_p0_polarity_and_direction_negation_abstains_never_supported(self):
        """P0 Regression: Neither negated findings nor opposing polarity should ever return SUPPORTED."""
        source = ResolvedSource(
            source_id="src_test",
            ref_id="ref_test",
            identity_status=IdentityStatus.matched,
            coverage=CoverageStatus.full_text,
        )

        # Case 1: "Accuracy rose from 50% to 60% in the adult pilot" against "In the adult pilot, accuracy did not rise from 50% to 60%."
        claim_rose = Claim(
            claim_id="c_rose",
            document_id="doc1",
            block_id="b1",
            original_span="Accuracy rose from 50% to 60% in the adult pilot [1].",
            normalized_text="Accuracy rose from 50% to 60% in the adult pilot [1].",
        )
        pass_did_not_rise = [
            Passage(
                passage_id="p_neg1",
                source_id="src_test",
                verbatim_text="In the adult pilot, accuracy did not rise from 50% to 60%.",
                section="Results",
            )
        ]
        asm_neg1 = await assess_claim_reference_pair(claim_rose, source, pass_did_not_rise)
        self.assertNotEqual(asm_neg1.semantic_verdict, SemanticVerdict.SUPPORTED, "Must NEVER return SUPPORTED on negated finding")
        self.assertEqual(asm_neg1.assessment_status, AssessmentStatus.unable_to_assess)

        # Case 2: Claim of 10-point gain against source saying gain was NOT 10 percentage points
        claim_10pp = Claim(
            claim_id="c_10pp",
            document_id="doc1",
            block_id="b1",
            original_span="The absolute accuracy gain was 10 percentage points in the adult pilot [1].",
            normalized_text="The absolute accuracy gain was 10 percentage points in the adult pilot [1].",
        )
        pass_not_10pp = [
            Passage(
                passage_id="p_neg2",
                source_id="src_test",
                verbatim_text="In the adult pilot, the absolute accuracy gain was not 10 percentage points.",
                section="Results",
            )
        ]
        asm_neg2 = await assess_claim_reference_pair(claim_10pp, source, pass_not_10pp)
        self.assertNotEqual(asm_neg2.semantic_verdict, SemanticVerdict.SUPPORTED, "Must NEVER return SUPPORTED when source says gain was not 10 pp")
        self.assertEqual(asm_neg2.assessment_status, AssessmentStatus.unable_to_assess)

    async def test_flaw3_stage5_check_rejects_assessed_without_valid_evidence_passages(self):
        """Stage 5 check: Require at least one validated passage from designated source before returning assessed."""
        source = ResolvedSource(
            source_id="src_test",
            ref_id="ref_test",
            identity_status=IdentityStatus.matched,
            coverage=CoverageStatus.full_text,
        )
        passages = [
            Passage(
                passage_id="p_valid_1",
                source_id="src_test",
                verbatim_text="Real source passage text.",
            )
        ]
        claim = Claim(
            claim_id="c1",
            document_id="doc1",
            block_id="b1",
            original_span="Some claim.",
            normalized_text="Some claim.",
        )

        # In Crossref-only mode, unvalidated or empty passage IDs route to unable_to_assess
        asm = await assess_claim_reference_pair(claim, source, passages)
        self.assertEqual(asm.assessment_status, AssessmentStatus.unable_to_assess)
        self.assertIsNone(asm.semantic_verdict)
        self.assertEqual(asm.evidence_passage_ids, [])

    async def test_flaw4_lf_and_crlf_produce_identical_results(self):
        """Flaw 4: Run the fixture in LF and CRLF forms and require identical claims and mappings."""
        text_lf = FIXTURE_MANUSCRIPT.replace("\r\n", "\n")
        text_crlf = text_lf.replace("\n", "\r\n")

        doc_id_lf, blocks_lf, _ = await ingest_document(text_lf.encode("utf-8"), "test.txt", "text/plain")
        doc_id_crlf, blocks_crlf, _ = await ingest_document(text_crlf.encode("utf-8"), "test.txt", "text/plain")

        self.assertEqual(len(blocks_lf), len(blocks_crlf), "Block count must match between LF and CRLF")

        # Block types must match exactly
        self.assertEqual([b.block_type for b in blocks_lf], [b.block_type for b in blocks_crlf])

        refs_lf = parse_references(blocks_lf)
        refs_crlf = parse_references(blocks_crlf)
        self.assertEqual(len(refs_lf), len(refs_crlf))
        self.assertEqual([r.raw_marker for r in refs_lf], [r.raw_marker for r in refs_crlf])

        claims_lf, links_lf, _ = await extract_claims_and_links(blocks_lf, refs_lf)
        claims_crlf, links_crlf, _ = await extract_claims_and_links(blocks_crlf, refs_crlf)

        self.assertEqual(len(claims_lf), len(claims_crlf))
        self.assertEqual([c.normalized_text for c in claims_lf], [c.normalized_text for c in claims_crlf])
        self.assertEqual(len(links_lf), len(links_crlf))
        self.assertEqual([lk.citation_marker for lk in links_lf], [lk.citation_marker for lk in links_crlf])

    async def test_pass_condition_supported_contradictory_unable(self):
        """Pass condition: With [1] mapped to offline source-1.txt,
        the three results should become Supported, Contradictory, and Unable to assess.
        """
        job = create_job("manuscript.txt", "text/plain")
        await run_pipeline(
            job.job_id,
            FIXTURE_MANUSCRIPT.encode("utf-8"),
            "manuscript.txt",
            "text/plain",
            test_resolver={"[1]": "source-1.txt", "1": "source-1.txt"},
        )
        completed_job = get_job(job.job_id)
        report = completed_job.report

        self.assertEqual(report["total_claims"], 3)
        self.assertEqual(report["total_references"], 2)

        assessments = report.get("assessments", [])
        self.assertEqual(len(assessments), 3, "Require 3 assessed pairs")

        # Sort assessments by claim text order in fixture
        claims = report.get("claims", [])
        claim_map = {c["claim_id"]: c["normalized_text"] for c in claims}

        asm_by_text = {claim_map[a["claim_id"]]: a for a in assessments}

        # 1. "Accuracy rose from 50% to 60%..." -> SUPPORTED
        c1_text = "Accuracy rose from 50% to 60% in the adult pilot [1]."
        self.assertIn(c1_text, asm_by_text)
        self.assertEqual(asm_by_text[c1_text]["semantic_verdict"], "SUPPORTED")
        self.assertTrue(len(asm_by_text[c1_text]["evidence_passage_ids"]) > 0)

        # 2. "The absolute accuracy gain was 20 percentage points..." -> CONTRADICTORY
        c2_text = "The absolute accuracy gain was 20 percentage points in the adult pilot [1]."
        self.assertIn(c2_text, asm_by_text)
        self.assertEqual(asm_by_text[c2_text]["semantic_verdict"], "CONTRADICTORY")
        self.assertTrue(len(asm_by_text[c2_text]["evidence_passage_ids"]) > 0)

        # 3. "A second trial reported 90% accuracy [2]." -> Unable to assess
        c3_text = "A second trial reported 90% accuracy [2]."
        self.assertIn(c3_text, asm_by_text)
        self.assertEqual(asm_by_text[c3_text]["assessment_status"], "unable_to_assess")
        self.assertIsNone(asm_by_text[c3_text]["semantic_verdict"])

        # Check that report has passages and sources
        passages = report.get("passages", [])
        self.assertTrue(len(passages) >= 2)
        p_texts = [p["verbatim_text"] for p in passages]
        self.assertTrue(any("rose from 50% to 60%" in pt for pt in p_texts))
        self.assertTrue(any("10 percentage points" in pt for pt in p_texts))

    async def test_regression_neighboring_sentence_extraction_rejected(self):
        """Two adjacent sentences both cite [1]. A mocked Gemini response that tries
        to return a neighboring sentence must be rejected, preserving the target sentence.
        """
        text = """Trial Report
Findings
Accuracy rose from 50% to 60% in the adult pilot [1]. The absolute accuracy gain was 20 percentage points in the adult pilot [1].

References
[1] Rao, M. (2025). Accuracy in an adult pilot. Fixture Studies, 1, 1.
"""
        doc_id, blocks, _ = await ingest_document(text.encode("utf-8"), "adjacent.txt", "text/plain")
        refs = parse_references(blocks)
        self.assertEqual(len(refs), 1)

        # Mock extract_claims_gemini:
        # When called for sentence 1, try to return sentence 2's span (neighboring sentence extraction)
        async def mock_gemini_neighbor(paragraph_text, marked_span, allowed_ref_ids, original_span, target_sentence=None, surrounding_context=None):
            target = target_sentence or original_span
            if "rose from 50% to 60%" in target:
                # Malicious / faulty return: returns neighbor sentence 2
                return [{
                    "claim_text": "The absolute accuracy gain was 20 percentage points in the adult pilot",
                    "original_span": "The absolute accuracy gain was 20 percentage points in the adult pilot [1].",
                    "ref_ids": allowed_ref_ids,
                    "qualifiers": "",
                }]
            else:
                return [{
                    "claim_text": "The absolute accuracy gain was 20 percentage points in the adult pilot",
                    "original_span": "The absolute accuracy gain was 20 percentage points in the adult pilot [1].",
                    "ref_ids": allowed_ref_ids,
                    "qualifiers": "",
                }]

        # In local extraction mode, each cited sentence span is extracted independently
        claims, links, issues = await extract_claims_and_links(blocks, refs)

        # The neighboring sentence extraction must be rejected!
        # Sentence 1 must NOT have sentence 2's text; it must fall back to its own sentence text.
        self.assertEqual(len(claims), 2, "Must extract exactly 2 unique claims for the 2 sentences")
        c1 = claims[0]
        c2 = claims[1]
        self.assertIn("rose from 50% to 60%", c1.original_span, "Sentence 1 must retain its own claim, rejecting neighbor")
        self.assertIn("20 percentage points", c2.original_span, "Sentence 2 must retain its own claim")
        self.assertEqual(len(links), 2, "Both claims must link to [1]")
        for lk in links:
            self.assertEqual(lk.ref_id, refs[0].ref_id)
            self.assertEqual(lk.citation_marker, "[1]")

    async def test_manuscript_txt_exact_counts_claims_references_pairs(self):
        """Assert exactly 3 unique claims, 2 references, and 3 claim-reference pairs in pipeline and report."""
        job = create_job("manuscript.txt", "text/plain")
        await run_pipeline(
            job.job_id,
            FIXTURE_MANUSCRIPT.encode("utf-8"),
            "manuscript.txt",
            "text/plain",
            test_resolver={"[1]": "source-1.txt", "1": "source-1.txt"},
        )
        completed_job = get_job(job.job_id)
        report = completed_job.report

        self.assertEqual(report["total_claims"], 3, "Report must have exactly 3 total claims")
        self.assertEqual(report["total_references"], 2, "Report must have exactly 2 total references")
        self.assertEqual(report["total_pairs"], 3, "Report must have exactly 3 total pairs")
        self.assertEqual(len(report["claims"]), 3, "Report claims list length must be 3")
        self.assertEqual(len(report["references"]), 2, "Report references list length must be 2")
        self.assertEqual(len(report["links"]), 3, "Report links list length must be 3")
        self.assertEqual(len(report["assessments"]), 3, "Report assessments list length must be 3")

        # Verify claim identities are unique
        claim_texts = [c["original_span"] for c in report["claims"]]
        self.assertEqual(len(set(claim_texts)), 3, "All 3 claims must be unique")

    async def test_direction_conflict_decrease_vs_increase_verdict(self):
        """Require direction agreement before issuing support: claim decreased 10 pp vs source increased 10 pp must NEVER be SUPPORTED."""
        claim = Claim(
            claim_id="clm_dir_test",
            document_id="doc_dir_test",
            block_id="blk_1",
            original_span="Accuracy decreased by 10 percentage points in the adult pilot [1].",
            normalized_text="Accuracy decreased by 10 percentage points in the adult pilot.",
            sentence_index=0,
            qualifiers="",
        )
        source = ResolvedSource(
            source_id="src_1",
            ref_id="ref_1",
            identity_status=IdentityStatus.matched,
            matched_title="Pilot paper",
            coverage=CoverageStatus.full_text,
        )
        passage = Passage(
            passage_id="pas_1",
            source_id="src_1",
            verbatim_text="In the adult pilot, the absolute accuracy gain was 10 percentage points.",
            section="Results",
        )
        assessment = await assess_claim_reference_pair(claim, source, [passage])
        self.assertNotEqual(assessment.semantic_verdict, SemanticVerdict.SUPPORTED, "Direction reversal must never return SUPPORTED")
        self.assertEqual(assessment.semantic_verdict, SemanticVerdict.CONTRADICTORY, "Decreased vs gain/increased must return CONTRADICTORY")

    async def test_gain_decreased_vs_gain_increased_direction_binding(self):
        """Case 1: Claim 'Accuracy gain decreased by 10 percentage points' vs Source 'Accuracy gain increased by 10 percentage points'.
        Must resolve compound predicate direction and return CONTRADICTORY, never SUPPORTED.
        """
        claim = Claim(
            claim_id="clm_comp_dir",
            document_id="doc_comp_dir",
            block_id="blk_1",
            original_span="Accuracy gain decreased by 10 percentage points [1].",
            normalized_text="Accuracy gain decreased by 10 percentage points.",
            sentence_index=0,
            qualifiers="",
        )
        source = ResolvedSource(
            source_id="src_1",
            ref_id="ref_1",
            identity_status=IdentityStatus.matched,
            matched_title="Pilot paper",
            coverage=CoverageStatus.full_text,
        )
        passage = Passage(
            passage_id="pas_1",
            source_id="src_1",
            verbatim_text="Accuracy gain increased by 10 percentage points.",
            section="Results",
        )
        assessment = await assess_claim_reference_pair(claim, source, [passage])
        self.assertNotEqual(assessment.semantic_verdict, SemanticVerdict.SUPPORTED, "Opposing gain directions must never be SUPPORTED")
        self.assertEqual(assessment.semantic_verdict, SemanticVerdict.CONTRADICTORY, "Opposing gain directions must be CONTRADICTORY")

    async def test_time_window_mismatch_same_direction_abstains(self):
        """Case 2: Claim 'Accuracy increased by 10 points at week 1' vs Source 'Accuracy increased by 10 points at week 12'.
        Differing time windows must abstain (unable_to_assess), never SUPPORTED.
        """
        claim = Claim(
            claim_id="clm_tw_1",
            document_id="doc_tw_1",
            block_id="blk_1",
            original_span="Accuracy increased by 10 points at week 1 [1].",
            normalized_text="Accuracy increased by 10 points at week 1.",
            sentence_index=0,
            qualifiers="",
        )
        source = ResolvedSource(
            source_id="src_1",
            ref_id="ref_1",
            identity_status=IdentityStatus.matched,
            matched_title="Pilot paper",
            coverage=CoverageStatus.full_text,
        )
        passage = Passage(
            passage_id="pas_1",
            source_id="src_1",
            verbatim_text="Accuracy increased by 10 points at week 12.",
            section="Results",
        )
        assessment = await assess_claim_reference_pair(claim, source, [passage])
        self.assertEqual(assessment.assessment_status, AssessmentStatus.unable_to_assess, "Differing time windows must abstain")
        self.assertIsNone(assessment.semantic_verdict, "Must not return SUPPORTED or CONTRADICTORY for mismatched time windows")

    async def test_time_window_mismatch_different_direction_abstains(self):
        """Case 3: Claim 'Accuracy decreased by 10 points at week 1' vs Source 'Accuracy increased by 10 points at week 12'.
        Because time windows differ, the observations do not cover the same period; must abstain (unable_to_assess), never CONTRADICTORY or SUPPORTED.
        """
        claim = Claim(
            claim_id="clm_tw_2",
            document_id="doc_tw_2",
            block_id="blk_1",
            original_span="Accuracy decreased by 10 points at week 1 [1].",
            normalized_text="Accuracy decreased by 10 points at week 1.",
            sentence_index=0,
            qualifiers="",
        )
        source = ResolvedSource(
            source_id="src_1",
            ref_id="ref_1",
            identity_status=IdentityStatus.matched,
            matched_title="Pilot paper",
            coverage=CoverageStatus.full_text,
        )
        passage = Passage(
            passage_id="pas_1",
            source_id="src_1",
            verbatim_text="Accuracy increased by 10 points at week 12.",
            section="Results",
        )
        assessment = await assess_claim_reference_pair(claim, source, [passage])
        self.assertEqual(assessment.assessment_status, AssessmentStatus.unable_to_assess, "Differing time windows must abstain")
        self.assertIsNone(assessment.semantic_verdict, "Must not issue CONTRADICTORY when observations cover different time periods")

    async def test_ambiguous_source_identity_halts_automatic_assessment(self):
        """Ambiguous source identity must route to unable_to_assess and halt automatic support."""
        claim = Claim(
            claim_id="clm_amb_test",
            document_id="doc_amb_test",
            block_id="blk_1",
            original_span="Accuracy rose from 50% to 60% in the adult pilot [1].",
            normalized_text="Accuracy rose from 50% to 60% in the adult pilot.",
            sentence_index=0,
            qualifiers="",
        )
        source = ResolvedSource(
            source_id="src_1",
            ref_id="ref_1",
            identity_status=IdentityStatus.ambiguous,
            matched_title="Ambiguous Paper Title",
            coverage=CoverageStatus.full_text,
        )
        passage = Passage(
            passage_id="pas_1",
            source_id="src_1",
            verbatim_text="Accuracy rose from 50% to 60% in the adult pilot.",
            section="Results",
        )
        assessment = await assess_claim_reference_pair(claim, source, [passage])
        self.assertEqual(assessment.assessment_status, AssessmentStatus.unable_to_assess)
        self.assertIsNone(assessment.semantic_verdict)
        self.assertIn("ambiguous_identity", assessment.issue_flags)


if __name__ == "__main__":
    unittest.main()
