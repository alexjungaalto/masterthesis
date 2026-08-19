#!/usr/bin/env python3
"""Render a linter run as a self-contained HTML dashboard.

Takes the combined output of ``run_all_linters.py`` (either by running the
suite here, or from a saved ``--from-run`` text file) and emits a single
self-contained HTML page: a summary band, one expandable card per linter
grouped by theme, and -- when the figure linter ran -- its figures x
ten-rules matrix rendered as a colour-coded table. No external assets: all
CSS is inline and the page works offline in any browser, light or dark.

Usage:
  python3 dashboard.py thesis.pdf --out dash.html            # run + render
  python3 dashboard.py thesis.pdf --llm --bib --open         # run, render, open
  python3 dashboard.py --from-run run.txt --title "..." \
      --author "..." --out dash.html                         # render only
  python3 dashboard.py --from-run run.txt --body-only --out body.html

--open launches the written page in your default browser (a file:// URL;
honours $BROWSER, silently skipped on a headless machine). Most users get
the dashboard straight from ``run_all_linters.py --dashboard`` instead,
which runs the suite once and opens the page for you.

--body-only omits <!doctype>/<html>/<head>/<body> (emits a <style> block plus
the page markup) for embedding in a host that supplies the document shell.
Exit status: 0 if every linter is clean, 1 if any has findings/errors.
"""

import argparse
import html
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent

# linter -> (theme group, one-line "what it checks"). Order within a group is
# preserved for display. Unknown scripts fall back to an "Other" group.
LINTERS = {
    # Structure & completeness
    "structure_lint.py": ("Structure & completeness", "required chapters present and in a sensible order"),
    "unreferenced_entity_linter.py": ("Structure & completeness", "every numbered figure/table/equation is referenced in the text"),
    "crossref_forward_lint.py": ("Structure & completeness", "no cross-reference points far ahead of where the float is defined"),
    "forward_ref_lint.py": ("Structure & completeness", "concepts are not used pages before they are introduced (regex)"),
    "unresolved_reference_lint.py": ("Structure & completeness", "no uncited appeals to companion studies; label-code schemes are defined"),
    "section_intro_lint_llm.py": ("Structure & completeness", "each chapter/section intro maps its subsections"),
    "thesis_checklist_llm.py": ("Structure & completeness", "the thesis meets the ml-theses.org content checklist"),
    "paper_checklist_llm.py": ("Structure & completeness", "the paper meets the reviewer-facing content checklist"),
    # Contribution & claims
    "contribution_support_lint_llm.py": ("Contribution & claims", "each claimed contribution is backed by a theorem/experiment/analysis"),
    # References
    "bibliography_linter.py": ("References", "cited works exist with the right authors, title, and venue"),
    "citation_style_lint.py": ("References", "citations follow a consistent IEEE-style format"),
    "related_work_faithfulness_llm.py": ("References", "each cited related work is described as its own abstract does"),
    # Language & prose
    "prose_lint.py": ("Language & prose", "prose defects: dangling references, vague quantifiers (regex)"),
    "prose_lint_llm.py": ("Language & prose", "self-editing pass: uncited claims, category errors, buzzwords"),
    "terminology_lint.py": ("Language & prose", "terminology matches the Aalto ML dictionary"),
    "acronym_lint.py": ("Language & prose", "every acronym is expanded at first use"),
    "flow_lint_llm.py": ("Language & prose", "paragraph-to-paragraph flow and leaf-section openers"),
    "type_consistency_lint_llm.py": ("Language & prose", "formal claims are well-typed (relations over compatible operands)"),
    "forward_ref_lint_llm.py": ("Language & prose", "concepts used before they are introduced (LLM)"),
    # Figures & captions
    "figure_lint_llm.py": ("Figures & captions", "figures scored against the PLOS Ten Simple Rules"),
    "caption_lint.py": ("Figures & captions", "no missing or too-short captions"),
    "caption_lint_llm.py": ("Figures & captions", "each caption is self-contained and informative"),
    # Math
    "math_typeset_lint.py": ("Math", "math is typeset, not written in plain text"),
    # Research questions
    "research_questions_lint_llm.py": ("Research questions", "each stated research question is answered and revisited"),
    "rq_quality_lint_llm.py": ("Research questions", "research questions are well-posed and self-contained"),
    # Method & data
    "data_split_lint_llm.py": ("Method & data", "train/validation/test splits are reported per method"),
    # Disclosure
    "ai_disclosure_lint.py": ("Disclosure", "use of AI tools is disclosed with versions"),
}
GROUP_ORDER = ["Structure & completeness", "Contribution & claims",
               "References", "Language & prose", "Figures & captions", "Math",
               "Research questions", "Method & data", "Disclosure", "Other"]

