#!/usr/bin/env python3
"""LLM linter: quality of every figure/table caption (the accurate cousin
of the word-count check in caption_lint.py).

Judges each caption individually against Rule 4 ("Captions Are Not
Optional") of Rougier, Droettboom & Bourne, "Ten Simple Rules for Better
Figures", PLOS Computational Biology 10(9):e1003833 (2014),
https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1003833
— the caption guideline the ml-theses.org guide links: the caption
explains how to read the figure, provides precision the graphic cannot
(key numeric values), and points out what the reader should notice.

Per caption, four criteria:

  states-what-shown   says WHAT the figure/table shows (data, setting,
                      method), not just names a topic
  defines-quantities  symbols, abbreviations, and plotted quantities that
                      appear in the caption are identified (axes/units
                      where clearly applicable)
  self-contained      readable without the body text; a reader skimming
                      figures can follow it, ideally told what to notice
  sentence-form       proper written form: starts with a capital, proper
                      nouns capitalized, no telegram style or spelling
                      slips ("wibson protocol visualized" fails); a mere
                      missing final period is tolerated

Verdict GOOD or WEAK per caption; each WEAK caption is one WARN
WEAK-CAPTION with the violated criteria and a suggested rewrite.
Findings are heuristic LLM judgements — review them.

Gateway: the Aalto AI API by default (see aalto_llm.py; $AALTO_API_KEY,
Aalto network/VPN only); --base-url switches gateways. Uses the full
GPT-5 model by default (the mini tier waves near-miss captions through).

Usage:
  python3 caption_lint_llm.py thesis.pdf
  python3 caption_lint_llm.py main.tex chapters/
  python3 caption_lint_llm.py thesis.pdf --match 4      # Figure/Table 4
Exit status: 0 clean, 1 findings, 2 usage error.
"""

import argparse
import concurrent.futures
import json
import re
import sys
from typing import List, Optional, Tuple

from aalto_llm import (API_KEY_HELP, BASE_URL, BASE_URL_HELP, default_model,
                       extract_json, is_responses_api, make_client)
from lintutil import Report, is_toc_line, load_lines, tex_files

CRITERIA = ["states-what-shown", "defines-quantities", "self-contained",
            "sentence-form"]

Caption = Tuple[str, str, str]  # (location, label e.g. "Figure 4", text)

PDF_CAPTION_RE = re.compile(
    r"^(Figure|Fig\.|Table|Tab\.|Algorithm|Listing)\s+(\d+(?:\.\d+)*)"
    r"\s*[:.]\s*(.*)")


def pdf_captions(path: str) -> List[Caption]:
    """Extract (location, label, text) captions from a PDF's text.

    Matches lines starting 'Figure/Table/... N:' and rejoins up to five
    following non-blank lines so a wrapped caption is reassembled.
    """
    lines, _ = load_lines([path])
    caps: List[Caption] = []
    i = 0
    while i < len(lines):
        where, t = lines[i]
        s = t.strip()
        m = PDF_CAPTION_RE.match(s)
        if m and not is_toc_line(s):
            kind, num, rest = m.groups()
            j = i + 1
            parts = [rest]
            while j < len(lines) and lines[j][1].strip() and \
                    not PDF_CAPTION_RE.match(lines[j][1].strip()) and \
                    j - i < 6:
                parts.append(lines[j][1].strip())
                j += 1
            caps.append((where, f"{kind.rstrip('.')} {num}",
                         " ".join(parts).strip()))
            i = j
            continue
        i += 1
    return caps


def tex_captions(paths: List[str]) -> List[Caption]:
    """Extract (file:line, env, caption text) from LaTeX sources.

    Reads each figure/table environment, brace-matches its `\\caption`
    argument, and normalizes whitespace. Environments without a caption
    are skipped here (caption_lint.py reports those as NO-CAPTION).
    """
    caps: List[Caption] = []
    for f in tex_files(paths):
        text = f.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(
                r"\\begin\{(figure|table)\*?\}(.*?)\\end\{\1\*?\}",
                text, re.S):
            env, body = m.group(1), m.group(2)
            lineno = text[:m.start()].count("\n") + 1
            cm = re.search(r"\\caption(?:\[[^\]]*\])?\{", body)
            if not cm:        # caption_lint.py reports NO-CAPTION
                continue
            depth, k = 1, cm.end()
            while k < len(body) and depth:
                if body[k] == "{" and body[k - 1] != "\\":
                    depth += 1
                elif body[k] == "}" and body[k - 1] != "\\":
                    depth -= 1
                k += 1
            caption = re.sub(r"\s+", " ", body[cm.end():k - 1]).strip()
            caps.append((f"{f}:{lineno}", env, caption))
    return caps


