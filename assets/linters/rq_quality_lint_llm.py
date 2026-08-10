#!/usr/bin/env python3
"""LLM linter: quality of a thesis's research scope and research questions.

Judges HOW GOOD the stated research questions and scope are --- not whether
they are answered (that is research_questions_lint_llm.py). The criteria
follow authoritative university guidance:

  * University research-question checklists (e.g. Monash University
    Library, "Developing research questions"): a good question is focused
    on a single problem, researchable with available sources/methods,
    feasible within the time frame, specific enough to answer thoroughly,
    complex enough to require analysis, and relevant to the field.
  * George Mason University Writing Center, "How to Write a Research
    Question": clear ("enough specifics that one's audience can easily
    understand its purpose"), focused ("narrow enough that it can be
    answered thoroughly"), concise, complex ("not answerable with a simple
    'yes' or 'no'"), and arguable ("potential answers are open to debate").
  * The FINER criteria (Hulley et al., Designing Clinical Research):
    Feasible, Interesting, Novel, Ethical, Relevant.
  * Self-containment (an ml-theses.org addition): every technical term or
    acronym the question uses is actually DEFINED -- glossed, expanded, or
    given a "let X denote ..." -- not merely mentioned, at or before the
    point where the question is stated, so the question is understandable
    where it appears rather than only after later chapters define its terms.

Per research question: verdict STRONG / ADEQUATE / WEAK with per-criterion
flags and a suggested reformulation for anything less than STRONG.
Scope-level checks: research gap identified, delimitations stated,
alignment between questions and stated objectives/contributions, and joint
coverage of the thesis aim.

  [WARN] WEAK-RQ / NO-RQS / scope-level gaps
  [INFO] STRONG-RQ / ADEQUATE-RQ and satisfied scope checks

Uses the full GPT-5 model by default on the Aalto AI API (the judgement is
calibration-sensitive). --base-url switches gateways (see aalto_llm.py).

Usage:
  python3 rq_quality_lint_llm.py thesis.pdf
  python3 rq_quality_lint_llm.py thesis.pdf --format markdown --out rq.md
Exit status: 0 no warnings, 1 findings, 2 usage error.
"""

import argparse
import sys
from typing import List

from aalto_llm import (API_KEY_HELP, BASE_URL, BASE_URL_HELP, default_model,
                       extract_json, is_responses_api, make_client)
from lintutil import load_lines

