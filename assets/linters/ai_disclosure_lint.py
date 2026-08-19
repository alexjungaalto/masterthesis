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
    rep = Report("AI disclosure lint report", " ".join(args.inputs),
                 about="Checks for a dedicated AI-use statement naming the "
                       "tool and version, and that it is not placed inside "
                       "the Methods chapter.")

    if mode == "tex":
        # Surface \chapter/\section/\subsection titles as their own lines so
        # the heading regexes (which expect a plain-text heading) can match
        # them; the original source line is kept too.
        expanded = []
        for w, t in lines:
            m = re.search(r"\\(?:chapter|section|subsection)\*?\{([^}]*)\}", t)
            if m:
                expanded.append((w, m.group(1)))
            expanded.append((w, t))
        lines = expanded

    # Locate a dedicated statement heading. `has_dedicated` records whether a
    # real disclosure heading exists (vs. only a fallback sentence found
    # later); IN-METHODS is about the *absence* of a dedicated statement.
    stmt_idx: Optional[int] = None
    for i, (w, t) in enumerate(lines):
        if HEADING_RE.match(t.strip()):
            stmt_idx = i
            break
    has_dedicated = stmt_idx is not None

    # Record which line indices fall inside a Methods/Methodology chapter, and
    # whether AI use is discussed there. A new chapter/section heading ends the
    # region — a numbered heading in extracted PDF text, or a \chapter/\section
    # macro in LaTeX (needed because unnumbered titles like "Use of AI" are not
    # matched by ANY_HEADING_RE and would otherwise never close the region).
    methods_indices = set()
    methods_has_ai = False
    in_methods = False
    for i, (w, t) in enumerate(lines):
        s = t.strip()
        tex_head = re.match(r"\\(?:chapter|section|subsection)\*?\{([^}]*)\}", s)
        if tex_head:
            in_methods = bool(METHODS_HEADING_RE.match(tex_head.group(1).strip()))
            continue  # the macro line itself is not body text
        if METHODS_HEADING_RE.match(s):
            in_methods = True
            continue
        if ANY_HEADING_RE.match(s):
            in_methods = False
            continue
        if in_methods:
            methods_indices.add(i)
            if AI_MENTION_RE.search(s) or TOOL_RE.search(s):
                methods_has_ai = True

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

    # Inspect the statement body (up to the next heading / 60 lines) for a
    # named tool and a version/model identifier. An explicit "no AI tools
    # were used" disclosure is accepted and not flagged for a missing tool.
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

    # IN-METHODS: there is no dedicated disclosure heading, and the only
    # AI-use discussion we found (the fallback sentence) sits inside a Methods
    # chapter — where the guideline says the disclosure does not belong. If a
    # dedicated statement exists (has_dedicated), extra methodological AI
    # mentions in Methods are legitimate and do not trip this.
    if not has_dedicated and methods_has_ai and stmt_idx in methods_indices:
        rep.add("WARN", "IN-METHODS", lines[stmt_idx][0],
                "AI-use discussion sits in the Methods chapter — the "
                "disclosure belongs in a dedicated statement.")

    print(rep.render())
    return rep.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
