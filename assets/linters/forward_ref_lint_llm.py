#!/usr/bin/env python3
"""
forward_ref_lint_llm.py
=======================

LLM-as-judge version of the forward-reference linter.

It screens a thesis PDF paragraph by paragraph and flags every paragraph
that *uses* a technical concept which is only *introduced / defined* in a
LATER paragraph.  Unlike the regex-based `forward_ref_lint.py`, the
detection of (a) concept introductions and (b) forward references is done
by a language model, by default the Aalto AI API (Azure OpenAI gateway).

Approach (sequential, stateful)
-------------------------------
A running set `introduced` of concepts already introduced earlier in the
document is maintained.  For each paragraph, in document order, the LLM is
asked:

  * (A) Which technical terms / concepts / acronyms USED in this paragraph
        have NOT yet been introduced earlier AND are NOT being introduced
        here for the first time?  -> these are forward references.
  * (B) Which concepts does this paragraph INTRODUCE / DEFINE for the
        first time?  -> add them to `introduced`.

The LLM responds in JSON, which is parsed and used to update state and
record findings.  Results are cached per paragraph to disk so re-runs /
resumes are cheap.

LLM gateway
-----------
Default: the Aalto AI API (Azure OpenAI gateway; Responses API,
Ocp-Apim-Subscription-Key auth from $AALTO_API_KEY, GPT-5-family models
with dated IDs; Aalto network/VPN only). Alternatives via --base-url:
the self-hosted Aalto LLM Gateway (OpenAI-style chat completions, Bearer
$AALTO_LLM_KEY, Qwen models; models scale to zero and answer 503 while
spinning up) and any OpenAI-style endpoint such as OpenRouter
($OPENROUTER_API_KEY). Protocol and key are picked from the URL.

Usage
-----
    export AALTO_API_KEY=...            # Aalto AI API (default gateway)
    python3 forward_ref_lint_llm.py thesis.pdf
    python3 forward_ref_lint_llm.py thesis.pdf --model gpt-5-2025-08-07
    python3 forward_ref_lint_llm.py thesis.pdf --pages 1-120 --out report.md
    python3 forward_ref_lint_llm.py thesis.pdf --batch 4 --concurrency 4
    python3 forward_ref_lint_llm.py thesis.pdf --resume            # use cache
    python3 forward_ref_lint_llm.py thesis.pdf --list-concepts
    # OpenRouter instead of the Aalto AI API:
    python3 forward_ref_lint_llm.py thesis.pdf \
        --base-url https://openrouter.ai/api/v1 --model google/gemini-2.5-flash

Requirements
------------
    pip install pymupdf        (no LLM SDK needed; stdlib urllib is used)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import concurrent.futures
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Set, Tuple

try:
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover
    fitz = None


from aalto_llm import (LLMClient, make_client, default_model,
                       extract_json, BASE_URL, AALTO_AZURE_URL,
                       LLMGW_BASE_URL, BASE_URL_HELP, API_KEY_HELP)

CACHE_SUFFIX = ".fwdref_cache.jsonl"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class Paragraph:
    index: int
    page: int
    text: str
    is_caption: bool = False
    is_reference: bool = False


@dataclass
class ParaResult:
    """LLM judgement for one paragraph."""
    index: int
    page: int
    introduced: List[str] = field(default_factory=list)
    forward_refs: List[str] = field(default_factory=list)
    raw: str = ""          # raw model response (for debugging)
    model: str = ""
    usage: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# PDF extraction (reused from the regex version, simplified)
# ---------------------------------------------------------------------------
def _looks_like_caption(text: str) -> bool:
    return bool(re.match(r"^(Figure|Fig\.|Table|Tab\.|Algorithm|Listing)\s+\d",
                         text.lstrip()))


def _looks_like_reference(text: str) -> bool:
    return bool(re.match(r"^\[\s*\d+\s*\]", text.strip()))


def _is_boilerplate(text: str) -> bool:
    """Skip cover/TOC/acknowledgement-ish pages' short lines."""
    t = text.strip()
    if not t:
        return True
    # Pure page number or very short token lines.
    if len(t) < 25 and not re.search(r"[\.]{2,}", t):
        # but keep TOC entries? They are forward refs by nature; skip them.
        if re.search(r"\.{2,}\s*\d+\s*$", t):
            return True
    return False


