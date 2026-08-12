#!/usr/bin/env python3
"""Linter: recurring prose defects from the ml-theses.org self-editing pass.

Guidelines enforced (heuristically):
  * Vague quantifiers — "significantly", "very", "a lot" without a number.
    -> [WARN] VAGUE-QUANTIFIER when a sentence contains such a word but no
       digit, percentage, or citation.
  * Jargon / undefined evaluative claims — "smoothest convergence", "the
    model struggles", "performs well": colloquial ML-speak that misuses
    defined terms (in the Aalto Dictionary "smooth" means differentiable)
    or claims a property with no defined metric. A nearby number does not
    excuse these.
    -> [WARN] JARGON per occurrence.
  * Dangling references — "this shows", "it follows" where "this"/"it" has
    no clear antecedent.
    -> [INFO] DANGLING-REFERENCE for sentences STARTING with a bare
       "This/These/It/Those" + verb (no noun in between). INFO because many
       such sentences are fine; scan the list quickly by eye.
  * Excessive forward referencing — forward-looking cue phrases such as
    "as we will see in Chapter 5" scattered throughout.
    -> [WARN] FORWARD-CUE per occurrence; [WARN] FORWARD-CUE-HABIT summary
       when the count exceeds --max-forward-cues (default 3).

For structural forward references to figures/equations use
crossref_forward_lint.py; for conceptual ones use forward_ref_lint(_llm).py.
The LLM cousin of this linter is prose_lint_llm.py.

Input: thesis PDF or LaTeX sources.
Usage:
  python3 prose_lint.py thesis.pdf
  python3 prose_lint.py main.tex chapters/
Exit status: 0 clean, 1 findings (WARN or worse), 2 usage error.
"""

import argparse
import re
from typing import List

from lintutil import (Report, is_toc_line, load_lines, paragraphs_from_lines,
                      sentences)

VAGUE_WORDS = [
    "significantly", "significant", "very", "a lot", "lots of", "huge",
    "hugely", "extremely", "considerably", "considerable", "substantially",
    "substantial", "drastically", "dramatically", "vastly", "greatly",
    "enormous", "massive", "immense", "much better", "much worse",
    "much faster", "much slower", "quite", "fairly", "really", "clearly",
    "obviously", "many", "few",
]
# "many"/"few"/"significant" are noisy; only the adverb forms and the worst
# offenders are on by default. The full list is enabled with --strict.
DEFAULT_VAGUE = [
    "significantly", "very", "a lot", "lots of", "hugely", "extremely",
    "drastically", "dramatically", "vastly", "enormous", "massive",
    "much better", "much worse", "much faster", "much slower",
]

HAS_NUMBER_RE = re.compile(r"\d|%|\\%")
CITATION_RE = re.compile(r"\[\d+(?:,\s*\d+)*\]|\\cite[pt]?\*?\{")
STAT_SIG_RE = re.compile(r"statistically\s+significant|p\s*[<=>]", re.I)

DANGLING_RE = re.compile(
    r"^(This|These|It|Those)\s+"
    r"(is|are|was|were|shows?|showed|means?|meant|implies|implied|"
    r"follows?|followed|suggests?|suggested|demonstrates?|demonstrated|"
    r"indicates?|indicated|leads?|led|results?|resulted|allows?|allowed|"
    r"makes?|made|can|could|will|would|may|might|does|did|has|have|had)\b")

# Colloquial/evaluative ML-speak: either misuses a defined technical term
# in an informal sense ("smooth" means differentiable in the Aalto
# Dictionary) or claims a property with no defined metric. A nearby number
# does not cure these — flag regardless.
JARGON_RE = re.compile(
    r"\b(smooth(?:est|er)?\s+convergence|converge[sd]?\s+(?:very\s+)?"
    r"smoothly|(?:model|training|network|method)\s+struggl\w+|"
    r"degrades?\s+gracefully|graceful\s+degradation|"
    r"(?:works?|performs?)\s+(?:very\s+|quite\s+|really\s+)?well|"
    r"(?:good|great|strong|excellent|impressive|decent)\s+"
    r"(?:performance|results|accuracy)|"
    r"(?:training|convergence)\s+is\s+(?:very\s+)?(?:stable|smooth)|"
    r"(?:fast(?:est)?|smooth(?:est)?|(?:most\s+)?stable)\s+"
    r"(?:and\s+(?:fast(?:est)?|smooth(?:est)?|(?:most\s+)?stable)\s+)?"
    r"convergence)\b", re.I)