BANNER_RE = re.compile(r"^>>> (\S+\.py)\s*$", re.M)
SUMMARY_STATUS_RE = re.compile(r"^\s{2}(\S+\.py)\s+(clean|findings|error.*)$", re.M)


def run_suite(inputs, llm, bib):
    """Run ``run_all_linters.py`` on ``inputs`` and return its combined
    stdout (the same text a ``--from-run`` file would hold)."""
    cmd = [sys.executable, str(HERE / "run_all_linters.py"), *inputs]
    if llm:
        cmd.append("--llm")
    if bib:
        cmd.append("--bib")
    print(f"[dashboard] running: {' '.join(cmd)}", file=sys.stderr)
    return subprocess.run(cmd, capture_output=True, text=True).stdout


def parse_run(text):
    """Split a combined run into [(script, body)], plus the Summary statuses."""
    summary = {m.group(1): m.group(2).strip()
               for m in SUMMARY_STATUS_RE.finditer(text)}
    # Drop the trailing Summary block from the body region if present.
    body_region = re.split(r"\n=+\nSummary\n=+", text)[0]
    marks = [(m.group(1), m.start(), m.end())
             for m in BANNER_RE.finditer(body_region)]
    sections = []
    for i, (script, _, end) in enumerate(marks):
        nxt = marks[i + 1][1] if i + 1 < len(marks) else len(body_region)
        body = body_region[end:nxt]
        # trim the '====' rule that follows each banner and blank edges
        body = re.sub(r"^=+\n", "", body.lstrip("\n")).strip("\n")
        sections.append((script, body))
    return sections, summary


def classify(script, body, summary):
    """Return one of clean|findings|error, preferring the Summary line."""
    s = summary.get(script, "")
    if s.startswith("error") or "error (" in s:
        return "error"
    if s == "clean":
        return "clean"
    if s == "findings":
        return "findings"
    # Fall back to content sniffing when no Summary line is available.
    low = body.lower()
    m = re.search(r"(\d+)\s+error\(s\)", low)
    if m and int(m.group(1)) > 0:
        return "error"
    if re.search(r"\bno findings\b|0 finding|all .*clean|verified, 0 error",
                 low) or "figure(s): 0 bad cell(s), 0 weak" in low:
        return "clean"
    if re.search(r"\bfinding|\bwarn|\bbad cell|weak cell|\[warn\]", low):
        return "findings"
    return "clean"


# ---- figure ten-rules matrix -> HTML table --------------------------------

MATRIX_ROW_RE = re.compile(r"^\|\s*(Figure [\d.]+)\s*\|(.+)\|\s*$", re.M)
GLYPH_CLASS = {"✓": "ok", "~": "weak", "✗": "bad", "·": "na", "?": "unk"}


