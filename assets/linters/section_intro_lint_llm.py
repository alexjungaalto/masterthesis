#!/usr/bin/env python3
"""LLM linter: quality of chapter/section introductions.

ml-theses.org: "Begin each chapter and section with an introductory
paragraph explaining its content and its connection to the rest of the
thesis." Related linters check that an intro EXISTS
(prose_lint_llm.py 'unmotivated-section', thesis_checklist_llm.py
'section-intros'); this linter judges how GOOD it is, for every chapter or
section that has subsections:

  * does the intro tell the reader what each subsection contains
    (coverage of the actual subsection list)?
  * does it explain how the subsections tie together into one argument,
    rather than being a bare list or a discussion of other sections?
  * does it connect the unit to the rest of the thesis?

Verdicts per unit:
  [WARN] MISSING-INTRO   heading is followed (almost) directly by the first
                         subsection heading
  [WARN] WEAK-INTRO      an intro exists but does not summarize the
                         subsections' contents or how they fit together
  [INFO] GOOD-INTRO      covers content and connective thread

The outline is taken from the PDF's embedded table of contents (PyMuPDF);
if none is present, numbered headings are detected heuristically from the
text. One LLM call judges all units.

Gateway: the Aalto AI API by default (see aalto_llm.py; $AALTO_API_KEY,
Aalto network/VPN only); --base-url switches gateways.

Usage:
  python3 section_intro_lint_llm.py thesis.pdf
  python3 section_intro_lint_llm.py thesis.pdf --levels 1,2 --out report.md
Exit status: 0 all good, 1 findings, 2 usage error.
"""

import argparse
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

MAX_INTRO_CHARS = 2600
MAX_SNIPPET_CHARS = 220
SKIP_TITLES_RE = re.compile(
    r"^(contents|abstract|references|bibliography|symbols|abbreviations|"
    r"preface|acknowledg)", re.I)


def load_outline(doc) -> List[Tuple[int, str, int]]:
    """[(level, title, page0)] from embedded TOC, else heading regex."""
    toc = doc.get_toc(simple=True) or []
    outline = [(lvl, title.strip(), page - 1) for lvl, title, page in toc
               if page > 0]
    if outline:
        return outline
    # Fallback: scan text for numbered headings like "2.3 Title".
    outline = []
    head_re = re.compile(r"^(\d+(?:\.\d+)*)\s+([A-Z][^\n]{2,80})$")
    for pno in range(doc.page_count):
        for line in doc[pno].get_text().splitlines():
            m = head_re.match(line.strip())
            if m and not re.search(r"\.{3,}", line):
                level = m.group(1).count(".") + 1
                outline.append((level, f"{m.group(1)} {m.group(2).strip()}",
                                pno))
    return outline


def page_text(doc, cache: Dict[int, str], pno: int) -> str:
    if pno not in cache:
        cache[pno] = doc[pno].get_text() if 0 <= pno < doc.page_count else ""
    return cache[pno]


def find_pos(doc, cache, title: str, page0: int) -> Tuple[int, int]:
    """(page, char-offset) of a heading; falls back to page start."""
    want = re.sub(r"\s+", " ", title).strip().lower()
    # headings may lack/carry their number in the body text
    bare = re.sub(r"^[\d.]+\s*", "", want)
    for pno in (page0, page0 + 1):
        text = page_text(doc, cache, pno)
        norm = re.sub(r"\s+", " ", text).lower()
        for needle in (want, bare):
            if needle and needle in norm:
                # map normalized offset back approximately
                idx = norm.index(needle)
                return pno, idx + len(needle)
    return page0, 0


def slice_between(doc, cache, start: Tuple[int, int],
                  end: Optional[Tuple[int, int]], max_chars: int) -> str:
    """Whitespace-normalized text between two (page, char-offset)
    positions, capped at `max_chars`. If `end` is None, reads to a
    couple of pages past `start` as a fallback bound."""
    (sp, so), out = start, []
    ep, eo = end if end else (min(sp + 2, doc.page_count - 1), None)
    for pno in range(sp, ep + 1):
        text = re.sub(r"\s+", " ", page_text(doc, cache, pno))
        a = so if pno == sp else 0
        b = eo if (end and pno == ep and eo is not None) else len(text)
        out.append(text[a:b])
        if sum(len(x) for x in out) > max_chars * 2:
            break
    return " ".join(out).strip()[:max_chars]


