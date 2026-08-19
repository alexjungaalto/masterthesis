#!/usr/bin/env python3
"""Linter: figures scored against the PLOS "Ten Simple Rules for Better
Figures" (Rougier, Droettboom & Bourne, PLOS Comput Biol 2014).

Looks at the RENDERED figures, not just their captions. Every figure in the
PDF is located, rendered, and judged by a vision model against each of the
ten rules; the output is a MATRIX with one row per figure and one column
per rule:

  R1  Know your audience          appropriate detail/notation for a thesis
  R2  Identify your message       one clear takeaway the visual conveys and
                                  that matches the caption's claim
  R3  Adapt to the medium         legible at thesis print size: font sizes
                                  vs body text, resolution, grayscale
  R4  Captions are not optional   caption states what is shown, defines
                                  symbols/units, points out what to notice
  R5  Do not trust the defaults   line widths/markers/tick density set
                                  deliberately, not raw tool defaults
  R6  Use color effectively       purposeful, distinguishable, colorblind-
                                  and grayscale-safe (n/a for mono diagrams)
  R7  Do not mislead the reader   honest axes/scales/proportions, no
                                  truncation or distortion that overstates
  R8  Avoid chartjunk             no needless 3D/decoration/heavy gridlines
                                  or large empty areas
  R9  Message trumps beauty       styling serves the message, not aesthetics
  R10 Get the right tool          a prepared figure/typeset table, not a raw
                                  screenshot standing in for one

Cell verdicts:  ok (pass) | weak (minor issue) | bad (clear violation) |
n/a (rule does not apply). A per-figure notes section lists every weak/bad
cell with a one-line reason.

Pixel heuristics (computed with PyMuPDF, no LLM) feed the relevant rules as
measurements: blank-area fraction (--max-white; informs R8) and embedded
raster dpi at printed size (--min-dpi; informs R3). With --no-llm only these
heuristic-informed cells are filled and the rest are left unassessed ("?").

A near-empty rendered region (>=98.5% blank) is treated as a mislocated
figure (the region heuristic missed the content), not a blank figure: that
row is reported as not-assessed rather than scored.

Gateway: the Aalto AI API by default (GPT-5 family is multimodal); on the
Aalto LLM Gateway the vision model Qwen3-VL is used (see aalto_llm.py).

Usage:
  python3 figure_lint_llm.py thesis.pdf
  python3 figure_lint_llm.py thesis.pdf --no-llm          # heuristics only
  python3 figure_lint_llm.py thesis.pdf --figures 3,7 --save-crops out/
Exit status: 0 all pass/n-a, 1 any weak/bad cell, 2 usage error.
"""

import argparse
import re
import sys
from pathlib import Path
from typing import List

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

from aalto_llm import (API_KEY_HELP, BASE_URL, BASE_URL_HELP,
                       default_vision_model, extract_json, make_client)

# Require a real caption separator: a colon, or a period FOLLOWED BY
# whitespace. Plain "[:.]" let the period inside a figure number act as the
# separator, so an in-text cross-reference ("Figure 6.6 shows ...") matched
# with number "6" -- fabricating phantom "Figure 6" entries from running prose
# and rendering blank space above the sentence as a bogus (illegible) figure.
CAPTION_RE = re.compile(
    r"^(Figure|Fig\.)\s+(\d+(?:\.\d+)*)\s*(?::|\.\s)\s*(.*)", re.S)
ZOOM = 2.0  # render at 144 dpi

# The ten rules (Rougier, Droettboom & Bourne, "Ten Simple Rules for Better
# Figures", PLOS Comput Biol 2014), in order. Keys are the matrix columns.
RULES = [
    ("R1", "Know your audience"),
    ("R2", "Identify your message"),
    ("R3", "Adapt to the medium"),
    ("R4", "Captions are not optional"),
    ("R5", "Do not trust the defaults"),
    ("R6", "Use color effectively"),
    ("R7", "Do not mislead the reader"),
    ("R8", "Avoid chartjunk"),
    ("R9", "Message trumps beauty"),
    ("R10", "Get the right tool"),
]
RULE_KEYS = [k for k, _ in RULES]
# Cell verdict -> compact glyph for the matrix.
GLYPH = {"ok": "✓", "weak": "~", "bad": "✗", "na": "·", "?": "?"}


