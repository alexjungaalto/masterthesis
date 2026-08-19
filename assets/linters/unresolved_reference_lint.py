#!/usr/bin/env python3
"""Linter: references the reader cannot resolve within the manuscript.

Two heuristic checks for pointers that send the reader to something they
cannot actually inspect:

  * COMPANION-REF — an appeal to a *companion / separate / forthcoming /
    related* study to carry part of the argument, with no citation backing
    it. E.g. "the remaining nine are evaluated in companion studies on the
    same platform" or "a series of related studies". If the work is cited
    ([n] / \\cite) the reader can find it, so cited sentences are not flagged.
    -> [WARN] COMPANION-REF per uncited occurrence.

  * UNDEFINED-CODE — a scheme of short label codes (R1, R2, ..., T1..T6, H1,
    RQ2, ...) used as load-bearing shorthand but never defined in the text.
    A code is "defined" when it appears with a gloss ("R1 (Fault
    Containment)", "R1: ...", "R1 — ...") or a defining keyword
    ("criterion R1", "R1 denotes ..."). A mere range mention "(R1–R5)" does
    NOT define its members. To stay precise the check only treats a prefix
    as a scheme when it has >= 2 distinct members AND either sits near a
    scheme keyword (criterion / requirement / research question / ...) or
    reaches --min-members distinct members (default 3) on its own — so
    R-squared "R2", the "L1"/"L2" norms, or an "F1" score alone are not
    mistaken for a scheme. It then reports the members used but never defined.
    -> [WARN] UNDEFINED-CODE per scheme with undefined members.

These are exactly the pointers that slip past the other linters: the
forward-reference linters model concepts defined LATER IN THE SAME document,
not appeals to external companion papers; and label codes are neither
acronyms (no expansion) nor dictionary synonyms.

Input: thesis/paper PDF or LaTeX sources.
Usage:
  python3 unresolved_reference_lint.py paper.pdf
  python3 unresolved_reference_lint.py main.tex chapters/
Exit status: 0 clean, 1 findings, 2 usage error.
"""

import argparse
import re
from collections import defaultdict
from typing import List

from lintutil import (Report, is_toc_line, load_lines, paragraphs_from_lines,
                      sentences)

CITATION_RE = re.compile(r"\[\d+(?:,\s*\d+)*\]|\\cite[pt]?\*?\{")

COMPANION_RE = re.compile(
    r"\b("
    r"companion\s+(?:stud(?:y|ies)|paper|papers|work|report)|"
    r"(?:series|set|number)\s+of\s+(?:related|companion)\s+"
    r"(?:stud(?:y|ies)|works?|papers?)|"
    r"in\s+(?:a\s+)?(?:separate|companion|parallel|forthcoming)\s+"
    r"(?:stud(?:y|ies)|paper|work|report|manuscript)|"
    r"(?:reported|evaluated|assessed|addressed|presented|described|"
    r"analy[sz]ed|examined|treated|studied|shown|demonstrated)\s+"
    r"(?:\w+\s+){0,3}elsewhere|"
    r"(?:remaining|other)\s+(?:\w+\s+){0,3}(?:are|were|is|will\s+be)\s+"
    r"(?:evaluated|addressed|reported|treated|examined|studied|presented|"
    r"described)\s+in\b|"
    r"our\s+(?:companion|separate|forthcoming|other|prior)\s+"
    r"(?:work|stud(?:y|ies)|paper|papers)|"
    r"reported\s+elsewhere|"
    r"forthcoming|in\s+preparation|under\s+review|to\s+appear"
    r")\b", re.I)

# A short label code: 1–3 uppercase letters + 1–2 digits (R1, T6, RQ2, H2).
# 1–2 digits excludes 3-digit hardware ids (A100, V100, H100, P100).
CODE_RE = re.compile(r"\b([A-Z]{1,3})(\d{1,2})\b")

# Conventional notation / domain tokens that are not label schemes.
STOP_CODES = {"R2", "F1", "F2", "L0", "L1", "L2", "P1", "P2", "P3",
              "K1", "K2", "K3", "K5", "K10",
              "S3", "EC2", "CO2", "O2", "H2", "N2", "NO2", "SO2", "H2O",
              "P2P", "V2", "G5", "G4", "G3"}

