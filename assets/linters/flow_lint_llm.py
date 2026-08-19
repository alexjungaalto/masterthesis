#!/usr/bin/env python3
"""LLM linter: narrative flow.

Two checks on how the manuscript reads as a linear (and non-linear)
narrative:

  opener  the first sentence(s) after every chapter/section heading must
          stand alone. Readers (and examiners) enter at headings; an
          opener whose antecedent lives before the heading ("A difference
          of almost an order of magnitude illustrates ...") is opaque to
          them. Each opener is judged WITHOUT the preceding text, exactly
          like such a reader.
            [WARN] OPAQUE-OPENER   backward reference across the heading,
                                   or presumes the preceding section
  flow    transitions between consecutive paragraphs within a section
          must not be non-sequiturs: an abrupt topic change with no
          connective, or a paragraph presupposing material not yet
          introduced.
            [WARN] FLOW-BREAK      discontinuity between two consecutive
                                   paragraphs

Related linters: section_intro_lint_llm.py judges whether an intro maps
its subsections (units WITH subsections only); prose_lint_llm.py flags
pronoun-based dangling references within a chunk. This linter owns the
cases both miss: leaf-section openers and paragraph-to-paragraph flow.

Findings are heuristic LLM judgements — review them.

Gateway: the Aalto AI API by default (see aalto_llm.py; $AALTO_API_KEY,
Aalto network/VPN only); --base-url switches gateways.

Usage:
  python3 flow_lint_llm.py thesis.pdf
  python3 flow_lint_llm.py thesis.pdf --checks opener
  python3 flow_lint_llm.py thesis.pdf --checks flow --pages 8-40
Exit status: 0 clean, 1 findings, 2 usage error.
"""

import argparse
import concurrent.futures
import json
import re
import sys
from typing import Dict, List, Optional, Tuple

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

from aalto_llm import (API_KEY_HELP, BASE_URL, BASE_URL_HELP, default_model,
                       extract_json, is_responses_api, make_client)
from lintutil import (Report, is_toc_line, load_lines,
                      paragraphs_from_lines, sentences)
from section_intro_lint_llm import (SKIP_TITLES_RE, find_pos, load_outline,
                                    slice_between)

CHECKS = ["opener", "flow"]

MAX_OPENER_CHARS = 420
WINDOW = 10          # paragraphs per flow-judgement call
PARA_HEAD, PARA_TAIL = 350, 250   # middle-truncation of long paragraphs

OPENER_SYSTEM_PROMPT = (
    "You judge the OPENING of one chapter/section of a master's thesis "
    "in machine learning. You get the heading (with its parent headings "
    "for orientation) and the first sentence(s) that follow it — and "
    "NOTHING that comes before the heading. Judge like a reader who "
    "opens the thesis at this heading, which is how sections are read "
    "and skimmed.\n\n"
    "Verdict OPAQUE when the opener cannot be fully interpreted without "
    "having read the text before the heading:\n"
    "  * an anaphor whose referent lies across the heading — a bare "
    "pronoun ('This shows ...', 'They also found ...') or, just as bad, "
    "a definite/indefinite noun phrase pointing at unstated prior "
    "content ('A difference of almost an order of magnitude "
    "illustrates ...', 'These studies ...', 'Such an approach ...'),\n"
    "  * a contrastive or resultive connective hanging on unstated "
    "prior content ('However, ...', 'This is why ...') with no clue in "
    "the sentence itself what is being contrasted or concluded,\n"
    "  * the sentence only makes sense as a continuation of the "
    "previous section's discussion rather than an opening of the topic "
    "named in the heading.\n\n"
    "NOT defects (verdict STANDALONE):\n"
    "  * deixis to the unit or thesis itself ('This section reviews "
    "...', 'In this thesis ...'),\n"
    "  * NAMED backward references the reader can follow ('As shown in "
    "Section 2.3 ...', 'The dataset of Section 3.1 ...'),\n"
    "  * ordinary technical vocabulary defined earlier in the thesis or "
    "standard in the field — flag referential dependence, not "
    "vocabulary,\n"
    "  * openers that are merely terse or dry but self-contained.\n\n"
    "Be conservative: flag only openers a careful editor would mark. "
    "Respond with STRICT JSON:\n"
    '{"verdict": "STANDALONE|OPAQUE", "problem": "...", "rewrite": "..."}\n'
    "'problem' names the unresolved reference or presumption in one "
    "sentence; 'rewrite' (OPAQUE only) is a self-contained replacement "
    "opener that names the antecedent explicitly."
)

