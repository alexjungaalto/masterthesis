#!/usr/bin/env python3
"""Run the whole ml-theses.org linter suite on a thesis.

Runs every applicable linter (PDF or LaTeX input), prints each report, and
ends with a one-line-per-linter summary. Fast heuristic linters run always;
the LLM-based ones (Aalto AI API; need $AALTO_API_KEY and the Aalto
network/VPN) and the network-based bibliography check are opt-in.

Usage:
  python3 run_all_linters.py thesis.pdf
  python3 run_all_linters.py thesis.pdf --llm            # + LLM linters
  python3 run_all_linters.py thesis.pdf --bib            # + bibliography
  python3 run_all_linters.py main.tex chapters/          # LaTeX sources
Exit status: 0 if every linter passed, 1 otherwise.
"""

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent

# (script, pdf-mode, tex-mode)
FAST = [
    ("structure_lint.py", True, True),
    ("unreferenced_entity_linter.py", True, True),
    ("crossref_forward_lint.py", True, False),
    ("forward_ref_lint.py", True, False),
    ("acronym_lint.py", True, True),
    ("prose_lint.py", True, True),
    ("terminology_lint.py", True, True),
    ("math_typeset_lint.py", False, True),
    ("citation_style_lint.py", True, True),
    ("caption_lint.py", True, True),
    ("ai_disclosure_lint.py", True, True),
]
LLM = [
    ("thesis_checklist_llm.py", True, False),
    ("data_split_lint_llm.py", True, False),
    ("research_questions_lint_llm.py", True, False),
    ("rq_quality_lint_llm.py", True, False),
    ("figure_lint_llm.py", True, False),
    ("section_intro_lint_llm.py", True, False),
    ("flow_lint_llm.py", True, False),
    ("prose_lint_llm.py", True, True),
    ("caption_lint_llm.py", True, True),
    ("forward_ref_lint_llm.py", True, False),
]
BIB = [("bibliography_linter.py", True, False)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run the full linter suite.")
    ap.add_argument("inputs", nargs="+", help="thesis.pdf or .tex files/dirs")
    ap.add_argument("--llm", action="store_true",
                    help="Also run the LLM linters (Aalto AI API).")
    ap.add_argument("--bib", action="store_true",
                    help="Also run the bibliography existence check "
                         "(network queries to Crossref/arXiv/DBLP).")
    args = ap.parse_args(argv)

    pdf_mode = args.inputs[0].lower().endswith(".pdf")
    todo = FAST + (LLM if args.llm else []) + (BIB if args.bib else [])
    results = []
    for script, pdf_ok, tex_ok in todo:
        if (pdf_mode and not pdf_ok) or (not pdf_mode and not tex_ok):
            continue
        print(f"\n{'=' * 74}\n>>> {script}\n{'=' * 74}", flush=True)
        rc = subprocess.run(
            [sys.executable, str(HERE / script), *args.inputs]).returncode
        results.append((script, rc))

    print(f"\n{'=' * 74}\nSummary\n{'=' * 74}")
    worst = 0
    for script, rc in results:
        status = {0: "clean", 1: "findings"}.get(rc, f"error ({rc})")
        print(f"  {script:<32} {status}")
        worst = max(worst, min(rc, 1))
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
