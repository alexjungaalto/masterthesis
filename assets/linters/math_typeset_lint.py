#!/usr/bin/env python3
"""Linter: mathematical typesetting conventions (ml-theses.org).

Guidelines enforced (LaTeX sources only):
  * "Use inline math ($...$) for short expressions within a sentence. Use
     display math (\\[...\\] or the equation environment) for standalone
     equations that are central or referenced."
       [WARN] LONG-INLINE      inline $...$ longer than --max-inline chars
                               (candidate for display math)
       [INFO] EQNARRAY         obsolete eqnarray environment (use align)
  * "Reference all numbered equations using \\eqref{}."
       [WARN] REF-NOT-EQREF    equation label referenced with \\ref instead
                               of \\eqref
  * "Punctuate displayed math as part of the surrounding sentence."
       [WARN] EQ-NO-PUNCT      display equation whose body does not end in
                               punctuation (. , ; :) although the following
                               text starts a new sentence
       [INFO] EQ-PUNCT-CHECK   display equation with no trailing punctuation
                               and the text continues in lowercase (often
                               fine — e.g. "where ..." — listed for a quick
                               eye pass)

Numbered-but-unreferenced equations are covered by
unreferenced_entity_linter.py.

Usage:
  python3 math_typeset_lint.py main.tex chapters/
  python3 math_typeset_lint.py thesis.tex --max-inline 60
Exit status: 0 clean, 1 findings (WARN or worse), 2 usage error.
"""

import argparse
import re
import sys
from typing import List, Optional, Tuple

from lintutil import Report, tex_files, strip_tex_comments

MATH_ENVS = ("equation", "align", "gather", "multline", "eqnarray",
             "alignat", "flalign", "displaymath")
BEGIN_RE = re.compile(r"\\begin\{(" + "|".join(MATH_ENVS) + r")\*?\}")
INLINE_RE = re.compile(r"(?<!\\)\$([^$]+)(?<!\\)\$")
LABEL_RE = re.compile(r"\\label\{([^}]+)\}")
REF_RE = re.compile(r"\\(ref|eqref|autoref|cref|Cref)\*?\{([^}]+)\}")
PUNCT_END_RE = re.compile(r"[.,;:!?]\s*$")


def read_sources(paths: List[str]) -> List[Tuple[str, int, str]]:
    """[(file, lineno, line-with-comments-stripped)] in reading order."""
    out = []
    files = tex_files(paths)
    if not files:
        sys.exit("No .tex input found (this linter needs LaTeX sources).")
    for f in files:
        for i, ln in enumerate(
                f.read_text(encoding="utf-8", errors="replace").splitlines(),
                start=1):
            out.append((str(f), i, strip_tex_comments(ln)))
    return out


def next_text(lines, idx) -> str:
    """First non-blank text after line index idx (up to 3 lines ahead)."""
    for j in range(idx + 1, min(idx + 4, len(lines))):
        t = lines[j][2].strip()
        if t:
            return t
    return ""


def main(argv: List[str] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Math typesetting linter (LaTeX sources).")
    ap.add_argument("inputs", nargs="+", help=".tex files or directories")
    ap.add_argument("--max-inline", type=int, default=80,
                    help="Inline math longer than this many characters is "
                         "flagged (default 80).")
    args = ap.parse_args(argv)

    lines = read_sources(args.inputs)
    rep = Report("Math typesetting lint report", " ".join(args.inputs))

    # --- inline math length + eqnarray ------------------------------------
    for fname, lno, text in lines:
        for m in INLINE_RE.finditer(text):
            body = m.group(1).strip()
            if len(body) > args.max_inline:
                rep.add("WARN", "LONG-INLINE", f"{fname}:{lno}",
                        f"inline math of {len(body)} chars — consider "
                        f"display math: ${body[:60]}…$")
        if re.search(r"\\begin\{eqnarray\*?\}", text):
            rep.add("INFO", "EQNARRAY", f"{fname}:{lno}",
                    "obsolete eqnarray environment — use align/equation.")

    # --- equation labels referenced with \ref instead of \eqref -----------
    eq_labels = set()
    depth = 0
    for fname, lno, text in lines:
        for m in re.finditer(r"\\begin\{[a-z]+\*?\}|\\end\{[a-z]+\*?\}|\\\[|\\\]|\\label\{([^}]+)\}", text):
            tok = m.group(0)
            if tok.startswith("\\begin") and BEGIN_RE.match(tok):
                depth += 1
            elif tok.startswith("\\end") and re.match(
                    r"\\end\{(" + "|".join(MATH_ENVS) + r")\*?\}", tok):
                depth = max(0, depth - 1)
            elif tok == "\\[":
                depth += 1
            elif tok == "\\]":
                depth = max(0, depth - 1)
            elif m.group(1) and depth > 0:
                eq_labels.add(m.group(1))
    for fname, lno, text in lines:
        for m in REF_RE.finditer(text):
            cmd, targets = m.group(1), m.group(2)
            if cmd != "ref":
                continue
            for target in (t.strip() for t in targets.split(",")):
                if target in eq_labels:
                    rep.add("WARN", "REF-NOT-EQREF", f"{fname}:{lno}",
                            f"equation label '{target}' referenced with "
                            f"\\ref — use \\eqref.")

    # --- display equation punctuation --------------------------------------
    i = 0
    while i < len(lines):
        fname, lno, text = lines[i]
        m = BEGIN_RE.search(text)
        if m:
            closer = re.compile(r"\\end\{" + m.group(1) + r"\*?\}")
        else:
            m = re.search(r"\\\[", text)
            closer = re.compile(r"\\\]")
        if not m:
            i += 1
            continue
        body_parts, j = [], i
        first = text[m.end():]
        while j < len(lines):
            t = lines[j][2] if j > i else first
            mm = closer.search(t)
            if mm:
                body_parts.append(t[:mm.start()])
                break
            body_parts.append(t)
            j += 1
        body = " ".join(body_parts)
        body = LABEL_RE.sub("", body)
        body = re.sub(r"\\(nonumber|notag|qedhere)\b", "", body).strip()
        body = re.sub(r"\\\\(\[[^\]]*\])?\s*$", "", body).strip()  # trailing \\
        follow = next_text(lines, j)
        if body and not PUNCT_END_RE.search(body):
            starts_sentence = bool(re.match(r"[A-Z]", follow)) and not \
                re.match(r"(where|with|and|for|such|which|whose|so|then|"
                         r"i\.e|e\.g)\b", follow, re.I)
            if starts_sentence:
                rep.add("WARN", "EQ-NO-PUNCT", f"{fname}:{lno}",
                        f"display equation ends without punctuation and the "
                        f"following text starts a new sentence "
                        f"('{follow[:40]}…').")
            else:
                rep.add("INFO", "EQ-PUNCT-CHECK", f"{fname}:{lno}",
                        f"display equation without trailing punctuation "
                        f"(continues '{follow[:40]}'). Verify the sentence "
                        f"reads through the equation.")
        i = j + 1 if j > i else i + 1

    print(rep.render())
    return rep.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