def extract_paragraphs(path: str, page_range: Optional[Tuple[int, int]]) -> List[Paragraph]:
    if fitz is None:
        raise RuntimeError("PyMuPDF (fitz) is required for extraction. pip install pymupdf")
    doc = fitz.open(path)
    paragraphs: List[Paragraph] = []
    for pno in range(len(doc)):
        page_no = pno + 1
        if page_range and not (page_range[0] <= page_no <= page_range[1]):
            continue
        page = doc[pno]
        blocks = page.get_text("dict")["blocks"]
        for b in blocks:
            if b.get("type", 0) != 0:
                continue
            lines = b.get("lines", [])
            if not lines:
                continue
            text_parts = []
            for ln in lines:
                buf = []
                for sp in ln.get("spans", []):
                    buf.append(sp.get("text", ""))
                text_parts.append("".join(buf).rstrip())
            text = "\n".join(text_parts).strip()
            if not text or _is_boilerplate(text):
                continue
            paragraphs.append(Paragraph(
                index=len(paragraphs),
                page=page_no,
                text=text,
                is_caption=_looks_like_caption(text),
                is_reference=_looks_like_reference(text),
            ))
    doc.close()
    return paragraphs


SYSTEM_PROMPT = (
    "You are a meticulous copy-editor reviewing a master's thesis paragraph "
    "by paragraph to detect FORWARD REFERENCES: a concept, technical term, "
    "method, metric, or acronym that is USED in a paragraph but is only "
    "INTRODUCED / DEFINED later in the document, so a first-time reader "
    "would not yet know what it means.\n\n"
    "You are given:\n"
    "  - `introduced`: concepts that have ALREADY been introduced/defined in "
    "earlier paragraphs (a JSON list of strings).\n"
    "  - `paragraph`: the current paragraph text.\n"
    "  - `page`, `index`: metadata.\n\n"
    "Decide two things:\n"
    "  1. `forward_refs`: terms USED in this paragraph that are NOT in "
    "`introduced` AND are NOT being introduced/defined in this very paragraph. "
    "Only include genuine technical concepts / named methods / metrics / "
    "acronyms that a reader would need explained. Do NOT include common "
    "English words, generic words (data, model, result, system, method, "
    "value, number, network, layer, input, output, training, test), or "
    "citation/figure/table references. If none, return [].\n"
    "  2. `introduced_here`: concepts that this paragraph INTRODUCES or "
    "DEFINES for the first time (definition, 'we call ...', 'we define ...', "
    "'X is ...', inline acronym 'Long Name (LN)', etc.). Add them here even "
    "if they were already listed under forward_refs (a paragraph can both "
    "introduce a term and forward-reference others). If none, return [].\n\n"
    "Respond with STRICT JSON only, no prose, of the form:\n"
    '{"forward_refs": ["...", "..."], "introduced_here": ["...", "..."]}'
)


def _build_user_prompt(introduced: List[str], para: Paragraph) -> str:
    intro_json = json.dumps(introduced, ensure_ascii=False)
    return (
        f"index: {para.index}\n"
        f"page: {para.page}\n"
        f"introduced: {intro_json}\n\n"
        f"paragraph:\n\"\"\"\n{para.text}\n\"\"\"\n"
    )


_extract_json = extract_json


