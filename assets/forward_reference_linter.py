#!/usr/bin/env python3
"""Forward-reference linter for thesis drafts.

A *forward reference* points the reader ahead to material they have not read
yet ("as we will see in Chapter 5", or a ``\\ref`` to a ``\\label`` that is
defined later in the document). A few are fine; a habit of them signals
disorganised structure and forces the reader to jump around. See the
"Self-Editing Pass (Prose Linter)" section of the ML-theses guide:
https://ml-theses.org/#self-editing-pass-prose-linter

This script flags two kinds of forward reference in ``.tex`` (and, for the
phrase check, ``.md``) sources:

1. **Cue phrases** — forward-looking wording such as "as we will see",
   "in the following section", "discussed below", "in the sequel".

2. **Cross-references defined later** (LaTeX only) — a ``\\ref``/``\\eqref``/
   ``\\cref``/``\\autoref``/... whose target ``\\label`` first appears *after*
   the citation in reading order. Pass the source files in the order they are
   ``\\input`` into the main document so the ordering is meaningful:

       forward_reference_linter.py intro.tex methods.tex results.tex

It is a *heuristic aid*, not a proofreader: expect false positives (a "below"
that is genuinely local) and skim the report rather than fixing blindly. The
exit status is non-zero when any issue is found, so it can be dropped into a
pre-commit hook or CI step.

Standard library only; runs on Python 3.8+.

Usage:
    forward_reference_linter.py [options] FILE [FILE ...]
    forward_reference_linter.py [options] DIR        # scans *.tex/*.md within

Options:
    --phrases-only   Only run the cue-phrase check (skip \\ref/\\label ordering).
    --refs-only      Only run the \\ref-before-\\label check (LaTeX only).
    --quiet          Print only the summary line.
    -h, --help       Show this help.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple, Tuple

# --------------------------------------------------------------------------- #
# 1. Forward-looking cue phrases.
#
# Each entry is (compiled regex, short reason). Patterns are matched
# case-insensitively against the raw source text. They are deliberately
# conservative: anchored on wording that almost always points *ahead*
# ("will", "following", "below", "later", "sequel") rather than on bare
# "see ..." which is just as often a backward reference.
# --------------------------------------------------------------------------- #

_CUE_PATTERNS: List[Tuple[str, str]] = [
    (r"\bas\s+we\s+(?:will|shall)\s+see\b", "points the reader ahead"),
    (r"\bwe\s+(?:will|shall)\s+see\b", "points the reader ahead"),
    (r"\bas\s+(?:we\s+(?:will|shall)|will\s+be)\s+"
     r"(?:shown|show|discuss(?:ed)?|describe[d]?|explain(?:ed)?|"
     r"present(?:ed)?|introduce[d]?|define[d]?|see[n]?)\b",
     "defers content to later"),
    (r"\bwill\s+be\s+"
     r"(?:shown|discussed|described|explained|presented|introduced|"
     r"defined|derived|proven|proved|addressed)\b",
     "defers content to later"),
    (r"\bin\s+the\s+(?:following|next|coming|subsequent|remaining)\s+"
     r"(?:section|subsection|chapter|part|paragraph)s?\b",
     "refers ahead to a later section/chapter"),
    (r"\b(?:discussed|described|shown|presented|defined|introduced|"
     r"derived|explained|detailed|elaborated)\s+(?:further\s+)?"
     r"(?:below|later|hereafter|subsequently)\b",
     "points the reader ahead"),
    (r"\b(?:see|cf\.?)\s+(?:the\s+)?"
     r"(?:section|chapter|figure|fig\.?|table|equation|eq\.?)\s+\S*\s*"
     r"(?:below|later)\b",
     "explicit forward pointer"),
    (r"\b(?:further|more)\s+(?:on\s+this\s+)?(?:below|later)\b",
     "points the reader ahead"),
    (r"\blater\s+(?:in\s+this\s+(?:thesis|chapter|section|work)|on)\b",
     "points the reader ahead"),
    (r"\bin\s+the\s+sequel\b", "points the reader ahead"),
    (r"\b(?:we\s+)?(?:return|come\s+back)\s+to\s+this\b[^.]*\blater\b",
     "defers content to later"),
    (r"\b(?:as\s+)?(?:detailed|elaborated|explained)\s+below\b",
     "points the reader ahead"),
    (r"\bfor\s+now\b", "signals a deferred explanation"),
]

_CUES = [(re.compile(p, re.IGNORECASE), reason) for p, reason in _CUE_PATTERNS]

# LaTeX comments (an unescaped %% to end of line) are stripped before matching
# so commented-out text is not flagged.
_COMMENT_RE = re.compile(r"(?<!\\)%.*")

_LABEL_RE = re.compile(r"\\label\s*\{([^}]+)\}")
_REF_RE = re.compile(
    r"\\(?:eq|c|C|auto|page|name|v|Cpage|labelc)?ref\*?\s*\{([^}]+)\}"
)

_TEX_SUFFIXES = {".tex", ".ltx"}
_TEXT_SUFFIXES = _TEX_SUFFIXES | {".md", ".markdown", ".txt"}


class Finding(NamedTuple):
    file: str
    line: int
    kind: str          # "phrase" or "xref"
    message: str
    excerpt: str


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _excerpt(text: str, start: int, end: int, width: int = 70) -> str:
    """A trimmed one-line snippet around [start, end) for the report."""
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end == -1:
        line_end = len(text)
    snippet = text[line_start:line_end].strip()
    if len(snippet) > width:
        # Keep the matched span visible, trimming the surroundings.
        rel = start - line_start
        lo = max(0, rel - width // 2)
        snippet = ("…" if lo > 0 else "") + snippet[lo:lo + width] + "…"
    return snippet


def _strip_comments(text: str, is_tex: bool) -> str:
    """Blank out LaTeX comments while preserving character offsets/line numbers."""
    if not is_tex:
        return text
    return _COMMENT_RE.sub(lambda m: " " * len(m.group(0)), text)


def find_cue_phrases(text: str, path: str, is_tex: bool) -> List[Finding]:
    scanned = _strip_comments(text, is_tex)
    # Collect every match, then keep only non-overlapping ones (leftmost wins)
    # so two patterns hitting the same span report the spot once.
    matches = sorted(
        (m.start(), m.end(), reason)
        for regex, reason in _CUES
        for m in regex.finditer(scanned))
    findings: List[Finding] = []
    covered_to = -1
    for start, end, reason in matches:
        if start < covered_to:
            continue
        covered_to = end
        findings.append(Finding(
            file=path,
            line=_line_of(text, start),
            kind="phrase",
            message=reason,
            excerpt=_excerpt(text, start, end),
        ))
    return findings


class _Event(NamedTuple):
    seq: int
    file: str
    line: int
    key: str
    text: str


def find_late_defined_refs(
    tex_files: List[Tuple[str, str]]
) -> Tuple[List[Finding], List[Finding]]:
    """Detect \\refs whose \\label is first defined later in reading order.

    ``tex_files`` is a list of (path, text) in the order the files are read
    into the document. Returns (forward_refs, undefined_refs).
    """
    seq = 0
    label_first: Dict[str, _Event] = {}   # key -> earliest \label event
    refs: List[_Event] = []

    for path, text in tex_files:
        scanned = _strip_comments(text, is_tex=True)
        events: List[Tuple[int, str, str]] = []  # (offset, kind, key)
        for m in _LABEL_RE.finditer(scanned):
            events.append((m.start(), "label", m.group(1).strip()))
        for m in _REF_RE.finditer(scanned):
            for key in m.group(1).split(","):  # \cref{a,b,c}
                events.append((m.start(), "ref", key.strip()))
        events.sort(key=lambda e: e[0])
        for offset, kind, key in events:
            seq += 1
            ev = _Event(seq, path, _line_of(text, offset), key,
                        _excerpt(text, offset, offset))
            if kind == "label":
                label_first.setdefault(key, ev)
            else:
                refs.append(ev)

    forward: List[Finding] = []
    undefined: List[Finding] = []
    for ref in refs:
        label = label_first.get(ref.key)
        if label is None:
            undefined.append(Finding(
                ref.file, ref.line, "xref",
                f"reference to undefined label '{ref.key}'", ref.text))
        elif label.seq > ref.seq:
            forward.append(Finding(
                ref.file, ref.line, "xref",
                f"'{ref.key}' is first defined later "
                f"({Path(label.file).name}:{label.line})", ref.text))
    return forward, undefined


def gather_files(paths: List[str]) -> List[Path]:
    out: List[Path] = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            out.extend(sorted(
                f for f in path.rglob("*")
                if f.suffix.lower() in _TEXT_SUFFIXES))
        else:
            out.append(path)
    return out


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Flag forward references in thesis drafts.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Pass .tex files in \\input order for the cross-reference check.")
    parser.add_argument("paths", nargs="+", metavar="FILE",
                        help="source files or a directory to scan")
    parser.add_argument("--phrases-only", action="store_true",
                        help="only run the cue-phrase check")
    parser.add_argument("--refs-only", action="store_true",
                        help="only run the \\ref-before-\\label check")
    parser.add_argument("--quiet", action="store_true",
                        help="print only the summary line")
    args = parser.parse_args(argv)

    if args.phrases_only and args.refs_only:
        parser.error("--phrases-only and --refs-only are mutually exclusive")

    files = gather_files(args.paths)
    loaded: List[Tuple[str, str, bool]] = []  # (path, text, is_tex)
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print(f"warning: cannot read {f}: {exc}", file=sys.stderr)
            continue
        loaded.append((str(f), text, f.suffix.lower() in _TEX_SUFFIXES))

    if not loaded:
        print("No readable source files found.", file=sys.stderr)
        return 2

    findings: List[Finding] = []
    if not args.refs_only:
        for path, text, is_tex in loaded:
            findings.extend(find_cue_phrases(text, path, is_tex))

    undefined: List[Finding] = []
    if not args.phrases_only:
        tex_files = [(p, t) for p, t, is_tex in loaded if is_tex]
        forward, undefined = find_late_defined_refs(tex_files)
        findings.extend(forward)

    findings.sort(key=lambda x: (x.file, x.line))

    if not args.quiet:
        for f in findings:
            tag = "forward-ref" if f.kind == "xref" else "forward-phrase"
            print(f"{f.file}:{f.line}: [{tag}] {f.message}")
            print(f"    {f.excerpt}")
        if undefined:
            print("\nUndefined cross-references (not necessarily forward, "
                  "but worth checking):")
            for f in undefined:
                print(f"{f.file}:{f.line}: {f.message}")
                print(f"    {f.excerpt}")

    n_phrase = sum(1 for f in findings if f.kind == "phrase")
    n_xref = sum(1 for f in findings if f.kind == "xref")
    print(f"\n{len(findings)} forward reference(s): "
          f"{n_phrase} cue phrase(s), {n_xref} late-defined cross-reference(s)"
          + (f"; {len(undefined)} undefined reference(s)" if undefined else ""))

    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