def figure_matrix_html(body):
    """Return an HTML fragment for the figure x ten-rules matrix parsed from
    ``body``, or "" if that linter's output holds no matrix rows. Each glyph
    (checkmark/tilde/cross/dot/question) becomes a colour-coded cell."""
    rows = MATRIX_ROW_RE.findall(body)
    if not rows:
        return ""
    header = ("<tr><th class='fig'>Figure</th>"
              + "".join(f"<th>R{i}</th>" for i in range(1, 11)) + "</tr>")
    trs = []
    for label, cells in rows:
        glyphs = [c.strip() for c in cells.split("|")]
        tds = [f"<td class='fig'>{html.escape(label)}</td>"]
        for g in glyphs[:10]:
            cls = GLYPH_CLASS.get(g, "unk")
            tds.append(f"<td class='cell {cls}'>{html.escape(g)}</td>")
        trs.append("<tr>" + "".join(tds) + "</tr>")
    legend = ("Rules: R1 audience &middot; R2 message &middot; R3 medium "
              "&middot; R4 captions &middot; R5 defaults &middot; R6 color "
              "&middot; R7 mislead &middot; R8 chartjunk &middot; R9 "
              "beauty &middot; R10 tool")
    return (f"<div class='matrix-wrap'><table class='matrix'>{header}"
            + "".join(trs) + f"</table><p class='legend'>{legend}</p></div>")


# ---- HTML rendering -------------------------------------------------------

