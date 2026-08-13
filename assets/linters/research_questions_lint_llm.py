#!/usr/bin/env python3
"""LLM linter: does the thesis answer the research questions it defines?

ml-theses.org requires that numerical results are "presented and discussed
thoroughly to answer your research questions". thesis_checklist_llm.py
gives one global verdict for that; this linter traces each research
question individually:

  1. Extract every research question the thesis explicitly states
     (RQ1/RQ2 lists, "this thesis investigates whether ...", hypotheses,
     numbered objectives), verbatim with its page.
  2. For each question, judge:
       verdict     ANSWERED / PARTIALLY-ANSWERED / UNANSWERED
       where       pages/sections in which the answer is developed
       answer      the thesis's answer in one or two sentences
       evidence    whether the presented results actually support that
                   answer (quote the key result)
       revisited   whether the conclusions chapter explicitly returns to
                   the question
       gap + fix   for anything less than ANSWERED

Findings:
  [WARN] NO-RQS               no explicitly stated research questions found
  [WARN] UNANSWERED / PARTIALLY-ANSWERED per research question
  [WARN] NOT-REVISITED        answered, but the conclusions never return
                              to the question
  [INFO] ANSWERED             per research question (the good case)

Gateway: the Aalto AI API by default (see aalto_llm.py; $AALTO_API_KEY,
Aalto network/VPN only); --base-url switches gateways.

Usage:
  python3 research_questions_lint_llm.py thesis.pdf
  python3 research_questions_lint_llm.py thesis.pdf --format markdown --out rq.md
Exit status: 0 all answered+revisited, 1 findings, 2 usage error.
"""

import argparse
import json
import sys
from typing import List

from aalto_llm import (API_KEY_HELP, BASE_URL, BASE_URL_HELP, default_model,
                       extract_json, make_client)
from lintutil import load_lines

SYSTEM_PROMPT = (
    "You are an experienced examiner of master's theses in machine "
    "learning at Aalto University. You are given the extracted text of a "
    "thesis (page markers '[[page N]]' included). Work in two steps.\n\n"
    "STEP 1 — EXTRACT. Find every research question the thesis EXPLICITLY "
    "defines: numbered lists (RQ1, RQ2, ...), hypotheses, or clearly "
    "enumerated research objectives. Quote each verbatim (lightly "
    "shortened is fine) with the page where it is stated. Do not invent "
    "questions the thesis never states; if none exist, return an empty "
    "list.\n\n"
    "STEP 2 — JUDGE each extracted question on its own:\n"
    "  verdict: 'ANSWERED' (a clear answer is developed and supported by "
    "the presented results), 'PARTIALLY-ANSWERED' (addressed, but the "
    "answer is incomplete, hedged without justification, or only weakly "
    "supported by the results), or 'UNANSWERED' (never resolved).\n"
    "  where: the pages/sections in which the answer is developed.\n"
    "  answer: the thesis's answer in 1-2 sentences (empty if none).\n"
    "  evidence: the key quantitative result or argument supporting the "
    "answer, quoted or tightly paraphrased with page numbers; state "
    "plainly if the results do NOT support the claimed answer.\n"
    "  revisited: true/false — does the conclusions/discussion chapter "
    "explicitly return to this question?\n"
    "  gap: for anything less than ANSWERED, what is missing.\n"
    "  fix: one concrete sentence on how to close the gap (empty for "
    "ANSWERED).\n\n"
    "Judge against what the thesis itself presents; do not demand "
    "external experiments. Respond with STRICT JSON:\n"
    '{"research_questions": [{"id": "RQ1", "question": "...", '
    '"stated_page": 12, "verdict": "ANSWERED|PARTIALLY-ANSWERED|'
    'UNANSWERED", "where": "...", "answer": "...", "evidence": "...", '
    '"revisited": true, "gap": "...", "fix": "..."}]}'
)