FORWARD_CUE_RE = re.compile(
    r"\b(as\s+(?:we\s+(?:will|shall)\s+see|will\s+be\s+(?:seen|shown|"
    r"discussed|explained|described))|"
    r"we\s+(?:will|shall)\s+(?:see|show|discuss|explain|describe|return\s+to|"
    r"come\s+back\s+to)|"
    r"(?:will|shall)\s+be\s+(?:discussed|described|explained|introduced|"
    r"presented|defined)\s+(?:in|later)|"
    r"more\s+on\s+this\s+(?:later|in)|"
    r"later\s+(?:in\s+this\s+(?:thesis|chapter|section)|chapters?|sections?))\b",
    re.I)


def main(argv: List[str] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Prose linter: vague quantifiers, dangling references, "
                    "forward-looking cue phrases.")
    ap.add_argument("inputs", nargs="+", help="thesis.pdf or .tex files/dirs")
    ap.add_argument("--strict", action="store_true",
                    help="Enable the full vague-word list (noisier: adds "
                         "'many', 'few', 'clearly', 'quite', ...).")
    ap.add_argument("--max-forward-cues", type=int, default=3,
                    help="Threshold for the FORWARD-CUE-HABIT summary "
                         "finding (default 3).")
    ap.add_argument("--no-dangling", action="store_true",
                    help="Skip the DANGLING-REFERENCE check.")
    args = ap.parse_args(argv)

    lines, mode = load_lines(args.inputs)
    lines = [(w, t) for (w, t) in lines if not is_toc_line(t)]
    rep = Report("Prose lint report (self-editing pass)",
                 " ".join(args.inputs),
                 about="Flags self-editing prose issues: vague quantifiers "
                       "without a number, colloquial/undefined claims, "
                       "forward-looking cue phrases, and dangling references.")

    vague = args.strict and VAGUE_WORDS or DEFAULT_VAGUE
    vague_re = re.compile(
        r"\b(" + "|".join(re.escape(w) for w in vague) + r")\b", re.I)

    n_cues = 0
    in_references = False
    for where, para in paragraphs_from_lines(lines):
        # Reference-list start: the bare heading, or the heading run into
        # the first numbered entry — but NOT a table-of-contents entry
        # like "References 96".
        if re.match(r"^(References|Bibliography)\s*(\[1\]|$)",
                    para.strip(), re.I):
            in_references = True
        if in_references:
            continue
        for sent in sentences(para):
            m = vague_re.search(sent)
            if m and not (HAS_NUMBER_RE.search(sent)
                          or CITATION_RE.search(sent)
                          or STAT_SIG_RE.search(sent)):
                rep.add("WARN", "VAGUE-QUANTIFIER", where,
                        f"'{m.group(1)}' without a number: "
                        f"\"{sent[:110]}{'…' if len(sent) > 110 else ''}\"")
            m = JARGON_RE.search(sent)
            if m:
                rep.add("WARN", "JARGON", where,
                        f"colloquial/undefined claim '{m.group(1)}' — "
                        f"define and measure the property or drop it: "
                        f"\"{sent[:95]}{'…' if len(sent) > 95 else ''}\"")
            m = FORWARD_CUE_RE.search(sent)
            if m:
                n_cues += 1
                rep.add("WARN", "FORWARD-CUE", where,
                        f"forward-looking phrase '{m.group(0)}': "
                        f"\"{sent[:100]}{'…' if len(sent) > 100 else ''}\"")
            if not args.no_dangling:
                m = DANGLING_RE.match(sent)
                if m:
                    rep.add("INFO", "DANGLING-REFERENCE", where,
                            f"sentence opens with bare '{m.group(1)} "
                            f"{m.group(2)}' — check the antecedent: "
                            f"\"{sent[:90]}{'…' if len(sent) > 90 else ''}\"")

    if n_cues > args.max_forward_cues:
        rep.add("WARN", "FORWARD-CUE-HABIT", "-",
                f"{n_cues} forward-looking cue phrases in total — 'a few "
                f"pointers are fine, but a habit of them signals "
                f"disorganised structure' (threshold "
                f"{args.max_forward_cues}).")

    print(rep.render())
    return rep.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