# A code is "defined" here: gloss in parens/colon/dash, or a defining verb.
def_patterns = [
    r"([A-Z]{1,3}\d{1,2})\s*[\(:]\s*[A-Z]",          # R1 (Fault..., R1: Fault
    r"([A-Z]{1,3}\d{1,2})\s*[—–-]\s*[A-Za-z]",       # R1 — Fault / R1 - Fault
    r"(?:criteri(?:on|a)|requirement|question|hypothesis|objective|"
    r"dimension)\s+([A-Z]{1,3}\d{1,2})\b",           # criterion R1
    r"([A-Z]{1,3}\d{1,2})\s+(?:denotes?|refers?\s+to|stands?\s+for|means?|"
    r"is\s+defined|=)",                              # R1 denotes ...
]
DEF_RE = re.compile("|".join(def_patterns))

SCHEME_KEYWORDS = re.compile(
    r"\b(criteri(?:on|a)|requirements?|research\s+questions?|hypothes[ei]s|"
    r"objectives?|dimensions?)\b", re.I)


def main(argv: List[str] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Linter: unresolvable references (uncited companion "
                    "studies; undefined label-code schemes).")
    ap.add_argument("inputs", nargs="+", help="paper.pdf or .tex files/dirs")
    ap.add_argument("--min-members", type=int, default=3,
                    help="Min distinct members for a code prefix to count as "
                         "a scheme (default 3).")
    args = ap.parse_args(argv)

    lines, mode = load_lines(args.inputs)
    lines = [(w, t) for (w, t) in lines if not is_toc_line(t)]
    rep = Report("Unresolved-reference lint report", " ".join(args.inputs),
                 about="Flags appeals to uncited companion/forthcoming "
                       "studies and label-code schemes (R1, T6, ...) used "
                       "without a definition in the text.")

    code_uses = defaultdict(list)     # code -> [where, ...]
    defined = set()                   # codes with a definition anywhere
    scheme_prefixes = set()           # prefixes seen near a scheme keyword
    in_references = False

    for where, para in paragraphs_from_lines(lines):
        if re.match(r"^(References|Bibliography)\s*(\[1\]|$)",
                    para.strip(), re.I):
            in_references = True
        if in_references:
            continue
        # A paragraph mentioning "criteria", "requirements", etc. makes any
        # codes in it candidate members of a real label scheme.
        near_keyword = bool(SCHEME_KEYWORDS.search(para))
        for code in DEF_RE.findall(para):
            # findall returns tuples (one group per alternative); take the hit
            hit = next((g for g in (code if isinstance(code, tuple)
                                    else (code,)) if g), "")
            if hit:
                defined.add(hit)
        # Record every code occurrence (and its location) for the family
        # tally below; skip known notation tokens and large-numbered ids.
        for m in CODE_RE.finditer(para):
            full, digits = m.group(0), int(m.group(2))
            if full in STOP_CODES or digits > 20:   # schemes are small-numbered
                continue
            code_uses[full].append(where)
            if near_keyword:
                scheme_prefixes.add(m.group(1))
        for sent in sentences(para):
            m = COMPANION_RE.search(sent)
            if m and not CITATION_RE.search(sent):
                rep.add("WARN", "COMPANION-REF", where,
                        f"appeals to '{m.group(1).strip()}' with no citation "
                        f"— the reader cannot verify it; cite the work or "
                        f"state the result here: "
                        f"\"{sent[:100]}{'…' if len(sent) > 100 else ''}\"")

    # Group codes into prefix families; report undefined members of schemes.
    families = defaultdict(dict)      # prefix -> {code: count}
    for code, wheres in code_uses.items():
        prefix = re.match(r"[A-Z]{1,3}", code).group(0)
        families[prefix][code] = len(wheres)
    for prefix, members in sorted(families.items()):
        # A scheme needs >= 2 distinct members (a lone code like "S3"/"B3" is
        # an id or section ref, not a scheme), AND either a member sat next to
        # a scheme keyword or the prefix has >= min-members distinct codes.
        is_scheme = (len(members) >= 2
                     and (prefix in scheme_prefixes
                          or len(members) >= args.min_members))
        if not is_scheme:
            continue
        undef = sorted(c for c in members if c not in defined)
        if not undef:
            continue
        total = sum(members[c] for c in undef)
        sev = "WARN" if total >= 3 else "INFO"
        first = code_uses[undef[0]][0]
        rep.add(sev, "UNDEFINED-CODE", first,
                f"code scheme '{prefix}*' used but not defined in the text: "
                f"{', '.join(undef)} "
                f"({total} use(s); defined members: "
                f"{', '.join(sorted(c for c in members if c in defined)) or 'none'}) "
                f"— define each at first use, e.g. '{undef[0]} (…)'.")

    print(rep.render())
    return rep.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