CSS = """
:root{
  --paper:#F4F6F8; --surface:#FFFFFF; --ink:#1A2230; --muted:#5B6474;
  --hair:#DDE2EA; --accent:#345BD6; --accent-soft:#E7ECFB;
  --ok:#2E9E6B; --ok-bg:#E6F4EC; --warn:#C8811C; --warn-bg:#FBF0DD;
  --err:#D14343; --err-bg:#FBE7E7;
  --shadow:0 1px 2px rgba(20,30,50,.06),0 4px 16px rgba(20,30,50,.05);
}
@media (prefers-color-scheme:dark){:root{
  --paper:#12151C; --surface:#1A1F2A; --ink:#E6EAF2; --muted:#9AA4B6;
  --hair:#2A313E; --accent:#7E9BFF; --accent-soft:#20263A;
  --ok:#57C793; --ok-bg:#13291F; --warn:#E4A44A;
  --warn-bg:#2C2413; --err:#F0776F; --err-bg:#2C1717;
  --shadow:0 1px 2px rgba(0,0,0,.3),0 6px 20px rgba(0,0,0,.25);
}}
:root[data-theme="light"]{
  --paper:#F4F6F8; --surface:#FFFFFF; --ink:#1A2230; --muted:#5B6474;
  --hair:#DDE2EA; --accent:#345BD6; --accent-soft:#E7ECFB;
  --ok:#2E9E6B; --ok-bg:#E6F4EC; --warn:#C8811C; --warn-bg:#FBF0DD;
  --err:#D14343; --err-bg:#FBE7E7;
}
:root[data-theme="dark"]{
  --paper:#12151C; --surface:#1A1F2A; --ink:#E6EAF2; --muted:#9AA4B6;
  --hair:#2A313E; --accent:#7E9BFF; --accent-soft:#20263A;
  --ok:#57C793; --ok-bg:#13291F; --warn:#E4A44A; --warn-bg:#2C2413;
  --err:#F0776F; --err-bg:#2C1717;
}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
  font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  line-height:1.5;-webkit-font-smoothing:antialiased}
.serif{font-family:"Iowan Old Style","Palatino Linotype","Book Antiqua",
  Palatino,Georgia,serif}
.mono{font-family:ui-monospace,"SF Mono","Cascadia Code",Menlo,monospace}
.wrap{max-width:1060px;margin:0 auto;padding:2.4rem 1.3rem 4rem}
header.top{border-bottom:1px solid var(--hair);padding-bottom:1.4rem;
  margin-bottom:1.8rem}
.eyebrow{font-size:.72rem;letter-spacing:.14em;text-transform:uppercase;
  color:var(--accent);font-weight:600;margin:0 0 .5rem}
h1{font-size:clamp(1.5rem,3.4vw,2.15rem);line-height:1.15;margin:.1rem 0 .5rem;
  text-wrap:balance;font-weight:600}
.byline{color:var(--muted);font-size:.95rem;margin:0}
.byline b{color:var(--ink);font-weight:600}
/* summary band */
.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:.8rem;
  margin:1.6rem 0 1rem}
@media(max-width:620px){.tiles{grid-template-columns:repeat(2,1fr)}}
.tile{background:var(--surface);border:1px solid var(--hair);border-radius:12px;
  padding:.9rem 1rem;box-shadow:var(--shadow)}
.tile .n{font-size:1.9rem;font-weight:700;font-variant-numeric:tabular-nums;
  line-height:1}
.tile .l{font-size:.78rem;color:var(--muted);margin-top:.3rem;
  text-transform:uppercase;letter-spacing:.06em}
.tile.ok .n{color:var(--ok)} .tile.warn .n{color:var(--warn)}
.tile.err .n{color:var(--err)}
.bar{display:flex;height:10px;border-radius:6px;overflow:hidden;
  margin:.2rem 0 1.7rem;border:1px solid var(--hair)}
.bar span{display:block}
.bar .s-ok{background:var(--ok)} .bar .s-warn{background:var(--warn)}
.bar .s-err{background:var(--err)}
/* filter */
.controls{display:flex;gap:.5rem;align-items:center;margin-bottom:1.3rem}
.controls button{font:inherit;font-size:.85rem;cursor:pointer;
  background:var(--surface);color:var(--ink);border:1px solid var(--hair);
  border-radius:999px;padding:.35rem .9rem}
.controls button[aria-pressed="true"]{background:var(--accent);
  color:#fff;border-color:var(--accent)}
/* groups & cards */
.group{margin:1.6rem 0 .6rem}
.group h2{font-size:.8rem;letter-spacing:.1em;text-transform:uppercase;
  color:var(--muted);font-weight:600;margin:0 0 .7rem;
  border-bottom:1px solid var(--hair);padding-bottom:.4rem}
.card{background:var(--surface);border:1px solid var(--hair);
  border-left:4px solid var(--hair);border-radius:10px;margin-bottom:.7rem;
  box-shadow:var(--shadow);overflow:hidden}
.card.s-clean{border-left-color:var(--ok)}
.card.s-findings{border-left-color:var(--warn)}
.card.s-error{border-left-color:var(--err)}
.card>summary{list-style:none;cursor:pointer;display:flex;align-items:center;
  gap:.8rem;padding:.85rem 1rem}
.card>summary::-webkit-details-marker{display:none}
.card>summary::after{content:"▸";color:var(--muted);margin-left:auto;
  transition:transform .15s}
.card[open]>summary::after{transform:rotate(90deg)}
.name{font-size:.92rem;font-weight:600}
.desc{color:var(--muted);font-size:.85rem;flex:1;min-width:0}
@media(max-width:620px){.desc{display:none}}
.pill{font-size:.72rem;font-weight:700;text-transform:uppercase;
  letter-spacing:.04em;padding:.2rem .6rem;border-radius:999px;white-space:nowrap}
.pill.s-clean{color:var(--ok);background:var(--ok-bg)}
.pill.s-findings{color:var(--warn);background:var(--warn-bg)}
.pill.s-error{color:var(--err);background:var(--err-bg)}
.body{border-top:1px solid var(--hair);padding:.4rem 1rem 1rem}
pre.out{font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:.8rem;
  line-height:1.5;background:var(--paper);border:1px solid var(--hair);
  border-radius:8px;padding:.8rem .9rem;overflow-x:auto;white-space:pre;
  max-height:460px;overflow-y:auto;margin:.6rem 0 0}
/* figure matrix */
.matrix-wrap{overflow-x:auto;margin:.6rem 0 0}
table.matrix{border-collapse:collapse;font-family:ui-monospace,Menlo,monospace;
  font-size:.82rem;min-width:420px}
table.matrix th,table.matrix td{border:1px solid var(--hair);padding:.32rem .5rem;
  text-align:center}
table.matrix th{background:var(--paper);color:var(--muted);font-weight:600}
table.matrix td.fig{text-align:left;white-space:nowrap;font-weight:600}
td.cell{font-weight:700}
td.cell.ok{color:var(--ok);background:var(--ok-bg)}
td.cell.weak{color:var(--warn);background:var(--warn-bg)}
td.cell.bad{color:var(--err);background:var(--err-bg)}
td.cell.na,td.cell.unk{color:var(--muted)}
.legend{font-size:.76rem;color:var(--muted);margin:.5rem 0 0}
footer{margin-top:2.4rem;padding-top:1.2rem;border-top:1px solid var(--hair);
  color:var(--muted);font-size:.82rem}
footer a{color:var(--accent)}
@media(prefers-reduced-motion:reduce){*{transition:none!important}}
"""