def judge_paragraph(
    client: LLMClient,
    model: str,
    introduced: List[str],
    para: Paragraph,
    timeout: float = 60.0,
    max_retries: int = 4,
) -> ParaResult:
    user = _build_user_prompt(introduced, para)
    last_err: Optional[Exception] = None
    backoff = 1.5
    for attempt in range(max_retries):
        try:
            raw, usage = client.complete(
                model=model,
                system=SYSTEM_PROMPT,
                user=user,
                timeout=timeout,
            )
            parsed = _extract_json(raw) or {}
            return ParaResult(
                index=para.index,
                page=para.page,
                introduced=[str(x) for x in parsed.get("introduced_here", [])],
                forward_refs=[str(x) for x in parsed.get("forward_refs", [])],
                raw=raw,
                model=model,
                usage=usage,
            )
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(backoff)
            backoff *= 2
    raise RuntimeError(f"LLM call failed for paragraph {para.index} after {max_retries} attempts: {last_err}")


# ---------------------------------------------------------------------------
# Batched judging (optional)
# ---------------------------------------------------------------------------
BATCH_SYSTEM_PROMPT = (
    "You are a meticulous copy-editor reviewing a master's thesis paragraph "
    "by paragraph to detect FORWARD REFERENCES: a concept, technical term, "
    "method, metric, or acronym that is USED in a paragraph but is only "
    "INTRODUCED / DEFINED later in the document, so a first-time reader "
    "would not yet know what it means.\n\n"
    "You are given:\n"
    "  - `introduced`: concepts that have ALREADY been introduced/defined in "
    "earlier parts of the document (a JSON list of strings). This is the "
    "state of knowledge at the START of this batch.\n"
    "  - `paragraphs`: an ORDERED list of paragraphs to judge, each with its "
    "`index`, `page`, and `text`.\n\n"
    "Process the paragraphs STRICTLY IN THE GIVEN ORDER. Within this batch, "
    "a concept introduced by an earlier paragraph is considered already known "
    "for all subsequent paragraphs in the SAME batch, so it is NOT a forward "
    "reference for them.\n\n"
    "For EACH paragraph decide:\n"
    "  1. `forward_refs`: technical terms / concepts / named methods / metrics / "
    "acronyms USED in this paragraph that are NOT in `introduced` (the initial "
    "set) AND NOT introduced by any earlier paragraph within this same batch "
    "AND NOT being introduced in this very paragraph. Only include genuine "
    "technical concepts a reader would need explained. Do NOT include common "
    "English words, generic words (data, model, result, system, method, value, "
    "number, network, layer, input, output, training, test), or "
    "citation/figure/table references. If none, [].\n"
    "  2. `introduced_here`: concepts this paragraph INTRODUCES / DEFINES for "
    "the first time (definition, 'we call ...', 'we define ...', 'X is ...', "
    "inline acronym 'Long Name (LN)', etc.). If none, [].\n\n"
    "Respond with STRICT JSON only, no prose, of the form:\n"
    '{"results": [{"index": <int>, "forward_refs": ["..."], '
    '"introduced_here": ["..."]}, ...]}\n'
    "The \"results\" array must contain exactly one entry per input paragraph, "
    "in the same order, each carrying the correct `index`."
)


def _build_batch_user_prompt(introduced: List[str], paras: List[Paragraph]) -> str:
    intro_json = json.dumps(introduced, ensure_ascii=False)
    items = [{"index": p.index, "page": p.page, "text": p.text} for p in paras]
    return (
        f"introduced: {intro_json}\n\n"
        f"paragraphs (process strictly in this order):\n"
        + json.dumps(items, ensure_ascii=False, indent=2)
    )


