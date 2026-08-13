#!/usr/bin/env python3
"""LLM linter: related-work faithfulness.

Identifies the (up to three) most-related prior works for a thesis/paper
draft, establishes how the draft ACTUALLY relates to each from that work's
real abstract, and checks whether the draft's Related Work section presents
that relation faithfully.

Three stages:
  1. DISCOVER (LLM, draft only -> Aalto endpoint): pick the <=3 cited works
     the draft treats as most related, and extract, per work, how the draft
     positions it (its stated relation) and the delta/novelty it claims over
     that work.
  2. GROUND-TRUTH (network, TITLES ONLY): fetch each work's real abstract
     from OpenAlex by title. Only the reference title string leaves
     the machine -- the same class of query the bibliography linter makes.
  3. VERIFY (LLM -> Aalto endpoint): compare the draft's stated relation to
     what the abstract shows and emit a per-work verdict.

Findings:
  [WARN] RELATION-MISSTATED   the stated relation contradicts the abstract
  [WARN] NOVELTY-OVERSTATED   the draft claims a delta the abstract does not
                              support (that work already does it)
  [WARN] RELATED-WORK-OMITTED (--discover external) a clearly related work is
                              not cited/discussed
  [INFO] SHALLOW-POSITIONING  cited, but the relation is not characterised
  [INFO] UNVERIFIABLE         no abstract could be fetched to check against
  [INFO] FAITHFUL             stated relation matches the abstract

Data handling: manuscript text goes ONLY to the configured LLM endpoint
(the Aalto AI API by default; see aalto_llm.py). Stage 2 sends only reference
TITLES to OpenAlex. '--discover external' additionally queries
OpenAlex with the DRAFT's own title (still title-only) to surface
related work the draft may have missed; it does not send the abstract or body.

Usage:
  python3 related_work_faithfulness_llm.py paper.pdf
  python3 related_work_faithfulness_llm.py paper.pdf --discover external
  python3 related_work_faithfulness_llm.py paper.pdf --max-related 3
Exit status: 0 clean, 1 findings (any WARN), 2 usage error.
"""

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import List

from aalto_llm import (API_KEY_HELP, BASE_URL, BASE_URL_HELP, default_model,
                       extract_json, make_client)
from lintutil import load_lines

OPENALEX = ("https://api.openalex.org/works?search={q}&per_page={n}"
            "&mailto=noreply@aalto.fi")
UA = {"User-Agent": "ml-theses-linter/1.0 (mailto:noreply@aalto.fi)"}

DISCOVER_PROMPT = (
    "You are an experienced reviewer for a machine-learning conference. You "
    "are given the extracted text of a paper/thesis draft (page markers "
    "'[[page N]]' included). Identify the prior works this draft treats as "
    "MOST related to its own contribution -- the ones a reviewer would check "
    "the positioning against most carefully.\n\n"
    "Return the paper's own title, a one-line summary of its contribution, "
    "and up to N most-related CITED works. For each related work give:\n"
    "  title:           the cited work's title as best you can recover it\n"
    "  ref:             the citation marker or first author + year\n"
    "  why_related:     one line on why it is among the most related\n"
    "  stated_relation: how THIS draft positions the work (quote or close "
    "paraphrase from the related-work/intro text), or '' if the work is "
    "cited but its relation to this draft is never characterised\n"
    "  claimed_delta:   what the draft claims it does differently/better "
    "than this work, or '' if none is claimed\n"
    "  page:            page number where the draft discusses it\n\n"
    "Respond with STRICT JSON:\n"
    '{"paper_title": "...", "contribution": "...", "related": '
    '[{"title": "...", "ref": "...", "why_related": "...", '
    '"stated_relation": "...", "claimed_delta": "...", "page": "N"}]}'
)

VERIFY_PROMPT = (
    "You are an experienced reviewer checking whether a draft's Related Work "
    "section faithfully represents the prior works it positions itself "
    "against. You are given the draft's contribution and, for each related "
    "work, (a) how the draft positions it, (b) the delta the draft claims "
    "over it, and (c) the work's REAL abstract. For each work decide a "
    "verdict:\n"
    "  FAITHFUL            stated relation is consistent with the abstract\n"
    "  RELATION-MISSTATED  stated relation contradicts the abstract "
    "(e.g. mischaracterises the work's problem, method, or findings)\n"
    "  NOVELTY-OVERSTATED  the draft claims a delta the abstract does not "
    "support -- the work already does what the draft claims as new\n"
    "  SHALLOW-POSITIONING the work is cited but its relation to the draft "
    "is not actually characterised (stated_relation empty/vacuous)\n"
    "  UNVERIFIABLE        the provided abstract is empty or clearly not the "
    "right paper, so faithfulness cannot be judged\n\n"
    "Base the verdict ONLY on the abstract provided; do not use outside "
    "knowledge to fill gaps. Respond with STRICT JSON:\n"
    '{"assessments": [{"title": "...", "verdict": "...", '
    '"true_relation": "one line on what the abstract actually shows", '
    '"evidence": "<=40-word justification", "fix": "for non-FAITHFUL: one '
    'concrete sentence"}]}'
)