def main(argv: List[str] = None) -> int:
    ap = argparse.ArgumentParser(
        description="LLM linter: per-research-question answer tracing.")
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
                    help="'paper' accepts a contributions list as the unit "
                         "and drops the thesis-only 'revisited in "
                         "conclusions' penalty.")
    args = ap.parse_args(argv)

    lines, mode = load_lines([args.pdf])
    if mode != "pdf":
        print("ERROR: this linter takes a compiled PDF.", file=sys.stderr)
        return 2

    chunks, cur_page = [], None
    for where, t in lines:
        if where != cur_page:
            cur_page = where
            chunks.append(f"\n[[page {where[1:]}]]\n")
        chunks.append(t + "\n")
    text = "".join(chunks)
    if len(text) > args.max_chars:
        text = text[: args.max_chars]
        print(f"[warn] text truncated to {args.max_chars} chars",
              file=sys.stderr)

    model = args.model or default_model(args.base_url)
    client = make_client(args.base_url, args.api_key)
    print(f"[info] gateway={args.base_url}\n[info] model={model}  "
          f"chars={len(text)}", file=sys.stderr)

    paper_note = ""
    if args.profile == "paper":
        paper_note = (
            "NOTE: this is a conference/journal paper, not a thesis. If it "
            "states no explicit research questions, treat its enumerated "
            "CONTRIBUTIONS or CLAIMS as the units to evaluate. A paper has no "
            "thesis-style conclusions chapter, so do NOT penalise a question/"
            "claim for not being 'revisited in conclusions'; judge only "
            "whether the results substantiate it.\n\n")
    raw, usage = client.complete(
        model=model, system=SYSTEM_PROMPT,
        user=f'{paper_note}paper text:\n"""\n{text}\n"""',
        timeout=600, max_tokens=12000)
    parsed = extract_json(raw) or {}
    rqs = [r for r in parsed.get("research_questions", [])
           if isinstance(r, dict)]

    md = args.format == "markdown"
    out = []
    header = f"Research-question lint report (LLM, {model})"
    out += [f"# {header}", "", f"File: `{args.pdf}`", ""] if md else \
           [f"== {header}", f"File: {args.pdf}", ""]

    n_bad = 0
    if not rqs:
        n_bad += 1
        msg = ("[WARN] NO-RQS  no explicitly stated research questions "
               "found — ml-theses.org expects results to be discussed "
               "against defined research questions; state them in the "
               "introduction.")
        out.append(msg if not md else f"**{msg}**")
    for r in rqs:
        rid = str(r.get("id", "RQ?"))
        verdict = str(r.get("verdict", "UNANSWERED")).upper()
        question = str(r.get("question", "")).strip()
        stated = r.get("stated_page", "?")
        where = str(r.get("where", "")).strip()
        answer = str(r.get("answer", "")).strip()
        evidence = str(r.get("evidence", "")).strip()
        revisited = bool(r.get("revisited", False))
        gap = str(r.get("gap", "")).strip()
        fix = str(r.get("fix", "")).strip()
        if verdict != "ANSWERED":
            n_bad += 1
        if md:
            out += [f"## {rid} — {verdict}",
                    f"> {question} *(stated p. {stated})*", ""]
            if answer:
                out.append(f"- **Answer:** {answer}")
            if where:
                out.append(f"- **Where:** {where}")
            if evidence:
                out.append(f"- **Evidence:** {evidence}")
            out.append(f"- **Revisited in conclusions:** "
                       f"{'yes' if revisited else 'no'}")
            if gap:
                out.append(f"- **Gap:** {gap}")
            if fix:
                out.append(f"- **Fix:** {fix}")
            out.append("")
        else:
            tag = "INFO" if verdict == "ANSWERED" else "WARN"
            out.append(f"[{tag}] {verdict:<19} {rid}: {question} "
                       f"(stated p.{stated})")
            if answer:
                out.append(f"        answer:    {answer}")
            if where:
                out.append(f"        where:     {where}")
            if evidence:
                out.append(f"        evidence:  {evidence}")
            out.append(f"        revisited in conclusions: "
                       f"{'yes' if revisited else 'no'}")
            if gap:
                out.append(f"        gap:       {gap}")
            if fix:
                out.append(f"        fix:       {fix}")
            out.append("")
        if verdict == "ANSWERED" and not revisited and args.profile != "paper":
            n_bad += 1
            line = (f"[WARN] NOT-REVISITED       {rid}: answered, but the "
                    f"conclusions never explicitly return to it.")
            out.append(line if not md else f"**{line}**\n")

    n_ok = sum(1 for r in rqs
               if str(r.get("verdict", "")).upper() == "ANSWERED")
    out.append(f"{len(rqs)} research question(s): {n_ok} answered, "
               f"{len(rqs) - n_ok} not fully answered.  "
               f"(tokens: {usage.get('total_tokens', '?')})")

    report = "\n".join(out)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(report + "\n")
        print(f"Report written to {args.out}", file=sys.stderr)
    else:
        print(report)
    return 1 if n_bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