def judge_batch(
    client: LLMClient,
    model: str,
    introduced: List[str],
    paras: List[Paragraph],
    timeout: float = 120.0,
    max_retries: int = 4,
) -> List[ParaResult]:
    """Judge several paragraphs in one LLM call.

    The model is told the `introduced` set as of the START of the batch and
    must process the paragraphs in order, so concepts introduced by earlier
    paragraphs in the same batch count as known for later ones.
    """
    if not paras:
        return []
    user = _build_batch_user_prompt(introduced, paras)
    last_err: Optional[Exception] = None
    backoff = 1.5
    for attempt in range(max_retries):
        try:
            raw, usage = client.complete(
                model=model,
                system=BATCH_SYSTEM_PROMPT,
                user=user,
                timeout=timeout,
            )
            parsed = _extract_json(raw) or {}
            # Accept either {"results": [...]} or a bare list.
            items = parsed.get("results", parsed if isinstance(parsed, list) else [])
            if not isinstance(items, list):
                items = []
            by_index: Dict[int, dict] = {}
            for it in items:
                if not isinstance(it, dict) or "index" not in it:
                    continue
                try:
                    by_index[int(it["index"])] = it
                except Exception:
                    continue
            out: List[ParaResult] = []
            for i, p in enumerate(paras):
                it = by_index.get(p.index, {})
                out.append(ParaResult(
                    index=p.index,
                    page=p.page,
                    introduced=[str(x) for x in it.get("introduced_here", [])],
                    forward_refs=[str(x) for x in it.get("forward_refs", [])],
                    # Attach token usage only to the first paragraph of the
                    # batch so report sums are not double-counted.
                    raw=raw if i == 0 else "",
                    model=model,
                    usage=usage if i == 0 else {},
                ))
            return out
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(backoff)
            backoff *= 2
    raise RuntimeError(
        f"LLM batch call failed (first index {paras[0].index}) "
        f"after {max_retries} attempts: {last_err}"
    )


# ---------------------------------------------------------------------------
# Reconciliation: remove false-positive forward refs produced under
# concurrency (where a batch did not know about concepts introduced by an
# earlier batch in the same concurrent window).
# ---------------------------------------------------------------------------
def _norm_term(t: str) -> str:
    return t.strip().strip(".,;:()\"'").lower()


def _stem(t: str) -> str:
    n = _norm_term(t)
    if len(n) > 4 and n.endswith("s") and not n.endswith("ss"):
        return n[:-1]
    return n


def _reconcile(results: List[ParaResult]) -> None:
    """In-place: drop forward_refs that are actually introduced by an earlier
    paragraph (by normalized + stemmed string match). Only ever removes items,
    so it can only fix false positives, never create false negatives beyond
    what the model already decided."""
    available: Dict[int, Set[str]] = {}
    seen: Set[str] = set()
    for r in sorted(results, key=lambda r: r.index):
        available[r.index] = set(seen)
        for t in r.introduced:
            seen.add(_norm_term(t))
            seen.add(_stem(t))
    for r in results:
        kept: List[str] = []
        av = available.get(r.index, set())
        for t in r.forward_refs:
            if _norm_term(t) in av or _stem(t) in av:
                continue
            kept.append(t)
        r.forward_refs = kept


def _write_cache(cache_path: str, results: List[ParaResult]) -> None:
    """Atomically (re)write the whole cache file with final results."""
    tmp = cache_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        for pr in results:
            fh.write(json.dumps(asdict(pr), ensure_ascii=False) + "\n")
    os.replace(tmp, cache_path)


