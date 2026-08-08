#!/usr/bin/env python3
"""LLM linter: type / dimension / range well-formedness of formal claims.

Catches a class of imprecision that the structural linters cannot see: a
relation or operator applied to operands the thesis *itself* has defined as
incompatible objects. Three sibling defects:

  type-mismatch   a same-type relation (approximates, equals, is close to,
                  converges to, is a subset/superset of, is distributed as,
                  minimizes/maximizes) applied to operands of different type
                  classes -- e.g. "the candidate active constraint set A_hat
                  (a set) best approximates the optimal strategy sigma*
                  (a bound-assignment vector)". A set and a vector are
                  different objects, so "approximates" is a category error.

  range          a value assigned outside the range its own type implies --
                  e.g. a quantity defined as a failure PROBABILITY (in (0,1))
                  set to delta = 10, which makes any "with probability >= 1 -
                  delta" guarantee vacuous.

  dimension      a dimensionless quantity carrying units, or unit mismatch --
                  e.g. "a speedup of 2.7 seconds" (a speedup is a ratio).

The check is grounded in the thesis's OWN definitions: STEP 1 builds a type
ledger from Definition environments / "let X denote ..." / notation tables;
STEP 2 scans formal claims and checks each relation's operands against that
ledger. A mismatch is only flagged when BOTH operands have an explicit
declared type -- otherwise the model returns UNCLEAR rather than guessing.

Bridge maps are respected. If the thesis defines a correspondence that makes
the comparison well-typed (e.g. A*(sigma) = "the active set induced by the
strategy sigma"), the finding is downgraded to a BRIDGE-LOOSE advisory:
"licensed but imprecise -- restate over the mapped object and note whether
the map is injective", rather than a hard FAIL.

Like the other linters this is a *heuristic aid*, not a proofreader: expect
false positives and skim the report. Exit status 1 if any FAIL is found
(BRIDGE-LOOSE / UNCLEAR do not fail the build).

Gateway: the Aalto AI API by default (see aalto_llm.py; $AALTO_API_KEY,
Aalto network/VPN only); --base-url switches to the Aalto LLM Gateway or any
OpenAI-style endpoint.

Usage:
  python3 type_consistency_lint_llm.py thesis.pdf
  python3 type_consistency_lint_llm.py thesis.pdf --out report.md --format markdown
Exit status: 0 no FAILs, 1 findings, 2 usage error.
"""

import argparse
import sys
from typing import List

from aalto_llm import (API_KEY_HELP, BASE_URL, BASE_URL_HELP, default_model,
                       extract_json, make_client)
from lintutil import load_lines

# The relation vocabulary the linter reasons about, and the type rule for
# each. Shown to the model so its judgements are anchored to explicit rules
# rather than taste.
RELATION_RULES = [
    ("approximates / equals / is close to / converges to / is estimated by",
     "both operands must belong to the SAME type class (set~set, "
     "vector/point~vector/point, scalar~scalar, function~function, "
     "distribution~distribution). A set compared to a vector, or an "
     "estimator compared to a scalar, is a type mismatch."),
    ("is a subset / superset of, is contained in",
     "both operands must be SETS."),
    ("minimizes / maximizes / is optimal for",
     "the subject is a decision variable or argument; the object must be a "
     "SCALAR objective/criterion, not a set or a vector."),
    ("is distributed as, ~, is drawn from",
     "the subject is a random variable; the object is a DISTRIBUTION."),
]

# Type classes the ledger uses.
TYPE_CLASSES = ("set, vector/point, scalar, function/map, "
                "distribution/random-variable, matrix, index/integer, "
                "probability (scalar in [0,1]), algorithm/procedure")

SYSTEM_PROMPT = (
    "You are an experienced supervisor of master's theses in machine "
    "learning and optimization at Aalto University. You check the FORMAL "
    "well-formedness of the thesis's claims: whether relations and operators "
    "are applied to operands of compatible mathematical type, and whether "
    "quantities respect the range and dimension their own definitions imply. "
    "You are given the extracted text of the thesis (page markers "
    "'[[page N]]' included).\n\n"
    "STEP 1 -- TYPE LEDGER. From the thesis's OWN definitions (Definition "
    "environments, 'let X denote ...', notation/symbol tables), extract the "
    "objects it defines and assign each a type class from: "
    f"{TYPE_CLASSES}. Record symbol(s), type, a short gloss, and page. Only "
    "record objects the thesis actually defines; do not invent types.\n\n"
    "STEP 2 -- CLAIM SCAN. Find sentences that apply a relation or operator "
    "to two operands, or that assign a numeric value to a defined quantity. "
    "PROSE claims in the abstract, results, and discussion count -- a "
    "sentence of the form 'X best approximates Y' is in scope even when it "
    "is not in a display equation. Also cross-reference every numeric value "
    "assigned to a symbol ANYWHERE, including parameter TABLES and their "
    "captions, against that symbol's ledger type and range. For each, "
    "resolve the operands to ledger entries and decide a code:\n"
    "Be EXHAUSTIVE about claims using the words 'approximate(s)' / "
    "'approximation' / 'best matches' -- approximation is the central "
    "relation here; enumerate every such claim and type-check its two "
    "operands, do not report only the first one you find.\n"
    "  TYPE-MISMATCH  a same-type relation applied to operands of different "
    "type classes (per the relation rules given). ONLY emit if BOTH operands "
    "have an explicit ledger type; if either is unclear, use UNCLEAR.\n"
    "  RANGE          a value assigned outside the range its type implies "
    "(e.g. a symbol declared a probability or confidence, so in (0,1), but "
    "assigned a value >= 1 in the text or a parameter table -- which would "
    "make any 'with probability >= 1 - x' guarantee vacuous; a count that "
    "is negative; a ratio beyond its definitional bound).\n"
    "  DIMENSION      a dimensionless quantity (ratio, speedup, probability, "
    "count) carrying units, or a units mismatch across an equation.\n"
    "  BRIDGE-LOOSE   a TYPE-MISMATCH that the thesis nonetheless LICENSES "
    "because it defines a correspondence/induced map between the two types "
    "(e.g. 'A*(sigma) = the active set induced by strategy sigma'). Report "
    "it, name the bridging map, and say whether the map is many-to-one "
    "(so the shorthand loses information).\n"
    "  UNCLEAR        text too garbled/truncated, or a operand lacks a "
    "declared type. Do NOT guess.\n\n"
    "Be conservative. Do NOT flag standard, well-typed usage (a network that "
    "approximates a target FUNCTION is function~function -- fine). Prefer "
    "UNCLEAR over a shaky flag. BUT a definite relation claim whose two "
    "operands have clear, different ledger types is NOT unclear just because "
    "it appears in prose rather than a display equation -- classify it "
    "TYPE-MISMATCH (or BRIDGE-LOOSE if the thesis defines a map between the "
    "two types). For each finding give a short verbatim quote (<=40 words), "
    "the page, the two operands WITH their ledger types, the relation, a "
    "one-line reason, and one concrete restatement that fixes it.\n\n"
    "Respond with STRICT JSON:\n"
    '{"ledger": [{"symbol": "...", "type": "...", "gloss": "...", '
    '"page": "N"}], "findings": [{"code": "TYPE-MISMATCH|RANGE|DIMENSION|'
    'BRIDGE-LOOSE|UNCLEAR", "claim": "...", "page": "N", "relation": "...", '
    '"operands": ["A_hat: set", "sigma*: vector"], "reason": "...", '
    '"bridge": "name of induced map, or empty", "suggestion": "..."}], '
    '"notes": "..."}'
)