SYSTEM_PROMPT = (
    "You are an experienced supervisor of master's theses in machine "
    "learning, judging figure and table captions against Rule 4 "
    "('Captions Are Not Optional') of Rougier, Droettboom & Bourne, 'Ten "
    "Simple Rules for Better Figures' (PLOS Computational Biology, 2014): "
    "the caption explains how to read the figure, provides precision that "
    "cannot be graphically represented (key numeric values), and "
    "explicitly points out what the reader should notice.\n\n"
    "You are given a numbered list of captions (text only — you cannot "
    "see the figures). Judge EACH caption on four criteria:\n"
    "  states-what-shown: it says WHAT is shown — the data, setting, or "
    "method — not merely a topic label ('Results', 'System overview', "
    "'wibson protocol visualized' all fail).\n"
    "  defines-quantities: symbols, abbreviations, and quantities that "
    "appear in the caption are identified; where the caption clearly "
    "describes a plot, the plotted quantities/axes are named. Judge only "
    "from the caption text; do not demand definitions of things the "
    "caption does not mention or common knowledge (e.g. 'CNN').\n"
    "  self-contained: a reader skimming only the figures can follow it "
    "without the body text; ideally it says what to notice or gives the "
    "key value. A bare pointer like 'see Section 4' fails.\n"
    "  sentence-form: proper written form — starts with a capital "
    "letter, proper nouns capitalized ('wibson' must be 'Wibson'), no "
    "telegram style, no grammatical or spelling errors. A correctly "
    "capitalized noun-phrase caption that merely lacks a final period is "
    "NOT a sentence-form violation — fragment captions are an accepted "
    "convention.\n\n"
    "Verdict per caption: GOOD only if all four criteria hold; otherwise "
    "WEAK with the violated criteria listed and a one-sentence suggested "
    "rewrite (keep the author's technical content; invent nothing beyond "
    "generic placeholders). Be conservative: captions of 2-3 full "
    "sentences that state content and quantities are GOOD even if not "
    "perfect. Respond with STRICT JSON:\n"
    '{"captions": [{"index": 1, "verdict": "GOOD|WEAK", '
    '"violated": ["..."], "rewrite": "..."}]}'
)


def build_batches(caps: List[Caption], per_batch: int
                  ) -> List[List[Tuple[int, Caption]]]:
    """Split captions into fixed-size batches, each item paired with its
    global index so findings map back to the right caption."""
    numbered = list(enumerate(caps))
    return [numbered[i:i + per_batch]
            for i in range(0, len(numbered), per_batch)]


def main(argv: List[str] = None) -> int:
    ap = argparse.ArgumentParser(
        description="LLM caption-quality linter (PLOS Ten Simple Rules, "
                    "Rule 4).")
    ap.add_argument("inputs", nargs="+", help="thesis.pdf or .tex files/dirs")
    ap.add_argument("--base-url", default=BASE_URL, help=BASE_URL_HELP)
    ap.add_argument("--api-key", default=None, help=API_KEY_HELP)
    ap.add_argument("--model", default=None,
                    help="Model id (default: full GPT-5 on the Aalto AI "
                         "API, else the gateway default).")
    ap.add_argument("--match", default=None,
                    help="Only judge captions whose label contains this "
                         "string (e.g. '4' or 'Table').")
    ap.add_argument("--per-batch", type=int, default=15,
                    help="Captions per LLM call (default 15).")
    ap.add_argument("--concurrency", type=int, default=3,
                    help="Concurrent LLM calls (default 3).")
    args = ap.parse_args(argv)

    pdf_mode = (len(args.inputs) == 1
                and args.inputs[0].lower().endswith(".pdf"))
    caps = (pdf_captions(args.inputs[0]) if pdf_mode
            else tex_captions(args.inputs))
    if args.match:
        caps = [c for c in caps if args.match in c[1]]
    if not caps:
        print("ERROR: no captions found.", file=sys.stderr)
        return 2

    model = args.model or ("gpt-5-2025-08-07"
                           if is_responses_api(args.base_url)
                           else default_model(args.base_url))
    client = make_client(args.base_url, args.api_key)
    batches = build_batches(caps, max(1, args.per_batch))
    print(f"[info] gateway={args.base_url}\n"
          f"[info] model={model}  captions={len(caps)}  "
          f"batches={len(batches)}", file=sys.stderr)

    def judge(batch: List[Tuple[int, Caption]]):
        listing = "\n".join(
            f"{i + 1}. [{label}] \"{text}\""
            for i, (_, (where, label, text)) in enumerate(batch))
        raw, usage = client.complete(model=model, system=SYSTEM_PROMPT,
                                     user=listing, timeout=300)
        parsed = extract_json(raw) or {}
        items = parsed.get("captions", [])
        return batch, items if isinstance(items, list) else [], usage

    rep = Report(f"Caption quality report (LLM, Rule 4; {model})",
                 " ".join(args.inputs),
                 about="LLM check: does each figure/table caption state what "
                       "is shown, define its symbols, and stand alone for a "
                       "figure-skimming reader?")
    total_tokens = 0
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=max(1, args.concurrency)) as ex:
        for batch, items, usage in ex.map(judge, batches):
            total_tokens += usage.get("total_tokens", 0)
            print(f"[progress] batch of {len(batch)}: "
                  f"{sum(1 for it in items if isinstance(it, dict) and it.get('verdict') == 'WEAK')} weak",
                  file=sys.stderr)
            for it in items:
                if not isinstance(it, dict):
                    continue
                try:
                    _, (where, label, text) = batch[int(it["index"]) - 1]
                except (KeyError, ValueError, IndexError):
                    continue
                if str(it.get("verdict", "")).upper() != "WEAK":
                    continue
                violated = [v for v in it.get("violated", [])
                            if v in CRITERIA] or ["(unspecified)"]
                rewrite = str(it.get("rewrite", "")).strip()
                rep.add("WARN", "WEAK-CAPTION", where,
                        f"{label}: \"{text[:60]}\" violates "
                        f"{', '.join(violated)} — suggest: "
                        f"\"{rewrite[:160]}\"")

    print(rep.render())
    print(f"\n{len(caps)} caption(s) judged. Total tokens used: "
          f"{total_tokens}")
    return rep.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
