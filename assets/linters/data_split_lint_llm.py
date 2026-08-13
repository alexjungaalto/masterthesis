#!/usr/bin/env python3
"""LLM linter: per-method train/validation/test split and diagnosis.

Where thesis_checklist_llm.py judges the thesis *globally* (a single
loss-functions / model-diagnosis verdict for the whole manuscript), this
linter works *per studied ML method*. It first has the model enumerate the
ML methods the thesis actually trains and studies (methods only named in
related work are excluded), then, for EACH method, checks four things the
ml-theses.org guide expects a good empirical ML thesis to make explicit:

  train-set          how the TRAINING set is constructed (source, size, and
                     how data points are selected into it) -- not merely
                     that "a training set" exists.
  validation-set     how the VALIDATION set is separated from training and
                     used for model selection / hyperparameter tuning
                     (split ratio, cross-validation folds, stratification).
                     PASS also if the method legitimately needs none AND the
                     thesis says so.
  test-set           how the TEST set is constructed, kept disjoint from
                     train/validation (held out, no leakage), and used only
                     for final evaluation.
  diagnosis-on-split the method is diagnosed USING that split -- training vs.
                     validation/test performance compared to read
                     over/underfitting, learning curves, error analysis on
                     the held-out set -- not a single aggregate number.

Verdicts: PASS / FAIL / UNCLEAR, each with quoted evidence and, for FAIL, a
concrete suggestion. Exit status 1 if any check FAILs.

Gateway: the Aalto AI API by default (see aalto_llm.py; $AALTO_API_KEY,
Aalto network/VPN only); --base-url switches to the Aalto LLM Gateway or
any OpenAI-style endpoint.

Usage:
  python3 data_split_lint_llm.py thesis.pdf
  python3 data_split_lint_llm.py thesis.pdf --out report.md --format markdown
Exit status: 0 no FAILs, 1 findings, 2 usage error.
"""

import argparse
import json
import sys
from typing import List

from aalto_llm import (API_KEY_HELP, BASE_URL, BASE_URL_HELP, default_model,
                       extract_json, make_client)
from lintutil import load_lines

# (check id, requirement shown to the model). The id doubles as the finding
# code (upper-cased) in the report.
CHECKS = [
    ("train-set",
     "The construction of the TRAINING set for this method is described: "
     "its data source, its size, and how data points are selected/split "
     "into it -- not merely a passing mention that a training set exists."),
    ("validation-set",
     "The VALIDATION set construction is described: how it is separated "
     "from the training set (hold-out split ratio, k-fold cross-validation, "
     "stratification) and that it is used for model selection / "
     "hyperparameter tuning. PASS also if this method legitimately needs no "
     "separate validation set AND the thesis says so explicitly."),
    ("test-set",
     "The TEST set construction is described and it is kept DISJOINT from "
     "the training and validation sets (held out, no leakage / no reuse for "
     "tuning) and used only for the final performance estimate."),
    ("diagnosis-on-split",
     "The method is DIAGNOSED using this split: e.g. training vs. "
     "validation/test performance are compared to detect over- or "
     "under-fitting, learning curves are shown, or error analysis is done "
     "on the held-out data -- rather than reporting a single aggregate "
     "score with no reference to the split."),
]

SYSTEM_PROMPT = (
    "You are an experienced supervisor of master's theses in machine "
    "learning at Aalto University. You check whether a thesis follows good "
    "empirical ML practice regarding data splits, per ml-theses.org. You "
    "are given the extracted text of the thesis (page markers '[[page N]]' "
    "included).\n\n"
    "STEP 1. Identify the ML methods the thesis actually TRAINS and STUDIES "
    "in its own experiments (e.g. 'random forest', 'a 3-layer CNN', "
    "'logistic regression baseline'). EXCLUDE methods only mentioned in "
    "background/related work and never trained by the author. If the thesis "
    "is purely theoretical and trains no model, return an empty 'methods' "
    "list and say so in 'notes'.\n\n"
    "STEP 2. For EACH studied method, and for EACH check id below, decide:\n"
    "  verdict: 'PASS', 'FAIL', or 'UNCLEAR' (text too garbled/truncated "
    "to judge)\n"
    "  evidence: a short quote (<=40 words) plus page number(s) that best "
    "support the verdict; for FAIL, quote what IS there or state what is "
    "missing\n"
    "  suggestion: for FAIL only, one concrete sentence on how to fix it\n\n"
    "A shared split described once for all methods counts for each method "
    "that uses it -- do not FAIL a method for not repeating it, but the "
    "split must still be described somewhere. Be strict but fair: a genuine "
    "description buried in one sentence still counts. Respond with STRICT "
    "JSON:\n"
    '{"methods": [{"name": "...", "checks": [{"id": "train-set", '
    '"verdict": "PASS|FAIL|UNCLEAR", "evidence": "...", "suggestion": '
    '"..."}, ...]}], "notes": "..."}'
)


