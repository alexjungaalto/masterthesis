#!/usr/bin/env python3
"""LLM linter: does the presented EVIDENCE back each claimed contribution?

A manuscript states contributions (in the abstract, the introduction, and any
"our contributions are" list) and is supposed to establish each one with a
concrete result: a theorem (with a proof), an empirical table, an
analysis/ablation, a construction, or a released dataset. This linter builds
that support chain per claim — which result is meant to back each contribution,
WHERE it is, and whether it actually does the job — so a gap between what is
claimed and what is shown is easy to see.

For every claimed contribution it reports:
  * type      -- what KIND of claim it is (theoretical / empirical /
                 methodological / analysis / dataset), i.e. what backing it
                 needs.
  * backing   -- the kind of result the manuscript OFFERS for it
                 (theorem+proof / theorem (sketch) / experiment / analysis /
                 ablation / construction / dataset / none).
  * evidence  -- the specific result(s) with location: "Theorem 3.2 (p5)",
                 "Table 2 (p7)", "Figure 4 ablation (p8)".
  * support   -- one of:
      SUPPORTED    a concrete result establishes the claim within its stated
                   scope (a theorem whose statement + assumptions entail the
                   claim and that is actually proved; an experiment/analysis
                   that isolates the claimed effect with an appropriate
                   baseline/control).
      PARTIAL      backed but with a nameable gap: a proof sketch only, a
                   theorem NARROWER than the sentence it backs, a single
                   dataset/setting for a general claim, a missing matched
                   baseline, an assumption that does not match the studied
                   setting.
      UNSUPPORTED  a result is presented but does NOT establish the claim
                   (the theorem is about a different quantity; the experiment
                   does not isolate the claimed effect).
      ASSERTED     the claim is stated but no theorem/experiment/analysis in
                   the body targets it.
  * why / gap -- how the evidence entails the claim (SUPPORTED), or the exact
                 shortfall (otherwise).

Theorems get special scrutiny: a formal-sounding claim is only SUPPORTED when
the theorem's STATEMENT and ASSUMPTIONS actually imply the prose claim and a
proof is given (not merely deferred or sketched). A theorem that is weaker or
narrower than the sentence it is cited to support is a PARTIAL "theorem-claim
gap", not support.

This is a reviewing aid, not a grade or an accept/reject verdict. Exit 1 if any
claim is not SUPPORTED; 0 if all are; 2 usage error.

Gateway: the Aalto AI API by default (see aalto_llm.py; $AALTO_API_KEY, Aalto
network/VPN only); --base-url switches gateways.

Usage:
  python3 contribution_support_lint_llm.py thesis.pdf
  python3 contribution_support_lint_llm.py paper.pdf --format markdown --out s.md
"""

import argparse
import sys
from typing import List, Optional

from aalto_llm import (API_KEY_HELP, BASE_URL, BASE_URL_HELP, default_model,
                       extract_json, make_client)
from lintutil import load_lines

