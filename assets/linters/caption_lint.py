#!/usr/bin/env python3
"""Linter: figure/table captions (ml-theses.org: "Ensure all figures are
clear, labelled, and have informative captions").

Findings:
  [WARN] SHORT-CAPTION   caption with fewer than --min-words words — a bare
                         "Figure 3: Results." tells the reader nothing
  [WARN] NO-CAPTION      (LaTeX mode) figure/table environment without a
                         \\caption
  [INFO] CAPTION         caption inventory line (--list only)

Whether a caption is truly *informative* (states what to see, defines
symbols/axes) is judged per caption by caption_lint_llm.py (and globally
by thesis_checklist_llm.py); this linter catches the mechanical failures.
Axis labelling cannot be checked from extracted text.

Input: thesis PDF or LaTeX sources.
Usage:
  python3 caption_lint.py thesis.pdf
  python3 caption_lint.py main.tex chapters/ --min-words 8
Exit status: 0 clean, 1 findings (WARN or worse), 2 usage error.
"""

import argparse
import re
from typing import List

from lintutil import Report, is_toc_line, load_lines, tex_files

PDF_CAPTION_RE = re.compile(
    r"^(Figure|Fig\.|Table|Tab\.|Algorithm|Listing)\s+(\d+(?:\.\d+)*)\s*[:.]\s*(.*)")


def word_count(text: str) -> int:
    """Count alphabetic words, ignoring bare numbers and punctuation so
    a caption's informativeness is judged on actual words."""
    return len(re.findall(r"[A-Za-z][A-Za-z\-']*", text))


def lint_pdf(path: str, rep: Report, min_words: int, list_all: bool) -> None:
    """Find captions in extracted PDF text and flag short ones.

    Detects lines opening with 'Figure/Table/... N:' , rejoins the
    following wrapped lines back into the caption, and adds a
    SHORT-CAPTION finding (or a CAPTION inventory line under --list).
    """
    lines, _ = load_lines([path])
    i = 0
    while i < len(lines):
        where, t = lines[i]
        s = t.strip()
        m = PDF_CAPTION_RE.match(s)
        if m and not is_toc_line(s):
            kind, num, rest = m.groups()
            # captions wrap: join following indented/short lines until blank
            j = i + 1
            parts = [rest]
            while j < len(lines) and lines[j][1].strip() and \
                    not PDF_CAPTION_RE.match(lines[j][1].strip()) and \
                    j - i < 6:
                parts.append(lines[j][1].strip())
                j += 1
            caption = " ".join(parts).strip()
            wc = word_count(caption)
            if wc < min_words:
                rep.add("WARN", "SHORT-CAPTION", where,
                        f"{kind} {num}: only {wc} word(s) — "
                        f"\"{caption[:80]}\"")
            elif list_all:
                rep.add("INFO", "CAPTION", where,
                        f"{kind} {num} ({wc} words): \"{caption[:70]}…\"")
            i = j
            continue
        i += 1


def lint_tex(paths: List[str], rep: Report, min_words: int,
             list_all: bool) -> None:
    """Scan LaTeX figure/table environments for caption problems.

    Reports NO-CAPTION for an environment with no `\\caption`, else
    brace-matches the caption argument, strips its markup, and flags it
    as SHORT-CAPTION when too few words remain.
    """
    for f in tex_files(paths):
        text = f.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(
                r"\\begin\{(figure|table)\*?\}(.*?)\\end\{\1\*?\}",
                text, re.S):
            env, body = m.group(1), m.group(2)
            lineno = text[:m.start()].count("\n") + 1
            where = f"{f}:{lineno}"
            cm = re.search(r"\\caption(?:\[[^\]]*\])?\{", body)
            if not cm:
                rep.add("WARN", "NO-CAPTION", where,
                        f"{env} environment without \\caption.")
                continue
            # crude brace matching for the caption argument
            depth, k = 1, cm.end()
            while k < len(body) and depth:
                if body[k] == "{" and body[k-1] != "\\":
                    depth += 1
                elif body[k] == "}" and body[k-1] != "\\":
                    depth -= 1
                k += 1
            caption = re.sub(r"\\[A-Za-z]+\*?(\[[^\]]*\])?|\{|\}", " ",
                             body[cm.end():k-1])
            wc = word_count(caption)
            if wc < min_words:
                rep.add("WARN", "SHORT-CAPTION", where,
                        f"{env} caption has only {wc} word(s): "
                        f"\"{caption.strip()[:80]}\"")
            elif list_all:
                rep.add("INFO", "CAPTION", where,
                        f"{env} caption ({wc} words).")


def main(argv: List[str] = None) -> int:
    ap = argparse.ArgumentParser(description="Figure/table caption linter.")
    ap.add_argument("inputs", nargs="+", help="thesis.pdf or .tex files/dirs")
    ap.add_argument("--min-words", type=int, default=6,
                    help="Captions shorter than this many words are "
                         "flagged (default 6).")
    ap.add_argument("--list", action="store_true", dest="list_all",
                    help="Also list every caption found (inventory).")
    args = ap.parse_args(argv)

    rep = Report("Caption lint report", " ".join(args.inputs),
                 about="Checks that every figure and table has a caption that "
                       "is present and long enough to be informative.")
    if len(args.inputs) == 1 and args.inputs[0].lower().endswith(".pdf"):
        lint_pdf(args.inputs[0], rep, args.min_words, args.list_all)
    else:
        lint_tex(args.inputs, rep, args.min_words, args.list_all)

    print(rep.render())
    return rep.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