SYSTEM_PROMPT = (
    "You judge the INTRODUCTORY TEXT of chapters/sections of a master's "
    "thesis in machine learning. For each unit you get: its title, the "
    "titles of its subsections (with a short snippet of how each "
    "subsection begins), and the text that stands between the unit's "
    "heading and its first subsection heading (the 'intro').\n\n"
    "Apply this test MECHANICALLY. A subsection counts as covered ONLY "
    "if the intro both (a) indicates its content and (b) frames it as an "
    "UPCOMING PART of this unit, through one of exactly these devices:\n"
    "  1. an explicit reference ('Section X.Y reviews ...'),\n"
    "  2. ordinal/sequential enumeration of the parts ('first ..., "
    "then ..., finally ...') aligned with the subsection order,\n"
    "  3. forward-pointing phrasing naming the part ('the following "
    "subsections describe ...', 'below we review the warm-start "
    "methods and then ...').\n"
    "Content description WITHOUT forward-pointing framing is NOT "
    "coverage, even when its wording closely resembles a subsection "
    "title: stating 'the methods fall into two branches: X and Y' does "
    "not tell a linear reader that the next two subsections treat X and "
    "Y — that alignment exists only in hindsight. Do not infer coverage "
    "from similarity between themes and titles.\n\n"
    "GOOD: every subsection covered in the above sense AND the intro "
    "states how the parts tie together (and ideally how the unit "
    "connects to the rest of the thesis).\n"
    "WEAK: intro text exists but one or more subsections are not "
    "covered, or there is no connective thread. Typical failure, which "
    "MUST be judged WEAK: for a section with subsections 'Solver "
    "warm-start methods' and 'Methods for active constraint set "
    "learning', the intro \"Methods closest to the ones applied in this "
    "thesis neither enumerate the whole parameter space (Section 2.1) "
    "nor replace the solver (Section 2.3). Instead, they learn to make "
    "the optimization solver faster while enforcing feasibility. The "
    "methods are categorized into two distinct branches: 1) supplying a "
    "better starting iterate, and 2) removing redundant constraints.\" "
    "— it positions against OTHER sections and names two branches, but "
    "never says which subsection treats which branch or what the reader "
    "will find in each; the branch-to-subsection mapping exists only in "
    "hindsight.\n\n"
    "MISSING means there is essentially no intro text (a sentence "
    "fragment, or the heading runs directly into the first subsection).\n\n"
    "Judge each unit independently. Respond with STRICT JSON:\n"
    '{"units": [{"id": "...", "verdict": "GOOD|WEAK|MISSING", '
    '"covered_subsections": ["..."], "uncovered_subsections": ["..."], '
    '"has_connective_thread": true, "comment": "...", '
    '"suggestion": "..."}]}\n'
    "'comment' states in one or two sentences what the intro does; "
    "'suggestion' (WEAK/MISSING only) says concretely what to add."
)


