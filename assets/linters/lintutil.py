#!/usr/bin/env python3
"""Shared helpers for the thesis linters: load a manuscript (.pdf, .tex, or a
directory of .tex files) as a list of (location, line) pairs, plus small text
utilities. Location is "p<page>" for PDFs and "<file>:<lineno>" for LaTeX."""

import re
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

Line = Tuple[str, str]  # (location, text)


# ---------------------------------------------------------------------------
# PDF extraction (pdftotext -layout preferred, PyMuPDF fallback)
# ---------------------------------------------------------------------------
def pdf_lines(path: str) -> List[Line]:
    text = None
    try:
        out = subprocess.run(["pdftotext", "-layout", path, "-"],
                             capture_output=True, timeout=120)
        if out.returncode == 0:
            text = out.stdout.decode("utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        pass
    if text is not None:
        pages = text.split("\f")
        out: List[Line] = []
        for pno, page in enumerate(pages, start=1):
            for ln in page.splitlines():
                out.append((f"p{pno}", ln))
            # Emit a blank line at every page break so paragraph grouping does
            # not merge the last paragraph of one page with the first of the
            # next (pdftotext's \f carries no blank line of its own). Without
            # this, a finding on page N+1 is reported at page N.
            out.append((f"p{pno}", ""))
        return out
    try:
        import fitz
    except ImportError:
        sys.exit("Need pdftotext (poppler) or PyMuPDF for PDF input.")
    doc = fitz.open(path)
    lines: List[Line] = []
    for pno in range(len(doc)):
        for ln in doc[pno].get_text().splitlines():
            lines.append((f"p{pno + 1}", ln))
        lines.append((f"p{pno + 1}", ""))   # page-break separator (see above)
    doc.close()
    return lines


# ---------------------------------------------------------------------------
# LaTeX loading (comments stripped, one entry per source line)
# ---------------------------------------------------------------------------
def strip_tex_comments(line: str) -> str:
    out, i = [], 0
    while i < len(line):
        c = line[i]
        if c == "\\" and i + 1 < len(line):
            out.append(line[i:i + 2])
            i += 2
            continue
        if c == "%":
            break
        out.append(c)
        i += 1
    return "".join(out)


def tex_files(paths: List[str]) -> List[Path]:
    files: List[Path] = []
    for p in paths:
        pth = Path(p)
        if pth.is_dir():
            files.extend(sorted(pth.rglob("*.tex")))
        elif pth.suffix == ".tex":
            files.append(pth)
    return files


def tex_lines(paths: List[str]) -> List[Line]:
    lines: List[Line] = []
    for f in tex_files(paths):
        try:
            raw = f.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            sys.exit(f"Cannot read {f}: {e}")
        for i, ln in enumerate(raw.splitlines(), start=1):
            lines.append((f"{f}:{i}", strip_tex_comments(ln)))
    return lines


def load_lines(paths: List[str]) -> Tuple[List[Line], str]:
    """Load input files; returns (lines, mode) with mode 'pdf' or 'tex'."""
    if len(paths) == 1 and paths[0].lower().endswith(".pdf"):
        return pdf_lines(paths[0]), "pdf"
    if any(p.lower().endswith(".pdf") for p in paths):
        sys.exit("Mix of PDF and LaTeX inputs is not supported.")
    lines = tex_lines(paths)
    if not lines:
        sys.exit("No .tex input found.")
    return lines, "tex"


# ---------------------------------------------------------------------------
# Text utilities
# ---------------------------------------------------------------------------
DOT_LEADER_RE = re.compile(r"\.{4,}\s*\d+\s*$")   # table-of-contents lines


def is_toc_line(text: str) -> bool:
    return bool(DOT_LEADER_RE.search(text))


def sentences(text: str) -> List[str]:
    """Crude sentence splitter that spares common abbreviations."""
    protected = re.sub(
        r"\b(e\.g|i\.e|et al|cf|vs|Fig|Eq|Sec|Tab|Alg|approx|resp|w\.r\.t|No)\.",
        lambda m: m.group(0).replace(".", "․"), text)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z(])", protected)
    return [p.replace("․", ".").strip() for p in parts if p.strip()]


def paragraphs_from_lines(lines: List[Line]) -> List[Tuple[str, str]]:
    """Group consecutive non-empty lines into paragraphs.
    Returns list of (location-of-first-line, paragraph-text)."""
    paras: List[Tuple[str, str]] = []
    buf: List[str] = []
    loc = ""
    for where, text in lines:
        if text.strip():
            if not buf:
                loc = where
            buf.append(text.strip())
        elif buf:
            paras.append((loc, " ".join(buf)))
            buf = []
    if buf:
        paras.append((loc, " ".join(buf)))
    return paras


class Report:
    """Collect findings and render the shared report format."""

    SEV_ORDER = {"ERROR": 0, "WARN": 1, "INFO": 2}

    def __init__(self, title: str, source: str):
        self.title = title
        self.source = source
        self.findings: List[Tuple[str, str, str, str]] = []

    def add(self, severity: str, code: str, where: str, message: str) -> None:
        self.findings.append((severity, code, where, message))

    def render(self) -> str:
        out = [f"== {self.title}", f"File: {self.source}", ""]
        if not self.findings:
            out.append("No findings.")
            return "\n".join(out)
        for sev, code, where, msg in sorted(
                self.findings, key=lambda f: (self.SEV_ORDER.get(f[0], 3), f[2])):
            out.append(f"[{sev}] {code:<18} {where:<12} {msg}")
        n_err = sum(1 for f in self.findings if f[0] == "ERROR")
        n_warn = sum(1 for f in self.findings if f[0] == "WARN")
        n_info = sum(1 for f in self.findings if f[0] == "INFO")
        out += ["", f"{len(self.findings)} finding(s): "
                    f"{n_err} error, {n_warn} warning, {n_info} info."]
        return "\n".join(out)

    def exit_code(self) -> int:
        return 1 if any(f[0] in ("ERROR", "WARN") for f in self.findings) else 0