# ---------------------------------------------------------------------------
# Cache (resume) — one JSONL line per paragraph result
# ---------------------------------------------------------------------------
def load_cache(cache_path: str) -> Dict[int, ParaResult]:
    cache: Dict[int, ParaResult] = {}
    if not os.path.exists(cache_path):
        return cache
    with open(cache_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            pr = ParaResult(
                index=obj["index"],
                page=obj.get("page", 0),
                introduced=obj.get("introduced", []),
                forward_refs=obj.get("forward_refs", []),
                raw=obj.get("raw", ""),
                model=obj.get("model", ""),
                usage=obj.get("usage", {}),
            )
            cache[pr.index] = pr
    return cache


def save_cache_line(cache_path: str, pr: ParaResult) -> None:
    with open(cache_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(pr), ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Sequential judging with running introduced-set
# ---------------------------------------------------------------------------
def run(
    paragraphs: List[Paragraph],
    client: LLMClient,
    model: str,
    cache_path: str,
    resume: bool,
    skip_captions: bool,
    skip_references: bool,
    log_every: int,
    batch_size: int = 1,
    concurrency: int = 1,
) -> Tuple[List[ParaResult], List[str]]:
    """Judge paragraphs, optionally in batches and/or concurrently.

    * ``batch_size > 1``: send that many paragraphs per LLM call. The model
      processes them in order, so concepts introduced by an earlier paragraph
      in the same batch are treated as known for the rest of the batch.
    * ``concurrency > 1``: run multiple batch calls concurrently. Each batch
      is seeded with the introduced-set as of the start of the run (a
      snapshot), so a later batch may flag concepts as forward-refs even
      though an earlier batch in the same window introduced them. A local
      reconciliation pass afterwards removes those false positives, keeping
      results correct. ``concurrency == 1`` updates the seed between batches
      and needs no reconciliation (still applied harmlessly).
    """
    cache = load_cache(cache_path) if resume else {}

    def _dedup(lst: List[str]) -> List[str]:
        seen: Set[str] = set()
        out: List[str] = []
        for x in lst:
            k = x.strip().lower()
            if k and k not in seen:
                seen.add(k)
                out.append(x)
        return out

    # Cached prefix (ordered).
    result_by_index: Dict[int, ParaResult] = {}
    max_cached = -1
    for p in paragraphs:
        if p.index in cache:
            result_by_index[p.index] = cache[p.index]
            max_cached = p.index
        else:
            break

    introduced: List[str] = []
    for idx in sorted(result_by_index):
        introduced.extend(result_by_index[idx].introduced)
    introduced = _dedup(introduced)

    if max_cached >= 0:
        print(f"[cache] resumed {len(result_by_index)} paragraphs "
              f"(up to index {max_cached})", file=sys.stderr)

    # Partition the remaining paragraphs into skipped (empty results) and
    # to-process (judged in batches).
    to_process: List[Paragraph] = []
    for p in paragraphs:
        if p.index <= max_cached:
            continue
        if (skip_captions and p.is_caption) or (skip_references and p.is_reference):
            result_by_index[p.index] = ParaResult(
                index=p.index, page=p.page, introduced=[],
                forward_refs=[], model=model,
            )
        else:
            to_process.append(p)

    batches = [to_process[i:i + batch_size]
               for i in range(0, len(to_process), batch_size)]

    seed_intro = list(introduced)  # snapshot at start of the run
    last_progress = -1

    def _maybe_log(last_para: Paragraph, first_result: ParaResult, batch_len: int) -> None:
        nonlocal last_progress
        if last_para.index == last_progress:
            return
        if last_para.index % log_every != 0 and last_para.index != paragraphs[-1].index:
            return
        last_progress = last_para.index
        tok = first_result.usage.get("total_tokens", "?") if first_result else "?"
        print(f"[progress] batch ending para {last_para.index}/{paragraphs[-1].index} "
              f"(page {last_para.page}) batch={batch_len} tok={tok}",
              file=sys.stderr)

    if concurrency <= 1:
        # Sequential: seed updates between batches (most accurate; the model
        # sees a growing introduced-set across batches).
        cur_seed = list(seed_intro)
        for b in batches:
            batch_results = judge_batch(client, model, cur_seed, b)
            for pr in batch_results:
                result_by_index[pr.index] = pr
                save_cache_line(cache_path, pr)
                introduced.extend(pr.introduced)
            introduced = _dedup(introduced)
            cur_seed = list(introduced)
            _maybe_log(b[-1], batch_results[0] if batch_results else None, len(b))
    else:
        # Concurrent windowed: all batches share the same seed snapshot.
        # Reconciliation afterwards removes cross-batch false positives.
        print(f"[concurrency] {concurrency} workers, {len(batches)} batches, "
              f"shared seed of {len(seed_intro)} concepts", file=sys.stderr)
        batch_map: Dict[int, List[ParaResult]] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as ex:
            futs = {ex.submit(judge_batch, client, model, list(seed_intro), b): b
                    for b in batches}
            for fut in concurrent.futures.as_completed(futs):
                b = futs[fut]
                batch_map[b[0].index] = fut.result()
        # Fold in document order and persist incrementally.
        for b in batches:
            batch_results = batch_map[b[0].index]
            for pr in batch_results:
                result_by_index[pr.index] = pr
                save_cache_line(cache_path, pr)
                introduced.extend(pr.introduced)
            introduced = _dedup(introduced)
            _maybe_log(b[-1], batch_results[0] if batch_results else None, len(b))

    # Final ordered results.
    results = [result_by_index[p.index] for p in paragraphs
               if p.index in result_by_index]

    # Reconcile (harmless in sequential mode; fixes concurrency false
    # positives) and rewrite cache with the final, consistent values so that
    # resume is stable.
    _reconcile(results)
    _write_cache(cache_path, results)

    # Final cumulative introduced list, in document order.
    final_intro: List[str] = []
    for r in results:
        final_intro.extend(r.introduced)
    final_intro = _dedup(final_intro)

    return results, final_intro


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def render_report(
    paragraphs: List[Paragraph],
    results: List[ParaResult],
    introduced: List[str],
    path: str,
    markdown: bool,
    list_concepts: bool,
) -> str:
    h = "##" if markdown else "=="
    bullet = "- " if markdown else "  * "
    lines: List[str] = []

    n_fwd = sum(len(r.forward_refs) for r in results)
    n_intro = len(introduced)
    total_tokens = sum(r.usage.get("total_tokens", 0) or 0 for r in results)

    lines.append(f"{h} Forward-reference lint report (LLM judge)")
    lines.append(f"File: {path}")
    lines.append(f"Paragraphs scanned: {len(results)}")
    lines.append(f"Concepts introduced (cumulative): {n_intro}")
    lines.append(f"Forward references found: {n_fwd}")
    lines.append(f"Total tokens used: {total_tokens}")
    lines.append("")

    by_para: Dict[int, ParaResult] = {r.index: r for r in results}
    flagged = [r for r in results if r.forward_refs]

    if not flagged:
        lines.append("No forward references detected.")
    else:
        for r in flagged:
            para = paragraphs[r.index] if r.index < len(paragraphs) else None
            preview = ""
            if para is not None:
                preview = para.text[:180].replace("\n", " ")
                if len(para.text) > 180:
                    preview += "…"
            lines.append(f"{h} Paragraph {r.index} (page {r.page})")
            lines.append(f"{bullet}text: {preview}")
            for term in r.forward_refs:
                lines.append(f"{bullet}forward-ref: '{term}'")
            if r.introduced:
                lines.append(f"{bullet}also introduces here: "
                             + ", ".join(f"'{x}'" for x in r.introduced))
            lines.append("")

    if list_concepts:
        lines.append(f"{h} Detected introduced concepts (cumulative)")
        for c in introduced:
            lines.append(f"{bullet}{c}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_page_range(s: str) -> Optional[Tuple[int, int]]:
    if not s:
        return None
    m = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", s)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        return (min(lo, hi), max(lo, hi))
    m = re.match(r"^\s*(\d+)\s*$", s)
    if m:
        n = int(m.group(1))
        return (n, n)
    raise ValueError(f"Bad --pages value: {s!r}")


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="LLM-as-judge forward-reference linter for a thesis PDF.",
    )
    p.add_argument("pdf", help="Path to the thesis PDF.")
    p.add_argument("--base-url", default=BASE_URL,
                   help="LLM endpoint (default: the Aalto AI API, "
                        f"{AALTO_AZURE_URL}). Alternatives: the Aalto LLM "
                        f"Gateway ({LLMGW_BASE_URL}) or any OpenAI-style "
                        "endpoint such as https://openrouter.ai/api/v1.")
    p.add_argument("--api-key", default=None,
                   help="API key (default: $AALTO_API_KEY for the Aalto AI "
                        "API, $AALTO_LLM_KEY for the Aalto LLM gateway, "
                        "$OPENROUTER_API_KEY otherwise).")
    p.add_argument("--model", default=None,
                   help="Model id (default depends on the gateway: "
                        "gpt-5-mini-2025-08-07 on the Aalto AI API).")
    p.add_argument("--out", help="Write report to this file instead of stdout.")
    p.add_argument("--format", choices=["text", "markdown"], default="text")
    p.add_argument("--pages", default=None, help="Page range e.g. '1-120' or '5'.")
    p.add_argument("--cache", default=None,
                   help=f"Cache file path (default: <pdf>{CACHE_SUFFIX}).")
    p.add_argument("--resume", action="store_true",
                   help="Reuse cached per-paragraph results if present.")
    p.add_argument("--no-captions", action="store_true", default=True,
                   help="Skip figure/table captions (default: on).")
    p.add_argument("--no-references", action="store_true", default=True,
                   help="Skip bibliography entries (default: on).")
    p.add_argument("--include-captions", dest="no_captions", action="store_false",
                   help="Do not skip captions.")
    p.add_argument("--include-references", dest="no_references", action="store_false",
                   help="Do not skip bibliography entries.")
    p.add_argument("--log-every", type=int, default=5,
                   help="Print progress every N paragraphs (default 5).")
    p.add_argument("--batch", type=int, default=1,
                   help="Number of paragraphs judged per LLM call (default 1). "
                        "Larger values cut call count and cost; e.g. --batch 5.")
    p.add_argument("--concurrency", type=int, default=1,
                   help="Run that many batch calls concurrently (default 1). "
                        "With concurrency>1 all batches in a run share a snapshot "
                        "of the introduced-set and a reconciliation pass fixes "
                        "cross-batch false positives. Ignored effectively when "
                        "batch==1 unless you want parallelism.")
    p.add_argument("--list-concepts", action="store_true",
                   help="Also list every detected introduced concept.")
    p.add_argument("--limit", type=int, default=None,
                   help="Stop after this many paragraphs (for quick tests).")
    args = p.parse_args(argv)

    if fitz is None:
        print("ERROR: PyMuPDF required. pip install pymupdf", file=sys.stderr)
        return 2

    if not args.model:
        args.model = default_model(args.base_url)

    page_range = parse_page_range(args.pages) if args.pages else None
    paragraphs = extract_paragraphs(args.pdf, page_range)
    if not paragraphs:
        print("ERROR: no paragraphs extracted.", file=sys.stderr)
        return 1
    if args.limit:
        paragraphs = paragraphs[: args.limit]

    cache_path = args.cache or (os.path.splitext(args.pdf)[0] + CACHE_SUFFIX)
    client = make_client(args.base_url, args.api_key)

    print(f"[info] gateway={args.base_url}\n"
          f"[info] model={args.model}  paragraphs={len(paragraphs)}  "
          f"batch={args.batch}  concurrency={args.concurrency}  "
          f"cache={cache_path}  resume={args.resume}", file=sys.stderr)

    results, introduced = run(
        paragraphs=paragraphs,
        client=client,
        model=args.model,
        cache_path=cache_path,
        resume=args.resume,
        skip_captions=args.no_captions,
        skip_references=args.no_references,
        log_every=args.log_every,
        batch_size=args.batch,
        concurrency=args.concurrency,
    )

    report = render_report(
        paragraphs, results, introduced, args.pdf,
        markdown=(args.format == "markdown"),
        list_concepts=args.list_concepts,
    )

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(report)
        print(f"Report written to {args.out}", file=sys.stderr)
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