FLOW_SYSTEM_PROMPT = (
    "You are a structural editor checking NARRATIVE FLOW in a numbered "
    "sequence of consecutive paragraphs from a master's thesis in "
    "machine learning. Judge every transition from one paragraph to the "
    "next and report the ones that break the narrative:\n"
    "  * a non-sequitur: the topic changes abruptly with no connective "
    "or bridging sentence, and nothing in the earlier paragraph "
    "prepares the jump,\n"
    "  * the later paragraph presupposes a concept, result, or "
    "experiment that no earlier paragraph in this excerpt has "
    "introduced and that is not a named reference (a citation, "
    "'Section 2.3', 'Table 4'),\n"
    "  * the later paragraph belongs earlier: it explains or motivates "
    "something the earlier paragraph already used.\n\n"
    "NOT defects:\n"
    "  * a paragraph that IS or STARTS WITH a section heading (e.g. "
    "'2.2.4 Negative externalities of tracking') — headings reset the "
    "narrative legitimately; never flag transitions into or out of a "
    "heading,\n"
    "  * float furniture — table rows, figure/table captions "
    "('Table 3: ...'), displayed equations, page numbers — interrupting "
    "the text; skip such paragraphs entirely when judging adjacency,\n"
    "  * terse but logical transitions, enumerated lists, or a new "
    "aspect of the same topic that any attentive reader follows.\n\n"
    "Be conservative: flag only transitions where a careful reader "
    "genuinely stumbles. Respond with STRICT JSON:\n"
    '{"breaks": [{"after": <paragraph number before the gap>, '
    '"quote": "<first words of the following paragraph, <=20 words>", '
    '"explanation": "..."}]}'
)


# ---------------------------------------------------------------------------
# opener check
# ---------------------------------------------------------------------------
def collect_openers(doc, levels: set) -> List[dict]:
    """One entry per outline heading: breadcrumb, heading, opener text."""
    outline = load_outline(doc)
    cache: Dict[int, str] = {}
    units = []
    trail: List[Tuple[int, str]] = []   # (level, title) breadcrumb stack
    for i, (lvl, title, page0) in enumerate(outline):
        trail = [(l, t) for (l, t) in trail if l < lvl] + [(lvl, title)]
        if lvl not in levels or SKIP_TITLES_RE.match(title):
            continue
        start = find_pos(doc, cache, title, page0)
        end = None
        if i + 1 < len(outline):
            nlvl, ntitle, npage = outline[i + 1]
            npos = find_pos(doc, cache, ntitle, npage)
            end = (npos[0], max(0, npos[1] - len(ntitle) - 20))
        text = slice_between(doc, cache, start, end, MAX_OPENER_CHARS * 2)
        # a unit whose own text is (nearly) empty is MISSING-INTRO
        # territory (section_intro_lint_llm.py), not an opener problem
        if len(text) < 40:
            continue
        opener = " ".join(sentences(text)[:2])[:MAX_OPENER_CHARS]
        units.append({"heading": title,
                      "breadcrumb": " > ".join(t for _, t in trail),
                      "page": f"p{start[0] + 1}",
                      "opener": opener})
    return units