SYSTEM_PROMPT = (
    "You are an experienced examiner judging the QUALITY of the research "
    "scope and research questions of a master's thesis in machine "
    "learning -- not whether they are answered, but whether they are "
    "well-posed. You receive the thesis text with '[[page N]]' markers.\n\n"
    "STEP 1 -- EXTRACT. Quote verbatim (lightly shortened is fine), with "
    "pages: the main aim; every explicitly stated research question or "
    "hypothesis; stated objectives/contributions; stated delimitations; "
    "the research-gap statement. Do not invent items; empty lists are "
    "valid.\n\n"
    "STEP 2 -- JUDGE EACH RESEARCH QUESTION against this checklist, "
    "compiled from university guidance (Monash University Library; George "
    "Mason University Writing Center; the FINER criteria):\n"
    "  clear: enough specifics that a reader understands its purpose "
    "without extra explanation (weak: 'How should social networking "
    "sites address the harm they cause?'; strong: names the actors, the "
    "harm, and the aspect of interest).\n"
    "  focused: a SINGLE problem, answerable thoroughly in the space of "
    "a thesis; flag double-barreled questions that bundle two askables.\n"
    "  concise: expressed without filler.\n"
    "  complex: not answerable with a bare 'yes'/'no' or a lookup; "
    "requires synthesis or quantified analysis. An engineering question "
    "in yes/no FORM ('Can X beat Y?') that plainly demands quantified "
    "evidence is a minor form issue -- suggest 'To what extent ...' "
    "phrasing -- whereas a question that a single fact settles is a "
    "substantive defect.\n"
    "  specific: key concepts are precise and measurable, not vague "
    "('effective', 'good performance') without stated metrics.\n"
    "  self-contained: every non-generic technical term, acronym, or "
    "named entity IN THE QUESTION must be actually DEFINED -- not merely "
    "mentioned -- at or BEFORE the page where the question is stated. A "
    "DEFINITION is a parenthetical gloss ('the agent harness (the "
    "non-model infrastructure between the LLM and the target system)'), a "
    "'let X denote ...' / 'X is defined as ...' / 'we call X ...' "
    "sentence, an acronym expansion, a Definition environment, or a "
    "notation/glossary entry. A bare earlier OCCURRENCE of the term with "
    "no explanation is 'mentioned, NOT defined' and does NOT satisfy this "
    "criterion. Check strictly by page order using the '[[page N]]' "
    "markers: the defining page must be <= the question's page; a "
    "definition that appears only in a LATER section (even one page later) "
    "does NOT count -- never justify self-containment by citing a section "
    "after the question. When you flag it, say whether the term is "
    "undefined entirely or only mentioned-not-defined before the RQ, and "
    "name the term, the RQ page, and the page where it is actually first "
    "defined (e.g. \"'agent harness' appears in the RQ on p10 but is only "
    "mentioned before then; first defined in 2.6 on p14\"). A term defined "
    "in the question's own sentence, or a genuinely common-ML term "
    "(accuracy, dataset, neural network), counts as satisfied. This is "
    "reader-POSITION self-containment -- distinct from 'clear' (rubric "
    "well-posedness in isolation): a question can be clear to an expert "
    "yet not self-contained. Mentioned-but-not-defined, or defined just a "
    "page or two later, is a minor issue; a term whose definition depends "
    "on a whole later chapter is substantive.\n"
    "  researchable-feasible: answerable with the data, methods, and "
    "time an MSc allows; not requiring inaccessible populations or "
    "unbounded experiments.\n"
    "  relevant-novel: tied to an identified gap; the answer matters to "
    "the field (FINER: interesting, novel, relevant).\n"
    "  arguable: the answer is genuinely open, not a foregone "
    "conclusion or definitional truth.\n\n"
    "Verdicts: STRONG (no criterion meaningfully violated), ADEQUATE "
    "(minor issues, e.g. yes/no form with obvious quantitative intent), "
    "WEAK (one or more substantive violations). For anything below "
    "STRONG give a concrete reformulation.\n\n"
    "STEP 3 -- JUDGE THE SCOPE as a whole: gap_identified (explicit "
    "research-gap statement exists), delimitations_stated (what is out "
    "of scope is said), aligned (each question maps to stated "
    "objectives/contributions and vice versa), covers_aim (the questions "
    "jointly operationalize the stated aim).\n\n"
    "Respond with STRICT JSON:\n"
    '{"aim": "...", "questions": [{"id": "RQ1", "question": "...", '
    '"page": 6, "verdict": "STRONG|ADEQUATE|WEAK", '
    '"criteria_violated": ["focused", "..."], "comment": "...", '
    '"reformulation": "..."}], '
    '"scope": {"gap_identified": true, "delimitations_stated": true, '
    '"aligned": true, "covers_aim": true, "comment": "..."}}'
)


