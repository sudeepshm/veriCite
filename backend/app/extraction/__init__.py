"""Stage 2: extract references and map atomic claims to citation markers.

Public API
----------
parse_references(blocks)                   -> list[Reference]
detect_citation_markers(block, refs)       -> list[tuple]
extract_claims_and_links(blocks, refs)     -> (claims, links, issues)
"""
from __future__ import annotations

import asyncio
import collections
import re
import uuid
import logging

from app.models import (
    BlockType,
    Claim,
    ClaimReferenceLink,
    DocumentBlock,
    MappingStatus,
    Reference,
)
from app.providers import extract_claims_gemini
from app.config import MAX_RETRIES, GEMINI_API_KEY

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex helpers
# ---------------------------------------------------------------------------

_DOI_RE = re.compile(r"10\.\d{4,}/\S+")
_YEAR_RE = re.compile(r"\b(1[9][0-9]{2}|20[0-9]{2})\b")

# Numeric citation: [1], [2,5], [2-5], [2–7]
_NUMERIC_CITE_RE = re.compile(
    r"\[(\d+(?:[,\s]*\d+)*(?:[–\-]\d+)*)\]"
)

# Author-year inline: (Smith et al., 2021; Jones, 2019) or (Smith 2021)
_AUTHOR_YEAR_RE = re.compile(
    r"\(([A-Z][a-z]+(?:\s+et\s+al\.)?(?:,?\s*\d{4}[a-z]?)(?:;\s*[A-Z][a-z]+"
    r"(?:\s+et\s+al\.)?(?:,?\s*\d{4}[a-z]?)*)*)\)"
)
# Narrative author-year: Smith et al. (2021)
_NARRATIVE_AY_RE = re.compile(
    r"([A-Z][a-z]+(?:\s+et\s+al\.)?)\s+\((\d{4}[a-z]?)\)"
)

# LaTeX: \cite{key}, \citep{key1,key2}, \citet{key}
_LATEX_CITE_RE = re.compile(r"\\cite[pt]?\{([^}]+)\}")

# Sentence splitter (naive but sufficient for clause extraction)
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _expand_range(start: int, end: int) -> list[int]:
    return list(range(start, end + 1))


def _expand_numeric_marker(marker_text: str) -> list[int]:
    """Expand '2,5', '2-7', '2–7' into a list of ints."""
    nums: list[int] = []
    # Replace en-dash with hyphen
    marker_text = marker_text.replace("–", "-")
    # Split on commas (handle spaces)
    parts = re.split(r",\s*", marker_text)
    for part in parts:
        part = part.strip()
        m = re.match(r"(\d+)\s*[-]\s*(\d+)$", part)
        if m:
            nums.extend(_expand_range(int(m.group(1)), int(m.group(2))))
        elif part.isdigit():
            nums.append(int(part))
    return nums


def _get_sentence_containing(text: str, char_pos: int) -> str:
    """Return the sentence from *text* that contains character position *char_pos*."""
    sentences = _SENT_SPLIT_RE.split(text)
    offset = 0
    for sent in sentences:
        end = offset + len(sent)
        if offset <= char_pos <= end:
            return sent
        offset = end + 1  # +1 for the space consumed by split
    return text[max(0, char_pos - 150): char_pos + 150]


# ---------------------------------------------------------------------------
# Function 1: parse_references
# ---------------------------------------------------------------------------


def parse_references(blocks: list[DocumentBlock]) -> list[Reference]:
    """Parse bibliography blocks into Reference objects."""
    bib_blocks = [b for b in blocks if b.block_type == BlockType.bibliography]
    if not bib_blocks:
        return []

    document_id = bib_blocks[0].document_id

    # Collect all raw text
    raw_text = "\n".join(b.text for b in bib_blocks)

    # Split into individual entries
    entries = _split_bib_entries(raw_text)

    refs: list[Reference] = []
    for idx, entry in enumerate(entries):
        entry = entry.strip()
        if not entry:
            continue
        ref_id = f"{document_id}_r{idx:04d}"
        raw_marker = _extract_raw_marker(entry, idx)
        doi = _extract_doi(entry)
        year = _extract_year(entry)
        authors = _extract_authors(entry, year)
        title = _extract_title(entry, authors, year)

        refs.append(
            Reference(
                ref_id=ref_id,
                document_id=document_id,
                raw_entry=entry,
                title=title,
                authors=authors,
                year=year,
                doi=doi,
                raw_marker=raw_marker,
            )
        )
    return refs