SYSTEM_PROMPT = (
    "You are an experienced, critical reviewer for a top ML venue. You are "
    "given the extracted text of a manuscript (a thesis or a research paper; "
    "page markers '[[page N]]' included). Your job is to check, contribution "
    "by contribution, whether the PRESENTED RESULTS actually back each "
    "CLAIMED contribution.\n\n"
    "STEP 1 -- LIST THE CLAIMS. Extract each distinct contribution the "
    "manuscript claims (from the abstract, the introduction, and any explicit "
    "'our contributions are' list). Tightly paraphrase each; do not paste "
    "bullets verbatim. Merge duplicates. Aim for the 2-5 real claims, not "
    "every sentence.\n\n"
    "STEP 2 -- FIND THE BACKING. For each claim, determine its TYPE (what "
    "backing it needs): theoretical (a theorem/lemma/proposition, a "
    "derivation, a guarantee/bound), empirical (experiments/tables), analysis "
    "(a diagnostic study, ablation, or measurement), methodological (a new "
    "method/algorithm/construction), or dataset (a released benchmark). Then "
    "find the specific RESULT in the body meant to establish it and give its "
    "kind (theorem+proof / theorem (proof sketch or deferred) / experiment / "
    "analysis / ablation / construction / dataset / none) and its LOCATION "
    "with page and label, e.g. 'Theorem 3.2 (p5)', 'Table 2 (p7)', 'Figure 4 "
    "(p8)'.\n\n"
    "STEP 3 -- JUDGE THE SUPPORT. Assign exactly one level per claim:\n"
    "  SUPPORTED    a concrete result establishes the claim within its stated "
    "scope. For a theoretical claim this means: the theorem's STATEMENT and "
    "ASSUMPTIONS actually entail the prose claim, AND a proof is given (not "
    "merely deferred or sketched). For an empirical/analysis claim: the "
    "experiment or analysis isolates the claimed effect with an appropriate "
    "baseline/control.\n"
    "  PARTIAL      backed, but with a specific, nameable gap: a proof sketch "
    "only or proof deferred; a theorem NARROWER or WEAKER than the sentence it "
    "backs (assumptions stronger than the setting, a special case, a bound "
    "that does not imply the stated conclusion); a general/robust claim shown "
    "on a single dataset/setting; a missing or non-matched baseline; a "
    "confound not ruled out.\n"
    "  UNSUPPORTED  a result IS presented but does not establish THIS claim "
    "(the theorem concerns a different quantity; the table does not isolate "
    "the claimed effect).\n"
    "  ASSERTED     the claim is stated but NO theorem/experiment/analysis in "
    "the body targets it.\n\n"
    "Be specific and conservative. For SUPPORTED, the 'why' must say, in one "
    "sentence, HOW the named result entails the claim (which theorem under "
    "which assumptions, or which comparison in which table). For the other "
    "levels, the 'gap' must name the concrete shortfall and, where relevant, "
    "the page of the result you inspected. Do not moralise; a modest claim "
    "with matching evidence is SUPPORTED. Do not reward a formal-sounding "
    "claim for merely HAVING a theorem -- check that the theorem says what the "
    "prose says.\n\n"
    "Keep every field CONCISE: at most 1-2 sentences; paraphrase, never paste "
    "long passages. Output MUST be a single valid JSON object and nothing "
    "else.\n\n"
    "Respond with STRICT JSON:\n"
    '{"claims": [{"id": "C1", "claim": "...", '
    '"claim_type": "theoretical|empirical|analysis|methodological|dataset", '
    '"backing": "theorem+proof|theorem (sketch)|experiment|analysis|ablation|'
    'construction|dataset|none", "evidence": ["Theorem 3.2 (p5)", "..."], '
    '"support": "SUPPORTED|PARTIAL|UNSUPPORTED|ASSERTED", '
    '"rationale": "..."}], "overall": "..."}'
)