def main(argv: List[str] = None) -> int:
    ap = argparse.ArgumentParser(
        description="LLM linter: quality of research scope and questions "
                    "(university guideline criteria).")
    ap.add_argument("pdf", help="Path to the thesis PDF.")
    ap.add_argument("--base-url", default=BASE_URL, help=BASE_URL_HELP)
    ap.add_argument("--api-key", default=None, help=API_KEY_HELP)
    ap.add_argument("--model", default=None,
                    help="Model id (default: full GPT-5 on the Aalto AI "
                         "API; gateway default otherwise).")
    ap.add_argument("--max-chars", type=int, default=400_000,
                    help="Truncate text beyond this (default 400000).")
    ap.add_argument("--out", help="Write report to this file.")
    ap.add_argument("--format", choices=["text", "markdown"],
                    default="text")
    args = ap.parse_args(argv)

    lines, mode = load_lines([args.pdf])
    if mode != "pdf":
        print("ERROR: this linter takes a compiled PDF.", file=sys.stderr)
        return 2
    chunks, cur = [], None
    for where, t in lines:
        if where != cur:
            cur = where
            chunks.append(f"\n[[page {where[1:]}]]\n")
        chunks.append(t + "\n")
    text = "".join(chunks)[: args.max_chars]

    model = args.model or ("gpt-5-2025-08-07"
                           if is_responses_api(args.base_url)
                           else default_model(args.base_url))
    client = make_client(args.base_url, args.api_key)
    print(f"[info] gateway={args.base_url}\n[info] model={model}  "
          f"chars={len(text)}", file=sys.stderr)

    raw, usage = client.complete(
        model=model, system=SYSTEM_PROMPT,
        user=f'thesis text:\n"""\n{text}\n"""',
        timeout=600, max_tokens=10000)
    parsed = extract_json(raw) or {}
    questions = [q for q in parsed.get("questions", [])
                 if isinstance(q, dict)]
    scope = parsed.get("scope", {}) if isinstance(parsed.get("scope"),
                                                  dict) else {}

    md = args.format == "markdown"
    out = []
    header = f"Research-scope quality report (LLM, {model})"
    out += [f"# {header}", "", f"File: `{args.pdf}`", ""] if md else \
           [f"== {header}", f"File: {args.pdf}", ""]
    aim = str(parsed.get("aim", "")).strip()
    if aim:
        out.append(f"Aim: {aim}")
        out.append("")

    n_warn = 0
    if not questions:
        n_warn += 1
        out.append("[WARN] NO-RQS            no explicitly stated research "
                   "questions found — state them in the introduction.")
    for q in questions:
        verdict = str(q.get("verdict", "WEAK")).upper()
        tag = {"STRONG": ("INFO", "STRONG-RQ"),
               "ADEQUATE": ("INFO", "ADEQUATE-RQ")}.get(
                   verdict, ("WARN", "WEAK-RQ"))
        if tag[0] == "WARN":
            n_warn += 1
        rid = str(q.get("id", "RQ?"))
        violated = ", ".join(str(c) for c in q.get("criteria_violated", []))
        comment = str(q.get("comment", "")).strip()
        reform = str(q.get("reformulation", "")).strip()
        if md:
            out += [f"## {rid} — {verdict}",
                    f"> {q.get('question', '')} *(p. {q.get('page', '?')})*",
                    ""]
            if violated:
                out.append(f"- **Criteria violated:** {violated}")
            out.append(f"- {comment}")
            if reform:
                out.append(f"- **Reformulation:** {reform}")
            out.append("")
        else:
            out.append(f"[{tag[0]}] {tag[1]:<12} {rid}: "
                       f"{str(q.get('question', ''))[:90]}… "
                       f"(p.{q.get('page', '?')})")
            if violated:
                out.append(f"        violates: {violated}")
            out.append(f"        {comment}")
            if reform:
                out.append(f"        reformulate: {reform}")
            out.append("")

    labels = [("gap_identified", "GAP-IDENTIFIED",
               "no explicit research-gap statement found"),
              ("delimitations_stated", "DELIMITATIONS",
               "what is out of scope is never stated"),
              ("aligned", "RQ-ALIGNMENT",
               "questions and stated objectives/contributions do not "
               "map onto each other"),
              ("covers_aim", "AIM-COVERAGE",
               "the questions do not jointly operationalize the aim")]
    for key, code, missing_msg in labels:
        ok = bool(scope.get(key, False))
        if ok:
            out.append(f"[INFO] {code:<16} satisfied")
        else:
            n_warn += 1
            out.append(f"[WARN] {code:<16} {missing_msg}")
    sc = str(scope.get("comment", "")).strip()
    if sc:
        out.append(f"        scope: {sc}")

    n_strong = sum(1 for q in questions
                   if str(q.get("verdict", "")).upper() == "STRONG")
    out += ["", f"{len(questions)} question(s): {n_strong} strong, "
                f"{len(questions) - n_strong} adequate/weak; "
                f"{n_warn} warning(s).  "
                f"(tokens: {usage.get('total_tokens', '?')})"]

    report = "\n".join(out)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(report + "\n")
        print(f"Report written to {args.out}", file=sys.stderr)
    else:
        print(report)
    return 1 if n_warn else 0


if __name__ == "__main__":
    raise SystemExit(main())