def _split_bib_entries(text: str) -> list[str]:
    """Split a bibliography text into individual reference entries."""
    # Try numbered list patterns first: [1] or 1. at start of line
    numbered_bracket = re.split(r"\n(?=\[\d+\])", text)
    if len(numbered_bracket) > 1:
        return numbered_bracket

    numbered_dot = re.split(r"\n(?=\d+\.)", text)
    if len(numbered_dot) > 1:
        return numbered_dot

    # Fallback: split on blank lines
    blank_split = re.split(r"\n{2,}", text)
    if len(blank_split) > 1:
        return blank_split

    # Last resort: one entry per line
    return text.splitlines()


def _extract_raw_marker(entry: str, fallback_idx: int) -> str | None:
    m = re.match(r"^\[(\d+)\]", entry.strip())
    if m:
        return f"[{m.group(1)}]"
    m2 = re.match(r"^(\d+)\.", entry.strip())
    if m2:
        return f"[{m2.group(1)}]"
    return None


def _extract_doi(entry: str) -> str | None:
    m = _DOI_RE.search(entry)
    if not m:
        return None
    doi = m.group(0).rstrip(".,;)")
    return doi


def _extract_year(entry: str) -> int | None:
    m = _YEAR_RE.search(entry)
    return int(m.group(0)) if m else None


def _extract_authors(entry: str, year: int | None) -> list[str]:
    """Heuristic: take text before the year (or first period) as authors."""
    # Strip leading marker
    text = re.sub(r"^\[?\d+\]?\.?\s*", "", entry.strip())
    if year:
        idx = text.find(str(year))
        if idx > 0:
            author_part = text[:idx]
        else:
            author_part = text.split(".")[0]
    else:
        author_part = text.split(".")[0]

    # Split on ; or , but keep name units together
    # Heuristic: each author is "Lastname, Initials" or "Firstname Lastname"
    raw_names = re.split(r";\s*|\band\b", author_part)
    authors: list[str] = []
    for name in raw_names:
        name = name.strip().rstrip(",")
        if name and len(name) > 2:
            authors.append(name)
    return authors[:10]  # cap at 10


def _extract_title(entry: str, authors: list[str], year: int | None) -> str | None:
    """Heuristic title extraction: text between year and journal/DOI."""
    text = entry
    # Remove leading marker
    text = re.sub(r"^\[?\d+\]?\.?\s*", "", text.strip())

    # Try quoted title
    m = re.search(r'"([^"]{10,})"', text)
    if m:
        return m.group(1).strip()

    # After year, take up to next period or volume indicator
    if year:
        idx = text.find(str(year))
        if idx >= 0:
            after_year = text[idx + 4:].lstrip(".,: ")
            # Title ends at next period (but not initials) or at DOI
            title_candidate = re.split(r"\.\s+[A-Z]", after_year)
            if title_candidate:
                candidate = title_candidate[0].strip().rstrip(".,")
                if 5 < len(candidate) < 300:
                    return candidate
    return None


# ---------------------------------------------------------------------------
# Function 2: detect_citation_markers
# ---------------------------------------------------------------------------