def run_opener_check(args, rep: Report) -> Tuple[int, int]:
    """Returns (units judged, total tokens)."""
    if fitz is None:
        print("ERROR: PyMuPDF required for the opener check. "
              "pip install pymupdf", file=sys.stderr)
        return 0, 0
    doc = fitz.open(args.inputs[0])
    levels = {int(x) for x in args.levels.split(",")}
    units = collect_openers(doc, levels)
    doc.close()
    if not units:
        print("[opener] no headings with own text found.", file=sys.stderr)
        return 0, 0

    # Subtle judgement (cf. section_intro_lint_llm.py): the mini tier
    # lets near-miss openers pass, so default to the full GPT-5 model.
    model = args.model or ("gpt-5-2025-08-07"
                           if is_responses_api(args.base_url)
                           else default_model(args.base_url))
    client = make_client(args.base_url, args.api_key)
    print(f"[info] opener: model={model}  units={len(units)}",
          file=sys.stderr)

    def judge(unit):
        user = (f"heading (with parents): {unit['breadcrumb']}\n\n"
                f"first sentence(s) after the heading:\n"
                f"\"\"\"\n{unit['opener']}\n\"\"\"")
        raw, usage = client.complete(model=model,
                                     system=OPENER_SYSTEM_PROMPT,
                                     user=user, timeout=300,
                                     max_tokens=2000)
        return extract_json(raw) or {}, usage

    total_tokens = 0
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=max(1, args.concurrency)) as ex:
        for unit, (res, usage) in zip(units, ex.map(judge, units)):
            total_tokens += usage.get("total_tokens", 0)
            verdict = str(res.get("verdict", "")).upper()
            print(f"[progress] opener {unit['heading']}: "
                  f"{verdict or '?'}", file=sys.stderr)
            if verdict == "OPAQUE":
                problem = str(res.get("problem", "")).strip()
                rewrite = str(res.get("rewrite", "")).strip()
                msg = (f"{unit['heading']}: opens \"{unit['opener'][:80]}\""
                       f" — {problem}")
                if rewrite:
                    msg += f" || rewrite: {rewrite}"
                rep.add("WARN", "OPAQUE-OPENER", unit["page"], msg)
    return len(units), total_tokens


# ---------------------------------------------------------------------------
# flow check
# ---------------------------------------------------------------------------
def trim_para(text: str) -> str:
    """Middle-truncate a long paragraph to its head and tail (joined by
    ' […] '), keeping the opening and closing that carry the transition
    while capping tokens sent to the LLM."""
    if len(text) <= PARA_HEAD + PARA_TAIL + 20:
        return text
    return text[:PARA_HEAD] + " […] " + text[-PARA_TAIL:]


def run_flow_check(args, rep: Report) -> Tuple[int, int]:
    """Returns (transitions judged, total tokens)."""
    lines, mode = load_lines(args.inputs)
    if args.pages and mode == "pdf":
        m = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", args.pages)
        if not m:
            print(f"ERROR: bad --pages value: {args.pages!r}",
                  file=sys.stderr)
            return 0, 0
        lo, hi = int(m.group(1)), int(m.group(2))
        lines = [(w, t) for (w, t) in lines if lo <= int(w[1:]) <= hi]
    lines = [(w, t) for (w, t) in lines if not is_toc_line(t)]

    # Drop the reference list — no narrative there.
    body = []
    in_refs = False
    for w, t in lines:
        if re.match(r"^\s*(References|Bibliography)\s*$", t.strip(), re.I):
            in_refs = True
        if not in_refs:
            body.append((w, t))

    paras = paragraphs_from_lines(body)
    if len(paras) < 2:
        print("[flow] not enough paragraphs.", file=sys.stderr)
        return 0, 0

    # Overlap windows by one paragraph so every adjacent pair is judged.
    windows = []
    step = max(1, WINDOW - 1)
    for start in range(0, len(paras) - 1, step):
        windows.append(list(range(start, min(start + WINDOW, len(paras)))))
    if args.limit:
        windows = windows[: args.limit]

    model = args.model or default_model(args.base_url)
    client = make_client(args.base_url, args.api_key)
    print(f"[info] flow: model={model}  paragraphs={len(paras)}  "
          f"windows={len(windows)}", file=sys.stderr)

    def judge(idxs):
        listing = "\n\n".join(
            f"P{i} ({paras[i][0]}): {trim_para(paras[i][1])}"
            for i in idxs)
        user = ("consecutive paragraphs (P<number> is the paragraph id, "
                "parenthesis its page):\n\n" + listing)
        raw, usage = client.complete(model=model,
                                     system=FLOW_SYSTEM_PROMPT,
                                     user=user, timeout=300)
        parsed = extract_json(raw) or {}
        breaks = parsed.get("breaks", [])
        return breaks if isinstance(breaks, list) else [], usage

    total_tokens = 0
    seen = set()
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=max(1, args.concurrency)) as ex:
        for idxs, (breaks, usage) in zip(windows, ex.map(judge, windows)):
            total_tokens += usage.get("total_tokens", 0)
            print(f"[progress] flow window at {paras[idxs[0]][0]}: "
                  f"{len(breaks)} break(s)", file=sys.stderr)
            for b in breaks:
                if not isinstance(b, dict):
                    continue
                try:
                    after = int(b.get("after"))
                except (TypeError, ValueError):
                    continue
                # boundary pairs are judged again by the next window
                if after < idxs[0] or after >= idxs[-1] or after in seen:
                    continue
                seen.add(after)
                where = paras[min(after + 1, len(paras) - 1)][0]
                quote = str(b.get("quote", "")).strip()
                expl = str(b.get("explanation", "")).strip()
                rep.add("WARN", "FLOW-BREAK", where,
                        f"\"{quote[:90]}\" — {expl[:160]}")
    return len(paras) - 1, total_tokens


