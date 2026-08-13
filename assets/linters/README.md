# Thesis linters

Command-line linters that check MSc thesis manuscripts (PDF or LaTeX
sources) against the writing instructions of
[ml-theses.org](https://ml-theses.org) — the thesis guide for students
supervised by Alex Jung at Aalto University. Pass `--profile paper` to lint
an IEEE/ACM-style conference or journal draft instead of a thesis (see
[Profiles](#profiles-thesis-vs-research-paper) below).

All scripts are run with `python3 <script> ...` and print a findings
report; exit status is `0` when clean, `1` when findings exist, and `2` on
usage errors, so they can be scripted.

## Quick start

```sh
# 1. get the suite
git clone https://github.com/alexjungaalto/masterthesis.git
cd masterthesis/assets/linters

# 2. one-time setup
python3 -m venv .venv && source .venv/bin/activate
pip install pymupdf                       # some PDF linters need it

# 3. fast heuristic pass (no LLM, no network) over a compiled PDF
python3 run_all_linters.py thesis.pdf

# 4. optional: add the LLM + bibliography linters
export AALTO_API_KEY=...                   # key from the Aalto API dev portal
python3 run_all_linters.py thesis.pdf --llm --bib
```

Linting a conference/journal draft instead of a thesis? Add
`--profile paper` (see [Profiles](#profiles-thesis-vs-research-paper)).
The rest of this page documents each linter, the data-handling rules for
the LLM linters, and how every ml-theses.org instruction maps to a check.

## Getting the scripts

All linters live in one directory —
[`assets/linters/`](https://github.com/alexjungaalto/masterthesis/tree/main/assets/linters)
in the masterthesis repo. Two ways to get them:

- **The whole suite (recommended)** — clone or download the repo and work
  inside `assets/linters/`:
  ```sh
  git clone https://github.com/alexjungaalto/masterthesis.git
  cd masterthesis/assets/linters
  ```
- **A single script** — each one is served on the website at its own URL,
  e.g. <https://ml-theses.org/assets/linters/prose_lint.py>. Download it (and
  the shared helper) with `curl`:
  ```sh
  curl -O https://ml-theses.org/assets/linters/prose_lint.py
  curl -O https://ml-theses.org/assets/linters/lintutil.py   # shared helper
  curl -O https://ml-theses.org/assets/linters/aalto_llm.py  # for *_llm scripts
  ```

Most linters import `lintutil.py`, and the `*_llm` ones import
`aalto_llm.py` (a few linters use only one of the two — e.g.
`figure_lint_llm.py` and `section_intro_lint_llm.py` need `aalto_llm.py`
but not `lintutil.py`). Keeping both helpers alongside the scripts covers
every linter, so grab both when you download a single script.

## Setup

```sh
# one-time setup — the venv sidesteps pip's PEP 668
# "externally managed environment" refusal on Homebrew/Debian Python
python3 -m venv .venv && source .venv/bin/activate
pip install pymupdf          # needed by several PDF linters (see "Needs" column)
export AALTO_API_KEY=...     # *_llm linters only
```

If you skip the venv and plain `pip install pymupdf` is refused with an
"externally managed environment" error (PEP 668), use
`pip3 install --user --break-system-packages pymupdf` instead — this works
on e.g. Aalto's JupyterHub.

Linters whose "Needs" column below is empty read PDFs with `pdftotext`
(poppler: `brew install poppler` / `apt install poppler-utils`) or PyMuPDF,
whichever is available; the ones marked **PyMuPDF** need that package —
most exit with status 2 and an install hint without it.

The `*_llm` linters call the
**[Aalto AI API](https://www.aalto.fi/en/services/ai-services)** by
default (`$AALTO_API_KEY` — sign up for a key on the
[Aalto API developer portal](https://ai-apidev.aalto.fi/); Aalto
network/VPN only — see `aalto_llm.py`; `--base-url` switches to the
Aalto LLM Gateway, a local on-device server, or any OpenAI-style
endpoint such as OpenRouter).
The exact model names on offer (GPT-5 family, e.g.
`gpt-5-mini-2025-08-07`) are listed on the
[Aalto AI APIs | Aalto University](https://www.aalto.fi/en/services/ai-apis-in-aalto)
page (Aalto login required).

### Data handling

The `*_llm` linters send the **manuscript text (and, for the figure and
caption linters, figure images)** to the configured endpoint. A thesis
draft is *unpublished material*, so keep it on an Aalto-hosted gateway:

- **Default keeps the draft on Aalto infrastructure.** The Aalto AI API
  and the Aalto LLM Gateway run within Aalto's tenant. Per Aalto's own
  description of these services, inputs are processed under Aalto's
  agreement and are not used to train the provider's models; this is the
  route Aalto recommends for unpublished, confidential, or personal
  material, unlike public services such as ChatGPT. For the authoritative
  terms, data classification, and GDPR position, check the
  [Aalto AI services](https://www.aalto.fi/en/services/ai-services) and
  [responsible use of AI in research](https://www.aalto.fi/en/services/responsible-use-of-artificial-intelligence-in-the-research-process)
  pages — they, not this README, are the source of truth.
- **A local on-device model is also compliant — and the most private.**
  Point `--base-url` at a server running on your own machine (e.g.
  `mlx_lm.server` on Apple Silicon, or Ollama — both expose an
  OpenAI-style `/v1/chat/completions` API); the manuscript never leaves
  the device, so no network, VPN, or key is needed. The client
  recognises `localhost` / `127.0.0.1` as a trusted endpoint and prints
  no warning. Use a capable model for quality on par with the gateway —
  a ~14B model such as `Qwen3-14B` handles the chunked linters (prose,
  flow, section-intro, caption) well; the whole-thesis linters
  (`thesis_checklist_llm`, `research_questions_lint_llm`,
  `rq_quality_lint_llm`, `type_consistency_lint_llm`) need more context
  and memory, and `figure_lint_llm` needs a vision model (Qwen3-VL).
  Very small models (≤2B) miss real defects — validate before relying on
  them. Example:
  ```sh
  mlx_lm.server --model mlx-community/Qwen3-14B-4bit --port 8080 &
  export LLM_BASE_URL=http://localhost:8080/v1
  export LLM_MODEL=mlx-community/Qwen3-14B-4bit
  python3 prose_lint_llm.py thesis.pdf
  ```
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
false positive; `[INFO]` a low-priority heads-up — usually fine, but may
ask you to eyeball something, e.g. confirm a pronoun's antecedent), a stable
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

## Profiles: thesis vs. research paper

The suite targets MSc theses by default, but a thesis and a conference/
journal paper are the same object — an ML manuscript — and ~14 of the
linters (prose, acronym, terminology, math, captions, figures, flow,
forward-references, citations, unreferenced entities, type-consistency)
apply verbatim to either. Pass `--profile paper` to lint an IEEE/ACM-style
paper draft instead:

```sh
python3 run_all_linters.py paper.pdf --profile paper --llm
```

`--profile thesis` is the default and changes nothing. `--profile paper`
adapts the suite in three ways:

- **Skipped** (thesis-only): `ai_disclosure_lint.py` (IEEE/ACM do not mandate
  a disclosure statement) and `thesis_checklist_llm.py`.
- **Swapped in**: `paper_checklist_llm.py` — the reviewer-facing content
  checklist (contributions, novelty positioning, claims-supported,
  reproducibility, limitations, venue-gated ethics; see below).
- **Adapted in place** (these five take a `--profile` flag of their own, so
  they behave the same run standalone):

  | Linter | `--profile paper` change |
  |---|---|
  | `structure_lint.py` | `LONE-CHILD` downgraded to `INFO` (a two-column paper legitimately has single-subsection sections) |
  | `citation_style_lint.py` | takes `--venue` (default `ieee`); non-IEEE venues skip the IEEE-specific checks rather than misflag them |
  | `data_split_lint_llm.py` | counts only methods the authors themselves train; pretrained/off-the-shelf models used as-is are out of scope |
  | `research_questions_lint_llm.py` | accepts an enumerated contributions list as the unit; drops the thesis-only "revisited in conclusions" penalty |
  | `rq_quality_lint_llm.py` | judges the problem statement + contributions by the same criteria when no explicit research questions are stated |

Venue defaults to IEEE. The paper checklist takes `--venue neurips|acl|…` to
require a broader-impact/ethics statement; for `ieee`/`acm` that item passes
by default.

For a **dashboard** instead of console text, pipe a run through
`dashboard.py`, which renders it as one self-contained HTML page — a summary
band, an expandable card per linter grouped by theme, and the figure linter's
figures × ten-rules matrix as a colour-coded table (works offline, light or
dark):

```bash
python3 dashboard.py thesis.pdf --llm --bib --out dashboard.html
python3 dashboard.py --from-run saved_run.txt --title "..." --out dash.html
```

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

## Coverage: ml-theses.org instruction → linter

### Manuscript preparation

| Instruction | Linter | How |
|---|---|---|
| Problem formulation: data points,<br>features, labels defined | `thesis_checklist_llm.py` | verdict `problem-formulation`<br>with quoted evidence |
| Research scope/questions well-posed<br>(clear, focused, specific, complex,<br>feasible, relevant, self-contained) | `rq_quality_lint_llm.py` | per-question criteria verdicts<br>+ scope checks (gap,<br>delimitations, alignment) |
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
| Figures clear, labelled,<br>informative captions | `figure_lint_llm.py`<br>`caption_lint.py`<br>`caption_lint_llm.py`<br>`thesis_checklist_llm.py` | rendered figures scored against the<br>PLOS Ten Simple Rules (figures × rules<br>matrix; pixels + vision LLM)<br>`SHORT-CAPTION`, `NO-CAPTION`<br>`WEAK-CAPTION` (per-caption LLM)<br>verdict `captions-informative` |
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
| Excessive forward referencing | `prose_lint.py`<br>`crossref_forward_lint.py`<br>`forward_ref_lint.py`<br>`forward_ref_lint_llm.py` | `FORWARD-CUE` phrases<br>floats (figures/tables) defined pages later<br>concepts used before defined<br>(regex and LLM variants) |
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
| Type / range / dimension mismatches<br>in formal claims | `type_consistency_lint_llm.py` | `TYPE-MISMATCH`, `RANGE`,<br>`DIMENSION`, `BRIDGE-LOOSE` |

### Responsible use of AI, references quality

| Instruction | Linter | How |
|---|---|---|
| Disclose AI use in a dedicated statement (not in Methods) | `ai_disclosure_lint.py` | `NO-AI-STATEMENT`, `IN-METHODS` |
| Record the tool, version, and settings | `ai_disclosure_lint.py` | `NO-TOOL-NAMED`, `NO-VERSION` |
| Citations verified;<br>high-quality references | `bibliography_linter.py` | existence + author/title/venue vs<br>Crossref/arXiv/DBLP; `PREPRINT`,<br>`WEB-SOURCE`, `NOT-FOUND` |

### Not machine-checkable (process instructions)

Some instructions concern *how you work*, not the finished manuscript, so no
linter can check them:

- **The writing process itself** — a linter only sees the compiled PDF, so it
  cannot tell whether an expected section is missing, nor in what order the
  chapters were written.
- **Keeping a lab notebook** and **budgeting enough revision rounds**.
- **Not uploading confidential data to public AI services.**
- **Accountability for the content** — the text and its claims remain yours.

The closest proxy: run the suite before every revision round.

## The linters

| Script | Checks | Input | Needs |
|---|---|---|---|
| [`bibliography_linter.py`](bibliography_linter.py) | cited references exist; author/title/<br>venue/year match Crossref/arXiv/DBLP | `.bib`, `.pdf` | network |
| [`structure_lint.py`](structure_lint.py) | sectioning units with exactly one subdivision | `.tex`, `.pdf` | — |
| [`unreferenced_entity_linter.py`](unreferenced_entity_linter.py) | numbered equations/tables/figures never referenced | `.tex`, `.pdf` | — |
| [`crossref_forward_lint.py`](crossref_forward_lint.py) | references to floats (figures, tables,<br>algorithms) defined many pages later | `.pdf` | PyMuPDF |
| [`forward_ref_lint.py`](forward_ref_lint.py) | concepts used before defined (regex) | `.pdf` | PyMuPDF |
| [`forward_ref_lint_llm.py`](forward_ref_lint_llm.py) | concepts used before defined (LLM) | `.pdf` | PyMuPDF +<br>Aalto AI API |
| [`acronym_lint.py`](acronym_lint.py) | acronym expanded at first use, no re-expansion | `.tex`, `.pdf` | — |
| [`prose_lint.py`](prose_lint.py) | vague quantifiers, dangling refs, forward cues | `.tex`, `.pdf` | — |
| [`unresolved_reference_lint.py`](unresolved_reference_lint.py) | uncited appeals to companion/forthcoming<br>studies; label-code schemes (R1, T6, …)<br>used without a definition in the text | `.tex`, `.pdf` | — |
| [`terminology_lint.py`](terminology_lint.py) | synonym mixing vs Aalto Dictionary terms | `.tex`, `.pdf` | — |
| [`math_typeset_lint.py`](math_typeset_lint.py) | display-math punctuation, `\eqref`, long inline math | `.tex` | — |
| [`citation_style_lint.py`](citation_style_lint.py) | IEEE reference/citation format | `.tex`, `.pdf` | — |
| [`caption_lint.py`](caption_lint.py) | missing/too-short figure & table captions | `.tex`, `.pdf` | — |
| [`caption_lint_llm.py`](caption_lint_llm.py) | per-caption quality: states what's shown,<br>defines quantities, self-contained,<br>sentence form | `.tex`, `.pdf` | Aalto AI API |
| [`ai_disclosure_lint.py`](ai_disclosure_lint.py) | dedicated AI-use statement with tool + version | `.tex`, `.pdf` | — |
| [`thesis_checklist_llm.py`](thesis_checklist_llm.py) | 9-item manuscript checklist,<br>PASS/FAIL + evidence (thesis profile) | `.pdf` | Aalto AI API |
| [`paper_checklist_llm.py`](paper_checklist_llm.py) | reviewer content checklist for a<br>research paper, PASS/FAIL + evidence<br>(paper profile; venue-gated ethics item) | `.pdf` | Aalto AI API |
| [`related_work_faithfulness_llm.py`](related_work_faithfulness_llm.py) | finds the <=3 most-related works and<br>checks the draft represents them<br>faithfully against their real abstracts | `.pdf` | Aalto AI API<br>+ OpenAlex |
| [`data_split_lint_llm.py`](data_split_lint_llm.py) | per studied ML method:<br>train/validation/test set construction<br>and diagnosis on that split | `.pdf` | Aalto AI API |
| [`research_questions_lint_llm.py`](research_questions_lint_llm.py) | each stated research question:<br>answered? where? on what evidence? | `.pdf` | Aalto AI API |
| [`rq_quality_lint_llm.py`](rq_quality_lint_llm.py) | how well-posed are research questions<br>and scope (university criteria)? | `.pdf` | Aalto AI API |
| [`figure_lint_llm.py`](figure_lint_llm.py) | figures scored against the PLOS<br>Ten Simple Rules for Better Figures<br>(figures × ten-rules matrix) | `.pdf` | PyMuPDF<br>(+ Aalto AI API<br>unless `--no-llm`) |
| [`section_intro_lint_llm.py`](section_intro_lint_llm.py) | does each chapter/section intro map<br>its subsections and tie them together? | `.pdf` | PyMuPDF +<br>Aalto AI API |
| [`type_consistency_lint_llm.py`](type_consistency_lint_llm.py) | formal claims well-typed: relations over<br>same-type operands, values in range,<br>dimensionless quantities unit-free<br>(`TYPE-MISMATCH`, `RANGE`, `DIMENSION`,<br>`BRIDGE-LOOSE`) | `.pdf` | Aalto AI API |
| [`flow_lint_llm.py`](flow_lint_llm.py) | narrative flow: section openers that<br>stand alone, no paragraph-to-paragraph<br>discontinuities | `.pdf` | PyMuPDF +<br>Aalto AI API |
| [`prose_lint_llm.py`](prose_lint_llm.py) | LLM self-editing pass (uncited<br>claims, tense drift, jargon, …) | `.tex`, `.pdf` | Aalto AI API |
| [`run_all_linters.py`](run_all_linters.py) | runs everything above | either | — |
| [`dashboard.py`](dashboard.py) | renders a run as a self-contained HTML dashboard | either | — |

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

**`crossref_forward_lint.py`** — a *float* is a figure, table, or algorithm,
which LaTeX positions ("floats") wherever it fits rather than exactly where
you place it. This linter flags "as depicted in Figure 7" on page 3 when
Figure 7 appears on page 21 (threshold: > 1 page forward by default).

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

**`unresolved_reference_lint.py`** — catches two pointers that send the reader
to something they cannot inspect, and that slip past the other linters.
`COMPANION-REF`: an uncited appeal to a *companion / separate / forthcoming /
related* study that carries part of the argument (e.g. "the remaining nine are
evaluated in companion studies") — cited sentences ([n] / `\cite`) are not
flagged, since the reader can then find the work. `UNDEFINED-CODE`: a scheme of
short label codes (R1, T6, RQ2, …) used as load-bearing shorthand but never
defined; a code counts as defined when it appears with a gloss ("R1 (Fault
Containment)", "R1: …", "R1 — …") or a defining keyword, while a bare range
"(R1–R5)" does not define its members. To stay precise the code check requires
a prefix to have ≥ 2 distinct small-numbered members and to sit near a scheme
keyword (criteria/requirement/research question/…) or have ≥ `--min-members`
members, so the "L1"/"L2" norms, an "R2" (R-squared) or "F1" score, an "S3"
bucket, or a "CO2" reading are not mistaken for a scheme. The forward-reference
linters model concepts defined LATER IN THE SAME document, not appeals to
external papers, so this check is complementary.

**`related_work_faithfulness_llm.py`** — goes beyond checking that a related
work is *cited* (`bibliography_linter.py`) or that novelty is *asserted*
(`paper_checklist_llm.py`'s `novelty-positioned`) to check whether the draft
represents its prior work *faithfully*. Three stages: (1) an LLM reads the
draft and picks the ≤3 cited works it treats as most related, extracting how
the draft positions each and the delta it claims; (2) each work's real
abstract is fetched from **OpenAlex by title** (only the reference title
leaves the machine — the same class of query the bibliography linter makes);
(3) an LLM compares the draft's stated relation to what the abstract actually
shows. Findings: `RELATION-MISSTATED`, `NOVELTY-OVERSTATED`,
`SHALLOW-POSITIONING`, `UNVERIFIABLE`, and (info) `FAITHFUL`. `--discover
external` additionally queries OpenAlex with the draft's own title (still
title-only) to flag a clearly related work that is not cited
(`RELATED-WORK-OMITTED`). Manuscript text goes only to the LLM endpoint
(Aalto by default); only titles reach OpenAlex.

**`paper_checklist_llm.py`** — the `--profile paper` analogue of
`thesis_checklist_llm.py`, same one-call PASS/FAIL/UNCLEAR machinery but a
reviewer-facing rubric: `contribution-stated`, `problem-formulation`,
`novelty-positioned`, `claims-supported`, `baselines`,
`results-answer-claims`, `reproducibility`, `limitations`, and a
venue-conditional `ethics-impact`. `--venue` (default `ieee`) governs the
ethics item: it is only required for `neurips`/`acl`/`emnlp`/`iclr` and
passes by default otherwise. The prompt tells the model to judge by
conference-reviewer standards (sections not chapters, contributions not
research-question chapters, page-limited exposition), so a terse but
complete treatment passes.

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
the figure region at 144 dpi, and scores it against the ten rules of
Rougier, Droettboom & Bourne, ["Ten Simple Rules for Better
Figures"](https://doi.org/10.1371/journal.pcbi.1003833) (PLOS Comput Biol
2014). The output is a **matrix**: one row per figure, one column per rule
(R1 know your audience, R2 identify your message, R3 adapt to the medium,
R4 captions are not optional, R5 do not trust the defaults, R6 use color
effectively, R7 do not mislead the reader, R8 avoid chartjunk, R9 message
trumps beauty, R10 get the right tool). A vision model gives each cell a
verdict — `✓` pass, `~` minor issue, `✗` clear violation, `·` not
applicable — with the body-text font size as the legibility yardstick, and
a per-figure notes section explains every flagged cell. Pixel heuristics
(computed offline with PyMuPDF) feed the relevant rules as measurements:
the blank-background fraction above `--max-white` informs R8, and an
embedded raster below `--min-dpi` at printed size informs R3; with
`--no-llm` only these heuristic cells are filled and the rest are left
unassessed (`?`). A near-empty rendered region (≥98.5% blank) is reported
as a mislocated figure, not scored as blank. `--save-crops DIR` writes the
judged renderings for inspection; `--figures 3,7` restricts the run. On the
Aalto LLM Gateway the Qwen3-VL vision model is used automatically.

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
the [George Mason University Writing Center research-question
criteria](https://writingcenter.gmu.edu/writing-resources/research-based-writing/how-to-write-a-research-question)
— clear, focused, concise, complex, arguable; and the FINER framework), plus a
self-containment check (every technical term in the question is actually
defined — not merely mentioned — at or before the page where the question is
stated). Per question:
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
