#!/usr/bin/env python3
"""LLM linter: ml-theses.org manuscript-content checklist.

One LLM call judges the whole thesis against the content items of the
ml-theses.org guide that cannot be checked mechanically:

  problem-formulation   data points, their features, and labels are clearly
                        defined
  data-sources-eval     data sources and evaluation criteria are identified
  loss-functions        the training loss AND, separately, the validation/
                        test loss are explicitly stated
  results-discussed     numerical results are presented and discussed
                        thoroughly to answer the research questions
  baselines             appropriate baselines or benchmarks are included
                        and discussed
  pseudocode            new methods are presented as pseudocode (PASS also
                        if the thesis introduces no new method)
  model-diagnosis       model diagnosis via numerical experiments
                        (benchmarks, sensitivity analysis) and, where
                        appropriate, mathematical analysis
  section-intros        each chapter/section begins with an introductory
                        paragraph explaining its content and its connection
                        to the rest of the thesis
  captions-informative  figure/table captions are informative (state what
                        to see, not just "Results")

Verdicts: PASS / FAIL / UNCLEAR, each with quoted evidence and, for FAIL,
a concrete suggestion. Exit status 1 if any item FAILs.

Gateway: the Aalto AI API by default (see aalto_llm.py; $AALTO_API_KEY,
Aalto network/VPN only); --base-url switches to the Aalto LLM Gateway or
any OpenAI-style endpoint.

Usage:
  python3 thesis_checklist_llm.py thesis.pdf
  python3 thesis_checklist_llm.py thesis.pdf --out report.md --format markdown
Exit status: 0 all pass/unclear-free, 1 findings, 2 usage error.
"""

import argparse
import json
import sys
from typing import List

from aalto_llm import (API_KEY_HELP, BASE_URL, BASE_URL_HELP, default_model,
                       extract_json, make_client)
from lintutil import load_lines

CHECK_ITEMS = [
    ("problem-formulation",
     "The ML problem is precisely formulated: the thesis states clearly "
     "what the data points are and how their features and labels are "
     "defined."),
    ("data-sources-eval",
     "Data sources and evaluation criteria (e.g. test accuracy, "
     "computational efficiency) are explicitly identified."),
    ("loss-functions",
     "The loss function used for training is explicitly stated AND, "
     "separately, the loss/metric used for validation or testing."),
    ("results-discussed",
     "Numerical results are presented and discussed thoroughly enough to "
     "answer the thesis's research questions."),
    ("baselines",
     "Appropriate baselines or benchmarks are included and discussed."),
    ("pseudocode",
     "Any NEW method proposed by the thesis is presented as pseudocode. "
     "PASS if the thesis proposes no new method."),
    ("model-diagnosis",
     "The trained models are diagnosed using numerical experiments "
     "(benchmarks, sensitivity/error analysis) and, where appropriate, "
     "mathematical analysis."),
    ("section-intros",
     "Chapters and major sections begin with an introductory paragraph "
     "explaining their content and their connection to the rest of the "
     "thesis (spot-check several)."),
    ("captions-informative",
     "Figure and table captions are informative: they state what the "
     "reader should see and define the shown quantities, rather than a "
     "bare label like 'Results'."),
]

SYSTEM_PROMPT = (
    "You are an experienced supervisor of master's theses in machine "
    "learning at Aalto University, checking a thesis against the "
    "ml-theses.org manuscript checklist. You are given the extracted text "
    "of the thesis (page markers '[[page N]]' included) and a list of "
    "checklist items with ids.\n\n"
    "For EACH item, decide:\n"
    "  verdict: 'PASS', 'FAIL', or 'UNCLEAR' (text too garbled/truncated "
    "to judge)\n"
    "  evidence: a short quote (<=40 words) plus the page number(s) that "
    "best support your verdict; for FAIL, quote what IS there or state "
    "what is missing\n"
    "  suggestion: for FAIL only, one concrete sentence on how to fix it\n\n"
    "Be strict but fair: a passing mention buried in one sentence still "
    "counts if it genuinely satisfies the item. Respond with STRICT JSON:\n"
    '{"results": [{"id": "...", "verdict": "PASS|FAIL|UNCLEAR", '
    '"evidence": "...", "suggestion": "..."}]}'
)


def main(argv: List[str] = None) -> int:
    ap = argparse.ArgumentParser(
        description="LLM checklist linter for a thesis PDF "
                    "(ml-theses.org manuscript items).")
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

    items_json = json.dumps(
        [{"id": i, "requirement": r} for i, r in CHECK_ITEMS], indent=1)
    user = (f"checklist items:\n{items_json}\n\n"
            f"thesis text{' (TRUNCATED)' if truncated else ''}:\n"
            f'"""\n{text}\n"""')
    raw, usage = client.complete(model=model, system=SYSTEM_PROMPT,
                                 user=user, timeout=600, max_tokens=12000)
    parsed = extract_json(raw) or {}
    results = {r.get("id"): r for r in parsed.get("results", [])
               if isinstance(r, dict)}

    md = args.format == "markdown"
    out_lines = []
    if md:
        out_lines += [f"# Thesis checklist report — {args.pdf}", "",
                      "| item | verdict | evidence / suggestion |",
                      "|---|---|---|"]
    else:
        out_lines += [f"== Thesis checklist report (LLM, {model})",
                      f"File: {args.pdf}", ""]
    n_fail = n_unclear = 0
    for item_id, req in CHECK_ITEMS:
        r = results.get(item_id, {})
        verdict = str(r.get("verdict", "UNCLEAR")).upper()
        evidence = str(r.get("evidence", "no answer from model")).strip()
        suggestion = str(r.get("suggestion", "")).strip()
        if verdict == "FAIL":
            n_fail += 1
        elif verdict != "PASS":
            n_unclear += 1
        if md:
            cell = evidence + (f" **Fix:** {suggestion}" if suggestion else "")
            out_lines.append(f"| {item_id} | {verdict} | {cell} |")
        else:
            out_lines.append(f"[{verdict}] {item_id}")
            out_lines.append(f"        {evidence}")
            if suggestion:
                out_lines.append(f"        fix: {suggestion}")
    out_lines += ["", f"{n_fail} FAIL, {n_unclear} UNCLEAR, "
                      f"{len(CHECK_ITEMS) - n_fail - n_unclear} PASS.  "
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
