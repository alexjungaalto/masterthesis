#!/usr/bin/env python3
"""LLM linter: research-paper manuscript-content checklist.

The paper-profile analogue of thesis_checklist_llm.py. One LLM call judges a
research-paper draft (IEEE/ACM/NeurIPS-style conference or journal manuscript)
against the content criteria a reviewer applies that cannot be checked
mechanically:

  contribution-stated   the introduction states explicit, enumerated
                        contributions
  problem-formulation   the problem is precisely formulated (data points,
                        features, labels, or the formal object of study)
  novelty-positioned    related work delineates what is new relative to
                        prior art (not just a literature list)
  claims-supported      each claim in the abstract/introduction is traceable
                        to a result in the paper
  baselines             appropriate baselines or benchmarks are included and
                        discussed (PASS if the paper proposes no method to
                        compare, e.g. a measurement/empirical study)
  results-answer-claims numerical results are presented and discussed enough
                        to substantiate the stated contributions
  reproducibility       code/data availability, hyperparameters, and compute
                        are stated, or an explicit reason they are not
  limitations           a limitations / threats-to-validity discussion exists
  ethics-impact         a broader-impact / ethics statement exists
                        (venue-conditional: checked only for --venue neurips|
                        acl; PASS-by-default for ieee/acm)

Verdicts: PASS / FAIL / UNCLEAR, each with quoted evidence and, for FAIL,
a concrete suggestion. Exit status 1 if any item FAILs.

Gateway: the Aalto AI API by default (see aalto_llm.py; $AALTO_API_KEY,
Aalto network/VPN only); --base-url switches to the Aalto LLM Gateway or
any OpenAI-style endpoint.

Usage:
  python3 paper_checklist_llm.py paper.pdf
  python3 paper_checklist_llm.py paper.pdf --venue neurips
Exit status: 0 all pass/unclear-free, 1 findings, 2 usage error.
"""

import argparse
import json
import sys
from typing import List

from aalto_llm import (API_KEY_HELP, BASE_URL, BASE_URL_HELP, default_model,
                       extract_json, make_client)
from lintutil import load_lines

# Venues that expect a dedicated broader-impact / ethics statement.
ETHICS_VENUES = {"neurips", "acl", "emnlp", "iclr"}

CHECK_ITEMS = [
    ("contribution-stated",
     "The introduction states the paper's contributions explicitly, ideally "
     "as an enumerated list, rather than leaving them implicit."),
    ("problem-formulation",
     "The problem is precisely formulated: the paper states what the data "
     "points / inputs are and how features and labels (or the formal object "
     "of study) are defined."),
    ("novelty-positioned",
     "Related work delineates what is NEW in this paper relative to prior "
     "art (an explicit gap or delta), not merely a list of references."),
    ("claims-supported",
     "Every claim made in the abstract and introduction is traceable to a "
     "specific result, table, or section in the paper."),
    ("baselines",
     "Appropriate baselines or benchmarks are included and discussed. PASS "
     "if the paper legitimately has nothing to compare against (e.g. a "
     "measurement or empirical-characterisation study) and says so."),
    ("results-answer-claims",
     "Numerical results are presented and discussed thoroughly enough to "
     "substantiate the paper's stated contributions."),
    ("reproducibility",
     "The paper states code/data availability, key hyperparameters, and the "
     "compute used, OR gives an explicit reason these are omitted."),
    ("limitations",
     "The paper includes a limitations or threats-to-validity discussion."),
    ("ethics-impact",
     "The paper includes a broader-impact or ethics statement. This is "
     "venue-conditional; when not required by the venue, PASS."),
]

SYSTEM_PROMPT = (
    "You are an experienced program-committee reviewer for a machine-learning "
    "conference (IEEE/ACM-style), checking a paper draft against a "
    "content checklist. You are given the extracted text of the paper (page "
    "markers '[[page N]]' included) and a list of checklist items with ids.\n\n"
    "This is a CONFERENCE/JOURNAL PAPER, not a thesis: it has sections (no "
    "chapters), frames CONTRIBUTIONS rather than a thesis-style research-"
    "question chapter, and is bound by a page limit — judge it by the "
    "standard a reviewer applies, not a thesis rubric. A terse but complete "
    "treatment PASSes; do not demand thesis-level exposition.\n\n"
    "For EACH item, decide:\n"
    "  verdict: 'PASS', 'FAIL', or 'UNCLEAR' (text too garbled/truncated "
    "to judge)\n"
    "  evidence: a short quote (<=40 words) plus the page number(s) that "
    "best support your verdict; for FAIL, quote what IS there or state "
    "what is missing\n"
    "  suggestion: for FAIL only, one concrete sentence on how to fix it\n\n"
    "Be strict but fair: a passing mention that genuinely satisfies the item "
    "counts. Respond with STRICT JSON:\n"
    '{"results": [{"id": "...", "verdict": "PASS|FAIL|UNCLEAR", '
    '"evidence": "...", "suggestion": "..."}]}'
)


def main(argv: List[str] = None) -> int:
    ap = argparse.ArgumentParser(
        description="LLM checklist linter for a research-paper PDF "
                    "(reviewer content items).")
    ap.add_argument("pdf", help="Path to the paper PDF.")
    ap.add_argument("--venue", default="ieee",
                    help="Target venue (ieee|acm|neurips|acl|...). Governs "
                         "whether the ethics-impact item is required "
                         "(default ieee: not required).")
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

    ethics_required = args.venue.lower() in ETHICS_VENUES
    items = [(i, r) for i, r in CHECK_ITEMS
             if i != "ethics-impact" or ethics_required]

    model = args.model or default_model(args.base_url)
    client = make_client(args.base_url, args.api_key)
    print(f"[info] gateway={args.base_url}\n[info] model={model}  "
          f"venue={args.venue}  chars={len(text)}", file=sys.stderr)

    items_json = json.dumps(
        [{"id": i, "requirement": r} for i, r in items], indent=1)
    user = (f"venue: {args.venue}\n\nchecklist items:\n{items_json}\n\n"
            f"paper text{' (TRUNCATED)' if truncated else ''}:\n"
            f'"""\n{text}\n"""')
    raw, usage = client.complete(model=model, system=SYSTEM_PROMPT,
                                 user=user, timeout=600, max_tokens=12000)
    parsed = extract_json(raw) or {}
    results = {r.get("id"): r for r in parsed.get("results", [])
               if isinstance(r, dict)}

    md = args.format == "markdown"
    out_lines = []
    if md:
        out_lines += [f"# Paper checklist report — {args.pdf}", "",
                      "| item | verdict | evidence / suggestion |",
                      "|---|---|---|"]
    else:
        out_lines += [f"== Paper checklist report (LLM, {model}; "
                      f"venue={args.venue})",
                      f"File: {args.pdf}", ""]
    n_fail = n_unclear = 0
    for item_id, req in items:
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
                      f"{len(items) - n_fail - n_unclear} PASS.  "
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