def main(argv: List[str] = None) -> int:
    ap = argparse.ArgumentParser(
        description="LLM linter: per-method train/validation/test split "
                    "construction and diagnosis (ml-theses.org).")
    ap.add_argument("pdf", help="Path to the thesis PDF.")
    ap.add_argument("--base-url", default=BASE_URL, help=BASE_URL_HELP)
    ap.add_argument("--api-key", default=None, help=API_KEY_HELP)
    ap.add_argument("--model", default=None,
                    help="Model id (default depends on the gateway).")
    ap.add_argument("--max-chars", type=int, default=400_000,
                    help="Truncate extracted text beyond this many "
                         "characters (default 400000).")
    ap.add_argument("--out", help="Write report to this file.")
    ap.add_argument("--format", choices=["text", "markdown"], default="text")
    ap.add_argument("--profile", choices=["thesis", "paper"], default="thesis",
                    help="'paper' excludes off-the-shelf/pretrained models the "
                         "authors do not themselves train from the check.")
    args = ap.parse_args(argv)

    lines, mode = load_lines([args.pdf])
    if mode != "pdf":
        print("ERROR: this linter takes a compiled PDF.", file=sys.stderr)
        return 2

    # Rebuild text with page markers.
    chunks, cur_page = [], None
    for where, t in lines:
        if where != cur_page:
            cur_page = where
            chunks.append(f"\n[[page {where[1:]}]]\n")
        chunks.append(t + "\n")
    text = "".join(chunks)
    truncated = len(text) > args.max_chars
    if truncated:
        text = text[: args.max_chars]
        print(f"[warn] text truncated to {args.max_chars} chars",
              file=sys.stderr)

    model = args.model or default_model(args.base_url)
    client = make_client(args.base_url, args.api_key)
    print(f"[info] gateway={args.base_url}\n[info] model={model}  "
          f"chars={len(text)}", file=sys.stderr)

    checks_json = json.dumps(
        [{"id": i, "requirement": r} for i, r in CHECKS], indent=1)
    paper_note = ""
    if args.profile == "paper":
        paper_note = (
            "NOTE: this is a conference/journal paper. Count ONLY methods the "
            "authors themselves train or fine-tune. Pretrained or off-the-"
            "shelf models used as-is (e.g. a stock detector for inference) are "
            "OUT OF SCOPE for train/validation/test checks — do not list them. "
            "If the paper trains no method (e.g. an infrastructure or "
            "measurement study), return an empty method list.\n\n")
    user = (f"{paper_note}"
            f"checks (apply each to every studied method):\n{checks_json}\n\n"
            f"paper text{' (TRUNCATED)' if truncated else ''}:\n"
            f'"""\n{text}\n"""')
    raw, usage = client.complete(model=model, system=SYSTEM_PROMPT,
                                 user=user, timeout=600, max_tokens=12000)
    parsed = extract_json(raw) or {}
    methods = [m for m in parsed.get("methods", []) if isinstance(m, dict)]
    notes = str(parsed.get("notes", "")).strip()

    md = args.format == "markdown"
    out_lines = []
    if md:
        out_lines += [f"# Data-split lint report — {args.pdf}", "",
                      f"_model: {model}_", ""]
    else:
        out_lines += [f"== Data-split lint report (LLM, {model})",
                      f"File: {args.pdf}", ""]

    n_fail = n_unclear = n_pass = 0
    if not methods:
        msg = notes or ("No trained ML method identified in the thesis "
                        "(purely theoretical, or extraction failed).")
        out_lines.append(("> " if md else "[INFO] ") + msg)
    else:
        for m in methods:
            name = str(m.get("name", "(unnamed method)")).strip()
            by_id = {c.get("id"): c for c in m.get("checks", [])
                     if isinstance(c, dict)}
            if md:
                out_lines += ["", f"## {name}", "",
                              "| check | verdict | evidence / suggestion |",
                              "|---|---|---|"]
            else:
                out_lines += ["", f"# method: {name}"]
            for cid, _req in CHECKS:
                c = by_id.get(cid, {})
                verdict = str(c.get("verdict", "UNCLEAR")).upper()
                evidence = str(c.get("evidence",
                                     "no answer from model")).strip()
                suggestion = str(c.get("suggestion", "")).strip()
                if verdict == "FAIL":
                    n_fail += 1
                elif verdict == "PASS":
                    n_pass += 1
                else:
                    n_unclear += 1
                if md:
                    cell = evidence + (f" **Fix:** {suggestion}"
                                       if suggestion else "")
                    out_lines.append(
                        f"| {cid} | {verdict} | {cell} |")
                else:
                    out_lines.append(f"  [{verdict}] {cid.upper()}")
                    out_lines.append(f"          {evidence}")
                    if suggestion:
                        out_lines.append(f"          fix: {suggestion}")

    out_lines += ["", f"{len(methods)} method(s); {n_fail} FAIL, "
                      f"{n_unclear} UNCLEAR, {n_pass} PASS.  "
                      f"(tokens: {usage.get('total_tokens', '?')})"]
    report = "\n".join(out_lines)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(report + "\n")
        print(f"Report written to {args.out}", file=sys.stderr)
    else:
        print(report)
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
