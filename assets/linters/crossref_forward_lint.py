#!/usr/bin/env python3
"""
crossref_forward_lint.py
========================

A linter that screens a thesis PDF for **forward cross-references** to
numbered floats (figures, equations, tables, algorithms, listings) and
optionally sections/chapters/appendices, flagging cases where the text
refers to a float that is defined MUCH FURTHER BELOW in the document.

Example of what it catches
---------------------------
    page 3:  "... as depicted in Figure 7, the pipeline ..."
    page 21: "Figure 7: Overview of the pipeline."
    -> flag: "Figure 7" is referenced on page 3 but defined on page 21
       (18 pages ahead).

How it works
------------
1.  Extract text line-by-line with positional info (page, y, x0, x1) and
    font flags via PyMuPDF.
2.  Build a registry of float DEFINITIONS:
       * Figure/Table/Algorithm/Listing captions:
             lines starting with "Figure 5", "Fig. 5", "Table 2", ...
       * Equation anchors:
             a span whose text is exactly "(N)" sitting near the right
             margin (the standard LaTeX equation-tag position).
       * Section/Chapter headings (optional):
             short, bold lines beginning with a number like "5.1 Foo".
3.  Scan every non-caption, non-anchor line for cross-reference patterns
    such as "Figure 5", "Fig. 5", "Eq. (3)", "Equation 3", "Table 2",
    "Algorithm 1", "Section 4.2", "Chapter 2", "Appendix A".
4.  For each reference, look up where the corresponding float is defined.
    If the definition is BELOW the reference (forward) and the distance
    exceeds a threshold (default: more than 1 page ahead), flag it.

Distance metric
---------------
    distance (pages) = (def_page - ref_page)
                        + (def_y - ref_y) / page_height

A reference is flagged when it is forward AND distance > --threshold
(default 1.0 page).  Use --any-forward to flag every forward reference
no matter how close, or raise --threshold to be stricter.

Usage
-----
    python3 crossref_forward_lint.py thesis.pdf
    python3 crossref_forward_lint.py thesis.pdf --threshold 2 --out report.md
    python3 crossref_forward_lint.py thesis.pdf --pages 1-60 --format markdown
    python3 crossref_forward_lint.py thesis.pdf --no-sections --no-equations
    python3 crossref_forward_lint.py thesis.pdf --json findings.json

Requires: PyMuPDF (fitz).  `pip install pymupdf`
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

try:
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover
    fitz = None


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
FLOAT_KINDS = ("figure", "table", "equation", "algorithm", "listing",
               "section", "chapter", "appendix")


@dataclass
class Line:
    page: int            # 1-based
    y: float             # top y of the line
    x0: float
    x1: float
    text: str
    is_bold: bool = False
    # If this line is a caption / anchor for a float, record it:
    caption_kind: Optional[str] = None
    caption_num: Optional[str] = None


@dataclass
class Definition:
    kind: str
    num: str
    page: int
    y: float
    text: str


@dataclass
class Reference:
    kind: str
    num: str
    page: int
    y: float
    snippet: str


@dataclass
class Finding:
    kind: str
    num: str
    ref_page: int
    ref_y: float
    def_page: int
    def_y: float
    distance_pages: float
    snippet: str
    def_text: str


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------
# Number token used for figures/tables/equations/algorithms/listings/sections.
_NUM = r"(\d+(?:\.\d+)*)"

# Reference patterns.  Each yields (kind, number).
REF_PATTERNS: List[Tuple[str, re.Pattern]] = [
    # "Figure 5", "Fig. 5", "Fig 5", "Figures 5", "Figs. 5"
    ("figure",  re.compile(r"\bFig(?:ure|s)?\.?\s+\(?\s*" + _NUM + r"\s*\)?", re.I)),
    # "Table 2", "Tab. 2", "Tables 2"
    ("table",   re.compile(r"\bTab(?:le|s)?\.?\s+\(?\s*" + _NUM + r"\s*\)?", re.I)),
    # "Equation 3", "Eq. (3)", "Eq. 3", "Eqs. (3)", "Eq.(3)"
    ("equation", re.compile(r"\bEq(?:uation|s)?\.?\s*\(?\s*" + _NUM + r"\s*\)?", re.I)),
    # "Algorithm 1"
    ("algorithm", re.compile(r"\bAlgorithm\s+\(?\s*" + _NUM + r"\s*\)?", re.I)),
    # "Listing 1"
    ("listing",  re.compile(r"\bListing\s+\(?\s*" + _NUM + r"\s*\)?", re.I)),
    # "Section 4.2", "Sec. 4.2", "Subsection 4.2", "Sections 4"
    ("section",  re.compile(r"\b(?:Sub)?Sec(?:tion|s)?\.?\s+\(?\s*" + _NUM + r"\s*\)?", re.I)),
    # "Chapter 2", "Chap. 2"
    ("chapter",  re.compile(r"\bChap(?:ter)?\.?\s+\(?\s*" + _NUM + r"\s*\)?", re.I)),
    # "Appendix A", "Appendix A.1"
    ("appendix", re.compile(r"\bAppendix\s+([A-Z](?:\.\d+)*)\b")),
]

# Caption patterns: a line that *starts* with one of these defines the float.
# We capture the kind + number.  Only the first occurrence per (kind, num)
# counts as the definition.
CAPTION_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("figure",   re.compile(r"^\s*(?:Figure|Fig\.)\s+" + _NUM + r"\b", re.I)),
    ("table",    re.compile(r"^\s*(?:Table|Tab\.)\s+" + _NUM + r"\b", re.I)),
    ("algorithm", re.compile(r"^\s*Algorithm\s+" + _NUM + r"\b", re.I)),
    ("listing",  re.compile(r"^\s*Listing\s+" + _NUM + r"\b", re.I)),
    # Chapter heading as a caption: "Chapter 3" / "3. Foo"
    ("chapter",  re.compile(r"^\s*Chapter\s+" + _NUM + r"\b", re.I)),
]

# Equation tag: a span whose text is exactly "(N)" or "(N.M)".
EQ_TAG_RE = re.compile(r"^\(\s*(\d+(?:\.\d+)*)\s*\)\s*$")

# Bare inline equation reference like "(3)" / "(3.1)".  We only resolve these
# against KNOWN equation tags (see collect_references), so random parenthesised
# numbers that do not correspond to a registered equation are ignored.
BARE_EQ_REF_RE = re.compile(r"(?<![\w(])\(\s*(\d+(?:\.\d+)*)\s*\)(?!\d)")

# Section heading heuristic: short bold line starting with a section number.
SECTION_HEADING_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)\s+\S.*$")

# Lines we never scan for references (table of contents, bibliography).
DOT_LEADER_RE = re.compile(r"\.{2,}\s*\d+\s*$")
BIBLINE_RE = re.compile(r"^\[\s*\d+\s*\]")


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------
def _is_toc_or_bib(line_text: str) -> bool:
    t = line_text.strip()
    if not t:
        return True
    if DOT_LEADER_RE.search(t):
        return True
    if BIBLINE_RE.match(t):
        return True
    return False


def extract_lines(path: str, page_range: Optional[Tuple[int, int]]) -> Tuple[List[Line], float]:
    """Return (lines, median_page_height)."""
    if fitz is None:
        raise RuntimeError("PyMuPDF (fitz) is required. pip install pymupdf")
    doc = fitz.open(path)
    lines: List[Line] = []
    page_heights: List[float] = []

    for pno in range(len(doc)):
        page_no = pno + 1
        if page_range and not (page_range[0] <= page_no <= page_range[1]):
            continue
        page = doc[pno]
        ph = page.rect.height
        page_heights.append(ph)
        pw = page.rect.width
        blocks = page.get_text("dict")["blocks"]
        for b in blocks:
            if b.get("type", 0) != 0:
                continue
            for ln in b.get("lines", []):
                spans = ln.get("spans", [])
                if not spans:
                    continue
                buf: List[str] = []
                bold_any = False
                line_x0 = math.inf
                line_x1 = -math.inf
                # Track the right-most short "(N)" span for equation anchors.
                eq_tag_num: Optional[str] = None
                eq_tag_x1 = -1.0
                for sp in spans:
                    s = sp.get("text", "")
                    if not s:
                        continue
                    buf.append(s)
                    flags = sp.get("flags", 0)
                    if flags & 16:  # bold bit
                        bold_any = True
                    sx0 = sp.get("bbox", [0, 0, 0, 0])[0]
                    sx1 = sp.get("bbox", [0, 0, 0, 0])[2]
                    line_x0 = min(line_x0, sx0)
                    line_x1 = max(line_x1, sx1)
                    # Equation tag: text is exactly "(N)" and near right margin.
                    stag = s.strip()
                    m = EQ_TAG_RE.match(stag)
                    if m and sx1 > pw * 0.55:  # right-ish half of the page
                        if sx1 > eq_tag_x1:
                            eq_tag_x1 = sx1
                            eq_tag_num = m.group(1)
                text = "".join(buf).strip()
                if not text:
                    continue
                bbox = ln.get("bbox", [0, 0, 0, 0])
                y = bbox[1]
                if line_x0 == math.inf:
                    line_x0 = bbox[0]
                    line_x1 = bbox[2]
                line = Line(
                    page=page_no, y=y, x0=line_x0, x1=line_x1,
                    text=text, is_bold=bold_any,
                )
                # Determine caption kind/num for this line (if any).
                ck, cn = _caption_for(line)
                if ck is None and eq_tag_num is not None:
                    ck, cn = "equation", eq_tag_num
                if ck is None:
                    ck, cn = _section_heading_for(line)
                line.caption_kind = ck
                line.caption_num = cn
                lines.append(line)
    doc.close()
    median_h = statistics.median(page_heights) if page_heights else 800.0
    return lines, median_h


def _caption_for(line: Line) -> Tuple[Optional[str], Optional[str]]:
    for kind, pat in CAPTION_PATTERNS:
        m = pat.match(line.text)
        if m:
            return kind, m.group(1)
    return None, None


def _section_heading_for(line: Line) -> Tuple[Optional[str], Optional[str]]:
    # A short, bold line beginning with a section number like "5.1 Foo".
    if not line.is_bold:
        return None, None
    if len(line.text) > 120:
        return None, None
    m = SECTION_HEADING_RE.match(line.text)
    if m:
        return "section", m.group(1)
    return None, None


# ---------------------------------------------------------------------------
# Build definition registry & references
# ---------------------------------------------------------------------------
def build_definitions(lines: List[Line]) -> Dict[Tuple[str, str], Definition]:
    """First occurrence per (kind, num) wins."""
    defs: Dict[Tuple[str, str], Definition] = {}
    for ln in lines:
        if ln.caption_kind is None or ln.caption_num is None:
            continue
        key = (ln.caption_kind, _norm_num(ln.caption_num))
        if key in defs:
            continue
        defs[key] = Definition(
            kind=ln.caption_kind, num=ln.caption_num,
            page=ln.page, y=ln.y, text=ln.text,
        )
    return defs


def _norm_num(n: str) -> str:
    # Normalise "5" vs "5.0"; keep dotted form, strip leading zeros per part.
    parts = [p.lstrip("0") or "0" for p in n.split(".")]
    return ".".join(parts)


def collect_references(
    lines: List[Line],
    skip_kinds: set,
    defs: Dict[Tuple[str, str], Definition],
    skip_bare_eqs: bool = False,
) -> List[Reference]:
    refs: List[Reference] = []
    for ln in lines:
        # Skip caption/anchor lines themselves (their leading "Figure 5" is
        # the definition, not a forward reference).
        if ln.caption_kind is not None:
            continue
        if _is_toc_or_bib(ln.text):
            continue
        seen_on_line: set = set()
        for kind, pat in REF_PATTERNS:
            if kind in skip_kinds:
                continue
            for m in pat.finditer(ln.text):
                num = m.group(1)
                if not num:
                    continue
                seen_on_line.add((kind, _norm_num(num)))
                refs.append(Reference(
                    kind=kind, num=num, page=ln.page, y=ln.y,
                    snippet=_snippet(ln.text, m),
                ))
        # Bare "(N)" equation references: only counted as equation references
        # when a matching equation tag is registered.  This keeps arbitrary
        # parenthesised numbers (tuples, list items, citations) from turning
        # into noise — they simply resolve to nothing and are dropped.
        if not skip_bare_eqs and "equation" not in skip_kinds:
            for m in BARE_EQ_REF_RE.finditer(ln.text):
                num = m.group(1)
                key = ("equation", _norm_num(num))
                if key in defs and key not in seen_on_line:
                    seen_on_line.add(key)
                    refs.append(Reference(
                        kind="equation", num=num, page=ln.page, y=ln.y,
                        snippet=_snippet(ln.text, m),
                    ))
    return refs


def _snippet(text: str, m: re.Match, width: int = 90) -> str:
    start = max(0, m.start() - width // 2)
    end = min(len(text), m.end() + width // 2)
    snip = text[start:end].replace("\n", " ")
    pre = "…" if start > 0 else ""
    post = "…" if end < len(text) else ""
    return f"{pre}{snip}{post}"


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
def analyze(
    refs: List[Reference],
    defs: Dict[Tuple[str, str], Definition],
    page_height: float,
    threshold: float,
    any_forward: bool,
) -> Tuple[List[Finding], List[Reference]]:
    """Return (flagged_findings, unresolved_references)."""
    findings: List[Finding] = []
    unresolved: List[Reference] = []
    seen: set = set()
    for r in refs:
        key = (r.kind, _norm_num(r.num))
        d = defs.get(key)
        if d is None:
            unresolved.append(r)
            continue
        # Forward if definition is strictly below the reference in reading order.
        if (d.page, d.y) <= (r.page, r.y):
            continue  # backward or same line -> not a forward ref
        distance = (d.page - r.page) + (d.y - r.y) / page_height
        if distance <= 0:
            continue
        is_forward = distance > 0
        if not is_forward:
            continue
        if not any_forward and distance <= threshold:
            continue
        dedup_key = (r.kind, r.num, r.page, round(r.y))
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        findings.append(Finding(
            kind=r.kind, num=r.num,
            ref_page=r.page, ref_y=r.y,
            def_page=d.page, def_y=d.y,
            distance_pages=distance,
            snippet=r.snippet,
            def_text=d.text[:120],
        ))
    findings.sort(key=lambda f: (f.ref_page, f.ref_y))
    return findings, unresolved


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def render_report(
    findings: List[Finding],
    unresolved: List[Reference],
    defs: Dict[Tuple[str, str], Definition],
    n_lines: int,
    page_height: float,
    threshold: float,
    any_forward: bool,
    path: str,
    markdown: bool,
) -> str:
    h = "##" if markdown else "=="
    bullet = "- " if markdown else "  * "
    lines: List[str] = []

    lines.append(f"{h} Cross-reference forward-reference lint report")
    lines.append(f"File: {path}")
    lines.append(f"Lines scanned: {n_lines}")
    lines.append(f"Floats defined: {len(defs)}")
    lines.append(f"Threshold: {'any forward' if any_forward else f'>{threshold:.2f} pages ahead'}")
    lines.append(f"Forward references flagged: {len(findings)}")
    lines.append(f"Unresolved references (no matching float found): {len(unresolved)}")
    lines.append("")

    # Summary by kind.
    by_kind: Dict[str, int] = {}
    for f in findings:
        by_kind[f.kind] = by_kind.get(f.kind, 0) + 1
    if by_kind:
        lines.append(f"{h} By type")
        for k in FLOAT_KINDS:
            if k in by_kind:
                lines.append(f"{bullet}{k}: {by_kind[k]}")
        lines.append("")

    if not findings:
        lines.append("No forward cross-references exceeding the threshold were found.")
        lines.append("")
    else:
        for f in findings:
            pages_ahead = f.def_page - f.ref_page
            same_page_note = ""
            if pages_ahead == 0:
                same_page_note = f" (same page, ~{(f.def_y - f.ref_y)/page_height:.1%} of a page below)"
            lines.append(
                f"{h} {f.kind.capitalize()} {f.num}  —  "
                f"page {f.ref_page} -> defined on page {f.def_page} "
                f"({pages_ahead} page(s) ahead{same_page_note})"
            )
            lines.append(f"{bullet}reference: {f.snippet}")
            lines.append(f"{bullet}defined by: {f.def_text}{'…' if len(f.def_text) == 120 else ''}")
            lines.append("")

    if unresolved:
        lines.append(f"{h} Unresolved references (could not locate a definition)")
        # Collapse duplicates for readability.
        seen: set = set()
        shown = 0
        for r in unresolved:
            key = (r.kind, _norm_num(r.num))
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"{bullet}{r.kind} {r.num}  (first seen on page {r.page})")
            shown += 1
            if shown >= 200:
                lines.append(f"{bullet}... and {len(unresolved) - shown} more")
                break
        lines.append("")

    return "\n".join(lines)


def render_json(findings: List[Finding], unresolved: List[Reference],
                defs, n_lines, page_height, threshold, any_forward, path) -> str:
    return json.dumps({
        "file": path,
        "lines_scanned": n_lines,
        "floats_defined": len(defs),
        "threshold": None if any_forward else threshold,
        "any_forward": any_forward,
        "forward_references_flagged": len(findings),
        "unresolved_count": len(unresolved),
        "findings": [
            {
                "kind": f.kind,
                "number": f.num,
                "ref_page": f.ref_page,
                "def_page": f.def_page,
                "pages_ahead": f.def_page - f.ref_page,
                "distance_pages": round(f.distance_pages, 3),
                "snippet": f.snippet,
                "definition_text": f.def_text,
            }
            for f in findings
        ],
    }, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_page_range(s: str) -> Optional[Tuple[int, int]]:
    if not s:
        return None
    m = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", s)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        return (min(lo, hi), max(lo, hi))
    m = re.match(r"^\s*(\d+)\s*$", s)
    if m:
        n = int(m.group(1))
        return (n, n)
    raise ValueError(f"Bad --pages value: {s!r} (expected '1-120' or '5')")


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="Flag forward cross-references (figures, equations, "
                    "tables, ...) to floats defined much further below in a "
                    "thesis PDF.",
    )
    p.add_argument("pdf", help="Path to the thesis PDF.")
    p.add_argument("--out", help="Write report to this file instead of stdout.")
    p.add_argument("--format", choices=["text", "markdown", "json"], default="text")
    p.add_argument("--pages", default=None, help="Page range e.g. '1-120' or '5'.")
    p.add_argument("--threshold", type=float, default=1.0,
                   help="Flag a forward reference only if the definition is "
                        "more than this many pages ahead (default 1.0). "
                        "Distance includes within-page vertical offset.")
    p.add_argument("--any-forward", action="store_true",
                   help="Flag every forward reference regardless of distance.")
    p.add_argument("--no-sections", action="store_true",
                   help="Do not scan for section/chapter references.")
    p.add_argument("--no-equations", action="store_true",
                   help="Do not scan for equation references.")
    p.add_argument("--no-bare-eqs", action="store_true",
                   help="Do not treat bare '(N)' as equation references; only "
                        "explicit 'Eq./Equation (N)' patterns count. By default "
                        "bare '(N)' is resolved against registered equation tags.")
    p.add_argument("--no-appendix", action="store_true",
                   help="Do not scan for appendix references.")
    p.add_argument("--json", help="Also write findings as JSON to this path.")
    args = p.parse_args(argv)

    if fitz is None:
        print("ERROR: PyMuPDF required. pip install pymupdf", file=sys.stderr)
        return 2

    skip_kinds: set = set()
    if args.no_sections:
        skip_kinds.update({"section", "chapter"})
    if args.no_equations:
        skip_kinds.add("equation")
    if args.no_appendix:
        skip_kinds.add("appendix")

    page_range = parse_page_range(args.pages) if args.pages else None
    lines, page_height = extract_lines(args.pdf, page_range)
    if not lines:
        print("ERROR: no text extracted from PDF.", file=sys.stderr)
        return 1

    defs = build_definitions(lines)
    refs = collect_references(lines, skip_kinds, defs,
                              skip_bare_eqs=args.no_bare_eqs)
    findings, unresolved = analyze(
        refs, defs, page_height,
        threshold=args.threshold, any_forward=args.any_forward,
    )

    if args.format == "json":
        out = render_json(findings, unresolved, defs, len(lines),
                          page_height, args.threshold, args.any_forward, args.pdf)
    else:
        out = render_report(
            findings, unresolved, defs, len(lines), page_height,
            args.threshold, args.any_forward, args.pdf,
            markdown=(args.format == "markdown"),
        )

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(out)
        print(f"Report written to {args.out}", file=sys.stderr)
    else:
        print(out)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            fh.write(render_json(findings, unresolved, defs, len(lines),
                                 page_height, args.threshold,
                                 args.any_forward, args.pdf))
        print(f"JSON written to {args.json}", file=sys.stderr)

    # Exit code: 1 if any finding, 0 otherwise (handy for CI/pre-commit).
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