class Figure:
    """One located figure: its number, the page it sits on, its caption
    text, the page region (``fitz.Rect``) to render, and the effective dpi
    of any embedded rasters (used by the resolution heuristic)."""

    def __init__(self, number, page_no, caption, rect, raster_dpis):
        self.number = number
        self.page_no = page_no          # 1-based
        self.caption = caption
        self.rect = rect                # fitz.Rect of the figure region
        self.raster_dpis = raster_dpis  # effective dpi of embedded rasters


def body_font_size(doc) -> float:
    """Median font size of running text (points)."""
    sizes = []
    for pno in range(min(len(doc), 30)):
        for b in doc[pno].get_text("dict")["blocks"]:
            for ln in b.get("lines", []):
                for sp in ln.get("spans", []):
                    if len(sp.get("text", "").strip()) > 20:
                        sizes.append(round(sp["size"], 1))
    if not sizes:
        return 11.0
    sizes.sort()
    return sizes[len(sizes) // 2]


def find_figures(doc) -> List[Figure]:
    """Locate every captioned figure in the PDF. For each caption matching
    ``CAPTION_RE`` it estimates the figure's region from the images/vector
    drawings sitting above the caption (falling back to the whitespace
    between the previous text block and the caption) and returns one
    ``Figure`` per caption."""
    figs: List[Figure] = []
    for pno in range(len(doc)):
        page = doc[pno]
        pw, ph = page.rect.width, page.rect.height
        blocks = page.get_text("dict")["blocks"]
        captions = []
        for b in blocks:
            if b.get("type", 0) != 0:
                continue
            text = " ".join(sp.get("text", "")
                            for ln in b.get("lines", [])
                            for sp in ln.get("spans", []))
            m = CAPTION_RE.match(text.strip())
            if m:
                captions.append((fitz.Rect(b["bbox"]), m.group(2),
                                 m.group(3)))
        if not captions:
            continue
        img_infos = page.get_image_info()
        drawings = [d["rect"] for d in page.get_drawings()]
        for cap_rect, number, cap_text in captions:
            # Figure content: images/vector graphics ABOVE the caption
            # (standard placement), horizontally overlapping the caption
            # column. Fall back to the space between the previous text
            # block and the caption.
            top = 0.0
            for b in blocks:
                r = fitz.Rect(b["bbox"])
                if b.get("type", 0) == 0 and r.y1 <= cap_rect.y0 - 4:
                    text = " ".join(sp.get("text", "")
                                    for ln in b.get("lines", [])
                                    for sp in ln.get("spans", []))
                    if len(text.strip()) > 60 and not \
                            CAPTION_RE.match(text.strip()):
                        top = max(top, r.y1)
            region = None
            dpis = []
            for info in img_infos:
                r = fitz.Rect(info["bbox"])
                if r.y1 <= cap_rect.y0 + 8 and r.y0 >= top - 30 and \
                        r.intersects(fitz.Rect(0, top, pw, cap_rect.y0)):
                    region = r if region is None else region | r
                    if r.width > 8:
                        dpis.append(info["width"] / (r.width / 72.0))
            for r in drawings:
                if r.y1 <= cap_rect.y0 + 8 and r.y0 >= top - 10 and \
                        r.width > 20 and r.height > 20:
                    region = r if region is None else region | r
            if region is None or region.width < 40 or region.height < 30:
                region = fitz.Rect(36, max(top, 36), pw - 36,
                                   cap_rect.y0 - 2)
            if region.height < 30:
                continue
            region = region & page.rect
            figs.append(Figure(number, pno + 1, cap_text.strip()[:200],
                               region, dpis))
    return figs


def white_ratio(pix) -> float:
    """Fraction of near-white pixels, sampled on a grid."""
    n = pix.n if pix.n <= 3 else 3
    data = pix.samples
    w, h, stride = pix.width, pix.height, pix.stride
    total = white = 0
    step_y = max(1, h // 200)
    step_x = max(1, w // 200)
    for y in range(0, h, step_y):
        row = y * stride
        for x in range(0, w, step_x):
            off = row + x * pix.n
            if all(data[off + c] > 245 for c in range(n)):
                white += 1
            total += 1
    return white / max(1, total)


SYSTEM_PROMPT = (
    "You are a figure-design examiner scoring ONE figure from a master's "
    "thesis (rendered at 144 dpi) against the ten rules of Rougier, "
    "Droettboom & Bourne, 'Ten Simple Rules for Better Figures' (PLOS "
    "Comput Biol 2014). The thesis body text is {body_pt} pt, about "
    "{body_px} px tall at this rendering — use it as the yardstick for "
    "text sizes; text under ~{small_px} px (~70% of body) is too small. "
    "{measurements}\n\n"
    "Give EVERY rule a verdict: 'ok' (satisfied / no problem a reader or "
    "printer would notice), 'weak' (a minor issue), 'bad' (a clear "
    "violation), or 'na' (the rule genuinely does not apply to this kind "
    "of figure). Be conservative — prefer 'ok' unless there is a concrete "
    "reason, and never nitpick pure aesthetics. For any 'weak' or 'bad', "
    "give a one-line, specific note; for 'ok'/'na' the note may be empty.\n\n"
    "The rules and how to judge each here:\n"
    "  R1 Know your audience: detail and notation suit a technical thesis "
    "reader — not oversimplified, not assuming unstated context. Usually "
    "'ok'.\n"
    "  R2 Identify your message: infer the single main takeaway from the "
    "VISUAL. 'bad' if there is no discernible point, or the visual "
    "contradicts / fails to support the specific claim the caption makes; "
    "state the inferred takeaway ('reads as: ...') in the note. A "
    "structural/architecture diagram whose job is to show structure "
    "satisfies this — its structure IS the message.\n"
    "  R3 Adapt to the medium: legible at print size. 'bad'/'weak' for "
    "tick/axis/legend text under the yardstick, overlapping or clipped "
    "labels, low-resolution/pixelated rasters, or distinctions that rely "
    "on color and collapse in grayscale.\n"
    "  R4 Captions are not optional: judge from the caption text supplied "
    "in the user message — it should state what is shown, define "
    "symbols/axes/units, and point out what to notice. 'weak'/'bad' if "
    "missing, bare, or not self-contained.\n"
    "  R5 Do not trust the defaults: line widths, marker sizes, tick "
    "density, and fonts look deliberately set, not raw tool defaults that "
    "hurt readability (e.g. default tiny ticks, default gray boxes).\n"
    "  R6 Use color effectively: color is purposeful, categories are "
    "distinguishable, and it survives colorblindness/grayscale. 'na' for "
    "monochrome figures and line-only diagrams with no color coding.\n"
    "  R7 Do not mislead the reader: axes, scales, and proportions are "
    "honest — no truncated/zoomed axis, distorted aspect, or dual-axis "
    "trick that overstates an effect. 'na' for non-quantitative diagrams.\n"
    "  R8 Avoid chartjunk: no needless 3D, heavy gridlines, redundant "
    "decoration, or large empty areas (use the measured blank fraction).\n"
    "  R9 Message trumps beauty: styling serves the message; nothing "
    "decorative is added at the cost of clarity. Usually 'ok'.\n"
    "  R10 Get the right tool: this is a prepared figure or typeset table, "
    "NOT a raw screen capture of an IDE/terminal/spreadsheet/application "
    "standing in for one (telltales: window chrome, toolbars, editor "
    "syntax colors, scrollbars, cursor). Note non-English interface text. "
    "'na'/'ok' when the interface itself is the legitimate subject (the UI "
    "of a system the thesis built/evaluates, or what participants saw); "
    "'bad' only when content that should have been typeset was "
    "screenshotted instead. A clean, deliberately cropped code listing "
    "shown AS a listing is 'ok'.\n\n"
    "Respond with STRICT JSON, exactly one entry per rule key:\n"
    '{{"rules": {{"R1": {{"v": "ok|weak|bad|na", "note": "..."}}, '
    '"R2": {{...}}, "R3": {{...}}, "R4": {{...}}, "R5": {{...}}, '
    '"R6": {{...}}, "R7": {{...}}, "R8": {{...}}, "R9": {{...}}, '
    '"R10": {{...}}}}}}'
)


def main(argv: List[str] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Visual figure-quality linter (pixel heuristics + "
                    "vision LLM).")
    ap.add_argument("pdf", help="Path to the thesis PDF.")
    ap.add_argument("--base-url", default=BASE_URL, help=BASE_URL_HELP)
    ap.add_argument("--api-key", default=None, help=API_KEY_HELP)
    ap.add_argument("--model", default=None,
                    help="Vision model id (default depends on gateway).")
    ap.add_argument("--no-llm", action="store_true",
                    help="Pixel heuristics only, no LLM calls.")
    ap.add_argument("--figures", default=None,
                    help="Comma-separated figure numbers to check "
                         "(default: all).")
    ap.add_argument("--max-white", type=float, default=0.95,
                    help="EXCESS-WHITESPACE threshold on the blank-pixel "
                         "fraction (default 0.95; line plots are naturally mostly white).")
    ap.add_argument("--min-dpi", type=int, default=100,
                    help="LOW-RESOLUTION threshold for embedded rasters "
                         "(default 100).")
    ap.add_argument("--save-crops", metavar="DIR",
                    help="Save the rendered figure regions as PNGs here "
                         "(inspect what was judged).")
    args = ap.parse_args(argv)

    if fitz is None:
        print("ERROR: PyMuPDF required. pip install pymupdf",
              file=sys.stderr)
        return 2

    doc = fitz.open(args.pdf)
    body_pt = body_font_size(doc)
    figs = find_figures(doc)
    if args.figures:
        wanted = {s.strip() for s in args.figures.split(",")}
        figs = [f for f in figs if f.number in wanted]
    if not figs:
        print("ERROR: no figure captions found.", file=sys.stderr)
        return 2

    client = model = None
    if not args.no_llm:
        model = args.model or default_vision_model(args.base_url)
        client = make_client(args.base_url, args.api_key)
        print(f"[info] gateway={args.base_url}\n[info] model={model}  "
              f"figures={len(figs)}  body-font={body_pt}pt",
              file=sys.stderr)

    crops_dir = None
    if args.save_crops:
        crops_dir = Path(args.save_crops)
        crops_dir.mkdir(parents=True, exist_ok=True)

    # One row per figure: {"label", "page", "verdicts": {Rkey: (v, note)},
    # "status": "" | note-string when the figure could not be scored}.
    rows = []
    total_tokens = 0
    for fig in figs:
        label = f"Figure {fig.number}"
        page = doc[fig.page_no - 1]
        pix = page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), clip=fig.rect)
        if crops_dir:
            pix.save(crops_dir / f"figure_{fig.number}.png")

        wr = white_ratio(pix)
        low_dpi = [d for d in fig.raster_dpis if d < args.min_dpi]

        # Heuristic-informed cells, filled with or without the LLM.
        heur = {}
        if wr > args.max_white:
            heur["R8"] = ("weak", f"{wr:.0%} of the region is blank "
                          f"background (measured)")
        if low_dpi:
            heur["R3"] = ("weak", f"embedded raster ~{min(low_dpi):.0f} dpi "
                          f"at printed size (< {args.min_dpi})")

        if wr >= 0.985:
            # Near-empty crop => the region heuristic missed the figure, not a
            # blank figure. Do not score it; skip the vision call.
            rows.append({"label": label, "page": fig.page_no,
                         "verdicts": {},
                         "status": f"not scored: rendered region {wr:.0%} "
                         f"blank -- content probably not located "
                         f"(inspect with --save-crops)"})
            print(f"[progress] {label} (p{fig.page_no}): mislocated "
                  f"(white={wr:.0%})", file=sys.stderr)
            continue

        if client is None:
            rows.append({"label": label, "page": fig.page_no,
                         "verdicts": heur, "status": ""})
            continue

        body_px = body_pt * ZOOM
        parts = []
        if wr > args.max_white:
            parts.append(f"{wr:.0%} of the figure region is blank")
        if low_dpi:
            parts.append(f"smallest embedded raster ~{min(low_dpi):.0f} dpi "
                         f"at printed size")
        measurements = ("Measured: " + "; ".join(parts) + ".") if parts \
            else "No pixel-heuristic issues were measured."
        system = SYSTEM_PROMPT.format(body_pt=body_pt,
                                      body_px=round(body_px),
                                      small_px=round(0.7 * body_px),
                                      measurements=measurements)
        user = (f"{label} (page {fig.page_no}). Caption: "
                f"\"{fig.caption}\"\nScore the attached rendering against "
                f"all ten rules.")
        try:
            raw, usage = client.complete(model=model, system=system,
                                         user=user, timeout=300,
                                         images=[pix.tobytes("png")])
        except RuntimeError as e:
            rows.append({"label": label, "page": fig.page_no,
                         "verdicts": heur,
                         "status": f"not scored: vision call failed ({e})"})
            continue
        total_tokens += usage.get("total_tokens", 0)
        parsed = extract_json(raw) or {}
        ruleset = parsed.get("rules", {}) if isinstance(parsed, dict) else {}
        verdicts = dict(heur)  # heuristics as a floor; LLM refines below
        for key in RULE_KEYS:
            cell = ruleset.get(key) if isinstance(ruleset, dict) else None
            if not isinstance(cell, dict):
                continue
            v = str(cell.get("v", "")).strip().lower()
            if v not in ("ok", "weak", "bad", "na"):
                continue
            note = str(cell.get("note", "")).strip()
            # Keep the more severe of heuristic vs LLM for a rule both touch.
            sev = {"ok": 0, "na": 0, "weak": 1, "bad": 2}
            if key in verdicts and sev[verdicts[key][0]] >= sev[v]:
                continue
            verdicts[key] = (v, note)
        n_bad = sum(1 for k in verdicts if verdicts[k][0] == "bad")
        n_weak = sum(1 for k in verdicts if verdicts[k][0] == "weak")
        print(f"[progress] {label} (p{fig.page_no}): "
              f"{n_bad} bad, {n_weak} weak (white={wr:.0%})",
              file=sys.stderr)
        rows.append({"label": label, "page": fig.page_no,
                     "verdicts": verdicts, "status": ""})

    doc.close()
    print(render_matrix(rows, args.pdf))
    if total_tokens:
        print(f"\nTotal tokens used: {total_tokens}")
    any_flag = any(c[0] in ("weak", "bad")
                   for r in rows for c in r["verdicts"].values())
    return 1 if any_flag else 0


def render_matrix(rows, source) -> str:
    """Render the figures x ten-rules matrix, a legend, and per-figure notes."""
    out = ['== Figure lint report (PLOS "Ten Simple Rules for Better '
           'Figures")', f"File: {source}", ""]
    if not rows:
        return "\n".join(out + ["No figures found.", ""])

    # Matrix. Column header is the rule key; a leading Figure column.
    fig_w = max(6, max(len(r["label"]) for r in rows))
    header = "| " + "Figure".ljust(fig_w) + " | " + \
        " | ".join(k.center(3) for k in RULE_KEYS) + " |"
    sep = "|" + "-" * (fig_w + 2) + "|" + \
        "|".join("-" * 5 for _ in RULE_KEYS) + "|"
    out += [header, sep]
    for r in rows:
        cells = []
        for k in RULE_KEYS:
            v = r["verdicts"].get(k, ("?", ""))[0]
            cells.append(GLYPH.get(v, "?").center(3))
        out.append("| " + r["label"].ljust(fig_w) + " | " +
                   " | ".join(cells) + " |")
    out.append("")

    # Legend.
    out.append("Rules (Rougier, Droettboom & Bourne, \"Ten Simple Rules for "
               "Better Figures\", PLOS Comput Biol 2014):")
    for k, name in RULES:
        out.append(f"  {k:<3} {name}")
    out.append("Cells:  ✓ pass   ~ minor issue   ✗ clear violation   "
               "· not applicable   ? not assessed")
    out.append("")

    # Per-figure notes for weak/bad cells, plus any not-scored rows.
    notes = []
    for r in rows:
        flagged = [(k, r["verdicts"][k]) for k in RULE_KEYS
                   if k in r["verdicts"]
                   and r["verdicts"][k][0] in ("weak", "bad")]
        if not flagged and not r["status"]:
            continue
        notes.append(f"{r['label']} (p{r['page']}):")
        if r["status"]:
            notes.append(f"    {r['status']}")
        for k, (v, note) in flagged:
            notes.append(f"    {k} {GLYPH.get(v, '?')} {note}".rstrip())
    if notes:
        out += ["Notes (flagged cells):"] + notes + [""]

    n_bad = sum(1 for r in rows for c in r["verdicts"].values()
                if c[0] == "bad")
    n_weak = sum(1 for r in rows for c in r["verdicts"].values()
                 if c[0] == "weak")
    n_unscored = sum(1 for r in rows if r["status"])
    out.append(f"{len(rows)} figure(s): {n_bad} bad cell(s), "
               f"{n_weak} weak cell(s), {n_unscored} not scored.")
    return "\n".join(out)


if __name__ == "__main__":
    raise SystemExit(main())
