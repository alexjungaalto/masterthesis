#!/usr/bin/env python3
"""Linter: reference formatting per IEEE guidelines (ml-theses.org:
"References: Format according to IEEE guidelines").

LaTeX mode (.tex files or directories):
  [ERROR] NO-IEEE-STYLE   \\bibliographystyle is not an IEEE style
                          (expected IEEEtran/ieeetr) and biblatex is not
                          loaded with style=ieee
  [WARN]  NO-BIB-STYLE    no \\bibliographystyle / biblatex style found
  [WARN]  NATBIB-TEXTUAL  \\citet/\\citep textual citations (IEEE uses
                          numeric [n]; typically \\cite with IEEEtran)

PDF mode (compiled thesis):
  [ERROR] REFS-NOT-NUMBERED  reference list entries are not numbered "[n]"
  [WARN]  ENTRY-STYLE        entry deviates from the IEEE pattern
                             "[n] A. Author, ..., \"Title,\" Venue, ..."
                             (initials-before-surname, quoted title)
  [INFO]  CITE-STYLE         in-text citations look author-year "(Author,
                             2020)" rather than numeric "[n]"

Checks are heuristic — IEEE formatting has many legitimate variants
(online sources, standards, theses); WARN findings are meant for a quick
eye pass, not as hard failures.

Usage:
  python3 citation_style_lint.py thesis.pdf
  python3 citation_style_lint.py main.tex
Exit status: 0 clean, 1 findings (WARN or worse), 2 usage error.
"""

import argparse
import re
from typing import List, Tuple

from lintutil import Report, load_lines, tex_files

NUMBERED_ENTRY_RE = re.compile(r"^\[(\d+)\]\s+(.*)")
# "A. B. Author" / "A.-B. C. Author" — IEEE initials-first author form
INITIALS_FIRST_RE = re.compile(
    r"^[A-Z]\.(?:\s?-?[A-Z]\.)*\s+(?:van|von|de|del|da|Le)?\s*"
    r"[A-Z][a-zA-Z'’\-]+")
QUOTED_TITLE_RE = re.compile(r"[\"“][^\"”]{6,}[,.]?[\"”]")
AUTHOR_YEAR_CITE_RE = re.compile(r"\([A-Z][a-zA-Z]+(?:\s+(?:and|&)\s+[A-Z][a-zA-Z]+|\s+et\s+al\.?)?,?\s+(19|20)\d{2}[a-z]?\)")


def lint_tex(paths: List[str], rep: Report) -> None:
    """Check LaTeX sources for a non-IEEE (or missing) bibliography style
    and for natbib \\citet/\\citep textual citations."""
    files = tex_files(paths)
    style_found = False
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"\\bibliographystyle\{([^}]+)\}", text):
            style_found = True
            style = m.group(1)
            if not re.search(r"ieee", style, re.I):
                rep.add("ERROR", "NO-IEEE-STYLE", str(f),
                        f"\\bibliographystyle{{{style}}} — IEEE guidelines "
                        f"expect IEEEtran (or ieeetr).")
        for m in re.finditer(r"\\usepackage\[([^\]]*)\]\{biblatex\}", text):
            style_found = True
            opts = m.group(1)
            if not re.search(r"style\s*=\s*ieee", opts):
                rep.add("ERROR", "NO-IEEE-STYLE", str(f),
                        f"biblatex loaded with [{opts}] — expected "
                        f"style=ieee.")
        n_textual = len(re.findall(r"\\cite[tp]\b", text))
        if n_textual:
            rep.add("WARN", "NATBIB-TEXTUAL", str(f),
                    f"{n_textual} \\citet/\\citep textual citation(s) — "
                    f"IEEE style is numeric \\cite{{...}} -> [n].")
    if not style_found:
        rep.add("WARN", "NO-BIB-STYLE", "-",
                "no \\bibliographystyle or biblatex style found in the "
                "given sources.")


def find_reference_entries(lines) -> Tuple[List[Tuple[str, str]], bool]:
    """Locate the References section and join wrapped lines into entries."""
    start = None
    for i, (where, t) in enumerate(lines):
        if re.match(r"^\s*(References|Bibliography)\s*$", t.strip(), re.I):
            start = i + 1
    if start is None:
        return [], False
    entries: List[Tuple[str, str]] = []
    buf, loc = [], ""
    for where, t in lines[start:]:
        t = t.strip()
        if not t:
            continue
        if NUMBERED_ENTRY_RE.match(t):
            if buf:
                entries.append((loc, " ".join(buf)))
            buf, loc = [t], where
        elif buf:
            buf.append(t)
    if buf:
        entries.append((loc, " ".join(buf)))
    return entries, True