SUPPORT_LEVELS = ("SUPPORTED", "PARTIAL", "UNSUPPORTED", "ASSERTED")
FAIL_LEVELS = {"PARTIAL", "UNSUPPORTED", "ASSERTED"}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="LLM linter: does the presented evidence (theorem, "
                    "experiment, analysis) back each claimed contribution?")
    ap.add_argument("pdf", help="Path to the thesis/paper PDF (or .txt "
                                "extract).")
    ap.add_argument("--base-url", default=BASE_URL, help=BASE_URL_HELP)
    ap.add_argument("--api-key", default=None, help=API_KEY_HELP)
    ap.add_argument("--model", default=None,
                    help="Model id (default depends on the gateway).")
    ap.add_argument("--max-chars", type=int, default=400_000,
                    help="Truncate extracted text beyond this many chars.")
    ap.add_argument("--out", help="Write report to this file.")
    ap.add_argument("--format", choices=["text", "markdown"], default="text")
    ap.add_argument("--profile", choices=["thesis", "paper"], default="thesis",
                    help="Manuscript type (accepted for suite compatibility; "
                         "the check is identical for both).")
    args = ap.parse_args(argv)

    lines, mode = load_lines([args.pdf])
    if mode != "pdf":
        print("ERROR: this linter takes a compiled PDF or a .txt extract.",
              file=sys.stderr)
        return 2

    chunks, cur = [], None
    for where, t in lines:
        if where != cur:
            cur = where
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

    user = (f"manuscript text{' (TRUNCATED)' if truncated else ''}:\n"
            f'"""\n{text}\n"""')
    raw, usage = client.complete(model=model, system=SYSTEM_PROMPT,
                                 user=user, timeout=600, max_tokens=4000)
    parsed = extract_json(raw) or {}
    claims = [c for c in parsed.get("claims", []) if isinstance(c, dict)]
    overall = str(parsed.get("overall", "")).strip()

    # normalise + tally
    norm = []
    for i, c in enumerate(claims, 1):
        support = str(c.get("support", "ASSERTED")).strip().upper()
        if support not in SUPPORT_LEVELS:
            support = "ASSERTED"
        ev = c.get("evidence", [])
        if isinstance(ev, str):
            ev = [ev]
        ev = [str(e).strip() for e in ev if str(e).strip()]
        norm.append({
            "id": str(c.get("id") or f"C{i}").strip(),
            "claim": str(c.get("claim", "")).strip(),
            "type": str(c.get("claim_type", "")).strip(),
            "backing": str(c.get("backing", "")).strip(),
            "evidence": ev,
            "support": support,
            "rationale": str(c.get("rationale", "")).strip(),
        })
    tally = {lvl: sum(1 for c in norm if c["support"] == lvl)
             for lvl in SUPPORT_LEVELS}

    md = args.format == "markdown"
    out = []
    summary = (f"{len(norm)} claim(s): {tally['SUPPORTED']} supported, "
               f"{tally['PARTIAL']} partial, {tally['UNSUPPORTED']} "
               f"unsupported, {tally['ASSERTED']} asserted")
    if md:
        out += [f"# Contribution support — {args.pdf}", "",
                f"_model: {model}_", "", f"**{summary}**", ""]
    else:
        out += [f"== Contribution-support lint (LLM, {model})",
                f"File: {args.pdf}", "", f"SUMMARY: {summary}", "",
                "How to read: for each claimed contribution — the result "
                "meant to back it, where it is, and whether it does.", ""]

    # order: weakest first (ASSERTED, UNSUPPORTED, PARTIAL, SUPPORTED)
    order = {"ASSERTED": 0, "UNSUPPORTED": 1, "PARTIAL": 2, "SUPPORTED": 3}
    for c in sorted(norm, key=lambda x: order.get(x["support"], 0)):
        ev = "; ".join(c["evidence"]) if c["evidence"] else "—"
        rat_label = "why" if c["support"] == "SUPPORTED" else "gap"
        if md:
            out.append(f"### `{c['support']}` — {c['id']} {c['claim']}")
            out.append("")
            out.append(f"- **type:** {c['type'] or '—'}")
            out.append(f"- **backing:** {c['backing'] or '—'}")
            out.append(f"- **evidence:** {ev}")
            if c["rationale"]:
                out.append(f"- **{rat_label}:** {c['rationale']}")
            out.append("")
        else:
            out.append(f"[{c['support']}]  {c['id']}  {c['claim']}")
            out.append(f"    type:     {c['type'] or '—'}")
            out.append(f"    backing:  {c['backing'] or '—'}")
            out.append(f"    evidence: {ev}")
            if c["rationale"]:
                out.append(f"    {rat_label}:      {c['rationale']}")
            out.append("")

    if overall:
        if md:
            out += [f"**Overall:** {overall}", ""]
        else:
            out += [f"Overall: {overall}", ""]

    out += [summary + f".  (tokens: {usage.get('total_tokens', '?')})"]
    report = "\n".join(out)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(report + "\n")
        print(f"Report written to {args.out}", file=sys.stderr)
    else:
        print(report)
    return 1 if any(c["support"] in FAIL_LEVELS for c in norm) else 0


if __name__ == "__main__":
    raise SystemExit(main())
