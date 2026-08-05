#!/usr/bin/env python3
"""LLM linter: the ml-theses.org self-editing pass, judged by a language
model (the accurate cousin of the regex-based prose_lint.py).

Screens the thesis in chunks and reports, per finding category:

  uncited-claim       an empirical or historical assertion that is not the
                      author's own result and carries no citation
  tense-drift         tense switches within a passage describing methods
                      or results
  dangling-reference  "this shows", "it follows" where the antecedent of
                      "this"/"it" is unclear
  vague-quantifier    "significantly", "very", "a lot" without a number
  jargon              colloquial/evaluative ML-speak ("smoothest
                      convergence", "performs well") where the property is
                      never defined or measured, or a technical term is
                      misused informally
  synonym-switch      silently switching between synonyms for one concept
                      (e.g. "data point" vs "sample" vs "instance")
  unmotivated-section a chapter/section opening without a sentence stating
                      what it covers and why it belongs here
  broken-idiom        a mangled or non-standard rendering of an English
                      idiom or collocation ("corner cuttings on safety"
                      for "cutting corners on safety")
  informal-register   colloquial or conversational phrasing out of place
                      in academic prose ("a bunch of", "way better",
                      contractions like "don't")

Findings are heuristic LLM judgements — review them; they are reported as
WARN and the exit status is 1 when any are found.

Gateway: the Aalto AI API by default (see aalto_llm.py; $AALTO_API_KEY,
Aalto network/VPN only); --base-url switches gateways.

Usage:
  python3 prose_lint_llm.py thesis.pdf
  python3 prose_lint_llm.py thesis.pdf --pages 9-60 --concurrency 4
  python3 prose_lint_llm.py thesis.pdf --checks uncited-claim,tense-drift
Exit status: 0 clean, 1 findings, 2 usage error.
"""

import argparse
import concurrent.futures
import json
import re
import sys
from typing import List, Optional, Tuple

from aalto_llm import (API_KEY_HELP, BASE_URL, BASE_URL_HELP, default_model,
                       extract_json, make_client)
from lintutil import Report, is_toc_line, load_lines, paragraphs_from_lines

CHECKS = ["uncited-claim", "tense-drift", "dangling-reference",
          "vague-quantifier", "jargon", "synonym-switch",
          "unmotivated-section", "broken-idiom", "informal-register"]

SYSTEM_PROMPT = (
    "You are a meticulous copy-editor doing the 'self-editing pass' of the "
    "ml-theses.org thesis guide on a chunk of a master's thesis in machine "
    "learning. Report ONLY defects of the requested categories:\n"
    "  uncited-claim: an empirical, quantitative, comparative, or "
    "historical assertion that is clearly NOT the author's own result and "
    "has no citation marker (citations look like [12], [3, 7], or "
    "Author (2020)) in or right after the sentence. Do not flag common "
    "knowledge, definitions, or the author's own results.\n"
    "  tense-drift: the tense switches mid-passage while describing the "
    "same methods/experiments/results (e.g. 'we train ... then we "
    "evaluated').\n"
    "  dangling-reference: a sentence built on 'this/it/these' whose "
    "antecedent is genuinely ambiguous to a careful reader.\n"
    "  vague-quantifier: 'significantly', 'very', 'a lot', 'much better' "
    "etc. with no number, percentage, or statistical test anywhere near.\n"
    "  jargon: colloquial or evaluative ML-speak in place of a defined, "
    "measured property — e.g. 'smoothest convergence', 'the model "
    "struggles', 'training is stable', 'degrades gracefully', 'performs "
    "well'. Flag when the claimed property (smoothness, stability, "
    "speed of convergence) is never defined or measured in the text, OR "
    "when a technical term is misused in an informal sense (in the Aalto "
    "Dictionary of ML, 'smooth' means differentiable — 'smooth "
    "convergence' for a low-noise training curve misuses it). A nearby "
    "number (e.g. a hyperparameter value) does NOT count as support for "
    "the claimed property itself.\n"
    "  synonym-switch: within this chunk, two different terms are used "
    "for the SAME concept (e.g. 'data point' vs 'sample', 'label' vs "
    "'target', 'loss' vs 'cost').\n"
    "  unmotivated-section: a chapter/section heading in this chunk whose "
    "following text dives into content without a sentence stating what "
    "the section covers and why.\n"
    "  broken-idiom: a mangled, garbled, or non-standard rendering of an "
    "English idiom or fixed collocation, where the intended standard form "
    "is recognizable — e.g. 'corner cuttings on safety' (for 'cutting "
    "corners on safety'), 'in a daily basis' (for 'on a daily basis'), "
    "'on the contrary to' (for 'in contrast to'), 'make research' (for "
    "'do/conduct research'). Do NOT flag correct idioms merely for being "
    "idiomatic, and do not flag domain terms of art.\n"
    "  informal-register: colloquial or conversational phrasing out of "
    "place in a thesis — e.g. 'a bunch of', 'way better', 'stuff', "
    "'pretty good', 'huge', contractions ('don't', \"it's\"). Do not "
    "double-report phrases already flagged as vague-quantifier or "
    "jargon.\n\n"
    "Be precise and conservative: only report defects a human editor "
    "would definitely mark. Each finding needs an exact short quote "
    "(<=25 words) from the text. Respond with STRICT JSON:\n"
    '{"findings": [{"category": "...", "quote": "...", '
    '"explanation": "..."}]}'
)