# Codes that fail the build.
FAIL_CODES = {"TYPE-MISMATCH", "RANGE", "DIMENSION"}


def _rules_block() -> str:
    lines = ["relation type rules:"]
    for rel, rule in RELATION_RULES:
        lines.append(f"  - {rel}: {rule}")
    return "\n".join(lines)


def main(argv: List[str] = None) -> int:
    ap = argparse.ArgumentParser(
        description="LLM linter: type/dimension/range well-formedness of "
                    "formal claims (ml-theses.org).")
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

    user = (f"{_rules_block()}\n\n"
            f"thesis text{' (TRUNCATED)' if truncated else ''}:\n"
            f'"""\n{text}\n"""')
    raw, usage = client.complete(model=model, system=SYSTEM_PROMPT,
                                 user=user, timeout=600, max_tokens=12000)
    parsed = extract_json(raw) or {}
    ledger = [e for e in parsed.get("ledger", []) if isinstance(e, dict)]
    findings = [f for f in parsed.get("findings", []) if isinstance(f, dict)]
    notes = str(parsed.get("notes", "")).strip()

    md = args.format == "markdown"
    out = []
    if md:
        out += [f"# Type-consistency lint report — {args.pdf}", "",
                f"_model: {model}_", ""]
    else:
        out += [f"== Type-consistency lint report (LLM, {model})",
                f"File: {args.pdf}", ""]

    n_fail = n_bridge = n_unclear = 0
    for f in findings:
        code = str(f.get("code", "UNCLEAR")).upper()
        if code in FAIL_CODES:
            n_fail += 1
        elif code == "BRIDGE-LOOSE":
            n_bridge += 1
        else:
            n_unclear += 1

    if md and ledger:
        out += ["## Type ledger", "", "| symbol | type | gloss | page |",
                "|---|---|---|---|"]
        for e in ledger:
            out.append(f"| {e.get('symbol','')} | {e.get('type','')} | "
                       f"{e.get('gloss','')} | {e.get('page','')} |")
        out.append("")

    if not findings:
        out.append(("> " if md else "[INFO] ")
                   + (notes or "No type/range/dimension issues identified."))
    else:
        if md:
            out += ["## Findings", ""]
        for f in findings:
            code = str(f.get("code", "UNCLEAR")).upper()
            claim = str(f.get("claim", "")).strip()
            page = str(f.get("page", "?")).strip()
            rel = str(f.get("relation", "")).strip()
            operands = f.get("operands", [])
            if isinstance(operands, list):
                operands = " vs. ".join(str(o) for o in operands)
            reason = str(f.get("reason", "")).strip()
            bridge = str(f.get("bridge", "")).strip()
            sugg = str(f.get("suggestion", "")).strip()
            if md:
                out += [f"### [{code}] p{page} — {rel}",
                        f"> {claim}", "",
                        f"- **operands:** {operands}",
                        f"- **why:** {reason}"]
                if bridge:
                    out.append(f"- **bridge:** {bridge}")
                if sugg:
                    out.append(f"- **fix:** {sugg}")
                out.append("")
            else:
                out.append(f"  [{code}] p{page}  ({rel}: {operands})")
                out.append(f"        claim: {claim}")
                out.append(f"        why:   {reason}")
                if bridge:
                    out.append(f"        bridge: {bridge}")
                if sugg:
                    out.append(f"        fix:   {sugg}")

    out += ["", f"{len(findings)} finding(s): {n_fail} FAIL, {n_bridge} "
                f"bridge-loose, {n_unclear} unclear.  "
                f"(tokens: {usage.get('total_tokens', '?')})"]
    report = "\n".join(out)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(report + "\n")
        print(f"Report written to {args.out}", file=sys.stderr)
    else:
        print(report)
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
