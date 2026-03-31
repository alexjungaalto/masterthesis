# CLAUDE.md

## Project Overview

This is a **public GitHub repository** providing guidance to master thesis students supervised by Alex Jung (Associate Professor for Machine Learning, Aalto University). The audience is current and prospective supervisees.

## Repository Structure

- `README.md` — Main guide: supervisor/student expectations, getting started, timeline, writing conventions, evaluation process
- `Topics.md` — Available thesis topic proposals
- `theses.csv` — Structured data of all supervised master theses (Aalto + TU Wien)
- `compile_theses.py` — Python script to compile, filter, and export the thesis list
- `theses.md` — Auto-generated markdown from `compile_theses.py` (build artifact)
- `material/` — PDFs and templates (grade characterization, self-assessment form, peer-review forms, current thesis list PDF)
- `material/creategraphtex.py` — Utility to extract LaTeX document structure as a graph

## Key Conventions

- **Audience**: All content is student-facing. Write clearly, accessibly, and actionably.
- **Terminology**: Use the [Aalto Dictionary of ML](https://aaltodictionaryofml.github.io/) for ML terms.
- **References**: Format citations per IEEE guidelines.
- **AI disclosure**: AI tool usage disclosures go in a dedicated statement, NOT in the Methods section (which is reserved for research methods).
- **No sensitive content**: This is a public repo. Do not add internal notes, credentials, or draft-quality content.

## Working with the Thesis List

- The source of truth for thesis data is `theses.csv` (columns: number, author, title, university, status, date, industry, url).
- The PDF `material/MasterThesisSupervisedCurrent.pdf` is the original source but may lag behind the CSV.
- Run `python compile_theses.py --stats` for summary statistics.
- Run `python compile_theses.py --markdown` to regenerate `theses.md`.
- When adding new theses, append to `theses.csv` and re-run the script.

## Style Notes

- Do not use emojis in README.md (Topics.md uses them — that is its existing style).
- Keep markdown well-structured with a table of contents for long documents.
- Link to Aalto's official policies (responsible AI use, academic appeals) rather than paraphrasing them extensively.
