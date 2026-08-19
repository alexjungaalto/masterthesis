#!/usr/bin/env python3
"""Linter: terminology consistency against the Aalto Dictionary of ML.

Guidelines enforced (ml-theses.org):
  * "Use terms defined in the Aalto Dictionary of ML."
  * "Pick one term per concept and do not silently switch between synonyms
     (e.g., 'data point' vs 'sample' vs 'instance')."

Each SYNONYM CLUSTER below lists interchangeable variants for one concept;
the FIRST variant is the term used by the Aalto Dictionary of ML. The linter
counts occurrences of every variant and flags clusters where two or more
variants are actually mixed in the document:

  [WARN] TERM-MIX        two or more synonyms of one concept each appear
                         >= --min-count times
  [INFO] NON-DICTIONARY  only a non-dictionary variant is used (consistent,
                         but not the dictionary term)

Counting is whole-word and case-insensitive, with naive plural folding.
Ambiguous words ("sample size", "target distribution") produce some false
positives — the report shows counts and first locations so mixes can be
verified quickly.

Input: thesis PDF or LaTeX sources.
Usage:
  python3 terminology_lint.py thesis.pdf
  python3 terminology_lint.py main.tex chapters/ --min-count 3
Exit status: 0 clean, 1 findings (WARN or worse), 2 usage error.
"""

import argparse
import re
from typing import Dict, List, Tuple

from lintutil import Report, is_toc_line, load_lines

# First variant per cluster = Aalto Dictionary of ML term.
SYNONYM_CLUSTERS: List[Tuple[str, List[str]]] = [
    ("data point",   ["data point", "sample", "instance", "observation"]),
    ("dataset",      ["dataset", "data set"]),
    ("feature",      ["feature", "attribute", "covariate", "input variable",
                      "explanatory variable", "independent variable"]),
    ("label",        ["label", "target", "response", "output variable",
                      "dependent variable", "ground truth"]),
    ("loss function", ["loss function", "cost function", "error function"]),
    ("hypothesis",   ["hypothesis", "predictor function", "prediction rule"]),
    ("model parameter", ["model parameter", "model weight"]),
    ("training set", ["training set", "training data", "train set",
                      "training dataset"]),
    ("validation set", ["validation set", "validation data", "dev set",
                        "development set", "holdout set", "hold-out set"]),
    ("test set",     ["test set", "test data", "testing set"]),
    ("learning rate", ["learning rate", "step size", "step-size"]),
    ("hyperparameter", ["hyperparameter", "hyper-parameter",
                        "tuning parameter"]),
    ("empirical risk", ["empirical risk", "training loss", "empirical error"]),
    ("artificial neural network", ["neural network", "neural net"]),
    ("k-means",      ["k-means", "kmeans", "k means"]),
    ("i.i.d.",       ["i.i.d.", "iid", "independent and identically distributed"]),
    ("machine learning", ["machine learning", "statistical learning"]),
]


def count_variants(text: str, variant: str) -> int:
    """Count whole-word occurrences of one synonym variant in `text`.

    Case-insensitive; a space in the variant matches any run of
    whitespace or a non-breaking `~`, and a trailing `s`/`es` is folded
    in so singular and plural forms count together.
    """
    # Word boundaries reject `[\w-]` on either side so 'sample' does not
    # match inside 'resampled'; `(?:e?s)?` is the naive plural fold.
    pat = re.escape(variant).replace(r"\ ", r"[\s~]+")
    return len(re.findall(rf"(?<![\w-]){pat}(?:e?s)?(?![\w-])", text, re.I))


def main(argv: List[str] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Terminology consistency vs the Aalto Dictionary of ML.")
    ap.add_argument("inputs", nargs="+", help="thesis.pdf or .tex files/dirs")
    ap.add_argument("--min-count", type=int, default=2,
                    help="A variant counts as 'in use' from this many "
                         "occurrences (default 2).")
    args = ap.parse_args(argv)

    lines, mode = load_lines(args.inputs)
    body: List[Tuple[str, str]] = []
    in_references = False
    for where, t in lines:
        if is_toc_line(t):
            continue
        if re.match(r"^\s*(References|Bibliography)\s*$", t, re.I):
            in_references = True
        if not in_references:
            body.append((where, t))
    full_text = "\n".join(t for _, t in body)

    def first_loc(variant: str) -> str:
        """Location tag ('p12' or 'file:line') of the variant's first
        occurrence in the body, or '-' if it never appears."""
        pat = re.escape(variant).replace(r"\ ", r"[\s~]+")
        rex = re.compile(rf"(?<![\w-]){pat}(?:e?s)?(?![\w-])", re.I)
        for where, t in body:
            if rex.search(t):
                return where
        return "-"

    rep = Report("Terminology lint report (Aalto Dictionary of ML)",
                 " ".join(args.inputs),
                 about="Flags synonym switching between equivalent terms; each "
                       "cluster lists the Aalto Dictionary of ML term to "
                       "standardise on first.")

    for preferred, variants in SYNONYM_CLUSTERS:
        counts: Dict[str, int] = {v: count_variants(full_text, v)
                                  for v in variants}
        used = {v: c for v, c in counts.items() if c >= args.min_count}
        if len(used) >= 2:
            detail = ", ".join(f"'{v}' x{c} (first {first_loc(v)})"
                               for v, c in sorted(used.items(),
                                                  key=lambda kv: -kv[1]))
            rep.add("WARN", "TERM-MIX", first_loc(preferred)
                    if counts.get(preferred) else "-",
                    f"concept '{preferred}': mixed synonyms — {detail}. "
                    f"Dictionary term: '{preferred}'.")
        elif len(used) == 1:
            (v, c), = used.items()
            if v != preferred:
                rep.add("INFO", "NON-DICTIONARY", first_loc(v),
                        f"uses '{v}' x{c} consistently; the Aalto "
                        f"Dictionary term is '{preferred}'.")

    print(rep.render())
    return rep.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