def lint_pdf(path: str, rep: Report) -> None:
    """Check a compiled thesis PDF: that the reference list is numbered,
    that each entry roughly matches the IEEE 'A. B. Surname, "Title," ...'
    pattern, and that in-text citations are numeric rather than author-year.
    The per-entry checks skip web/online sources and books/theses/standards,
    whose IEEE forms legitimately differ (no quoted title, no initials)."""
    lines, _ = load_lines([path])
    entries, found_section = find_reference_entries(lines)
    if not found_section:
        rep.add("WARN", "NO-REFS-SECTION", "-",
                "could not locate a References/Bibliography section.")
        return
    if not entries:
        rep.add("ERROR", "REFS-NOT-NUMBERED", "-",
                "reference list entries are not numbered '[n]' — IEEE "
                "references are cited and listed by number.")
        return
    for where, entry in entries:
        m = NUMBERED_ENTRY_RE.match(entry)
        body = m.group(2) if m else entry
        problems = []
        starts_ok = (INITIALS_FIRST_RE.match(body)
                     or re.match(r"^[A-Z][a-zA-Z\-]+\s+[A-Z]\.", body))
        is_web = bool(re.match(r"^(https?://|www\.)", body)) or \
            re.search(r"\b(dataset|documentation|available|online|accessed)\b",
                      body, re.I)
        # Books/theses/standards carry italic (unquoted) titles in IEEE.
        is_book = re.search(r"\b(Press|Springer|Wiley|Elsevier|McGraw|"
                            r"Prentice|University|Ph\.?D\.?|M\.?Sc\.?|"
                            r"dissertation|thesis|ed\.|Std\.)\b", body)
        if not starts_ok and not is_web:
            problems.append("authors not in IEEE 'A. B. Surname' form")
        if not QUOTED_TITLE_RE.search(body) and not is_web and not is_book:
            problems.append('title not in quotation marks ("Title,")')
        if problems:
            rep.add("WARN", "ENTRY-STYLE", where,
                    f"[{m.group(1) if m else '?'}] {'; '.join(problems)}: "
                    f"\"{body[:90]}…\"")
    # in-text citation style (scan text before the references section)
    n_authoryear = 0
    for where, t in lines:
        if re.match(r"^\s*(References|Bibliography)\s*$", t.strip(), re.I):
            break
        n_authoryear += len(AUTHOR_YEAR_CITE_RE.findall(t))
    if n_authoryear > 3:
        rep.add("INFO", "CITE-STYLE", "-",
                f"{n_authoryear} author-year style citations '(Author, "
                f"2020)' found in the text — IEEE in-text citations are "
                f"numeric [n].")


def main(argv: List[str] = None) -> int:
    """Dispatch to PDF or LaTeX checking based on the input, unless a
    non-IEEE --venue is given (in which case all checks are skipped, since
    only the IEEE style is encoded here). A single .pdf argument runs the
    compiled-thesis checks; anything else is treated as LaTeX sources."""
    ap = argparse.ArgumentParser(
        description="IEEE reference-format linter.")
    ap.add_argument("inputs", nargs="+", help="thesis.pdf or .tex files/dirs")
    ap.add_argument("--profile", choices=["thesis", "paper"], default="thesis",
                    help="Manuscript type. 'thesis' pins the venue to IEEE "
                         "(the ml-theses.org rule) regardless of --venue; "
                         "'paper' honours --venue.")
    ap.add_argument("--venue", default=None,
                    help="Citation venue style (default: ieee; used only with "
                         "--profile paper). Non-ieee venues (acm|neurips|...) "
                         "skip the IEEE-specific checks, which would otherwise "
                         "mis-flag them.")
    args = ap.parse_args(argv)

    # A thesis follows the ml-theses.org rubric (IEEE), so its venue is fixed
    # even if --venue is passed; a paper's venue is configurable.
    if args.profile == "thesis":
        venue = "ieee"
    else:
        venue = (args.venue or "ieee").lower()
    rep = Report(f"Citation style lint report ({venue.upper()})",
                 " ".join(args.inputs),
                 about="Checks that the reference list and in-text citations "
                       "follow the IEEE style used in the thesis guide.")
    if venue != "ieee":
        rep.add("INFO", "VENUE-SKIP", "-",
                f"venue={venue}: IEEE-specific citation checks skipped "
                f"(this linter only encodes the IEEE style).")
        print(rep.render())
        return rep.exit_code()
    if len(args.inputs) == 1 and args.inputs[0].lower().endswith(".pdf"):
        lint_pdf(args.inputs[0], rep)
    else:
        lint_tex(args.inputs, rep)

    print(rep.render())
    return rep.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
