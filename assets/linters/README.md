# Thesis linters

Command-line linters that check MSc thesis manuscripts (PDF or LaTeX
sources) against the writing instructions of
[ml-theses.org](https://ml-theses.org) — the thesis guide for students
supervised by Alex Jung at Aalto University.

All scripts are run with `python3 <script> ...` and print a findings
report; exit status is `0` when clean, `1` when findings exist, and `2` on
usage errors, so they can be scripted. The heuristic linters need at most
`pdftotext` (poppler) or PyMuPDF; the `*_llm` linters call the **Aalto AI
API** by default (`$AALTO_API_KEY`, Aalto network/VPN only — see
`aalto_llm.py`; `--base-url` switches to the Aalto LLM Gateway or any
OpenAI-style endpoint such as OpenRouter).

Run everything at once:

```sh
python3 run_all_linters.py thesis.pdf              # fast heuristic suite
python3 run_all_linters.py thesis.pdf --llm --bib  # + LLM + bibliography
```

## Coverage: ml-theses.org instruction → linter

### Manuscript preparation

| Instruction | Linter | How |
|---|---|---|
| Problem formulation: state what the data points are, how features and labels are defined | `thesis_checklist_llm.py` | LLM verdict `problem-formulation` with quoted evidence |
| Research scope/questions well-posed (clear, focused, specific, complex, feasible, relevant — per university guidance) | `rq_quality_lint_llm.py` | per-question criteria verdicts + scope checks (gap, delimitations, alignment) |
| Identify data sources and evaluation criteria | `thesis_checklist_llm.py` | verdict `data-sources-eval` |
| Explicitly state the training loss and, separately, the validation/test loss | `thesis_checklist_llm.py` | verdict `loss-functions` |
| Present and discuss numerical results thoroughly to answer your research questions | `research_questions_lint_llm.py` (per-question tracing), `thesis_checklist_llm.py` (global verdict `results-discussed`) | LLM |
| Use appropriate baselines or benchmarks | `thesis_checklist_llm.py` | verdict `baselines` |
| Begin each chapter/section with an introductory paragraph | `section_intro_lint_llm.py` (per-unit quality: does the intro map its subsections and tie them together), `thesis_checklist_llm.py` (verdict `section-intros`), `prose_lint_llm.py` (`unmotivated-section`) | LLM |
| Reference all numbered equations using `\eqref{}` | `math_typeset_lint.py` | `REF-NOT-EQREF` (LaTeX) |
| Only number equations that are referenced; all numbered equations, tables, figures referenced in the text | `unreferenced_entity_linter.py` | `UNREFERENCED`, `UNLABELED-EQ`, `UNLABELED-FLOAT` (LaTeX + PDF) |
| Present new methods as pseudocode | `thesis_checklist_llm.py` | verdict `pseudocode` |
| Model diagnosis via numerical experiments and mathematical analysis | `thesis_checklist_llm.py` | verdict `model-diagnosis` |
| Figures clear, labelled, informative captions | `figure_lint_llm.py` (rendered figures: font size, whitespace, contrast, axis labels), `caption_lint.py` (`SHORT-CAPTION`, `NO-CAPTION`), `thesis_checklist_llm.py` (verdict `captions-informative`) | pixels + vision LLM + heuristic |
| References formatted per IEEE guidelines | `citation_style_lint.py` | style/entry/citation checks (LaTeX + PDF) |
| Use terms defined in the Aalto Dictionary of ML | `terminology_lint.py` | `NON-DICTIONARY`, `TERM-MIX` (dictionary term listed first per cluster) |

### Typesetting mathematical texts

| Instruction | Linter | How |
|---|---|---|
| Inline math for short expressions; display math for central/referenced equations | `math_typeset_lint.py` | `LONG-INLINE` (+ `EQNARRAY` hygiene) |
| Punctuate displayed equations as part of the sentence | `math_typeset_lint.py` | `EQ-NO-PUNCT`, `EQ-PUNCT-CHECK` |

### Self-editing pass (prose linter)

| Instruction | Linter | How |
|---|---|---|
| Excessive forward referencing | `prose_lint.py` (`FORWARD-CUE`), `crossref_forward_lint.py` (floats defined pages later), `forward_ref_lint.py` / `forward_ref_lint_llm.py` (concepts used before defined) | heuristic + LLM |
| Undefined or re-defined acronyms | `acronym_lint.py` | `USED-BEFORE-EXPANSION`, `NEVER-EXPANDED`, `RE-EXPANDED` |
| Inconsistent terminology / synonym switching | `terminology_lint.py` (`TERM-MIX`), `prose_lint_llm.py` (`synonym-switch`) | heuristic + LLM |
| Vague quantifiers without a number | `prose_lint.py` (`VAGUE-QUANTIFIER`), `prose_lint_llm.py` | heuristic + LLM |
| Jargon / undefined evaluative claims ("smoothest convergence", "performs well") | `prose_lint.py` (`JARGON`), `prose_lint_llm.py` (`jargon`) | heuristic + LLM |
| Uncited claims (empirical/historical assertions need citations) | `prose_lint_llm.py` (`uncited-claim`); `bibliography_linter.py` verifies the cited references themselves | LLM + database lookup |
| Dangling references ("this shows" without antecedent) | `prose_lint.py` (`DANGLING-REFERENCE`), `prose_lint_llm.py` | heuristic + LLM |
| Unmotivated sections | `prose_lint_llm.py` (`unmotivated-section`), `thesis_checklist_llm.py` | LLM |
| Tense drift | `prose_lint_llm.py` (`tense-drift`) | LLM |

### Responsible use of AI, references quality

| Instruction | Linter | How |
|---|---|---|
| Disclose AI use in a dedicated statement (not in Methods) | `ai_disclosure_lint.py` | `NO-AI-STATEMENT`, `IN-METHODS` |
| Record the tool, version, and settings | `ai_disclosure_lint.py` | `NO-TOOL-NAMED`, `NO-VERSION` |
| Verify every (AI-generated) citation independently; use high-quality references | `bibliography_linter.py` | existence + author/title/venue checks vs Crossref/arXiv/DBLP; flags `PREPRINT`, `WEB-SOURCE`, `NOT-FOUND` |

### Not machine-checkable (process instructions)

Write literature review/methodology first, defer results chapters, write the
abstract last, keep a lab notebook, budget revision rounds, don't upload
confidential data to public AI services, accountability for content — these
concern *how you work*, not the manuscript text, so no linter can check
them. The closest proxy: run the suite before every revision round.

## The linters

| Script | Checks | Input | Needs |
|---|---|---|---|
| `bibliography_linter.py` | cited references exist; author/title/venue/year match Crossref/arXiv/DBLP | `.bib`, `.pdf` | network |
| `unreferenced_entity_linter.py` | numbered equations/tables/figures never referenced | `.tex`, `.pdf` | — |
| `crossref_forward_lint.py` | references to floats defined much later | `.pdf` | PyMuPDF |
| `forward_ref_lint.py` | concepts used before defined (regex) | `.pdf` | PyMuPDF |
| `forward_ref_lint_llm.py` | concepts used before defined (LLM) | `.pdf` | Aalto AI API |
| `acronym_lint.py` | acronym expanded at first use, no re-expansion | `.tex`, `.pdf` | — |
| `prose_lint.py` | vague quantifiers, dangling refs, forward cues | `.tex`, `.pdf` | — |
| `terminology_lint.py` | synonym mixing vs Aalto Dictionary terms | `.tex`, `.pdf` | — |
| `math_typeset_lint.py` | display-math punctuation, `\eqref`, long inline math | `.tex` | — |
| `citation_style_lint.py` | IEEE reference/citation format | `.tex`, `.pdf` | — |
| `caption_lint.py` | missing/too-short figure & table captions | `.tex`, `.pdf` | — |
| `ai_disclosure_lint.py` | dedicated AI-use statement with tool + version | `.tex`, `.pdf` | — |
| `thesis_checklist_llm.py` | 9-item manuscript-content checklist, PASS/FAIL + evidence | `.pdf` | Aalto AI API |
| `research_questions_lint_llm.py` | extracts each stated research question; judges whether it is answered, where, and on what evidence | `.pdf` | Aalto AI API |
| `rq_quality_lint_llm.py` | judges how well-posed the research questions/scope are, against university guideline criteria | `.pdf` | Aalto AI API |
| `figure_lint_llm.py` | visual figure quality: font sizes vs body text, whitespace, contrast, unlabeled axes, resolution | `.pdf` | PyMuPDF (+ Aalto AI API unless `--no-llm`) |
| `section_intro_lint_llm.py` | per chapter/section with subsections: does the intro summarize each subsection and how they tie together | `.pdf` | PyMuPDF + Aalto AI API |
| `prose_lint_llm.py` | LLM self-editing pass (uncited claims, tense drift, …) | `.tex`, `.pdf` | Aalto AI API |
| `run_all_linters.py` | runs everything above | either | — |

Shared modules: `lintutil.py` (text extraction, report format),
`aalto_llm.py` (Aalto AI API client; also used by the `*_llm` linters).

### Notes on individual linters

**`bibliography_linter.py`** — verifies that cited references exist and
match a real record. Findings include `NOT-FOUND` (possibly hallucinated),
`AUTHOR-MISMATCH`, `TITLE-DRIFT`, `VENUE-MISMATCH`, `PREPRINT`,
`YEAR-MISMATCH`. Results cached in `.bibcheck_cache.json`.

**`unreferenced_entity_linter.py`** — LaTeX mode flags `\label`s no
`\ref`/`\eqref`/`\cref` points to, numbered math without `\label`, captioned
floats without `\label`; PDF mode works from captions and right-aligned
equation numbers.

**`crossref_forward_lint.py`** — flags "as depicted in Figure 7" on page 3
when Figure 7 appears on page 21 (threshold: > 1 page forward by default).

**`forward_ref_lint.py` / `forward_ref_lint_llm.py`** — paragraph-level
conceptual forward references; the LLM version maintains a running
introduced-concept set, caches per paragraph
(`<input>.fwdref_cache.jsonl`, `--resume`).

**`terminology_lint.py`** — each synonym cluster lists the Aalto Dictionary
of ML term first; `TERM-MIX` fires only when two or more variants each occur
`--min-count` times.

**`thesis_checklist_llm.py`** — one LLM call over the full extracted text
(page markers included) returns PASS/FAIL/UNCLEAR per checklist item with a
quoted, page-referenced evidence snippet and a concrete fix for each FAIL.

**`prose_lint_llm.py`** — chunked LLM pass (`--chunk-chars`,
`--concurrency`, `--checks` to select categories, `--pages` for a partial
run).

**`figure_lint_llm.py`** — locates every figure via its caption, renders
the figure region at 144 dpi, and checks it two ways. Pixel heuristics
(work offline, `--no-llm`): `EXCESS-WHITESPACE` (blank-background fraction
above `--max-white`) and `LOW-RESOLUTION` (embedded raster below
`--min-dpi` at printed size). Vision LLM judgement (the rendered figure is
sent with the body-text font size as yardstick): `FONT-TOO-SMALL`,
`AXES-UNLABELED`, `OVERLAPPING-TEXT`, `LOW-CONTRAST`, `EXCESS-WHITESPACE`,
`ILLEGIBLE`. `--save-crops DIR` writes the judged renderings for
inspection; `--figures 3,7` restricts the run. On the Aalto LLM Gateway the
Qwen3-VL vision model is used automatically.

**`section_intro_lint_llm.py`** — for every chapter/section that has
subsections (outline from the PDF's embedded TOC), extracts the text
between the heading and the first subsection heading and judges it:
GOOD only if each subsection is framed as an upcoming part (explicit
section reference, ordinal enumeration, or forward-pointing phrasing) with
its content indicated, plus a connective thread. A thematic categorization
that never says which subsection treats which theme is judged WEAK — the
alignment exists only in hindsight. Uses the full GPT-5 model by default
(the mini tier lets near-miss intros pass). `--match 2.4` restricts to one
unit; `--levels 1,2` selects outline depths.

**`rq_quality_lint_llm.py`** — judges how well-posed the research
questions and scope are, against criteria compiled from authoritative
university guidance (the Monash University Library research-question
checklist — focused, researchable, feasible, specific, complex, relevant;
the George Mason University Writing Center criteria — clear, focused,
concise, complex, arguable; and the FINER framework). Per question:
STRONG/ADEQUATE/WEAK with the violated criteria named and a concrete
reformulation (a yes/no-formed engineering question with obvious
quantitative intent is treated as a minor form issue, not a defect).
Scope-level checks: gap identified, delimitations stated, question–
objective alignment, aim coverage. Uses the full GPT-5 model by default.

**`research_questions_lint_llm.py`** — extracts every explicitly stated
research question (RQ lists, hypotheses, numbered objectives) and judges
each one: ANSWERED / PARTIALLY-ANSWERED / UNANSWERED, where the answer is
developed, whether the presented results actually support it, and whether
the conclusions chapter revisits it. Warns on `NO-RQS` (none stated) and
`NOT-REVISITED`. Exit 1 unless every question is answered and revisited.

## Typical workflow for a new thesis PDF

```sh
python3 run_all_linters.py thesis.pdf              # fast pass, fix mechanics
python3 thesis_checklist_llm.py thesis.pdf         # content checklist
python3 research_questions_lint_llm.py thesis.pdf  # RQs answered?
python3 prose_lint_llm.py thesis.pdf               # deep prose pass
python3 bibliography_linter.py thesis.pdf          # verify references
```