def detect_citation_markers(
    block: DocumentBlock,
    refs: list[Reference],
) -> list[tuple[str, int, int, list[str]]]:
    """Return list of (marker_text, char_start, char_end, matched_ref_ids)."""
    text = block.text
    results: list[tuple[str, int, int, list[str]]] = []

    # Build lookup indices
    # Numeric marker → ref_id
    marker_to_ref: dict[str, str] = {}
    has_explicit_numeric = False
    for ref in refs:
        if ref.raw_marker:
            cleaned = ref.raw_marker.strip()
            marker_to_ref[cleaned] = ref.ref_id
            m_num = re.match(r"^\[?(\d+)\]?$", cleaned)
            if m_num:
                has_explicit_numeric = True
                marker_to_ref[f"[{m_num.group(1)}]"] = ref.ref_id
                marker_to_ref[m_num.group(1)] = ref.ref_id

    # 1) Numeric citations
    for m in _NUMERIC_CITE_RE.finditer(text):
        marker_text = m.group(0)
        nums = _expand_numeric_marker(m.group(1))
        matched_ids: list[str] = []
        for n in nums:
            key = f"[{n}]"
            if key in marker_to_ref:
                matched_ids.append(marker_to_ref[key])
            elif not has_explicit_numeric and 1 <= n <= len(refs):
                matched_ids.append(refs[n - 1].ref_id)
        results.append((marker_text, m.start(), m.end(), matched_ids))

    # 2) Author-year (parenthetical)
    for m in _AUTHOR_YEAR_RE.finditer(text):
        marker_text = m.group(0)
        inner = m.group(1)
        matched_ids = _resolve_author_year_inner(inner, refs)
        results.append((marker_text, m.start(), m.end(), matched_ids))

    # 3) Narrative author-year: Smith et al. (2021)
    for m in _NARRATIVE_AY_RE.finditer(text):
        marker_text = m.group(0)
        surname = m.group(1).split()[0]
        year_str = m.group(2)
        matched_ids = _resolve_surname_year(surname, year_str, refs)
        results.append((marker_text, m.start(), m.end(), matched_ids))

    # 4) LaTeX citations
    for m in _LATEX_CITE_RE.finditer(text):
        marker_text = m.group(0)
        keys = [k.strip() for k in m.group(1).split(",")]
        matched_ids = _resolve_latex_keys(keys, refs)
        results.append((marker_text, m.start(), m.end(), matched_ids))

    # De-duplicate by position (keep first match per span)
    seen_spans: set[tuple[int, int]] = set()
    deduped: list[tuple[str, int, int, list[str]]] = []
    for item in results:
        span = (item[1], item[2])
        if span not in seen_spans:
            seen_spans.add(span)
            deduped.append(item)

    return deduped


def _resolve_author_year_inner(inner: str, refs: list[Reference]) -> list[str]:
    """Resolve 'Smith et al., 2021; Jones, 2019' style string."""
    # Split on semicolons
    parts = re.split(r";\s*", inner)
    matched: list[str] = []
    for part in parts:
        part = part.strip()
        yr_m = _YEAR_RE.search(part)
        if not yr_m:
            continue
        year_str = yr_m.group(0)
        surname = part.split()[0]
        ids = _resolve_surname_year(surname, year_str, refs)
        matched.extend(ids)
    return matched


def _resolve_surname_year(surname: str, year_str: str, refs: list[Reference]) -> list[str]:
    """Match refs by first author surname and year."""
    year = int(re.sub(r"[a-z]$", "", year_str))
    matched: list[str] = []
    for ref in refs:
        if ref.year == year:
            for author in ref.authors[:1]:
                if surname.lower() in author.lower():
                    matched.append(ref.ref_id)
                    break
    return matched


def _resolve_latex_keys(keys: list[str], refs: list[Reference]) -> list[str]:
    matched: list[str] = []
    for key in keys:
        for ref in refs:
            if key in ref.ref_id or (ref.raw_entry and key in ref.raw_entry):
                matched.append(ref.ref_id)
                break
    return matched


def _split_sentences_with_spans(text: str) -> list[tuple[str, int, int]]:
    """Split text into sentence spans while tracking character offsets."""
    boundary_re = re.compile(r"(?<=[.!?])\s+|\n+")
    splits = [0]
    for m in boundary_re.finditer(text):
        splits.append(m.start())
        splits.append(m.end())
    splits.append(len(text))

    spans: list[tuple[str, int, int]] = []
    for i in range(0, len(splits) - 1, 2):
        s_start = splits[i]
        s_end = splits[i + 1]
        sent = text[s_start:s_end]
        if sent.strip():
            lead_ws = len(sent) - len(sent.lstrip())
            trail_ws = len(sent) - len(sent.rstrip())
            actual_start = s_start + lead_ws
            actual_end = s_end - trail_ws
            spans.append((text[actual_start:actual_end], actual_start, actual_end))
    return spans


