#!/usr/bin/env python3
"""Structure linter: sectioning units with exactly one child.

A chapter with a single section, or a section with a single subsection, is
a structural smell: a lone child cannot articulate a division, so either
the child heading should be dropped (folding its text into the parent) or
a sibling is missing. The ml-theses.org guide asks for zero or >= 2
subdivisions at every level.

Input handling:
  * PDF: prefers the embedded bookmark outline (PyMuPDF); falls back to
    scanning the extracted text for numbered headings ("2", "2.1", "A.1").
  * LaTeX: parses \\chapter/\\section/\\subsection/\\subsubsection in
    source order (starred variants are unnumbered and skipped).

Findings are WARN LONE-CHILD, one per offending parent unit.

Usage:
  python3 structure_lint.py thesis.pdf
  python3 structure_lint.py main.tex chapters/
Exit status: 0 clean, 1 findings.
"""

import re
import sys
from typing import List, Optional, Tuple

from lintutil import Line, Report, load_lines, strip_tex_comments, tex_files

# (level, number-or-None, title, location); level 1 = top (chapter)
Unit = Tuple[int, Optional[str], str, str]


# ---------------------------------------------------------------------------
# PDF: bookmark outline, then text-scan fallback
# ---------------------------------------------------------------------------
def outline_units(path: str) -> List[Unit]:
    """Read sectioning units from the PDF's embedded bookmark outline via
    PyMuPDF. Splits a leading number (``2``, ``2.1``, ``A.1``) off each
    title. Returns [] if PyMuPDF is missing or the PDF has no outline."""
    try:
        import fitz
    except ImportError:
        return []
    try:
        doc = fitz.open(path)
        toc = doc.get_toc()
        doc.close()
    except Exception:
        return []
    units: List[Unit] = []
    for level, title, page in toc:
        title = title.strip()
        m = re.match(r"^(\d+(?:\.\d+)*|[A-Z](?:\.\d+)*)\.?\s+(\S.*)$", title)
        number, name = (m.group(1), m.group(2)) if m else (None, title)
        units.append((level, number, name, f"p{page}"))
    return units


HEADING_RE = re.compile(
    r"^\s*(\d+(?:\.\d+)*|[A-Z](?:\.\d+)+)\.?\s+([A-Z]\S*(?:\s+\S+)*?)\s*$")


def scanned_units(lines: List[Line]) -> List[Unit]:
    """Fallback: collect numbered headings from extracted text. Keeps the
    first occurrence of each number (usually the table of contents, which
    lists every unit in order)."""
    seen = {}
    order: List[Unit] = []
    for where, text in lines:
        m = HEADING_RE.match(text.rstrip(" .0123456789") or "")
        if not m:
            continue
        number, name = m.group(1), m.group(2)
        parts = number.split(".")
        # Years, page numbers, versions: top-level numeric chapters are
        # small, and every sub-unit must extend an already-seen parent.
        if parts[0].isdigit() and int(parts[0]) > 40:
            continue
        if len(parts) > 1 and ".".join(parts[:-1]) not in seen:
            continue
        if number in seen:
            continue
        seen[number] = True
        order.append((len(parts), number, name, where))
    return order


# ---------------------------------------------------------------------------
# LaTeX sources
# ---------------------------------------------------------------------------
TEX_UNIT_RE = re.compile(
    r"\\(chapter|section|subsection|subsubsection)(\*?)\s*(?:\[[^\]]*\])?"
    r"\{([^}]*)\}")
TEX_LEVELS = {"chapter": 0, "section": 1, "subsection": 2, "subsubsection": 3}


def tex_units(paths: List[str]) -> List[Unit]:
    """Collect sectioning units from LaTeX sources in source order.

    Skips starred (unnumbered) variants. Levels are normalised so the
    shallowest command present becomes level 1, letting article-class
    sources (no ``\\chapter``) share the same lone-child check as reports.
    """
    units: List[Unit] = []
    for f in tex_files(paths):
        try:
            raw = f.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            sys.exit(f"Cannot read {f}: {e}")
        for i, ln in enumerate(raw.splitlines(), start=1):
            for m in TEX_UNIT_RE.finditer(strip_tex_comments(ln)):
                if m.group(2):        # starred variant: unnumbered
                    continue
                units.append((TEX_LEVELS[m.group(1)], None,
                              m.group(3).strip(), f"{f}:{i}"))
    if not units:
        return []
    top = min(u[0] for u in units)    # article-class sources have no \chapter
    return [(lvl - top + 1, num, name, where)
            for (lvl, num, name, where) in units]


# ---------------------------------------------------------------------------
# The check: every unit must have zero or >= 2 children
# ---------------------------------------------------------------------------
def lone_children(units: List[Unit]) -> List[Tuple[Unit, Unit]]:
    """Return (parent, only-child) pairs for units with exactly one child."""
    bad = []
    for i, (lvl, num, name, where) in enumerate(units):
        children = []
        for lvl2, num2, name2, where2 in units[i + 1:]:
            if lvl2 <= lvl:
                break
            if lvl2 == lvl + 1:
                children.append((lvl2, num2, name2, where2))
        if len(children) == 1:
            bad.append(((lvl, num, name, where), children[0]))
    return bad


def label(unit: Unit) -> str:
    _, num, name, _ = unit
    return f"{num} {name}" if num else name


def main(argv: List[str] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="Structure linter: units with exactly one subdivision.")
    ap.add_argument("inputs", nargs="+", help="thesis.pdf or .tex files/dirs")
    ap.add_argument("--profile", choices=["thesis", "paper"], default="thesis",
                    help="'paper' downgrades LONE-CHILD to INFO (a two-column "
                         "paper legitimately has single-subsection sections).")
    args = ap.parse_args(argv)

    pdf_mode = (len(args.inputs) == 1
                and args.inputs[0].lower().endswith(".pdf"))
    if pdf_mode:
        units = outline_units(args.inputs[0])
        via = "PDF outline"
        if not units:
            lines, _ = load_lines(args.inputs)
            units = scanned_units(lines)
            via = "text scan"
    else:
        units = tex_units(args.inputs)
        via = "LaTeX sources"

    rep = Report("Structure lint report", " ".join(args.inputs),
                 about="Flags sectioning units with exactly one subdivision "
                       "(a lone subsection cannot articulate its parent "
                       "heading).")
    if not units:
        print(rep.render())
        print("\nNo sectioning units found — nothing to check.",
              file=sys.stderr)
        return 0

    severity = "INFO" if args.profile == "paper" else "WARN"
    for parent, child in lone_children(units):
        rep.add(severity, "LONE-CHILD", parent[3],
                f"'{label(parent)}' has exactly one subdivision "
                f"('{label(child)}') — fold it into the parent or add a "
                f"sibling; every unit needs zero or >= 2 subdivisions")

    print(rep.render())
    print(f"\n{len(units)} sectioning unit(s) checked (via {via}).")
    return rep.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