FILTER_JS = """
(function(){
  var btns=document.querySelectorAll('.controls button');
  function apply(mode){
    document.querySelectorAll('.card').forEach(function(c){
      var attn=!c.classList.contains('s-clean');
      c.style.display=(mode==='attn'&&!attn)?'none':'';
    });
    document.querySelectorAll('.group').forEach(function(g){
      var any=[].some.call(g.querySelectorAll('.card'),function(c){
        return c.style.display!=='none';});
      g.style.display=any?'':'none';
    });
    btns.forEach(function(b){b.setAttribute('aria-pressed',
      b.dataset.mode===mode);});
  }
  btns.forEach(function(b){b.addEventListener('click',function(){
    apply(b.dataset.mode);});});
})();
"""


def open_in_browser(path):
    """Open a written dashboard file in the default browser (a file:// URL).

    Returns True if a browser was launched. Safe on headless machines: any
    failure (no display, no browser) is swallowed and reported as False, so
    callers can fall back to just printing the path. Honours $BROWSER via the
    stdlib webbrowser module; set it to a no-op to suppress launching.
    """
    import webbrowser
    try:
        url = Path(path).resolve().as_uri()
        return webbrowser.open(url)
    except Exception:  # pragma: no cover - environment dependent
        return False


def esc(s):
    return html.escape(s or "")


def render_card(script, body, status):
    """Return the ``<details>`` card fragment for one linter: name, its
    one-line description, a status pill, and the expandable body (the figure
    matrix table for the figure linter, otherwise the raw output in a
    ``<pre>``)."""
    group, desc = LINTERS.get(script, ("Other", ""))
    label = {"clean": "clean", "findings": "findings",
             "error": "errors"}[status]
    matrix = figure_matrix_html(body) if script == "figure_lint_llm.py" else ""
    detail = matrix if matrix else \
        f"<pre class='out'>{esc(body) or 'No output.'}</pre>"
    return (
        f"<details class='card s-{status}'>"
        f"<summary><span class='name mono'>{esc(script)}</span>"
        f"<span class='desc'>{esc(desc)}</span>"
        f"<span class='pill s-{status}'>{label}</span></summary>"
        f"<div class='body'>{detail}</div></details>"
    )


