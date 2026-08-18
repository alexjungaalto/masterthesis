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
  python3 run_all_linters.py paper.pdf --profile paper --llm   # conf/journal paper
  python3 run_all_linters.py thesis.pdf --dashboard      # + HTML report, opened
Exit status: 0 if every linter passed, 1 otherwise.
"""

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent


def _dashboard_out_path(inputs, explicit):
    """Where to write the HTML dashboard: --dashboard-out if given, else
    ``<first-input-stem>_lint_dashboard.html`` in the current directory."""
    if explicit:
        return Path(explicit)
    stem = Path(inputs[0]).stem or "thesis"
    return Path(f"{stem}_lint_dashboard.html")

THESIS, PAPER = "thesis", "paper"
BOTH = (THESIS, PAPER)

# (script, pdf-mode, tex-mode, profiles, passes_profile)
#   profiles       -- manuscript types this linter runs for
#   passes_profile -- forward --profile=<p> to the linter (it adapts itself)
FAST = [
    ("structure_lint.py", True, True, BOTH, True),
    ("unreferenced_entity_linter.py", True, True, BOTH, False),
    ("crossref_forward_lint.py", True, False, BOTH, False),
    ("forward_ref_lint.py", True, False, BOTH, False),
    ("acronym_lint.py", True, True, BOTH, False),
    ("prose_lint.py", True, True, BOTH, False),
    ("unresolved_reference_lint.py", True, True, BOTH, False),
    ("terminology_lint.py", True, True, BOTH, False),
    ("math_typeset_lint.py", False, True, BOTH, False),
    ("citation_style_lint.py", True, True, BOTH, True),
    ("caption_lint.py", True, True, BOTH, False),
    ("ai_disclosure_lint.py", True, True, (THESIS,), False),
]
LLM = [
    ("thesis_checklist_llm.py", True, False, (THESIS,), False),
    ("paper_checklist_llm.py", True, False, (PAPER,), False),
    ("data_split_lint_llm.py", True, False, BOTH, True),
    ("research_questions_lint_llm.py", True, False, BOTH, True),
    ("rq_quality_lint_llm.py", True, False, BOTH, True),
    ("related_work_faithfulness_llm.py", True, False, BOTH, True),
    ("figure_lint_llm.py", True, False, BOTH, False),
    ("section_intro_lint_llm.py", True, False, BOTH, False),
    ("flow_lint_llm.py", True, False, BOTH, False),
    ("prose_lint_llm.py", True, True, BOTH, False),
    ("caption_lint_llm.py", True, True, BOTH, False),
    ("forward_ref_lint_llm.py", True, False, BOTH, False),
    ("type_consistency_lint_llm.py", True, False, BOTH, False),
    ("contribution_support_lint_llm.py", True, False, BOTH, False),
]
BIB = [("bibliography_linter.py", True, False, BOTH, False)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run the full linter suite.")
    ap.add_argument("inputs", nargs="+", help="thesis.pdf or .tex files/dirs")
    ap.add_argument("--profile", choices=[THESIS, PAPER], default=THESIS,
                    help="Manuscript type: 'thesis' (default, ml-theses.org "
                         "rubric) or 'paper' (IEEE/ACM conference/journal "
                         "draft; skips thesis-only checks, adapts the rest).")
    ap.add_argument("--llm", action="store_true",
                    help="Also run the LLM linters (Aalto AI API).")
    ap.add_argument("--bib", action="store_true",
                    help="Also run the bibliography existence check "
                         "(network queries to Crossref/arXiv/DBLP).")
    ap.add_argument("--dashboard", action="store_true",
                    help="Also render the run as a self-contained HTML "
                         "dashboard and open it in the default browser.")
    ap.add_argument("--dashboard-out", default=None, metavar="FILE",
                    help="Dashboard path (implies --dashboard; default "
                         "<input>_lint_dashboard.html in the current dir).")
    ap.add_argument("--no-open", action="store_true",
                    help="With --dashboard, write the HTML but do not open a "
                         "browser (for headless/CI runs).")
    args = ap.parse_args(argv)

    want_dashboard = args.dashboard or bool(args.dashboard_out)

    # When building a dashboard we also need each linter's report text, so
    # capture stdout and echo it (stderr still streams live, keeping LLM
    # progress visible). A plain run streams straight through, unchanged.
    buf = []

    def emit(text="", end="\n"):
        sys.stdout.write(text + end)
        sys.stdout.flush()
        if want_dashboard:
            buf.append(text + end)

    pdf_mode = args.inputs[0].lower().endswith(".pdf")
    todo = FAST + (LLM if args.llm else []) + (BIB if args.bib else [])
    results = []
    for script, pdf_ok, tex_ok, profiles, passes in todo:
        if args.profile not in profiles:
            continue
        if (pdf_mode and not pdf_ok) or (not pdf_mode and not tex_ok):
            continue
        extra = [f"--profile={args.profile}"] if passes else []
        emit(f"\n{'=' * 74}\n>>> {script}\n{'=' * 74}")
        cmd = [sys.executable, str(HERE / script), *args.inputs, *extra]
        if want_dashboard:
            # Capture stdout (the report the dashboard parses); let stderr
            # inherit so progress lines still stream to the terminal live.
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, text=True)
            emit(proc.stdout, end="")
            rc = proc.returncode
        else:
            rc = subprocess.run(cmd).returncode
        results.append((script, rc))

    emit(f"\n{'=' * 74}\nSummary\n{'=' * 74}")
    worst = 0
    for script, rc in results:
        status = {0: "clean", 1: "findings"}.get(rc, f"error ({rc})")
        emit(f"  {script:<32} {status}")
        worst = max(worst, min(rc, 1))

    if want_dashboard:
        _build_dashboard(args, "".join(buf))
    return worst


def _build_dashboard(args, run_text):
    """Render the captured run as HTML via dashboard.py and open it."""
    sys.path.insert(0, str(HERE))
    try:
        import dashboard
    except Exception as e:  # pragma: no cover - defensive
        print(f"[dashboard] could not import dashboard.py: {e}",
              file=sys.stderr)
        return
    sections, summary = dashboard.parse_run(run_text)
    if not sections:
        print("[dashboard] no linter sections captured; skipping HTML.",
              file=sys.stderr)
        return
    out = _dashboard_out_path(args.inputs, args.dashboard_out)
    title = Path(args.inputs[0]).stem or "Master's thesis"
    flags = [f"--profile {args.profile}"]
    if args.llm:
        flags.append("--llm")
    if args.bib:
        flags.append("--bib")
    meta = f"{Path(args.inputs[0]).name} · run_all_linters.py {' '.join(flags)}"
    doc, n_flag = dashboard.render(sections, summary, title, "&nbsp;",
                                   meta, body_only=False)
    out.write_text(doc, encoding="utf-8")
    print(f"[dashboard] wrote {out} ({len(sections)} linters, {n_flag} with "
          f"findings/errors)", file=sys.stderr)
    if args.no_open:
        return
    if dashboard.open_in_browser(out):
        print(f"[dashboard] opened {out} in your browser", file=sys.stderr)
    else:
        print(f"[dashboard] could not open a browser; open {out} manually",
              file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