def _span_belongs_to_sentence(span: str, sentence: str) -> bool:
    """Validate that *span* belongs to *sentence* (exact or normalized substring)."""
    s_clean = span.strip()
    t_clean = sentence.strip()
    if not s_clean or not t_clean:
        return False
    if s_clean in t_clean:
        return True
    s_norm = " ".join(s_clean.split()).lower()
    t_norm = " ".join(t_clean.split()).lower()
    if s_norm in t_norm:
        return True
    s_no_cite = re.sub(r"\[\d+\]|\([^)]+\)", "", s_clean).strip().lower()
    t_no_cite = re.sub(r"\[\d+\]|\([^)]+\)", "", t_clean).strip().lower()
    if s_no_cite and s_no_cite in t_no_cite:
        return True
    return False


# ---------------------------------------------------------------------------
# Function 3: extract_claims_and_links
# ---------------------------------------------------------------------------


async def extract_claims_and_links(
    blocks: list[DocumentBlock],
    refs: list[Reference],
) -> tuple[list[Claim], list[ClaimReferenceLink], list[str]]:
    """Stage 2 main: extract atomic claims and their reference links.

    Returns (claims, links, issues).
    """
    claims: list[Claim] = []
    links: list[ClaimReferenceLink] = []
    issues: list[str] = []

    non_bib_blocks = [b for b in blocks if b.block_type != BlockType.bibliography]

    for block in non_bib_blocks:
        markers = detect_citation_markers(block, refs)
        if not markers:
            continue

        sentence_spans = _split_sentences_with_spans(block.text)
        if not sentence_spans:
            sentence_spans = [(block.text.strip(), 0, len(block.text))]

        # Assign markers to the sentence span they reside in
        assigned_markers: dict[int, list[tuple[str, int, int, list[str]]]] = collections.defaultdict(list)
        for m in markers:
            m_text, cs, ce, m_rids = m
            matched_span = False
            for s_idx, (s_txt, s_st, s_en) in enumerate(sentence_spans):
                if s_st <= cs <= s_en or s_st <= ce <= s_en or (cs <= s_st and ce >= s_en):
                    assigned_markers[s_idx].append(m)
                    matched_span = True
                    break
            if not matched_span:
                for s_idx, (s_txt, s_st, s_en) in enumerate(sentence_spans):
                    if s_st <= cs:
                        matched_span = True
                        assigned_markers[s_idx].append(m)
                        break
                if not matched_span:
                    assigned_markers[0].append(m)

        for sent_idx, (sent_text, sent_start, sent_end) in enumerate(sentence_spans):
            sent_markers = assigned_markers.get(sent_idx)
            if not sent_markers:
                continue

            target_sentence = sent_text.strip()
            surrounding_context = (block.text[:sent_start] + " " + block.text[sent_end:]).strip()

            unmatched_markers = [m for m in sent_markers if not m[3]]
            matched_markers = [m for m in sent_markers if m[3]]

            sentence_allowed_ref_ids: list[str] = []
            for m_text, cs, ce, rids in matched_markers:
                for rid in rids:
                    if rid not in sentence_allowed_ref_ids:
                        sentence_allowed_ref_ids.append(rid)

            combined_markers_str = ", ".join(m[0] for m in sent_markers)

            claim_dicts: list[dict] = []
            last_error: str | None = None
            if GEMINI_API_KEY and sentence_allowed_ref_ids:
                for attempt in range(MAX_RETRIES):
                    try:
                        claim_dicts = await extract_claims_gemini(
                            paragraph_text=block.text,
                            marked_span=combined_markers_str,
                            allowed_ref_ids=sentence_allowed_ref_ids,
                            original_span=target_sentence,
                            target_sentence=target_sentence,
                            surrounding_context=surrounding_context,
                        )
                        last_error = None
                        break
                    except RuntimeError as exc:
                        last_error = str(exc)
                        logger.warning(
                            "extract_claims_gemini attempt %d/%d failed: %s",
                            attempt + 1,
                            MAX_RETRIES,
                            last_error,
                        )
                        await asyncio.sleep(2 ** attempt)  # exponential back-off

                if last_error is not None:
                    issues.append(
                        f"block={block.block_id} markers='{combined_markers_str}': "
                        f"Gemini extraction failed: {last_error}. Using deterministic clause fallback."
                    )

            # Validate that each returned original_span belongs to the target sentence
            valid_claim_dicts: list[dict] = []
            for item in claim_dicts:
                orig_span = item.get("original_span", "")
                if _span_belongs_to_sentence(orig_span, target_sentence):
                    valid_claim_dicts.append(item)
                else:
                    logger.warning(
                        "Rejected claim extraction because original_span %r does not belong to target sentence %r",
                        orig_span,
                        target_sentence,
                    )

            # If no valid claim returned by Gemini, use deterministic target sentence fallback
            if not valid_claim_dicts:
                valid_claim_dicts = [{
                    "claim_text": target_sentence,
                    "original_span": target_sentence,
                    "ref_ids": sentence_allowed_ref_ids,
                    "qualifiers": "",
                }]

            for claim_dict in valid_claim_dicts:
                short_uuid = uuid.uuid4().hex[:8]
                claim_id = f"{block.document_id}_c{short_uuid}"
                claim = Claim(
                    claim_id=claim_id,
                    document_id=block.document_id,
                    block_id=block.block_id,
                    original_span=claim_dict.get("original_span", target_sentence).strip(),
                    normalized_text=claim_dict.get("claim_text", target_sentence).strip(),
                    char_start=None,
                    char_end=None,
                )
                claims.append(claim)

                # Attach unmatched markers from the sentence
                for m_text, cs, ce, _ in unmatched_markers:
                    issues.append(
                        f"block={block.block_id}: unmatched citation marker '{m_text}'"
                    )
                    links.append(
                        ClaimReferenceLink(
                            link_id=f"lnk_{uuid.uuid4().hex[:12]}",
                            claim_id=claim_id,
                            ref_id="",
                            citation_marker=m_text,
                            marker_char_start=cs,
                            marker_char_end=ce,
                            citation_group_id=None,
                            mapping_status=MappingStatus.unmatched,
                        )
                    )

                # Attach matched markers from the sentence
                claim_rids = [
                    r for r in claim_dict.get("ref_ids", [])
                    if r in sentence_allowed_ref_ids
                ]

                for marker_idx, (m_text, cs, ce, m_rids) in enumerate(matched_markers):
                    is_ambiguous_group = len(m_rids) > 1
                    group_id = (
                        f"group_{block.block_id}_{sent_idx}_{marker_idx}"
                        if is_ambiguous_group
                        else None
                    )
                    target_rids = [r for r in m_rids if (not claim_rids or r in claim_rids)]
                    if not target_rids and not claim_rids:
                        target_rids = m_rids

                    for rid in target_rids:
                        links.append(
                            ClaimReferenceLink(
                                link_id=f"lnk_{uuid.uuid4().hex[:12]}",
                                claim_id=claim_id,
                                ref_id=rid,
                                citation_marker=m_text,
                                marker_char_start=cs,
                                marker_char_end=ce,
                                citation_group_id=group_id,
                                mapping_status=MappingStatus.ambiguous if is_ambiguous_group else MappingStatus.mapped,
                            )
                        )

    # Deduplicate claims with identical normalized text within the document
    deduped_claims: list[Claim] = []
    seen_texts: dict[str, str] = {}
    for c in claims:
        key = c.normalized_text.strip().lower() or c.original_span.strip().lower()
        if key not in seen_texts:
            seen_texts[key] = c.claim_id
            deduped_claims.append(c)

    # Remap links to deduplicated claim IDs and drop duplicate links
    deduped_links: list[ClaimReferenceLink] = []
    seen_links: set[tuple[str, str, str]] = set()
    for lk in links:
        target_claim_id = lk.claim_id
        matching_claim = next((c for c in claims if c.claim_id == lk.claim_id), None)
        if matching_claim:
            key = matching_claim.normalized_text.strip().lower() or matching_claim.original_span.strip().lower()
            target_claim_id = seen_texts.get(key, lk.claim_id)

        pair_key = (target_claim_id, lk.ref_id, lk.citation_marker)
        if pair_key not in seen_links:
            seen_links.add(pair_key)
            if target_claim_id != lk.claim_id:
                lk = lk.model_copy(update={"claim_id": target_claim_id})
            deduped_links.append(lk)

    return deduped_claims, deduped_links, issues


__all__ = [
    "parse_references",
    "detect_citation_markers",
    "extract_claims_and_links",
]