def render(sections, summary, title, author, meta_line, body_only):
    """Assemble the whole report and return ``(html, n_flagged)``.

    Builds the summary tiles/bar, the filter controls, and the theme-grouped
    cards, wrapping them in a full HTML document unless ``body_only`` (then a
    ``<style>`` block plus markup only). ``n_flagged`` is the count of
    linters with findings or errors.
    """
    statuses = {sc: classify(sc, bd, summary) for sc, bd in sections}
    n = len(sections)
    n_clean = sum(1 for v in statuses.values() if v == "clean")
    n_find = sum(1 for v in statuses.values() if v == "findings")
    n_err = sum(1 for v in statuses.values() if v == "error")

    tiles = (
        f"<div class='tiles'>"
        f"<div class='tile'><div class='n'>{n}</div>"
        f"<div class='l'>Checks run</div></div>"
        f"<div class='tile ok'><div class='n'>{n_clean}</div>"
        f"<div class='l'>Clean</div></div>"
        f"<div class='tile warn'><div class='n'>{n_find}</div>"
        f"<div class='l'>With findings</div></div>"
        f"<div class='tile err'><div class='n'>{n_err}</div>"
        f"<div class='l'>Errors</div></div></div>"
    )

    def pct(x):
        return f"{(100.0 * x / n):.4f}%" if n else "0%"
    bar = (f"<div class='bar' role='img' aria-label='"
           f"{n_clean} clean, {n_find} findings, {n_err} errors'>"
           f"<span class='s-ok' style='width:{pct(n_clean)}'></span>"
           f"<span class='s-warn' style='width:{pct(n_find)}'></span>"
           f"<span class='s-err' style='width:{pct(n_err)}'></span></div>")

    controls = ("<div class='controls'><span class='desc'>Show:</span>"
                "<button data-mode='all' aria-pressed='true'>All checks"
                "</button><button data-mode='attn' aria-pressed='false'>"
                "Needs attention</button></div>")

    # group the cards
    by_group = {}
    for sc, bd in sections:
        g = LINTERS.get(sc, ("Other", ""))[0]
        by_group.setdefault(g, []).append((sc, bd))
    groups_html = []
    for g in GROUP_ORDER:
        if g not in by_group:
            continue
        cards = "".join(render_card(sc, bd, statuses[sc])
                        for sc, bd in by_group[g])
        groups_html.append(f"<section class='group'><h2>{esc(g)}</h2>"
                            f"{cards}</section>")

    header = (
        f"<header class='top'><p class='eyebrow'>Thesis linter report</p>"
        f"<h1 class='serif'>{esc(title)}</h1>"
        f"<p class='byline'>{author}</p></header>"
    )
    footer = (
        f"<footer><p>{esc(meta_line)}</p><p>Generated by the "
        f"<a href='https://ml-theses.org/assets/linters/'>ml-theses.org "
        f"linter suite</a>. "
        f"Figure rules: Rougier, Droettboom &amp; Bourne, &ldquo;Ten Simple "
        f"Rules for Better Figures&rdquo;, PLOS Comput Biol 2014.</p></footer>"
    )
    inner = (f"<div class='wrap'>{header}{tiles}{bar}{controls}"
             f"{''.join(groups_html)}{footer}</div>"
             f"<script>{FILTER_JS}</script>")
    if body_only:
        return f"<style>{CSS}</style>\n{inner}", (n_find + n_err)
    doc = (
        f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>Linter report &mdash; {esc(title)}</title>"
        f"<style>{CSS}</style></head><body>{inner}</body></html>"
    )
    return doc, (n_find + n_err)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Render a linter run as an HTML "
                                 "dashboard.")
    ap.add_argument("inputs", nargs="*", help="thesis.pdf (runs the suite)")
    ap.add_argument("--from-run", help="render a saved run_all_linters output")
    ap.add_argument("--llm", action="store_true", help="pass --llm to the suite")
    ap.add_argument("--bib", action="store_true", help="pass --bib to the suite")
    ap.add_argument("--title", default="Master's thesis")
    ap.add_argument("--author", default="")
    ap.add_argument("--meta", default="", help="footer meta line (run info)")
    ap.add_argument("--out", default="dashboard.html")
    ap.add_argument("--body-only", action="store_true",
                    help="emit page markup only, no document shell")
    ap.add_argument("--open", dest="open_", action="store_true",
                    help="open the written dashboard in the default browser")
    args = ap.parse_args(argv)

    if args.from_run:
        text = Path(args.from_run).read_text(encoding="utf-8", errors="replace")
    elif args.inputs:
        text = run_suite(args.inputs, args.llm, args.bib)
    else:
        ap.error("give a thesis.pdf to run, or --from-run <file>")

    sections, summary = parse_run(text)
    if not sections:
        sys.exit("error: no linter sections found in the run output")
    author = args.author or "&nbsp;"
    doc, n_flag = render(sections, summary, args.title, author,
                         args.meta, args.body_only)
    Path(args.out).write_text(doc, encoding="utf-8")
    print(f"[dashboard] wrote {args.out} ({len(sections)} linters, "
          f"{n_flag} with findings/errors)", file=sys.stderr)
    if args.open_ and not args.body_only:
        if open_in_browser(args.out):
            print(f"[dashboard] opened {args.out} in your browser",
                  file=sys.stderr)
        else:
            print(f"[dashboard] could not open a browser; open {args.out} "
                  f"manually", file=sys.stderr)
    return 1 if n_flag else 0


if __name__ == "__main__":
    raise SystemExit(main())