def main(argv: List[str] = None) -> int:
    ap = argparse.ArgumentParser(
        description="LLM linter: do chapter/section intros summarize "
                    "their subsections and how they tie together?")
    ap.add_argument("pdf", help="Path to the thesis PDF.")
    ap.add_argument("--base-url", default=BASE_URL, help=BASE_URL_HELP)
    ap.add_argument("--api-key", default=None, help=API_KEY_HELP)
    ap.add_argument("--model", default=None,
                    help="Model id (default depends on the gateway).")
    ap.add_argument("--levels", default="1,2",
                    help="Outline levels to judge, comma-separated "
                         "(default '1,2': chapters and sections).")
    ap.add_argument("--match", default=None,
                    help="Only judge units whose id contains this "
                         "substring (quick checks).")
    ap.add_argument("--concurrency", type=int, default=4,
                    help="Concurrent LLM calls (default 4).")
    ap.add_argument("--out", help="Write report to this file.")
    ap.add_argument("--format", choices=["text", "markdown"],
                    default="text")
    args = ap.parse_args(argv)

    if fitz is None:
        print("ERROR: PyMuPDF required. pip install pymupdf",
              file=sys.stderr)
        return 2
    levels = {int(x) for x in args.levels.split(",")}

    doc = fitz.open(args.pdf)
    outline = load_outline(doc)
    if not outline:
        print("ERROR: no outline (TOC or numbered headings) found.",
              file=sys.stderr)
        return 2

    cache: Dict[int, str] = {}
    units = []
    for i, (lvl, title, page0) in enumerate(outline):
        if lvl not in levels or SKIP_TITLES_RE.match(title):
            continue
        # children = following entries until the next entry at <= lvl
        children = []
        for lvl2, title2, page2 in outline[i + 1:]:
            if lvl2 <= lvl:
                break
            if lvl2 == lvl + 1:
                children.append((title2, page2))
        if not children:
            continue
        start = find_pos(doc, cache, title, page0)
        first_child_pos = find_pos(doc, cache, children[0][0],
                                   children[0][1])
        # intro = text between the unit heading and its first child heading
        end = (first_child_pos[0],
               max(0, first_child_pos[1] - len(children[0][0]) - 20))
        intro = slice_between(doc, cache, start, end, MAX_INTRO_CHARS)
        subs = []
        for j, (ctitle, cpage) in enumerate(children):
            cpos = find_pos(doc, cache, ctitle, cpage)
            snippet = slice_between(doc, cache, cpos, None,
                                    MAX_SNIPPET_CHARS)
            subs.append({"title": ctitle, "starts_with": snippet})
        units.append({"id": title, "level": lvl, "intro": intro,
                      "subsections": subs})

    if args.match:
        units = [u for u in units if args.match.lower() in u["id"].lower()]
    if not units:
        print("ERROR: no chapters/sections with subsections at levels "
              f"{sorted(levels)}.", file=sys.stderr)
        return 2

    # This judgement is subtler than most linters': the mini tier lets
    # near-miss intros pass, so default to the full GPT-5 model on the
    # Aalto AI API.
    model = args.model or ("gpt-5-2025-08-07"
                           if is_responses_api(args.base_url)
                           else default_model(args.base_url))
    client = make_client(args.base_url, args.api_key)
    print(f"[info] gateway={args.base_url}\n[info] model={model}  "
          f"units={len(units)}", file=sys.stderr)

    import concurrent.futures

    def judge(unit):
        user = ("unit to judge (return a one-element \"units\" array):\n"
                + json.dumps([unit], ensure_ascii=False, indent=1))
        raw, usage = client.complete(model=model, system=SYSTEM_PROMPT,
                                     user=user, timeout=300,
                                     max_tokens=3000)
        parsed = extract_json(raw) or {}
        arr = parsed.get("units", [])
        return (arr[0] if isinstance(arr, list) and arr
                and isinstance(arr[0], dict) else {}), usage

    results = {}
    total_tokens = 0
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=max(1, args.concurrency)) as ex:
        for unit, (res, u_usage) in zip(units, ex.map(judge, units)):
            results[unit["id"]] = res
            total_tokens += u_usage.get("total_tokens", 0)
            print(f"[progress] {unit['id']}: "
                  f"{res.get('verdict', '?')}", file=sys.stderr)
    usage = {"total_tokens": total_tokens}

    md = args.format == "markdown"
    out = []
    header = f"Section-introduction lint report (LLM, {model})"
    out += [f"# {header}", "", f"File: `{args.pdf}`", ""] if md else \
           [f"== {header}", f"File: {args.pdf}", ""]
    n_bad = 0
    for u in units:
        r = results.get(u["id"], {})
        verdict = str(r.get("verdict", "WEAK")).upper()
        comment = str(r.get("comment", "no answer from model")).strip()
        suggestion = str(r.get("suggestion", "")).strip()
        uncovered = [str(x) for x in r.get("uncovered_subsections", [])]
        tag = {"GOOD": ("INFO", "GOOD-INTRO"),
               "MISSING": ("WARN", "MISSING-INTRO")}.get(
                   verdict, ("WARN", "WEAK-INTRO"))
        if tag[0] == "WARN":
            n_bad += 1
        if md:
            out.append(f"## {u['id']} — {verdict}")
            out.append(comment)
            if uncovered:
                out.append(f"- **Subsections not reflected:** "
                           f"{', '.join(uncovered)}")
            if suggestion:
                out.append(f"- **Fix:** {suggestion}")
            out.append("")
        else:
            out.append(f"[{tag[0]}] {tag[1]:<14} {u['id']}")
            out.append(f"        {comment}")
            if uncovered:
                out.append(f"        not reflected: {', '.join(uncovered)}")
            if suggestion:
                out.append(f"        fix: {suggestion}")
            out.append("")
    out.append(f"{len(units)} unit(s) judged: {len(units) - n_bad} good, "
               f"{n_bad} weak/missing.  "
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