OMIT_PROMPT = (
    "You are a reviewer checking a draft for missed related work. You are "
    "given the draft's contribution, the titles it already cites among its "
    "most-related works, and candidate papers (title + abstract) found by a "
    "literature search. For each candidate decide whether it is clearly "
    "related to the draft's contribution AND not already among the cited "
    "works, i.e. a genuine omission a reviewer would flag. Ignore candidates "
    "that are only loosely related or are effectively the same as a cited "
    "work. Respond with STRICT JSON:\n"
    '{"omissions": [{"title": "...", "why": "one line on why it should be '
    'discussed"}]}'
)


def _get(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def _reconstruct_abstract(inv: dict) -> str:
    """Rebuild abstract text from OpenAlex's inverted index {word: [pos,...]}."""
    if not inv:
        return ""
    pos = {}
    for word, idxs in inv.items():
        for i in idxs:
            pos[i] = word
    return " ".join(pos[i] for i in sorted(pos))


def lit_search(title: str, n: int = 1) -> List[dict]:
    """OpenAlex title search. Sends only the title string; returns records
    with a reconstructed abstract. OpenAlex's keyless polite pool is far more
    rate-tolerant than Semantic Scholar's search endpoint."""
    if not title.strip():
        return []
    try:
        url = OPENALEX.format(q=urllib.parse.quote(title), n=n)
        data = json.loads(_get(url))
    except (urllib.error.URLError, json.JSONDecodeError, ValueError):
        return []
    out = []
    for w in data.get("results", []) or []:
        out.append({
            "title": (w.get("title") or "").strip(),
            "abstract": _reconstruct_abstract(
                w.get("abstract_inverted_index")).strip(),
            "year": w.get("publication_year"),
        })
    return out


def _rebuild_text(pdf: str, max_chars: int):
    lines, mode = load_lines([pdf])
    if mode != "pdf":
        return None, False
    chunks, cur = [], None
    for where, t in lines:
        if where != cur:
            cur = where
            chunks.append(f"\n[[page {where[1:]}]]\n")
        chunks.append(t + "\n")
    text = "".join(chunks)
    truncated = len(text) > max_chars
    return (text[:max_chars] if truncated else text), truncated


def main(argv: List[str] = None) -> int:
    ap = argparse.ArgumentParser(
        description="LLM linter: related-work faithfulness (discover most-"
                    "related works, verify the draft represents them faithfully).")
    ap.add_argument("pdf", help="Path to the paper/thesis PDF.")
    ap.add_argument("--profile", choices=["thesis", "paper"], default="paper",
                    help="Accepted for suite consistency; behaviour is the "
                         "same for both.")
    ap.add_argument("--max-related", type=int, default=3,
                    help="Max most-related works to check (default 3).")
    ap.add_argument("--discover", choices=["internal", "external"],
                    default="internal",
                    help="internal: check only the draft's own cited works "
                         "(default; sends only cited titles to Semantic "
                         "Scholar). external: additionally query Semantic "
                         "Scholar with the draft's own title to flag missed "
                         "related work (still title-only).")
    ap.add_argument("--base-url", default=BASE_URL, help=BASE_URL_HELP)
    ap.add_argument("--api-key", default=None, help=API_KEY_HELP)
    ap.add_argument("--model", default=None,
                    help="Model id (default depends on the gateway).")
    ap.add_argument("--max-chars", type=int, default=400_000,
                    help="Truncate extracted text beyond this (default 400000).")
    ap.add_argument("--out", help="Write report to this file.")
    args = ap.parse_args(argv)

    text, truncated = _rebuild_text(args.pdf, args.max_chars)
    if text is None:
        print("ERROR: this linter takes a compiled PDF.", file=sys.stderr)
        return 2

    model = args.model or default_model(args.base_url)
    client = make_client(args.base_url, args.api_key)
    print(f"[info] gateway={args.base_url}\n[info] model={model}  "
          f"discover={args.discover}  chars={len(text)}", file=sys.stderr)

    # --- Stage 1: discover most-related cited works (manuscript -> LLM) ---
    raw, usage1 = client.complete(
        model=model, system=DISCOVER_PROMPT,
        user=(f"N = {args.max_related}\n\ndraft text"
              f"{' (TRUNCATED)' if truncated else ''}:\n\"\"\"\n{text}\n\"\"\""),
        timeout=600, max_tokens=6000)
    disc = extract_json(raw) or {}
    related = [r for r in disc.get("related", []) if isinstance(r, dict)][
        : args.max_related]
    paper_title = str(disc.get("paper_title", "")).strip()
    contribution = str(disc.get("contribution", "")).strip()

    out = [f"== Related-work faithfulness report (LLM, {model}; "
           f"discover={args.discover})", f"File: {args.pdf}", "",
           f"Draft: {paper_title or '(title not recovered)'}",
           f"Contribution: {contribution or '(not recovered)'}", ""]
    tok = usage1.get("total_tokens", 0)
    n_warn = 0

    if not related:
        out.append("[INFO] NO-RELATED   the model identified no most-related "
                   "cited works to check (unusual — inspect the draft's "
                   "related-work section manually).")
        print("\n".join(out))
        return 0

    # --- Stage 2: fetch real abstracts by title (TITLES ONLY -> network) ---
    for r in related:
        hits = lit_search(r.get("title", ""), n=1)
        ab_hit = hits[0] if hits else {}
        r["_abstract"] = (ab_hit.get("abstract") or "").strip()
        r["_fetched_title"] = (abd := ab_hit.get("title")) and abd.strip() or ""

    # --- Stage 3: verify faithfulness (relations + abstracts -> LLM) ---
    payload = [{
        "title": r.get("title", ""),
        "stated_relation": r.get("stated_relation", ""),
        "claimed_delta": r.get("claimed_delta", ""),
        "abstract": r.get("_abstract", "") or "(no abstract retrieved)",
    } for r in related]
    raw2, usage2 = client.complete(
        model=model, system=VERIFY_PROMPT,
        user=(f"draft contribution: {contribution}\n\nrelated works:\n"
              f"{json.dumps(payload, indent=1)}"),
        timeout=600, max_tokens=6000)
    ver = extract_json(raw2) or {}
    assess = {a.get("title"): a for a in ver.get("assessments", [])
              if isinstance(a, dict)}
    tok += usage2.get("total_tokens", 0)

    SEV = {"RELATION-MISSTATED": "WARN", "NOVELTY-OVERSTATED": "WARN",
           "SHALLOW-POSITIONING": "INFO", "UNVERIFIABLE": "INFO",
           "FAITHFUL": "INFO"}
    for r in related:
        a = assess.get(r.get("title"), {})
        verdict = str(a.get("verdict", "UNVERIFIABLE")).upper()
        sev = SEV.get(verdict, "INFO")
        if sev == "WARN":
            n_warn += 1
        page = r.get("page", "-") or "-"
        loc = f"p{page}" if str(page).strip("-").isdigit() else "-"
        title = (r.get("title") or "?")[:70]
        out.append(f"[{sev}] {verdict:<19} {loc:<6} {title}")
        out.append(f"        related: {r.get('why_related', '').strip()}")
        if r.get("stated_relation"):
            out.append(f"        draft says: {r['stated_relation'].strip()}")
        if a.get("true_relation"):
            out.append(f"        abstract shows: {a['true_relation'].strip()}")
        if not r.get("_abstract"):
            out.append("        note: no abstract retrieved for this title — "
                       "verdict is unverified against the real work.")
        if a.get("evidence"):
            out.append(f"        {a['evidence'].strip()}")
        if verdict != "FAITHFUL" and a.get("fix"):
            out.append(f"        fix: {a['fix'].strip()}")
        out.append("")

    # --- Optional: external discovery of omitted related work ---
    if args.discover == "external":
        cands = lit_search(paper_title, n=6)
        cited_titles = " ".join((r.get("title") or "").lower()
                                for r in related)
        fresh = [{"title": c.get("title", ""),
                  "abstract": (c.get("abstract") or "")[:1200]}
                 for c in cands
                 if c.get("title")
                 and c.get("title", "").lower() not in cited_titles]
        if fresh:
            raw3, usage3 = client.complete(
                model=model, system=OMIT_PROMPT,
                user=(f"draft contribution: {contribution}\n\ncited most-"
                      f"related titles: {cited_titles}\n\ncandidates:\n"
                      f"{json.dumps(fresh, indent=1)}"),
                timeout=600, max_tokens=3000)
            tok += usage3.get("total_tokens", 0)
            omit = (extract_json(raw3) or {}).get("omissions", [])
            for o in omit:
                if isinstance(o, dict) and o.get("title"):
                    n_warn += 1
                    out.append(f"[WARN] RELATED-WORK-OMITTED  -     "
                               f"{o['title'][:70]}")
                    out.append(f"        {str(o.get('why', '')).strip()}")
                    out.append("")

    n_checked = len(related)
    out.append(f"{n_checked} related work(s) checked; {n_warn} warning(s).  "
               f"(tokens: {tok})")
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
