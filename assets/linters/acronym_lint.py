#!/usr/bin/env python3
"""Linter: acronym discipline (ml-theses.org self-editing pass).

Guideline enforced: "Expand each acronym at first use, then use it
consistently; do not re-expand it later."

Findings:
  [WARN] USED-BEFORE-EXPANSION  acronym used before its inline expansion
                                "Long Name (LN)" appears
  [WARN] NEVER-EXPANDED         acronym used repeatedly but never expanded
  [WARN] RE-EXPANDED            inline expansion repeated after first use
  [INFO] EXPANDED-ONCE-UNUSED   acronym expanded but never used again

Input: a thesis PDF or LaTeX sources (files/directories). Abstract pages are
treated leniently (an abstract conventionally re-expands acronyms), as are
figure/table captions and the reference list.

Usage:
  python3 acronym_lint.py thesis.pdf
  python3 acronym_lint.py main.tex chapters/
Exit status: 0 clean, 1 findings (WARN or worse), 2 usage error.
"""

import argparse
import re
import sys
from typing import Dict, List, Tuple

from lintutil import Report, is_toc_line, load_lines

# Acronym: 2-6 chars, mostly capitals, may contain digits/hyphens (ReLU, k-NN
# handled via explicit pattern below). Whitelisted tokens are never flagged.
ACRO_RE = re.compile(r"\b([A-Z][A-Za-z]?[A-Z0-9][A-Z0-9a-z]{0,4})\b")
EXPANSION_RE = re.compile(
    r"([A-Za-z][A-Za-z\-']*(?:[ \-][A-Za-z][A-Za-z\-']*){1,7})\s*"
    r"\(\s*([A-Z][A-Za-z]?[A-Z0-9][A-Za-z0-9\-]{0,8}s?)\s*\)")

WHITELIST = {
    # Roman numerals, units, common non-acronym capitals
    "II", "III", "IV", "VI", "VII", "IX", "XI", "XII",
    "USA", "UK", "EU", "US", "PhD", "MSc", "BSc", "DSc",
    "IEEE", "ACM", "ISBN", "ISSN", "DOI", "URL", "HTTP", "HTTPS", "WWW",
    "CPU", "GPU", "RAM", "TPU", "GHz", "MHz", "GB", "MB", "KB", "TB",
    "3D", "2D", "1D", "OK", "ID", "AND", "OR", "NOT", "THE", "IF",
    "LaTeX", "TeX", "PDF", "CSV", "JSON", "XML", "SQL", "API",
    "Eq", "Fig", "Tab", "Sec", "Ch", "App", "Alg",
    "TODO", "NOTE",
}

TEX_STRIP_RE = re.compile(
    r"\\(?:cite[pt]?|ref|eqref|autoref|cref|Cref|label|includegraphics|"
    r"input|include|bibliography\w*|url|href)\*?(?:\[[^\]]*\])?\{[^}]*\}")
MATH_RE = re.compile(r"\$[^$]*\$|\\\[[^\]]*\\\]|\\\(.*?\\\)")


def clean_line(text: str, mode: str) -> str:
    if mode == "tex":
        text = TEX_STRIP_RE.sub(" ", text)
        text = MATH_RE.sub(" ", text)
        text = re.sub(r"\\[A-Za-z]+", " ", text)
    else:
        text = re.sub(r"\[\d+(?:,\s*\d+)*\]", " ", text)  # [12] citations
    return text


def is_heading_or_caption(text: str) -> bool:
    t = text.strip()
    return bool(re.match(r"^(Figure|Fig\.|Table|Tab\.|Algorithm|Listing|"
                         r"Chapter|Appendix)\b", t))


def main(argv: List[str] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Acronym linter: expand at first use, no re-expansion.")
    ap.add_argument("inputs", nargs="+", help="thesis.pdf or .tex files/dirs")
    ap.add_argument("--min-uses", type=int, default=2,
                    help="Flag NEVER-EXPANDED only if used at least this "
                         "many times (default 2).")
    ap.add_argument("--skip-pages", type=int, default=0,
                    help="PDF mode: ignore the first N pages (cover, "
                         "abstract; default 0).")
    args = ap.parse_args(argv)

    try:
        lines, mode = load_lines(args.inputs)
    except SystemExit:
        raise
    if mode == "pdf" and args.skip_pages:
        lines = [(w, t) for (w, t) in lines
                 if int(w[1:]) > args.skip_pages]

    rep = Report("Acronym lint report", " ".join(args.inputs))

    # Pass 1: collect, in reading order, every acronym use and expansion.
    uses: Dict[str, List[Tuple[int, str]]] = {}        # acro -> [(seq, where)]
    expansions: Dict[str, List[Tuple[int, str, str]]] = {}  # acro -> [(seq, where, long)]
    seq = 0
    in_references = False
    for where, raw in lines:
        if is_toc_line(raw):
            continue
        t = raw.strip()
        if re.match(r"^(References|Bibliography)\s*$", t, re.I):
            in_references = True
        if in_references:
            continue
        text = clean_line(raw, mode)
        seq += 1
        for m in EXPANSION_RE.finditer(text):
            long_form, acro = m.group(1), m.group(2)
            key = acro.rstrip("s")
            # Plausibility: expansion words should roughly supply the
            # acronym's letters (first letters of words vs acronym letters).
            initials = "".join(w[0] for w in re.split(r"[ \-]", long_form)
                               if w).lower()
            letters = re.sub(r"[^A-Za-z]", "", key).lower()
            if len(letters) < 2:
                continue
            hits = sum(1 for c in letters if c in initials)
            if hits < max(2, len(letters) - 1):
                continue
            expansions.setdefault(key, []).append((seq, where, long_form))
        for m in ACRO_RE.finditer(text):
            acro = m.group(1)
            key = acro.rstrip("s")
            if key in WHITELIST or len(re.sub(r"[^A-Z]", "", key)) < 2:
                continue
            uses.setdefault(key, []).append((seq, where))

    # Pass 2: findings.
    for acro, exps in sorted(expansions.items()):
        first_exp_seq, first_exp_where, long_form = exps[0]
        early_uses = [w for (s, w) in uses.get(acro, [])
                      if s < first_exp_seq]
        # Uses on the very line of the expansion get the same seq; fine.
        if early_uses:
            rep.add("WARN", "USED-BEFORE-EXPANSION", early_uses[0],
                    f"'{acro}' used at {early_uses[0]} before its expansion "
                    f"\"{long_form} ({acro})\" at {first_exp_where} "
                    f"({len(early_uses)} early use(s)).")
        for s, w, lf in exps[1:]:
            rep.add("WARN", "RE-EXPANDED", w,
                    f"'{acro}' re-expanded as \"{lf}\" (first expanded at "
                    f"{first_exp_where}).")
        later_uses = [1 for (s, w) in uses.get(acro, []) if s > first_exp_seq]
        if not later_uses:
            rep.add("INFO", "EXPANDED-ONCE-UNUSED", first_exp_where,
                    f"'{acro}' expanded as \"{long_form}\" but never "
                    f"used afterwards — consider dropping the acronym.")

    for acro, occ in sorted(uses.items()):
        if acro in expansions:
            continue
        if len(occ) >= args.min_uses:
            rep.add("WARN", "NEVER-EXPANDED", occ[0][1],
                    f"'{acro}' used {len(occ)} time(s) but never expanded "
                    f"(first use at {occ[0][1]}).")

    print(rep.render())
    return rep.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
