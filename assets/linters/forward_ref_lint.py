#!/usr/bin/env python3
"""
forward_ref_lint.py
===================

A lightweight linter that screens a thesis PDF paragraph by paragraph and
flags paragraphs that *reference* a concept which is only *introduced*
(defined) in a LATER paragraph.

The approach is deliberately heuristic — there is no real NLP/semantic
understanding — but it is useful as a first-pass screen to find "forward
references" to terminology that the reader has not yet been told about.

How it works
------------
1.  Extract text from the PDF (PyMuPDF preferred, pdfplumber fallback).
2.  Split the text into paragraphs.
3.  Detect "concept introductions" in each paragraph.  A concept is
    considered introduced in the first paragraph that matches one of the
    definition patterns, e.g.
        - "we define <X> as ..."
        - "<X> is defined as ..."
        - "we call ... <X>"
        - "let <X> denote ..."
        - "<X> (also called <Y>) is ..."
    Bold/italic spans are treated as candidate defined terms when they sit
    next to a definition cue ("is", "refers to", "denotes", ...).
4.  Build a registry mapping each concept (normalised) -> the index of the
    paragraph where it is first introduced.
5.  For every paragraph, scan for mentions of every known concept.  If a
    concept is mentioned in paragraph N but is only introduced in paragraph
    M > N, flag it as a forward reference.

Usage
-----
    python3 forward_ref_lint.py thesis.pdf
    python3 forward_ref_lint.py thesis.pdf --out report.md
    python3 forward_ref_lint.py thesis.pdf --pages 1-120 --min-term-len 4

Notes / limitations
-------------------
* Heuristic only. False positives (common words captured as "concepts") and
  false negatives (definitions that don't match the cue phrases) will occur.
* Term matching is case-insensitive on whole tokens; plurals are crudely
  stemmed (strip trailing 's').
* Equations, figure/table captions, and reference lists are ignored where
  possible.
* Acronyms introduced inline ("Compressive Sensing (CS)") are captured.

Requires: PyMuPDF (fitz) or pdfplumber.  No nltk needed.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Optional PDF backends
# ---------------------------------------------------------------------------
try:
    import fitz  # PyMuPDF
    _HAVE_FITZ = True
except Exception:
    _HAVE_FITZ = False

try:
    import pdfplumber
    _HAVE_PDFPLUMBER = True
except Exception:
    _HAVE_PDFPLUMBER = False


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class Paragraph:
    index: int                # 0-based running index across the document
    page: int                 # 1-based page number
    text: str
    is_caption: bool = False
    is_reference: bool = False
    bold_spans: List[str] = field(default_factory=list)
    italic_spans: List[str] = field(default_factory=list)


@dataclass
class Finding:
    para_index: int
    page: int
    concept: str
    introduced_at_para: int
    introduced_at_page: int
    snippet: str


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------
def _looks_like_caption(text: str) -> bool:
    t = text.lstrip()
    return bool(re.match(r"^(Figure|Fig\.|Table|Tab\.|Algorithm|Listing)\s+\d", t))


def _looks_like_reference(text: str) -> bool:
    # A line that starts with [N] or looks like a bib entry.
    return bool(re.match(r"^\[\s*\d+\s*\]", text.strip()))


def extract_paragraphs(path: str, page_range: Optional[Tuple[int, int]]) -> List[Paragraph]:
    """Return a flat list of Paragraph objects across the document."""
    paragraphs: List[Paragraph] = []

    if _HAVE_FITZ:
        doc = fitz.open(path)
        for pno in range(len(doc)):
            page_no = pno + 1
            if page_range and not (page_range[0] <= page_no <= page_range[1]):
                continue
            page = doc[pno]
            # Use blocks to preserve paragraph structure.
            blocks = page.get_text("dict")["blocks"]
            for b in blocks:
                if b.get("type", 0) != 0:  # 0 == text block
                    continue
                lines = b.get("lines", [])
                if not lines:
                    continue
                bold: List[str] = []
                italic: List[str] = []
                text_parts: List[str] = []
                for ln in lines:
                    buf = []
                    for sp in ln.get("spans", []):
                        s = sp.get("text", "")
                        if not s.strip():
                            buf.append(s)
                            continue
                        flags = sp.get("flags", 0)
                        # font flags: bit 0 (1) = superscript, bit 1 (2) = italic,
                        # bit 4 (16) = bold
                        if flags & 16:
                            bold.append(s.strip())
                        if flags & 2:
                            italic.append(s.strip())
                        buf.append(s)
                    text_parts.append("".join(buf).rstrip())
                text = "\n".join(text_parts).strip()
                if not text:
                    continue
                paragraphs.append(Paragraph(
                    index=len(paragraphs),
                    page=page_no,
                    text=text,
                    is_caption=_looks_like_caption(text),
                    is_reference=_looks_like_reference(text),
                    bold_spans=[b for b in bold if b],
                    italic_spans=[i for i in italic if i],
                ))
        doc.close()
    elif _HAVE_PDFPLUMBER:
        with pdfplumber.open(path) as pdf:
            for pno, page in enumerate(pdf.pages):
                page_no = pno + 1
                if page_range and not (page_range[0] <= page_no <= page_range[1]):
                    continue
                words = page.extract_words(use_text_flow=True, keep_blank_chars=False)
                if not words:
                    continue
                # Group words into paragraphs by y-gap heuristic.
                lines: List[List[dict]] = []
                cur: List[dict] = []
                last_bottom = None
                for w in words:
                    if last_bottom is not None and (w["top"] - last_bottom) > 14:
                        lines.append(cur)
                        cur = []
                    cur.append(w)
                    last_bottom = w["bottom"]
                if cur:
                    lines.append(cur)
                # Merge lines into paragraphs: a paragraph break is a blank-ish
                # vertical gap.  pdfplumber already gives us lines; we treat each
                # line as its own paragraph if spacing unknown — crude but ok.
                for ln in lines:
                    ln_sorted = sorted(ln, key=lambda w: w["x0"])
                    text = " ".join(w["text"] for w in ln_sorted).strip()
                    if not text:
                        continue
                    paragraphs.append(Paragraph(
                        index=len(paragraphs),
                        page=page_no,
                        text=text,
                        is_caption=_looks_like_caption(text),
                        is_reference=_looks_like_reference(text),
                    ))
    else:
        raise RuntimeError(
            "No PDF backend found. Install PyMuPDF (`pip install pymupdf`) "
            "or pdfplumber (`pip install pdfplumber`)."
        )

    # Merge consecutive non-empty lines that are clearly part of the same
    # paragraph (no blank line between them in PyMuPDF blocks this is already
    # handled; for pdfplumber we collapse short lines).
    return paragraphs


# ---------------------------------------------------------------------------
# Concept introduction detection
# ---------------------------------------------------------------------------
# Definition cue phrases.  When matched, the captured group(s) are treated as
# the introduced concept(s).  Patterns are applied case-insensitively.
DEFINITION_PATTERNS: List[re.Pattern] = [
    # "we define X as ..." / "we define X, Y, and Z as ..."
    re.compile(r"\bwe\s+define\s+(.+?)\s+as\b", re.I),
    # "X is defined as ..."  (capture X)
    re.compile(r"\b(.+?)\s+is\s+defined\s+as\b", re.I),
    # "X is defined (to be) ..."
    re.compile(r"\b(.+?)\s+is\s+defined\s+to\s+be\b", re.I),
    # "we call ... X"
    re.compile(r"\bwe\s+call\s+(.+?)\s+(?:a|an|the)\s+(.+?)[\.\,;]", re.I),
    # "we refer to ... as X"
    re.compile(r"\bwe\s+refer\s+to\s+.+?\s+as\s+(.+?)[\.\,;]", re.I),
    # "let X denote ..."
    re.compile(r"\blet\s+(.+?)\s+denote\b", re.I),
    # "X denotes ..."
    re.compile(r"\b(.+?)\s+denotes\b", re.I),
    # "X stands for ..."
    re.compile(r"\b(.+?)\s+stands\s+for\b", re.I),
    # "by X we mean ..."
    re.compile(r"\bby\s+(.+?)\s+we\s+mean\b", re.I),
    # "the term X refers to ..."
    re.compile(r"\bthe\s+term\s+(.+?)\s+refers\s+to\b", re.I),
    # "X (also known as Y) is ..."  -> capture X
    re.compile(r"\b(.+?)\s+\(also\s+known\s+as\b", re.I),
    # "X (also called Y) ..." -> capture X
    re.compile(r"\b(.+?)\s+\(also\s+called\b", re.I),
    # Acronym inline: "Compressive Sensing (CS)"  -> capture both
    re.compile(r"\b([A-Z][a-zA-Z]{2,}(?:\s+[A-Z][a-zA-Z]{1,}){0,4})\s+\(([A-Z]{2,6})\)", re.I),
]

# Words that should never be treated as concepts even if captured.
STOPWORDS = {
    "the", "a", "an", "this", "that", "these", "those", "it", "its",
    "we", "our", "us", "i", "you", "they", "their", "them", "he", "she",
    "and", "or", "but", "if", "then", "else", "when", "while", "as", "of",
    "to", "in", "on", "for", "with", "without", "by", "from", "into",
    "is", "are", "was", "were", "be", "been", "being", "has", "have", "had",
    "do", "does", "did", "not", "no", "yes", "such", "so", "than", "very",
    "can", "could", "may", "might", "must", "shall", "should", "will", "would",
    "which", "who", "whom", "what", "where", "why", "how", "all", "any",
    "both", "each", "few", "more", "most", "other", "some", "one", "two",
    "first", "second", "third", "new", "old", "same", "different",
    "above", "below", "over", "under", "again", "further", "here", "there",
    "figure", "table", "equation", "eq", "section", "chapter", "page",
    "note", "example", "see", "cf", "etc", "versus", "vs",
}

# Ordinary English words that are never a thesis "concept", even when a
# definition-cue pattern happens to capture them (e.g. "... denotes multiple
# years"). These are the main source of noise Salma flagged; deliberately
# excludes genuine ML terms (feature, label, model, method, loss, ...).
ORDINARY_WORDS = {
    # quantities / amounts
    "multiple", "single", "several", "various", "numerous", "number",
    "numbers", "amount", "amounts", "total", "totals", "majority", "minority",
    "count", "counts", "half", "quarter", "percentage", "percentages",
    # time
    "year", "years", "month", "months", "week", "weeks", "day", "days",
    "hour", "hours", "minute", "minutes", "second", "seconds", "time",
    "times", "decade", "decades", "period", "periods", "moment", "moments",
    # generic filler nouns
    "thing", "things", "way", "ways", "lot", "kind", "kinds", "sort", "sorts",
    "part", "parts", "piece", "pieces", "area", "areas", "aspect", "aspects",
    "item", "items", "order", "place", "places", "point", "points", "side",
    "sides", "end", "ends", "range", "ranges", "matter", "issue", "issues",
    "fact", "facts", "reason", "reasons", "detail", "details", "step", "steps",
}
STOPWORDS |= ORDINARY_WORDS


def _normalise_term(term: str) -> str:
    """Canonicalise a term for registry keys: strip surrounding
    punctuation/whitespace, collapse inner spaces, and lower-case it."""
    t = term.strip().strip(".,;:()\"'").strip()
    t = re.sub(r"\s+", " ", t)
    return t.lower()


def _split_terms(group: str) -> List[str]:
    """A captured group may contain 'X, Y, and Z'; split into individual terms."""
    parts = re.split(r",|;|\band\b|\bor\b", group)
    out = []
    for p in parts:
        n = _normalise_term(p)
        if n and len(n) >= 3 and n not in STOPWORDS:
            # Drop terms that are a single stopword-ish token.
            tokens = [w for w in n.split() if w not in STOPWORDS]
            if tokens:
                out.append(" ".join(tokens))
    return out


def _stem(term: str) -> str:
    """Crude plural stemmer: drop trailing 's' for matching purposes."""
    if len(term) > 4 and term.endswith("s") and not term.endswith("ss"):
        return term[:-1]
    return term


def detect_introductions(paragraphs: List[Paragraph]) -> Dict[str, int]:
    """Map normalised concept -> index of paragraph where first introduced."""
    registry: Dict[str, int] = {}
    for para in paragraphs:
        if para.is_reference:
            continue
        text = para.text

        # Pattern-based cues
        for pat in DEFINITION_PATTERNS:
            for m in pat.finditer(text):
                for grp in m.groups():
                    if not grp:
                        continue
                    for term in _split_terms(grp):
                        if term in registry:
                            continue
                        registry[term] = para.index

        # Bold/italic spans adjacent to a definition cue word are strong
        # signals of an introduced term.
        cue_regex = re.compile(
            r"\b(?:is|are|refers?\s+to|denotes?|stands\s+for|means|defined\s+as|"
            r"called|known\s+as|introduces?|represents?)\b",
            re.I,
        )
        if cue_regex.search(text):
            for span_list in (para.bold_spans, para.italic_spans):
                for span in span_list:
                    term = _normalise_term(span)
                    if (
                        term
                        and len(term) >= 3
                        and term not in STOPWORDS
                        and not term.isdigit()
                        and term not in registry
                    ):
                        # Only accept multi-word terms or capitalised acronyms
                        # from spans, to limit noise.
                        if " " in term or term.isupper() or span[:1].isupper():
                            registry[term] = para.index
    return registry


# ---------------------------------------------------------------------------
# Forward-reference detection
# ---------------------------------------------------------------------------
def _term_word_regex(term: str) -> re.Pattern:
    """Build a whole-token, case-insensitive regex for a concept."""
    stem = _stem(term)
    # Allow optional trailing 's' on the last word.
    words = stem.split()
    esc_words = [re.escape(w) for w in words]
    if esc_words:
        last = esc_words[-1]
        if not last.endswith("s"):
            esc_words[-1] = last + "s?"
    pattern = r"\b" + r"\s+".join(esc_words) + r"\b"
    return re.compile(pattern, re.I)


def _snippet_around(text: str, match: re.Match, width: int = 80) -> str:
    """Return a short context window of `text` centred on `match`, with
    ellipses marking where it was truncated, for display in the report."""
    start = max(0, match.start() - width // 2)
    end = min(len(text), match.end() + width // 2)
    snip = text[start:end].replace("\n", " ")
    pre = "…" if start > 0 else ""
    post = "…" if end < len(text) else ""
    return f"{pre}{snip}{post}"


def find_forward_references(
    paragraphs: List[Paragraph],
    registry: Dict[str, int],
    min_term_len: int,
    min_term_words: int,
) -> List[Finding]:
    """Scan every paragraph for mentions of registered concepts and return a
    Finding for each concept used in a paragraph that precedes the one where
    the concept is introduced. `min_term_len`/`min_term_words` filter out
    short or single-word terms to cut noise; each concept is reported at most
    once per paragraph."""
    findings: List[Finding] = []

    # Precompile term regexes, filtering noisy single common words.
    term_regexes: List[Tuple[str, int, re.Pattern]] = []
    for term, intro_idx in registry.items():
        words = term.split()
        if len(term) < min_term_len:
            continue
        if len(words) < min_term_words:
            continue
        # Skip if the term is a single very generic word.
        if len(words) == 1 and term in STOPWORDS:
            continue
        term_regexes.append((term, intro_idx, _term_word_regex(term)))

    for para in paragraphs:
        if para.is_reference or para.is_caption:
            continue
        text = para.text
        seen_here: set = set()
        for term, intro_idx, rx in term_regexes:
            if intro_idx <= para.index:
                continue  # introduced at or before this paragraph -> fine
            m = rx.search(text)
            if m and term not in seen_here:
                seen_here.add(term)
                intro_para = paragraphs[intro_idx]
                findings.append(Finding(
                    para_index=para.index,
                    page=para.page,
                    concept=term,
                    introduced_at_para=intro_idx,
                    introduced_at_page=intro_para.page,
                    snippet=_snippet_around(text, m),
                ))
    return findings


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def render_report(
    paragraphs: List[Paragraph],
    registry: Dict[str, int],
    findings: List[Finding],
    path: str,
    markdown: bool,
) -> str:
    """Build the human-readable report string (text or markdown) summarising
    the scan and listing each forward reference by the page where the term is
    used and the page where it is first defined."""
    lines: List[str] = []
    h = "##" if markdown else "=="
    bullet = "- " if markdown else "  * "

    lines.append(f"{h} Forward-reference lint report")
    lines.append(f"File: {path}")
    lines.append(
        "What this checks: a passage that uses a term whose definition appears "
        "only on a LATER page — a \"forward reference\" the reader meets before "
        "it is introduced.")
    lines.append(
        "Heuristic, so expect false positives: an ordinary word can be "
        "mistaken for a defined term. For fewer, more reliable hits re-run "
        "with --min-term-words 2; add --list-concepts to see what was treated "
        "as a term.")
    lines.append("")
    lines.append(f"Paragraphs scanned: {len(paragraphs)}")
    lines.append(f"Concepts registered: {len(registry)}")
    lines.append(f"Forward references found: {len(findings)}")
    lines.append("")

    # Group findings by paragraph (kept internal; the listing is by page).
    by_para: Dict[int, List[Finding]] = {}
    for f in findings:
        by_para.setdefault(f.para_index, []).append(f)

    if not findings:
        lines.append("No forward references detected. "
                     "(Remember: detection is heuristic; this is not a guarantee.)")
        return "\n".join(lines)

    lines.append("Each finding — the page where the term is used, the term, "
                 "and the page where it is first defined:")
    lines.append("")
    for pidx in sorted(by_para):
        for f in by_para[pidx]:
            lines.append(
                f"{bullet}page {f.page}: uses '{f.concept}' — "
                f"first defined on page {f.introduced_at_page}"
            )
            lines.append(f"    context: {f.snippet}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_page_range(s: str) -> Optional[Tuple[int, int]]:
    """Parse a --pages value ('1-120' or a single '5') into an inclusive
    (lo, hi) 1-based page tuple, or None if empty; raises ValueError on a
    malformed value."""
    if not s:
        return None
    m = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", s)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        if lo > hi:
            lo, hi = hi, lo
        return (lo, hi)
    m = re.match(r"^\s*(\d+)\s*$", s)
    if m:
        n = int(m.group(1))
        return (n, n)
    raise ValueError(f"Bad --pages value: {s!r} (expected '1-120' or '5')")


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="Lint a thesis PDF for forward references to concepts "
                    "introduced only in later paragraphs.",
    )
    p.add_argument("pdf", help="Path to the thesis PDF.")
    p.add_argument("--out", help="Write report to this file instead of stdout.")
    p.add_argument("--format", choices=["text", "markdown"], default="text",
                   help="Report format (default: text).")
    p.add_argument("--pages", default=None,
                   help="Restrict to a page range, e.g. '1-120' or '5'.")
    p.add_argument("--min-term-len", type=int, default=4,
                   help="Minimum character length of a concept to consider (default 4).")
    p.add_argument("--min-term-words", type=int, default=1,
                   help="Minimum number of words in a concept to consider (default 1). "
                        "Raise to 2 to reduce noise from single-word terms.")
    p.add_argument("--list-concepts", action="store_true",
                   help="Also print every detected concept and where it was introduced.")
    args = p.parse_args(argv)

    if not _HAVE_FITZ and not _HAVE_PDFPLUMBER:
        print("ERROR: need PyMuPDF or pdfplumber.", file=sys.stderr)
        return 2

    page_range = parse_page_range(args.pages) if args.pages else None

    paragraphs = extract_paragraphs(args.pdf, page_range)
    if not paragraphs:
        print("ERROR: no text extracted from PDF.", file=sys.stderr)
        return 1

    registry = detect_introductions(paragraphs)
    findings = find_forward_references(
        paragraphs, registry,
        min_term_len=args.min_term_len,
        min_term_words=args.min_term_words,
    )

    report = render_report(
        paragraphs, registry, findings, args.pdf,
        markdown=(args.format == "markdown"),
    )

    if args.list_concepts:
        report += "\n\n## Detected concepts (introduction index)\n"
        for term in sorted(registry, key=lambda t: registry[t]):
            intro_para = paragraphs[registry[term]]
            report += f"- {term}  ->  para {registry[term]} (page {intro_para.page})\n"

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(report)
        print(f"Report written to {args.out}", file=sys.stderr)
    else:
        print(report)
    # 0 clean, 1 when forward references were found — so the suite runner and
    # dashboard report "findings" rather than "clean" when the report is
    # non-empty (consistent with the other linters).
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