# ---------------------------------------------------------------------------
def main(argv: List[str] = None) -> int:
    ap = argparse.ArgumentParser(
        description="LLM linter: standalone section openers and "
                    "paragraph-to-paragraph narrative flow.")
    ap.add_argument("inputs", nargs="+", help="thesis.pdf")
    ap.add_argument("--base-url", default=BASE_URL, help=BASE_URL_HELP)
    ap.add_argument("--api-key", default=None, help=API_KEY_HELP)
    ap.add_argument("--model", default=None,
                    help="Model id for BOTH checks (default: full GPT-5 "
                         "for openers, the gateway default for flow).")
    ap.add_argument("--checks", default=",".join(CHECKS),
                    help=f"Comma-separated subset of: {', '.join(CHECKS)}")
    ap.add_argument("--levels", default="1,2,3",
                    help="Outline levels for the opener check "
                         "(default '1,2,3').")
    ap.add_argument("--pages", default=None,
                    help="Flow check: PDF page range, e.g. '8-40'.")
    ap.add_argument("--limit", type=int, default=None,
                    help="Flow check: stop after this many windows "
                         "(quick tests).")
    ap.add_argument("--concurrency", type=int, default=4,
                    help="Concurrent LLM calls (default 4).")
    args = ap.parse_args(argv)

    checks = [c.strip() for c in args.checks.split(",") if c.strip()]
    bad = [c for c in checks if c not in CHECKS]
    if bad:
        print(f"ERROR: unknown check(s): {', '.join(bad)}", file=sys.stderr)
        return 2
    if not args.inputs[0].lower().endswith(".pdf"):
        print("ERROR: PDF input required (the opener check needs the "
              "document outline).", file=sys.stderr)
        return 2

    print(f"[info] gateway={args.base_url}", file=sys.stderr)
    rep = Report("Narrative flow lint report (LLM)",
                 " ".join(args.inputs),
                 about="LLM check: do section openers stand alone (read at the "
                       "heading), and do consecutive paragraphs follow without "
                       "narrative jumps?")
    n_openers = n_pairs = total_tokens = 0
    if "opener" in checks:
        n_openers, tok = run_opener_check(args, rep)
        total_tokens += tok
    if "flow" in checks:
        n_pairs, tok = run_flow_check(args, rep)
        total_tokens += tok

    print(rep.render())
    print(f"\n{n_openers} opener(s) and {n_pairs} transition(s) judged.  "
          f"(tokens: {total_tokens})")
    return rep.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