def parse_page_range(s: str) -> Optional[Tuple[int, int]]:
    m = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", s or "")
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        return (min(lo, hi), max(lo, hi))
    m = re.match(r"^\s*(\d+)\s*$", s or "")
    if m:
        return (int(m.group(1)), int(m.group(1)))
    raise ValueError(f"Bad --pages value: {s!r}")


def build_chunks(paras: List[Tuple[str, str]],
                 chunk_chars: int) -> List[Tuple[str, str]]:
    """Group (loc, paragraph) pairs into chunks of ~chunk_chars."""
    chunks: List[Tuple[str, str]] = []
    buf: List[str] = []
    loc = ""
    size = 0
    for where, para in paras:
        if not buf:
            loc = where
        buf.append(para)
        size += len(para)
        if size >= chunk_chars:
            chunks.append((loc, "\n\n".join(buf)))
            buf, size = [], 0
    if buf:
        chunks.append((loc, "\n\n".join(buf)))
    return chunks


def main(argv: List[str] = None) -> int:
    ap = argparse.ArgumentParser(
        description="LLM prose linter (ml-theses.org self-editing pass).")
    ap.add_argument("inputs", nargs="+", help="thesis.pdf or .tex files/dirs")
    ap.add_argument("--base-url", default=BASE_URL, help=BASE_URL_HELP)
    ap.add_argument("--api-key", default=None, help=API_KEY_HELP)
    ap.add_argument("--model", default=None,
                    help="Model id (default depends on the gateway).")
    ap.add_argument("--pages", default=None,
                    help="PDF mode: page range, e.g. '9-60'.")
    ap.add_argument("--checks", default=",".join(CHECKS),
                    help=f"Comma-separated subset of: {', '.join(CHECKS)}")
    ap.add_argument("--chunk-chars", type=int, default=9000,
                    help="Approximate characters per LLM call "
                         "(default 9000).")
    ap.add_argument("--concurrency", type=int, default=3,
                    help="Concurrent LLM calls (default 3).")
    ap.add_argument("--limit", type=int, default=None,
                    help="Stop after this many chunks (quick tests).")
    args = ap.parse_args(argv)

    checks = [c.strip() for c in args.checks.split(",") if c.strip()]
    bad = [c for c in checks if c not in CHECKS]
    if bad:
        print(f"ERROR: unknown check(s): {', '.join(bad)}", file=sys.stderr)
        return 2

    lines, mode = load_lines(args.inputs)
    if args.pages and mode == "pdf":
        lo, hi = parse_page_range(args.pages)
        lines = [(w, t) for (w, t) in lines if lo <= int(w[1:]) <= hi]
    lines = [(w, t) for (w, t) in lines if not is_toc_line(t)]

    # Drop the reference list — nothing there to prose-lint.
    body = []
    in_refs = False
    for w, t in lines:
        if re.match(r"^\s*(References|Bibliography)\s*$", t.strip(), re.I):
            in_refs = True
        if not in_refs:
            body.append((w, t))

    paras = [(w, p) for (w, p) in paragraphs_from_lines(body)
             if len(p) > 60]
    chunks = build_chunks(paras, args.chunk_chars)
    if args.limit:
        chunks = chunks[: args.limit]
    if not chunks:
        print("ERROR: no text extracted.", file=sys.stderr)
        return 2

    model = args.model or default_model(args.base_url)
    client = make_client(args.base_url, args.api_key)
    print(f"[info] gateway={args.base_url}\n"
          f"[info] model={model}  chunks={len(chunks)}  "
          f"checks={','.join(checks)}", file=sys.stderr)

    def judge(chunk: Tuple[str, str]):
        where, text = chunk
        user = (f"requested categories: {json.dumps(checks)}\n\n"
                f"text chunk (starts at {where}):\n\"\"\"\n{text}\n\"\"\"")
        raw, usage = client.complete(model=model, system=SYSTEM_PROMPT,
                                     user=user, timeout=300)
        parsed = extract_json(raw) or {}
        finds = parsed.get("findings", [])
        return where, finds if isinstance(finds, list) else [], usage

    rep = Report(f"Prose lint report (LLM self-editing pass, {model})",
                 " ".join(args.inputs))
    total_tokens = 0
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=max(1, args.concurrency)) as ex:
        for where, finds, usage in ex.map(judge, chunks):
            total_tokens += usage.get("total_tokens", 0)
            print(f"[progress] chunk at {where}: {len(finds)} finding(s)",
                  file=sys.stderr)
            for f in finds:
                if not isinstance(f, dict):
                    continue
                cat = str(f.get("category", "")).strip()
                if cat not in checks:
                    continue
                quote = str(f.get("quote", "")).strip()
                expl = str(f.get("explanation", "")).strip()
                rep.add("WARN", cat.upper(), where,
                        f"\"{quote[:100]}\" — {expl[:140]}")

    print(rep.render())
    print(f"\nTotal tokens used: {total_tokens}")
    return rep.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
