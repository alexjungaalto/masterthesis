# Thesis linters

Command-line linters that check MSc thesis manuscripts (PDF or LaTeX
sources) against the writing instructions of
[ml-theses.org](https://ml-theses.org) — the thesis guide for students
supervised by Alex Jung at Aalto University.

All scripts are run with `python3 <script> ...` and print a findings
report; exit status is `0` when clean, `1` when findings exist, and `2` on
usage errors, so they can be scripted.

## Setup

```sh
# one-time setup — the venv sidesteps pip's PEP 668
# "externally managed environment" refusal on Homebrew/Debian Python
python3 -m venv .venv && source .venv/bin/activate
pip install pymupdf          # needed by several PDF linters (see "Needs" column)
export AALTO_API_KEY=...     # *_llm linters only
```

If you skip the venv and plain `pip install pymupdf` is refused with an
"externally managed environment" error, use
`pip3 install --user --break-system-packages pymupdf`.

Linters whose "Needs" column below is empty read PDFs with `pdftotext`
(poppler: `brew install poppler` / `apt install poppler-utils`) or PyMuPDF,
whichever is available; the ones marked **PyMuPDF** need that package —
most exit with status 2 and an install hint without it.

The `*_llm` linters call the
**[Aalto AI API](https://www.aalto.fi/en/services/ai-services)** by
default (`$AALTO_API_KEY` — sign up for a key on the
[Aalto API developer portal](https://ai-apidev.aalto.fi/); Aalto
network/VPN only — see `aalto_llm.py`; `--base-url` switches to the
Aalto LLM Gateway or any OpenAI-style endpoint such as OpenRouter).
The exact model names on offer (GPT-5 family, e.g.
`gpt-5-mini-2025-08-07`) are listed on the
[AI APIs in Aalto](https://www.aalto.fi/en/services/ai-apis-in-aalto)
page (Aalto login required).

### Data handling

The `*_llm` linters send the **manuscript text (and, for the figure and
caption linters, figure images)** to the configured endpoint. A thesis
draft is *unpublished material*, so keep it on an Aalto-hosted gateway:

- **Default is compliant.** The Aalto AI API and the Aalto LLM Gateway
  run within Aalto's tenant; inputs are not shared with OpenAI and are
  not used to train models. This is the GDPR-compliant path Aalto policy
  requires for unpublished, confidential, or personal material — unlike
  public services such as ChatGPT.
- **Do not point `--base-url` at a public endpoint** (e.g. OpenRouter)
  for a real draft — that would send unpublished material to a public AI
  service, contrary to
  [Aalto's guidance](https://www.aalto.fi/en/services/responsible-use-of-artificial-intelligence-in-the-research-process).
  The client prints a warning when the endpoint is not Aalto-hosted.
- **Special-category personal data** (e.g. interview transcripts,
  human-subjects data embedded in the draft) needs a data-classification
  check before linting, even on the Aalto gateway.
- When running these on a student's draft, tell the student that
  supervisor feedback may be produced by routing their manuscript through
  this suite — the mirror image of the AI-use disclosure asked of them.

## Basic usage

Run one linter on a compiled thesis PDF (or run everything at once, below):

```sh
python3 acronym_lint.py thesis.pdf
```

```
== Acronym lint report
File: thesis.pdf

[WARN] NEVER-EXPANDED     p12    'INT4' used 11 time(s) but never expanded (first use at p12).
[WARN] USED-BEFORE-EXPANSION p9  'CNN' used on p9 but expanded only on p17.
```

Each finding line has four parts: a **severity** (`[ERROR]` almost
certainly a defect, fix it; `[WARN]` worth reviewing, occasionally a
false positive; `[INFO]` informational, no action required), a stable
**finding code** (the codes are listed per linter in the tables below),
the **location** (page `pNN` for PDF input, `file:line` for LaTeX
input), and the **evidence** — what was found and why it is flagged. A
clean run prints no finding lines and exits `0`; findings exit `1`;
missing input or dependencies exit `2`.

Run everything at once:

```sh
python3 run_all_linters.py thesis.pdf              # fast heuristic suite
python3 run_all_linters.py thesis.pdf --llm --bib  # + LLM + bibliography
```

`run_all_linters.py` prints each linter's report followed by a one-line
per-linter summary (`clean` / `findings` / `error`).

## Coverage: ml-theses.org instruction → linter

### Manuscript preparation

| Instruction | Linter | How |
|---|---|---|
| Problem formulation: data points,<br>features, labels defined | `thesis_checklist_llm.py` | verdict `problem-formulation`<br>with quoted evidence |
| Research scope/questions well-posed<br>(clear, focused, specific, complex,<br>feasible, relevant) | `rq_quality_lint_llm.py` | per-question criteria verdicts<br>+ scope checks (gap,<br>delimitations, alignment) |
| Identify data sources and evaluation criteria | `thesis_checklist_llm.py` | verdict `data-sources-eval` |
| Training loss and validation/test<br>loss explicitly stated | `thesis_checklist_llm.py` | verdict `loss-functions` |
| Per studied method: training,<br>validation and test set construction<br>described, and the method diagnosed<br>on that split | `data_split_lint_llm.py` | enumerates the trained methods,<br>then per method: `train-set`,<br>`validation-set`, `test-set`,<br>`diagnosis-on-split` verdicts |
| Numerical results answer the<br>research questions | `research_questions_lint_llm.py`<br>`thesis_checklist_llm.py` | per-question tracing<br>global verdict `results-discussed` |
| Use appropriate baselines or benchmarks | `thesis_checklist_llm.py` | verdict `baselines` |
| Chapter/section introductions | `section_intro_lint_llm.py`<br>`thesis_checklist_llm.py`<br>`prose_lint_llm.py` | intro maps its subsections<br>verdict `section-intros`<br>`unmotivated-section` |
| Reference all numbered equations using `\eqref{}` | `math_typeset_lint.py` | `REF-NOT-EQREF` (LaTeX) |
| All numbered equations, tables,<br>figures referenced in the text | `unreferenced_entity_linter.py` | `UNREFERENCED`, `UNLABELED-EQ`,<br>`UNLABELED-FLOAT` (LaTeX + PDF) |
| Present new methods as pseudocode | `thesis_checklist_llm.py` | verdict `pseudocode` |
| Model diagnosis via numerical experiments and mathematical analysis | `thesis_checklist_llm.py` | verdict `model-diagnosis` |
| Figures clear, labelled,<br>informative captions | `figure_lint_llm.py`<br>`caption_lint.py`<br>`caption_lint_llm.py`<br>`thesis_checklist_llm.py` | rendered figures: fonts, whitespace,<br>contrast, axes (pixels + vision LLM)<br>`SHORT-CAPTION`, `NO-CAPTION`<br>`WEAK-CAPTION` (per-caption LLM)<br>verdict `captions-informative` |
| References formatted per IEEE guidelines | `citation_style_lint.py` | style/entry/citation checks (LaTeX + PDF) |
| Terms from the Aalto<br>Dictionary of ML | `terminology_lint.py` | `NON-DICTIONARY`, `TERM-MIX`<br>(dictionary term first per cluster) |
| Every chapter/section has zero<br>or >= 2 subdivisions | `structure_lint.py` | `LONE-CHILD` (LaTeX + PDF) |

### Typesetting mathematical texts

| Instruction | Linter | How |
|---|---|---|
| Inline math for short expressions; display math for central/referenced equations | `math_typeset_lint.py` | `LONG-INLINE` (+ `EQNARRAY` hygiene) |
| Punctuate displayed equations as part of the sentence | `math_typeset_lint.py` | `EQ-NO-PUNCT`, `EQ-PUNCT-CHECK` |

### Self-editing pass (prose linter)

| Instruction | Linter | How |
|---|---|---|
| Excessive forward referencing | `prose_lint.py`<br>`crossref_forward_lint.py`<br>`forward_ref_lint.py`<br>`forward_ref_lint_llm.py` | `FORWARD-CUE` phrases<br>floats defined pages later<br>concepts used before defined<br>(regex and LLM variants) |
| Undefined or re-defined acronyms | `acronym_lint.py` | `USED-BEFORE-EXPANSION`, `NEVER-EXPANDED`, `RE-EXPANDED` |
| Inconsistent terminology /<br>synonym switching | `terminology_lint.py`<br>`prose_lint_llm.py` | `TERM-MIX`<br>`synonym-switch` |
| Vague quantifiers without a number | `prose_lint.py`<br>`prose_lint_llm.py` | `VAGUE-QUANTIFIER`<br>`vague-quantifier` |
| Jargon / undefined evaluative claims<br>("smoothest convergence") | `prose_lint.py`<br>`prose_lint_llm.py` | `JARGON`<br>`jargon` |
| Uncited claims | `prose_lint_llm.py`<br>`bibliography_linter.py` | `uncited-claim`<br>verifies the cited references |
| Dangling references<br>("this shows" without antecedent) | `prose_lint.py`<br>`prose_lint_llm.py` | `DANGLING-REFERENCE`<br>`dangling-reference` |
| Unmotivated sections | `prose_lint_llm.py`<br>`thesis_checklist_llm.py` | `unmotivated-section`<br>verdict `section-intros` |
| Tense drift | `prose_lint_llm.py` (`tense-drift`) | LLM |
| Broken idioms ("corner cuttings<br>on safety") | `prose_lint_llm.py` (`broken-idiom`) | LLM |
| Informal register ("a bunch of",<br>contractions) | `prose_lint_llm.py` (`informal-register`) | LLM |
| Category errors (an algorithm named<br>where a metric is meant) | `prose_lint_llm.py` (`category-error`) | LLM |
| Empty buzzwords ("framework",<br>"leverage", unearned "robust") | `prose_lint_llm.py` (`empty-buzzword`) | LLM |
| Section openers stand alone;<br>no narrative jumps between paragraphs | `flow_lint_llm.py` | `OPAQUE-OPENER` (judged without<br>the preceding text), `FLOW-BREAK` |

### Responsible use of AI, references quality

| Instruction | Linter | How |
|---|---|---|
| Disclose AI use in a dedicated statement (not in Methods) | `ai_disclosure_lint.py` | `NO-AI-STATEMENT`, `IN-METHODS` |
| Record the tool, version, and settings | `ai_disclosure_lint.py` | `NO-TOOL-NAMED`, `NO-VERSION` |
| Citations verified;<br>high-quality references | `bibliography_linter.py` | existence + author/title/venue vs<br>Crossref/arXiv/DBLP; `PREPRINT`,<br>`WEB-SOURCE`, `NOT-FOUND` |

### Not machine-checkable (process instructions)

Write literature review/methodology first, defer results chapters, write the
abstract last, keep a lab notebook, budget revision rounds, don't upload
confidential data to public AI services, accountability for content — these
concern *how you work*, not the manuscript text, so no linter can check
them. The closest proxy: run the suite before every revision round.

## The linters

| Script | Checks | Input | Needs |
|---|---|---|---|
| `bibliography_linter.py` | cited references exist; author/title/<br>venue/year match Crossref/arXiv/DBLP | `.bib`, `.pdf` | network |
| `structure_lint.py` | sectioning units with exactly one subdivision | `.tex`, `.pdf` | — |
| `unreferenced_entity_linter.py` | numbered equations/tables/figures never referenced | `.tex`, `.pdf` | — |
| `crossref_forward_lint.py` | references to floats defined much later | `.pdf` | PyMuPDF |
| `forward_ref_lint.py` | concepts used before defined (regex) | `.pdf` | PyMuPDF |
| `forward_ref_lint_llm.py` | concepts used before defined (LLM) | `.pdf` | PyMuPDF +<br>Aalto AI API |
| `acronym_lint.py` | acronym expanded at first use, no re-expansion | `.tex`, `.pdf` | — |
| `prose_lint.py` | vague quantifiers, dangling refs, forward cues | `.tex`, `.pdf` | — |
| `terminology_lint.py` | synonym mixing vs Aalto Dictionary terms | `.tex`, `.pdf` | — |
| `math_typeset_lint.py` | display-math punctuation, `\eqref`, long inline math | `.tex` | — |
| `citation_style_lint.py` | IEEE reference/citation format | `.tex`, `.pdf` | — |
| `caption_lint.py` | missing/too-short figure & table captions | `.tex`, `.pdf` | — |
| `caption_lint_llm.py` | per-caption quality: states what's shown,<br>defines quantities, self-contained,<br>sentence form | `.tex`, `.pdf` | Aalto AI API |
| `ai_disclosure_lint.py` | dedicated AI-use statement with tool + version | `.tex`, `.pdf` | — |
| `thesis_checklist_llm.py` | 9-item manuscript checklist,<br>PASS/FAIL + evidence | `.pdf` | Aalto AI API |
| `data_split_lint_llm.py` | per studied ML method:<br>train/validation/test set construction<br>and diagnosis on that split | `.pdf` | Aalto AI API |
| `research_questions_lint_llm.py` | each stated research question:<br>answered? where? on what evidence? | `.pdf` | Aalto AI API |
| `rq_quality_lint_llm.py` | how well-posed are research questions<br>and scope (university criteria)? | `.pdf` | Aalto AI API |
| `figure_lint_llm.py` | figure quality: fonts vs body text,<br>whitespace, contrast, axes, resolution,<br>raw screenshots as figures | `.pdf` | PyMuPDF<br>(+ Aalto AI API<br>unless `--no-llm`) |
| `section_intro_lint_llm.py` | does each chapter/section intro map<br>its subsections and tie them together? | `.pdf` | PyMuPDF +<br>Aalto AI API |
| `type_consistency_lint_llm.py` | formal claims well-typed: relations over<br>same-type operands, values in range,<br>dimensionless quantities unit-free<br>(`TYPE-MISMATCH`, `RANGE`, `DIMENSION`,<br>`BRIDGE-LOOSE`) | `.pdf` | Aalto AI API |
| `flow_lint_llm.py` | narrative flow: section openers that<br>stand alone, no paragraph-to-paragraph<br>discontinuities | `.pdf` | PyMuPDF +<br>Aalto AI API |
| `prose_lint_llm.py` | LLM self-editing pass (uncited<br>claims, tense drift, jargon, …) | `.tex`, `.pdf` | Aalto AI API |
| `run_all_linters.py` | runs everything above | either | — |

Shared modules: `lintutil.py` (text extraction, report format),
`aalto_llm.py` (Aalto AI API client; also used by the `*_llm` linters).

Maintainer note: this directory (`assets/linters/` in the masterthesis
repo) is the single source of truth for the linter suite; edit here,
then commit and push this repo to deploy to ml-theses.org.

### Notes on individual linters

**`bibliography_linter.py`** — verifies that cited references exist and
match a real record. Findings include `NOT-FOUND` (possibly hallucinated),
`AUTHOR-MISMATCH`, `TITLE-DRIFT`, `VENUE-MISMATCH`, `PREPRINT`,
`YEAR-MISMATCH`. Results cached in `.bibcheck_cache.json`.

**`unreferenced_entity_linter.py`** — LaTeX mode flags `\label`s no
`\ref`/`\eqref`/`\cref` points to, numbered math without `\label`, captioned
floats without `\label`; PDF mode works from captions and right-aligned
equation numbers.

**`structure_lint.py`** — a lone subdivision cannot articulate a division:
`LONE-CHILD` flags a chapter with a single section, a section with a single
subsection, etc. PDF mode prefers the embedded bookmark outline (PyMuPDF)
and falls back to scanning extracted text for numbered headings; LaTeX mode
parses the sectioning commands (starred variants are unnumbered and
skipped).

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

**`data_split_lint_llm.py`** — where `thesis_checklist_llm.py` judges the
manuscript globally (one `loss-functions` / `model-diagnosis` verdict for
the whole thesis), this linter works per studied ML method. One LLM call
first enumerates the methods the thesis actually *trains* (methods only
named in related work are excluded), then for each emits `train-set`,
`validation-set`, `test-set`, and `diagnosis-on-split` verdicts
(PASS/FAIL/UNCLEAR) with page-referenced evidence and a fix for each FAIL.
`validation-set` also passes when a method legitimately needs no held-out
validation set and the thesis says so.

**`prose_lint_llm.py`** — chunked LLM pass (`--chunk-chars`,
`--concurrency`, `--checks` to select categories, `--pages` for a partial
run).

**`caption_lint_llm.py`** — judges every figure/table caption against
Rule 4 ("Captions Are Not Optional") of the PLOS ["Ten Simple Rules for
Better Figures"](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1003833):
states what's shown, defines the quantities/symbols it mentions,
self-contained for a figure-skimming reader, proper sentence form
(a caption like "wibson protocol visualized" fails on all four). One
`WEAK-CAPTION` per deficient caption with the violated criteria and a
suggested rewrite. Uses the full GPT-5 model by default; `--match 4`
restricts to one figure, `--per-batch`/`--concurrency` tune the calls.

**`figure_lint_llm.py`** — locates every figure via its caption, renders
the figure region at 144 dpi, and checks it two ways. Pixel heuristics
(work offline, `--no-llm`): `EXCESS-WHITESPACE` (blank-background fraction
above `--max-white`) and `LOW-RESOLUTION` (embedded raster below
`--min-dpi` at printed size). Vision LLM judgement (the rendered figure is
sent with the body-text font size as yardstick): `FONT-TOO-SMALL`,
`AXES-UNLABELED`, `OVERLAPPING-TEXT`, `LOW-CONTRAST`, `EXCESS-WHITESPACE`,
`SCREENSHOT` (raw IDE/terminal/application capture in place of a prepared
figure or table, noting non-English interface text), `ILLEGIBLE`. `--save-crops DIR` writes the judged renderings for
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

**`flow_lint_llm.py`** — two checks on the manuscript as a narrative.
`opener`: the first sentence(s) after every chapter/section heading are
judged WITHOUT the preceding text — exactly like a reader entering at
the heading — and flagged `OPAQUE-OPENER` when they hang on an
antecedent across the heading (a bare pronoun, or a definite noun
phrase like "A difference of almost an order of magnitude
illustrates ..."); named references ("as shown in Section 2.3") and
deixis to the unit itself are fine. Judged with the full GPT-5 model
(one call per heading, `--levels 1,2,3`). `flow`: overlapping windows
of consecutive paragraphs are scanned for non-sequitur transitions and
paragraphs that presuppose not-yet-introduced material (`FLOW-BREAK`);
headings legitimately reset the narrative and float furniture is
skipped. Complements `section_intro_lint_llm.py` (which judges only
units WITH subsections) and the `dangling-reference` checks (which only
see pronoun anaphora, and judge resolvability in-chunk rather than
from the heading).

**`rq_quality_lint_llm.py`** — judges how well-posed the research
questions and scope are, against criteria compiled from authoritative
university guidance (the [Monash University Library research-question
checklist](https://www.monash.edu/library/help/assignments-research/developing-research-questions)
— focused, researchable, feasible, specific, complex, relevant;
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
python3 data_split_lint_llm.py thesis.pdf          # per-method train/val/test + diagnosis
python3 research_questions_lint_llm.py thesis.pdf  # RQs answered?
python3 prose_lint_llm.py thesis.pdf               # deep prose pass
python3 type_consistency_lint_llm.py thesis.pdf    # type/range/dimension of formal claims
python3 bibliography_linter.py thesis.pdf          # verify references
```
