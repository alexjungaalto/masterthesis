#!/usr/bin/env python3
"""Linter: find numbered entities (equations, tables, figures) that are never
referenced in the text. Works on LaTeX sources AND compiled PDFs.

Guideline being enforced (ml-theses.org): every numbered equation, table, and
figure must be referenced in the text ("only number equations that are
referenced").

LaTeX mode (*.tex files or directories):
  1. UNREFERENCED    - \\label in a numbered environment that no \\ref, \\eqref,
                       \\autoref, \\cref/\\Cref, \\vref, \\pageref, or
                       \\hyperref points to.
  2. UNLABELED-EQ    - numbered math environment with no \\label at all.
  3. UNLABELED-FLOAT - captioned figure/table without a \\label.

PDF mode (*.pdf files) works on extracted text (pdftotext -layout, falling
back to PyMuPDF):
  Definitions detected:
    - caption lines starting with "Figure N:", "Table N:", "Algorithm N." etc.
    - equation numbers "(N)" right-aligned at the end of a line.
  Mentions detected:
    - "Figure N", "Fig. N", "Tables N and M", "Tables 11-17" (ranges/lists),
    - "Equation N", "Eq. (N)", and bare inline "(N)" (disable the bare form
      with --no-bare-eq-refs; bare "(N)" also matches enumerations, so keeping
      it ON avoids false alarms but may miss some unreferenced equations).
  An entity whose number never occurs outside its own caption/definition line
  is reported as UNREFERENCED. Lines with dot leaders (table of contents) are
  ignored.

PDF-mode limitations: heuristic text extraction; equation numbers only found
when right-aligned with >=2 spaces before "(N)"; mentions split across a page
break in mid-phrase may be missed (adjacent-line joins, including a hyphenated
word break such as "Ta-\nble 2.2", are handled).

Usage:
  python3 unreferenced_entity_linter.py thesis.pdf
  python3 unreferenced_entity_linter.py main.tex chapters/ [-a]
Exit status: 0 clean, 1 findings, 2 usage error.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

# --------------------------------------------------------------------------
# LaTeX mode
# --------------------------------------------------------------------------

NUMBERED_MATH_ENVS = {
    "equation", "align", "gather", "multline", "eqnarray", "alignat", "flalign",
}
FLOAT_ENVS = {"figure", "table", "figure*", "table*", "algorithm", "listing"}

BEGIN_RE = re.compile(r"\\begin\{([A-Za-z*]+)\}")
END_RE_TMPL = r"\\end\{%s\}"
LABEL_RE = re.compile(r"\\label\{([^}]+)\}")
CAPTION_CMD_RE = re.compile(r"\\caption\b")
REF_RE = re.compile(r"\\(?:ref|eqref|autoref|cref|Cref|vref|pageref)\*?\{([^}]+)\}")
HYPERREF_RE = re.compile(r"\\hyperref\[([^\]]+)\]")
COMMENT_RE = re.compile(r"(?<!\\)%.*")


def strip_comments(line: str) -> str:
    return COMMENT_RE.sub("", line)


def classify(env, label):
    base = env.rstrip("*") if env else ""
    if base in NUMBERED_MATH_ENVS:
        return "equation"
    if base in {"figure", "table", "algorithm", "listing"}:
        return base
    prefix = label.split(":", 1)[0].lower() if ":" in label else ""
    return {
        "eq": "equation", "fig": "figure", "tab": "table", "table": "table",
        "alg": "algorithm", "sec": "section", "ch": "chapter", "chap": "chapter",
        "app": "appendix", "lst": "listing", "thm": "theorem", "lem": "lemma",
    }.get(prefix, "other")


def scan_tex_file(path: Path):
    lines = [strip_comments(l) for l in
             path.read_text(encoding="utf-8", errors="replace").splitlines()]
    entities, refs = [], set()
    unlabeled_math, unlabeled_floats = [], []

    for ln in lines:
        for m in REF_RE.finditer(ln):
            refs.update(x.strip() for x in m.group(1).split(","))
        for m in HYPERREF_RE.finditer(ln):
            refs.add(m.group(1).strip())

    stack = []  # [env, start_line, has_label, has_caption, starred]
    for lineno, ln in enumerate(lines, start=1):
        pos = 0
        while True:
            b = BEGIN_RE.search(ln, pos)
            e = None
            for entry in stack:
                m = re.search(END_RE_TMPL % re.escape(entry[0]), ln[pos:])
                if m and (e is None or m.start() < e[0].start()):
                    e = (m, entry)
            if b and (e is None or b.start() - pos < e[0].start()):
                env = b.group(1)
                if env.rstrip("*") in NUMBERED_MATH_ENVS or env in FLOAT_ENVS:
                    stack.append([env, lineno, False, False, env.endswith("*")])
                pos = b.end()
                continue
            if e:
                m, entry = e
                env, start, has_label, has_caption, starred = entry
                if env.rstrip("*") in NUMBERED_MATH_ENVS and not starred and not has_label:
                    unlabeled_math.append({"env": env, "file": path, "line": start})
                if env in FLOAT_ENVS and has_caption and not has_label:
                    unlabeled_floats.append({"env": env, "file": path, "line": start})
                stack.remove(entry)
                pos += m.end()
                continue
            break

        for m in LABEL_RE.finditer(ln):
            label = m.group(1).strip()
            env = stack[-1][0] if stack else None
            if stack:
                stack[-1][2] = True
            entities.append({"label": label, "kind": classify(env, label),
                             "env": env, "file": path, "line": lineno})
        if stack and CAPTION_CMD_RE.search(ln):
            stack[-1][3] = True

    return entities, refs, unlabeled_math, unlabeled_floats


def run_tex_mode(files, all_labels):
    all_entities, all_refs = [], set()
    all_umath, all_ufloat = [], []
    for f in files:
        ents, refs, umath, ufloat = scan_tex_file(f)
        all_entities.extend(ents)
        all_refs |= refs
        all_umath.extend(umath)
        all_ufloat.extend(ufloat)

    checked = {"equation", "figure", "table", "algorithm", "listing"}
    findings = 0
    for ent in sorted((e for e in all_entities
                       if e["label"] not in all_refs
                       and (all_labels or e["kind"] in checked)),
                      key=lambda x: (str(x["file"]), x["line"])):
        print(f"{ent['file']}:{ent['line']}: UNREFERENCED {ent['kind']} "
              f"'\\label{{{ent['label']}}}' is never referenced in the text")
        findings += 1
    for it in all_umath:
        print(f"{it['file']}:{it['line']}: UNLABELED-EQ numbered '{it['env']}' "
              f"environment has no \\label -- its number can never be "
              f"referenced (star it, or label and reference it)")
        findings += 1
    for it in all_ufloat:
        print(f"{it['file']}:{it['line']}: UNLABELED-FLOAT captioned "
              f"'{it['env']}' has no \\label -- numbered but unreferenceable")
        findings += 1

    n = sum(1 for e in all_entities if all_labels or e["kind"] in checked)
    print(f"\n[tex] checked {len(files)} file(s), {n} labeled entit(ies), "
          f"{len(all_refs)} referenced label(s): {findings} finding(s)")
    return findings


# --------------------------------------------------------------------------
# PDF mode
# --------------------------------------------------------------------------

FLOAT_WORDS = {
    "figure": "figure", "figures": "figure", "fig.": "figure", "figs.": "figure",
    "table": "table", "tables": "table",
    "algorithm": "algorithm", "algorithms": "algorithm",
    "listing": "listing", "listings": "listing",
}
NUM = r"[A-Z]?\d+(?:\.\d+)?"
# Separator after the number must be a colon, or a period FOLLOWED by
# whitespace/end -- never the period inside the number itself. Plain "[:.]"
# let the regex backtrack "2.4" to "2" and match the internal dot, recording a
# phantom "Figure 2" definition from a body line like "Figure 2.4 summarises
# these layers:" and then reporting that non-existent float as unreferenced.
CAPTION_DEF_RE = re.compile(
    rf"^\s*(Figure|Fig\.|Table|Algorithm|Listing)\s+({NUM})\s*(?::|\.(?=\s|$))")
EQ_DEF_RE = re.compile(rf"(?:\s{{2,}}|^\s*)\(({NUM})\)\s*$")
FLOAT_MENTION_RE = re.compile(
    rf"\b(Figures?|Figs?\.|Tables?|Algorithms?|Listings?)\s+"
    rf"({NUM}(?:\s*(?:,|and|&|/|to|--?|–|—)\s*{NUM})*)")
EQ_WORD_MENTION_RE = re.compile(
    rf"\b(?:Equations?|Eqs?\.)\s*\(?({NUM}(?:\)?\s*(?:,|and|&|--?|–)\s*\(?{NUM})*)\)?")
BARE_EQ_RE = re.compile(r"\((\d{1,3})\)")
DOT_LEADER_RE = re.compile(r"(?:\.\s){4,}|\.{4,}")
NUM_TOKEN_RE = re.compile(NUM)


def extract_pdf_pages(path: Path):
    try:
        out = subprocess.run(["pdftotext", "-layout", str(path), "-"],
                             capture_output=True, check=True)
        return out.stdout.decode("utf-8", errors="replace").split("\f")
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    try:
        import fitz  # PyMuPDF
    except ImportError:
        sys.exit("error: need either pdftotext (poppler) or PyMuPDF to read PDFs")
    with fitz.open(path) as doc:
        return [page.get_text() for page in doc]


def expand_number_list(list_str):
    """'11-17' -> 11..17; '5 and 6' -> 5,6; '13/16/19' -> 13,16,19."""
    nums = NUM_TOKEN_RE.findall(list_str)
    out = list(nums)
    for m in re.finditer(rf"({NUM})\s*(?:--?|–|—|to)\s*({NUM})", list_str):
        a, b = m.group(1), m.group(2)
        if a.isdigit() and b.isdigit() and int(a) < int(b) <= int(a) + 50:
            out.extend(str(i) for i in range(int(a) + 1, int(b)))
    return out


def sort_key(entity):
    kind, num = entity
    m = re.match(r"([A-Z]*)(\d+)(?:\.(\d+))?", num)
    return (kind, m.group(1), int(m.group(2)), int(m.group(3) or 0))


def scan_pdf(path: Path, bare_eq_refs=True):
    pages = extract_pdf_pages(path)
    defs = {}      # (kind, number) -> first page of definition
    mentions = set()  # (kind, number)

    for pageno, page in enumerate(pages, start=1):
        lines = page.splitlines()
        for i, line in enumerate(lines):
            if DOT_LEADER_RE.search(line):
                continue  # table-of-contents / list-of-figures entry

            cap = CAPTION_DEF_RE.match(line)
            if cap:
                kind = FLOAT_WORDS[cap.group(1).lower()]
                defs.setdefault((kind, cap.group(2)), pageno)

            eq = EQ_DEF_RE.search(line)
            if eq:
                defs.setdefault(("equation", eq.group(1)), pageno)

            for m in FLOAT_MENTION_RE.finditer(line):
                # skip the caption's own "Figure N:" occurrence
                if cap and m.start(1) == cap.start(1):
                    continue
                kind = FLOAT_WORDS[m.group(1).lower()]
                for n in expand_number_list(m.group(2)):
                    mentions.add((kind, n))

            for m in EQ_WORD_MENTION_RE.finditer(line):
                for n in expand_number_list(m.group(1)):
                    mentions.add(("equation", n))

            if bare_eq_refs:
                bares = list(BARE_EQ_RE.finditer(line))
                if eq and bares and bares[-1].start() >= eq.start():
                    bares = bares[:-1]  # last one is the definition itself
                for m in bares:
                    mentions.add(("equation", m.group(1)))

            # A mention split across a line break, including a HYPHENATED
            # word break: "... Table\n2.2 ..." or "... Ta-\nble 2.2 ...".
            # Heal the seam (join the hyphenated word, else glue the last word
            # to the next line) and re-scan it, so the reference is still seen.
            # Additive: this can only add mentions, never suppress a finding.
            if i + 1 < len(lines):
                cur = line.rstrip()
                nxt = lines[i + 1].lstrip()
                seam = (cur[:-1].rsplit(" ", 1)[-1] + nxt) if cur.endswith("-") \
                    else (cur.rsplit(" ", 1)[-1] + " " + nxt)
                for m in FLOAT_MENTION_RE.finditer(seam):
                    kind = FLOAT_WORDS[m.group(1).lower()]
                    for n in expand_number_list(m.group(2)):
                        mentions.add((kind, n))
                for m in EQ_WORD_MENTION_RE.finditer(seam):
                    for n in expand_number_list(m.group(1)):
                        mentions.add(("equation", n))

    findings = 0
    for (kind, num), page in sorted(defs.items(), key=lambda kv: sort_key(kv[0])):
        if (kind, num) not in mentions:
            label = f"({num})" if kind == "equation" else f"{kind.capitalize()} {num}"
            print(f"{path}: UNREFERENCED {kind} {label} "
                  f"(defined on PDF page {page}) is never mentioned in the text")
            findings += 1

    n_eq = sum(1 for k, _ in defs if k == "equation")
    print(f"\n[pdf] {path.name}: {len(defs)} numbered entit(ies) found "
          f"({n_eq} equations, {len(defs) - n_eq} floats), "
          f"{findings} finding(s)"
          + ("" if bare_eq_refs else "  [bare '(N)' not counted as references]"))
    return findings


# --------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Find numbered equations/tables/figures never referenced "
                    "in the text (LaTeX sources or PDF).")
    ap.add_argument("paths", nargs="+", help=".tex files, directories, or .pdf files")
    ap.add_argument("-a", "--all-labels", action="store_true",
                    help="[tex] also report unreferenced non-float labels")
    ap.add_argument("--no-bare-eq-refs", action="store_true",
                    help="[pdf] do not count bare inline '(N)' as an equation "
                         "reference (stricter; may flag enumerations)")
    args = ap.parse_args(argv)

    tex_files, pdf_files = [], []
    for p in map(Path, args.paths):
        if p.is_dir():
            tex_files.extend(sorted(p.rglob("*.tex")))
        elif p.is_file() and p.suffix.lower() == ".pdf":
            pdf_files.append(p)
        elif p.is_file():
            tex_files.append(p)
        else:
            sys.exit(f"error: no such file or directory: {p}")
    if not tex_files and not pdf_files:
        sys.exit("error: no .tex or .pdf files found")

    findings = 0
    if tex_files:
        findings += run_tex_mode(tex_files, args.all_labels)
    for pdf in pdf_files:
        findings += scan_pdf(pdf, bare_eq_refs=not args.no_bare_eq_refs)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
