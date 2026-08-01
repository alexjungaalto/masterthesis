#!/usr/bin/env python3
"""Linter: responsible-AI disclosure statement (ml-theses.org).

Guidelines enforced:
  * "Disclose when and how you used AI tools, in a dedicated statement —
     not in the Methods section."
  * "Record the tool, version, and settings."

Findings:
  [WARN] NO-AI-STATEMENT     no AI-use disclosure section/statement found
  [WARN] NO-TOOL-NAMED       statement found but no recognizable AI tool
                             is named
  [WARN] NO-VERSION          statement names tools but records no
                             version/model identifier
  [WARN] IN-METHODS          the only AI-use discussion sits inside a
                             Methods/Methodology chapter
  [INFO] STATEMENT-FOUND     location of the detected statement (for a
                             quick eye pass)

A thesis genuinely written without AI tools should say so too; a document
with no statement at all cannot be distinguished from an undisclosed use,
hence NO-AI-STATEMENT is a warning, not an error.

Input: thesis PDF or LaTeX sources.
Usage:
  python3 ai_disclosure_lint.py thesis.pdf
Exit status: 0 clean, 1 findings (WARN or worse), 2 usage error.
"""

import argparse
import re
from typing import List, Optional, Tuple

from lintutil import Report, is_toc_line, load_lines

HEADING_RE = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*\s+)?"
    r"(use\s+of\s+(?:ai|artificial\s+intelligence|generative\s+ai)|"
    r"(?:ai|artificial\s+intelligence)[ -]use|"
    r"(?:ai|generative\s+ai)\s+(?:disclosure|statement|declaration)|"
    r"disclosure\s+of\s+ai|"
    r"declaration\s+of\s+(?:ai|the\s+use)|"
    r"statement\s+on\s+(?:the\s+)?use\s+of\s+ai)\b.{0,40}$",
    re.I)

METHODS_HEADING_RE = re.compile(
    r"^\s*(?:chapter\s+)?\d?\.?\s*(methods?|methodology)\s*$", re.I)
ANY_HEADING_RE = re.compile(r"^\s*(?:chapter\s+)?\d+(?:\.\d+)*\s+\S|^\s*(abstract|acknowledg|contents|references|bibliography|appendix)", re.I)

TOOL_RE = re.compile(
    r"\b(ChatGPT|GPT-?[3-9](?:\.\d)?[a-z]*|Claude(?:\s+(?:Code|Opus|Sonnet|"
    r"Haiku))?|Gemini|Copilot|Grammarly|DeepL|LLaMA|Llama|Mistral|Qwen|"
    r"DeepSeek|Cursor|Perplexity|Overleaf\s+AI|Writefull|QuillBot|"
    r"large\s+language\s+model)\b", re.I)
VERSION_RE = re.compile(
    r"\b(v?\d+(?:\.\d+)+|GPT-?[3-9](?:\.\d)?[a-z]*|4o|o[13](?:-mini)?|"
    r"(?:Opus|Sonnet|Haiku)\s*[\d.]*|20\d{2}-\d{2}|version\s+\S+)\b",
    re.I)
AI_MENTION_RE = re.compile(
    r"\b(AI\s+tools?|artificial\s+intelligence|generative\s+AI|"
    r"large\s+language\s+models?|LLMs?)\b")


def main(argv: List[str] = None) -> int:
    ap = argparse.ArgumentParser(description="AI-use disclosure linter.")
    ap.add_argument("inputs", nargs="+", help="thesis.pdf or .tex files/dirs")
    args = ap.parse_args(argv)

    lines, mode = load_lines(args.inputs)
    lines = [(w, t) for (w, t) in lines if not is_toc_line(t)]
    rep = Report("AI disclosure lint report", " ".join(args.inputs))

    if mode == "tex":
        # surface \section{...} arguments as heading lines
        expanded = []
        for w, t in lines:
            m = re.search(r"\\(?:chapter|section|subsection)\*?\{([^}]*)\}", t)
            if m:
                expanded.append((w, m.group(1)))
            expanded.append((w, t))
        lines = expanded

    # Locate a dedicated statement heading.
    stmt_idx: Optional[int] = None
    for i, (w, t) in enumerate(lines):
        if HEADING_RE.match(t.strip()):
            stmt_idx = i
            break

    # Track whether AI mentions occur inside a Methods chapter.
    methods_ai_loc: Optional[str] = None
    in_methods = False
    for w, t in lines:
        s = t.strip()
        if METHODS_HEADING_RE.match(s):
            in_methods = True
        elif ANY_HEADING_RE.match(s) and not METHODS_HEADING_RE.match(s):
            in_methods = False
        if in_methods and (AI_MENTION_RE.search(s) or TOOL_RE.search(s)):
            methods_ai_loc = methods_ai_loc or w

    if stmt_idx is None:
        # fall back: any paragraph that reads like a disclosure sentence
        fallback = None
        for i, (w, t) in enumerate(lines):
            if re.search(r"\b(AI|artificial intelligence|language model)s?\b."
                         r"{0,80}\b(used|employed|assisted|utili[sz]ed)\b|"
                         r"\b(used|employed|utili[sz]ed)\b.{0,60}"
                         r"\b(ChatGPT|Claude|Copilot|AI tools?|LLMs?)\b",
                         t, re.I):
                fallback = i
                break
        if fallback is None:
            rep.add("WARN", "NO-AI-STATEMENT", "-",
                    "no AI-use disclosure statement found — ml-theses.org "
                    "requires a dedicated statement (also if no AI tools "
                    "were used, say so).")
            print(rep.render())
            return rep.exit_code()
        stmt_idx = fallback
        rep.add("INFO", "STATEMENT-FOUND", lines[stmt_idx][0],
                "AI-use discussion found in running text (no dedicated "
                "heading detected): "
                f"\"{lines[stmt_idx][1].strip()[:90]}…\"")
    else:
        rep.add("INFO", "STATEMENT-FOUND", lines[stmt_idx][0],
                f"dedicated statement: \"{lines[stmt_idx][1].strip()}\"")

    # Inspect the statement body (up to the next heading / 60 lines).
    body_lines = []
    for w, t in lines[stmt_idx + 1: stmt_idx + 61]:
        if ANY_HEADING_RE.match(t.strip()) and t.strip():
            break
        body_lines.append(t)
    body = " ".join(body_lines + [lines[stmt_idx][1]])

    tools = TOOL_RE.findall(body)
    if not tools:
        if re.search(r"\bno\b.{0,40}\bAI\b|\bwithout\b.{0,30}\bAI\b",
                     body, re.I):
            pass  # explicit "no AI tools were used" — fine
        else:
            rep.add("WARN", "NO-TOOL-NAMED", lines[stmt_idx][0],
                    "AI statement does not name any tool — record the "
                    "tool, version, and settings.")
    else:
        if not VERSION_RE.search(body):
            rep.add("WARN", "NO-VERSION", lines[stmt_idx][0],
                    f"tool(s) named ({', '.join(sorted(set(tools))[:4])}) "
                    f"but no version/model identifier recorded.")

    if methods_ai_loc and stmt_idx is not None:
        stmt_in_methods = False
        # if the statement itself is the Methods mention, warn
        if lines[stmt_idx][0] == methods_ai_loc:
            stmt_in_methods = True
        if stmt_in_methods:
            rep.add("WARN", "IN-METHODS", methods_ai_loc,
                    "AI-use discussion sits in the Methods chapter — the "
                    "disclosure belongs in a dedicated statement.")

    print(rep.render())
    return rep.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
